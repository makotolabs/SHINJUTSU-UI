# -*- coding: utf-8 -*-
"""
Comfy SDK transport, end to end and fully offline:

    SHINJUTSU  --comfy-sdk-->  comfy-api-proxy (Comfy API v2)  --native HTTP-->  fake ComfyUI

Exercises the exact code path used against Comfy Cloud: uploads become content-hashed assets bound with
`set_input`, the graph is submitted as a job, state is polled, outputs are resolved to download URLs.
Skipped automatically when `comfy-sdk` / `comfy-api-proxy` are not installed (they need Python 3.10+).
"""
import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

pytest.importorskip("comfy_sdk")
pytest.importorskip("comfy_api_proxy")

from conftest import txt2img_graph  # noqa: E402
from core import comfy_client  # noqa: E402
from core.model_manager import compile_ui_workflow_to_api_prompt  # noqa: E402
from fake_comfyui import FakeComfyServer, free_port  # noqa: E402

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f00f0004850180848c3121"
    "0000000049454e44ae426082"
)


@pytest.fixture()
def proxy_stack(clean_transport_env, tmp_path):
    with FakeComfyServer() as comfy:
        port = free_port()
        exe = shutil.which("comfy-api-proxy")
        cmd = [exe] if exe else [sys.executable, "-m", "comfy_api_proxy.cli"]
        cmd += ["--comfyui", comfy.url, "--port", str(port)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(tmp_path))
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"{base}/api/v2/health", timeout=1) as r:
                        if r.status == 200:
                            break
                except Exception:
                    time.sleep(0.1)
            else:
                proc.kill()
                out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
                pytest.fail(f"comfy-api-proxy did not start:\n{out}")
            clean_transport_env.setenv("COMFY_BASE_URL", base)
            clean_transport_env.setenv("SHINJUTSU_TRANSPORT", "auto")
            comfy_client.reset_sdk_client()
            yield comfy, base
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except Exception:
                proc.kill()


def test_auto_selects_sdk_when_configured(proxy_stack):
    assert comfy_client.transport_mode() == "sdk"
    assert comfy_client.transport_info()["target"].startswith("http://127.0.0.1:")


def test_sdk_job_with_asset_upload(proxy_stack, tmp_path):
    comfy, _base = proxy_stack
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "hero.png").write_bytes(PNG_1PX)

    # Staging in SDK mode keeps the file local; it is uploaded as an asset at submit time
    staged = comfy_client.stage_input_file(uploads / "hero.png", comfy.url, direct_uploader=None)
    assert staged == "hero.png"

    graph = txt2img_graph()
    graph["10"] = {"class_type": "LoadImage", "inputs": {"image": "example.png"}}
    body = {"comfy_url": comfy.url, "mode": "images", "workflow": graph, "slot1_file": staged, "prompt": "via sdk"}
    res = comfy_client.queue_studio_job(body, compile_ui_workflow_to_api_prompt, uploads, tmp_path / "compiled")
    assert res["queued"] and res["transport"] == "sdk", res

    # The proxy uploaded the asset to ComfyUI and resolved the core/ASSET reference to a filename
    sent = comfy.state.prompts[-1]["prompt"]
    assert isinstance(sent["10"]["inputs"]["image"], str) and sent["10"]["inputs"]["image"]
    assert comfy.state.uploads, "asset bytes never reached ComfyUI"
    assert sent["4"]["inputs"]["text"] == "via sdk"

    deadline = time.time() + 20
    st = {}
    while time.time() < deadline:
        st = comfy_client.get_job_status(res["job_id"], comfy.url, "sdk")
        if st["status"] in ("completed", "error"):
            break
        time.sleep(0.2)
    assert st.get("status") == "completed", st
    assert st["media_type"] == "image"
    assert st["view_url"].startswith(f"/shinjutsu/api/jobs/{res['job_id']}/outputs/")

    output_id = st["view_url"].rsplit("/", 1)[-1]
    redirect_url, data, ctype = comfy_client.sdk_output_download(res["job_id"], output_id)
    assert redirect_url or data
