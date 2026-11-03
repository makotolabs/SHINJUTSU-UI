# -*- coding: utf-8 -*-
"""
End-to-end studio job flow over real HTTP against a fake ComfyUI (direct `/prompt` transport):
compile -> validate against /object_info -> submit -> poll -> output URL.
"""
import time

from conftest import txt2img_graph
from core.comfy_client import get_job_status, queue_studio_job, transport_mode
from core.model_manager import compile_ui_workflow_to_api_prompt


def _queue(fake, tmp_path, graph, **extra):
    body = {"comfy_url": fake.url, "mode": "images", "workflow": graph, "client_id": "test"}
    body.update(extra)
    return queue_studio_job(body, compile_ui_workflow_to_api_prompt, tmp_path / "uploads", tmp_path / "compiled")


def _wait(fake, job_id, transport="direct", timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = get_job_status(job_id, fake.url, transport)
        if st["status"] in ("completed", "error"):
            return st
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_auto_transport_defaults_to_direct(clean_transport_env):
    assert transport_mode() == "direct"


def test_direct_happy_path_image(clean_transport_env, fake_comfy, tmp_path):
    res = _queue(fake_comfy, tmp_path, txt2img_graph(), prompt="a red fox")
    assert res["ok"] and res["queued"], res
    assert res["transport"] == "direct"
    assert res["validation"]["checked"] is True
    assert (tmp_path / "compiled" / "shinjutsu_images_api.json").is_file()
    # the user prompt really reached ComfyUI
    sent = fake_comfy.state.prompts[-1]["prompt"]
    assert sent["4"]["inputs"]["text"] == "a red fox"

    st = _wait(fake_comfy, res["job_id"])
    assert st["status"] == "completed" and st["media_type"] == "image"
    assert st["view_url"].startswith(fake_comfy.url + "/view?")


def test_wrong_wiring_is_blocked_before_comfyui(clean_transport_env, fake_comfy, tmp_path):
    g = txt2img_graph()
    g["9"] = {"class_type": "SaveAudioAdvanced", "inputs": {"audio": ["8", 0], "filename_prefix": "a", "format": "flac"}}
    # IMAGE -> AUDIO is a type error, so validation must block it before ComfyUI ever sees it
    res = _queue(fake_comfy, tmp_path, g)
    assert res["ok"] is False and "expects AUDIO" in res["error"]
    assert fake_comfy.state.prompts == []


def test_direct_audio_output_is_detected(clean_transport_env, fake_comfy, tmp_path):
    g = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": "source.mp4"}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "SaveAudioAdvanced", "inputs": {"audio": ["2", 1], "filename_prefix": "SHINJUTSU/a", "format": "mp3", "format.quality": "V0"}},
    }
    res = _queue(fake_comfy, tmp_path, g)
    assert res["queued"], res
    st = _wait(fake_comfy, res["job_id"])
    assert st["status"] == "completed" and st["media_type"] == "audio"


def test_missing_model_blocks_queue_with_clear_message(clean_transport_env, fake_comfy, tmp_path):
    res = _queue(fake_comfy, tmp_path, txt2img_graph(unet="missing_model.safetensors"))
    assert res["ok"] is False and res["queued"] is False
    assert "missing_model.safetensors" in res["error"]
    assert fake_comfy.state.prompts == []


def test_execution_error_is_surfaced(clean_transport_env, fake_comfy, tmp_path):
    fake_comfy.state.fail_next = True
    res = _queue(fake_comfy, tmp_path, txt2img_graph())
    st = _wait(fake_comfy, res["job_id"])
    assert st["status"] == "error" and "CUDA out of memory" in st["error"]


def test_open_weights_strict_mode_refuses_partner_nodes(clean_transport_env, fake_comfy, tmp_path):
    # Strict Open-Weights mode is ON by default out of the box (no env var needed)
    g = txt2img_graph()
    g["10"] = {"class_type": "GeminiImageNode", "inputs": {"prompt": "x"}}
    res = _queue(fake_comfy, tmp_path, g)
    assert res["ok"] is False and "GeminiImageNode" in res["error"]


def test_offline_comfy_still_saves_compiled_workflow(clean_transport_env, tmp_path):
    body = {"comfy_url": "http://127.0.0.1:9", "mode": "images", "workflow": txt2img_graph()}
    res = queue_studio_job(body, compile_ui_workflow_to_api_prompt, tmp_path / "u", tmp_path / "c")
    assert res["queued"] is False and res["validation"]["checked"] is False
    assert (tmp_path / "c" / "shinjutsu_images_api.json").is_file()
