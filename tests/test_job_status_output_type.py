# -*- coding: utf-8 -*-
"""
Tests for direct_job_status output type filtering.
Guards against product bug where LoadVideo / LoadImage input previews (type: 'input')
were wrongly returned to the user as final results.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from core.comfy_client import direct_job_status


def _fake_http_response(payload: dict):
    raw = json.dumps(payload).encode("utf-8")
    resp = io.BytesIO(raw)
    setattr(resp, "read", resp.read)
    setattr(resp, "__enter__", lambda s: s)
    setattr(resp, "__exit__", lambda s, *a: None)
    return resp


def test_direct_job_status_prefers_output_over_input_previews(monkeypatch):
    """When both LoadVideo input preview and SaveVideo output are present, return SaveVideo."""
    history_payload = {
        "job_123": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {
                "300": {
                    "gifs": [{"filename": "input_video.mp4", "subfolder": "", "type": "input"}]
                },
                "81": {
                    "videos": [{"filename": "SHINJUTSU_Studio_00001_.mp4", "subfolder": "Dance", "type": "output"}]
                },
            },
        }
    }

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _fake_http_response(history_payload))

    st = direct_job_status("job_123", "http://fake-comfy:8188")
    assert st["ok"] is True
    assert st["status"] == "completed"
    assert st["filename"] == "SHINJUTSU_Studio_00001_.mp4"

    # All returned outputs must be type output, never input
    for out in st["outputs"]:
        assert out["name"] != "input_video.mp4"
        assert out["type"] == "output"


def test_direct_job_status_rejects_history_with_only_input_previews(monkeypatch):
    """When a workflow finishes but only has input previews (e.g. from LoadVideo), return error."""
    history_payload = {
        "job_456": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {
                "300": {
                    "gifs": [{"filename": "only_input.mp4", "subfolder": "", "type": "input"}]
                }
            },
        }
    }

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _fake_http_response(history_payload))

    st = direct_job_status("job_456", "http://fake-comfy:8188")
    assert st["ok"] is False
    assert st["status"] == "error"
    assert "produced no image, video or audio output" in st["error"]


def test_direct_job_status_falls_back_to_temp_if_no_output(monkeypatch):
    """Fallback to temp previews when no final output items are present."""
    history_payload = {
        "job_789": {
            "status": {"status_str": "success", "completed": True},
            "outputs": {
                "50": {
                    "images": [{"filename": "preview_0001.png", "subfolder": "", "type": "temp"}]
                }
            },
        }
    }

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _fake_http_response(history_payload))

    st = direct_job_status("job_789", "http://fake-comfy:8188")
    assert st["ok"] is True
    assert st["status"] == "completed"
    assert st["filename"] == "preview_0001.png"
    assert st["outputs"][0]["type"] == "temp"
