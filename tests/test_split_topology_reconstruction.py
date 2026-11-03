# -*- coding: utf-8 -*-
"""
Tests for Task T1: Split-topology Control-LoRA reconstruction.
Ensures:
1. When target ComfyUI is remote or lacks shared filesystem, local reconstruction is NOT invoked.
2. The validator produces a clear "missing model, reconstruct on the GPU host" message.
3. Choices are NEVER forcibly injected into object_info — availability is strictly determined by target ComfyUI's /object_info.
4. When local/embedded reconstruction succeeds and target ComfyUI lists the patch, the job proceeds.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.comfy_client import (
    can_reconstruct_locally,
    is_loopback_url,
    queue_studio_job,
    summarize_validation,
    validate_api_prompt,
)
from core.control_lora_codec import RECONSTRUCTED_PATCH_FILENAME


def _shinjutsu_graph() -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors"}},
        "2": {"class_type": "ModelPatchLoader", "inputs": {"name": RECONSTRUCTED_PATCH_FILENAME, "model": ["1", 0]}},
        "3": {"class_type": "ApplyPatch", "inputs": {"model": ["2", 0]}},
    }


def test_is_loopback_url():
    assert is_loopback_url("http://127.0.0.1:8188")
    assert is_loopback_url("http://localhost:8188")
    assert is_loopback_url("http://[::1]:8188")
    assert not is_loopback_url("http://192.168.1.50:8188")
    assert not is_loopback_url("http://colab-tunnel.example.com")


def test_can_reconstruct_locally_remote_and_embedded(monkeypatch):
    # Non-loopback URL -> False
    assert not can_reconstruct_locally("http://remote.host:8188")

    # Force env overrides
    monkeypatch.setenv("SHINJUTSU_FORCE_LOCAL_MODELS", "0")
    assert not can_reconstruct_locally("http://127.0.0.1:8188")
    monkeypatch.setenv("SHINJUTSU_FORCE_LOCAL_MODELS", "1")
    assert can_reconstruct_locally("http://127.0.0.1:8188")
    monkeypatch.delenv("SHINJUTSU_FORCE_LOCAL_MODELS", raising=False)

    # Embedded mode simulated via mock server.PromptServer
    mock_server = MagicMock()
    mock_server.PromptServer.instance = object()
    monkeypatch.setitem(__import__("sys").modules, "server", mock_server)
    assert can_reconstruct_locally("http://127.0.0.1:8188")


def test_remote_comfyui_missing_patch_blocks_with_clear_error(tmp_path, monkeypatch):
    """
    Split topology: ComfyUI is remote (or over SSH tunnel) and lacks the patch in /object_info.
    Local reconstruction must NOT run, choices must NOT be faked, and validation must report
    'missing model, reconstruct on the GPU host'.
    """
    recon_mock = MagicMock()
    monkeypatch.setattr("core.control_lora_codec.ensure_reconstructed_control_patch", recon_mock)

    # Remote URL
    remote_url = "http://192.168.1.99:8188"

    # object_info where ModelPatchLoader has NO patch files
    object_info = {
        "UNETLoader": {"input": {"required": {"unet_name": [["minimax_h3_ref2va_pruned_int8_convrot.safetensors"]]}}, "output": ["MODEL"]},
        "ModelPatchLoader": {"input": {"required": {"name": [["other_patch.safetensors"]], "model": ["MODEL"]}}, "output": ["MODEL"]},
        "ApplyPatch": {"input": {"required": {"model": ["MODEL"]}}, "output": []},
    }

    monkeypatch.setattr("core.comfy_client.fetch_object_info", lambda url, **kw: copy.deepcopy(object_info))

    body = {
        "comfy_url": remote_url,
        "mode": "shinjutsu",
        "workflow": _shinjutsu_graph(),
        "client_id": "test_client",
    }

    res = queue_studio_job(body, lambda wf, **kw: wf, tmp_path / "u", tmp_path / "c")

    # Local reconstruction must NEVER have been called on the client machine
    recon_mock.assert_not_called()

    # Job must be rejected
    assert res["ok"] is False
    assert res["queued"] is False
    assert "reconstruct on the GPU host" in res["error"]
    assert RECONSTRUCTED_PATCH_FILENAME in res["error"]

    # Choices must NOT have been mutated
    mp_choices = object_info["ModelPatchLoader"]["input"]["required"]["name"][0]
    assert RECONSTRUCTED_PATCH_FILENAME not in mp_choices


def test_embedded_reconstruction_only_passes_if_refetched_object_info_lists_it(tmp_path, monkeypatch):
    """
    When local reconstruction runs, choices are NOT blindly appended.
    Only if the re-fetched /object_info actually lists the reconstructed patch will validation pass.
    """
    monkeypatch.setenv("SHINJUTSU_FORCE_LOCAL_MODELS", "1")

    # 1. Simulate reconstruction running but ComfyUI's object_info still missing it
    fake_patch = tmp_path / RECONSTRUCTED_PATCH_FILENAME
    fake_patch.write_bytes(b"0" * 1024)

    monkeypatch.setattr("core.control_lora_codec.ensure_reconstructed_control_patch", lambda *a, **kw: fake_patch)

    object_info_missing = {
        "UNETLoader": {"input": {"required": {"unet_name": [["minimax_h3_ref2va_pruned_int8_convrot.safetensors"]]}}, "output": ["MODEL"]},
        "ModelPatchLoader": {"input": {"required": {"name": [["other_patch.safetensors"]], "model": ["MODEL"]}}, "output": ["MODEL"]},
        "ApplyPatch": {"input": {"required": {"model": ["MODEL"]}}, "output": []},
    }

    monkeypatch.setattr("core.comfy_client.fetch_object_info", lambda url, **kw: copy.deepcopy(object_info_missing))

    body = {
        "comfy_url": "http://127.0.0.1:8188",
        "mode": "shinjutsu",
        "workflow": _shinjutsu_graph(),
    }

    res = queue_studio_job(body, lambda wf, **kw: wf, tmp_path / "u", tmp_path / "c")
    assert res["ok"] is False
    assert "reconstruct on the GPU host" in res["error"]

    # 2. Simulate ComfyUI's re-fetched object_info now listing the reconstructed patch
    object_info_ready = copy.deepcopy(object_info_missing)
    object_info_ready["ModelPatchLoader"]["input"]["required"]["name"][0].append(RECONSTRUCTED_PATCH_FILENAME)

    fetch_call_count = [0]
    def _mock_fetch(url, **kw):
        fetch_call_count[0] += 1
        if fetch_call_count[0] == 1:
            return copy.deepcopy(object_info_missing)
        return copy.deepcopy(object_info_ready)

    monkeypatch.setattr("core.comfy_client.fetch_object_info", _mock_fetch)
    monkeypatch.setattr("core.comfy_client.submit_job", lambda *a, **kw: {"job_id": "test_pid", "transport": "direct"})

    res2 = queue_studio_job(body, lambda wf, **kw: wf, tmp_path / "u", tmp_path / "c")
    assert res2["ok"] is True
    assert res2["queued"] is True
    assert res2["job_id"] == "test_pid"
