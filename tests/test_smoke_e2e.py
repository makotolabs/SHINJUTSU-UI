# -*- coding: utf-8 -*-
"""
Tests for Task T2: E2E Smoke Test Driver (`scripts/smoke_e2e.py`) against FakeComfyUI.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import threading
import time

import pytest
from aiohttp import web

from conftest import txt2img_graph
from scripts.smoke_e2e import (
    compute_code_manifest,
    generate_reports,
    get_system_info,
    run_smoke_mode,
)

try:
    from tests.fake_comfyui import FakeComfyState, free_port, make_app
except ImportError:
    from fake_comfyui import FakeComfyState, free_port, make_app  # type: ignore

try:
    from tests.test_routes import _load_package_with_mock_server
except ImportError:
    from test_routes import _load_package_with_mock_server  # type: ignore


@pytest.fixture(scope="module")
def loaded():
    return _load_package_with_mock_server()


class EmbeddedStudioServer:
    def __init__(self, routes):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.state = FakeComfyState()
        self.routes = routes
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._loop = None
        self._runner = None

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        app = make_app(self.state)
        app._client_max_size = 100 * 1024 * 1024
        app.add_routes(self.routes)
        self._runner = web.AppRunner(app)
        self._loop.run_until_complete(self._runner.setup())
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        self._loop.run_until_complete(site.start())
        self._ready.set()
        self._loop.run_forever()

    def __enter__(self):
        self._thread.start()
        self._ready.wait(10)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._loop and self._runner:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop)
                fut.result(5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)


def test_compute_code_manifest(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "core").mkdir()
    (proj / "core" / "mod.py").write_text("print('hello')", encoding="utf-8")
    (proj / "web").mkdir()
    (proj / "web" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (proj / "workflows").mkdir()
    (proj / "workflows" / "wf.json").write_text("{}", encoding="utf-8")

    (proj / "runtime").mkdir()
    (proj / "runtime" / "ignored.py").write_text("ignored", encoding="utf-8")
    (proj / "models").mkdir()
    (proj / "models" / "weights.safetensors").write_bytes(b"0" * 100)
    (proj / "outputs").mkdir()
    (proj / "outputs" / "out.png").write_bytes(b"0" * 100)

    manifest = compute_code_manifest(proj)
    assert "core/mod.py" in manifest
    assert "web/app.js" in manifest
    assert "workflows/wf.json" in manifest
    assert not any("runtime" in k for k in manifest)
    assert not any("models" in k for k in manifest)
    assert not any("outputs" in k for k in manifest)


def test_smoke_driver_against_embedded_fake_comfy(loaded, clean_transport_env, tmp_path):
    """Runs smoke_e2e logic against an embedded FakeComfyUI HTTP server with valid outputs."""
    _, routes = loaded

    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    with EmbeddedStudioServer(routes) as srv:
        base_url = srv.url

        res = run_smoke_mode(
            base_url=base_url,
            mode="images",
            preset="smoke",
            inputs_dir=None,
            out_dir=out_dir,
            poll_timeout=15.0,
            poll_interval=0.1,
            min_size_bytes=10,  # fake comfy outputs tiny 68-byte PNG
        )

        assert res["status"] == "passed", res
        assert res["job_id"] is not None
        assert res["output_file"] is not None
        assert res["output_size_bytes"] > 0
        assert res["output_sha256"] is not None

        # Verify artifacts on disk
        mode_dir = out_dir / "images"
        assert (mode_dir / "request_body.json").is_file()
        assert (mode_dir / "history.json").is_file()
        assert (mode_dir / "meta.json").is_file()
        assert (mode_dir / res["output_file"]).is_file()

        # Generate report
        manifest = compute_code_manifest(Path(__file__).resolve().parent.parent)
        sys_info = get_system_info(base_url)
        md_path, json_path = generate_reports(
            out_dir=out_dir,
            base_url=base_url,
            preset="smoke",
            mode_results={"images": res},
            code_manifest=manifest,
            system_info=sys_info,
        )

        assert md_path.is_file()
        assert json_path.is_file()

        report_json = json.loads(json_path.read_text(encoding="utf-8"))
        assert report_json["summary"]["passed"] == 1
        assert report_json["summary"]["failed"] == 0
        assert "images" in report_json["results"]

        report_md = md_path.read_text(encoding="utf-8")
        assert "| `images` | ✅ PASS |" in report_md
        assert "Code Manifest SHA256" in report_md


def test_smoke_driver_fails_when_history_missing(loaded, clean_transport_env, tmp_path, monkeypatch):
    """Verifies that a mode FAILS if ComfyUI /history/<job_id> cannot be retrieved or is empty."""
    _, routes = loaded

    out_dir = tmp_path / "smoke_out_nohist"
    out_dir.mkdir(parents=True, exist_ok=True)

    with EmbeddedStudioServer(routes) as srv:
        base_url = srv.url

        orig_urlopen = __import__("urllib.request").request.urlopen

        def mock_urlopen(req, *args, **kwargs):
            url_str = req.full_url if hasattr(req, "full_url") else str(req)
            if "/history/" in url_str and threading.current_thread() is threading.main_thread():
                raise __import__("urllib.error").error.HTTPError(url_str, 404, "Not Found", {}, None)
            return orig_urlopen(req, *args, **kwargs)

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        res = run_smoke_mode(
            base_url=base_url,
            mode="images",
            preset="smoke",
            inputs_dir=None,
            out_dir=out_dir,
            poll_timeout=15.0,
            poll_interval=0.1,
            min_size_bytes=10,
        )

        assert res["status"] == "failed"
        assert "history" in str(res["error"]).lower()


def test_smoke_driver_fails_when_output_under_min_size(loaded, clean_transport_env, tmp_path):
    """Verifies that a mode FAILS if output file size is below the required 10 KB threshold."""
    _, routes = loaded

    out_dir = tmp_path / "smoke_out_small"
    out_dir.mkdir(parents=True, exist_ok=True)

    with EmbeddedStudioServer(routes) as srv:
        base_url = srv.url

        # By default, min_size_bytes is 10 KB (10240 bytes). FakeComfy outputs ~68 bytes.
        res = run_smoke_mode(
            base_url=base_url,
            mode="images",
            preset="smoke",
            inputs_dir=None,
            out_dir=out_dir,
            poll_timeout=15.0,
            poll_interval=0.1,
            min_size_bytes=10 * 1024,  # standard requirement
        )

        assert res["status"] == "failed"
        assert "below minimum threshold" in str(res["error"])
