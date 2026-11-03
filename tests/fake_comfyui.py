# -*- coding: utf-8 -*-
"""
A tiny stand-in for ComfyUI's native HTTP surface, used by the test-suite (no GPU, no models).

Implements just enough for SHINJUTSU's direct transport AND for `comfy-api-proxy` (SDK transport):
  GET  /object_info            -> tests/fixtures/object_info_min.json
  GET  /system_stats
  POST /prompt                 -> accepts an optional client-supplied `prompt_id` (as the proxy sends)
  GET  /history/{id}           -> completes ~0.3 s after submission with an output matching the graph
  GET  /queue
  GET  /view                   -> tiny PNG / bytes
  POST /upload/image
  POST /api/jobs/{id}/cancel
  GET  /ws                     -> idle websocket (progress is optional for both transports)
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import socket
import threading
import time
import uuid
from typing import Any, Dict, Optional

from aiohttp import web

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OBJECT_INFO = json.loads((FIXTURES / "object_info_min.json").read_text(encoding="utf-8"))

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeComfyState:
    def __init__(self) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.uploads: Dict[str, bytes] = {}
        self.prompts: list = []
        self.complete_after = 0.3
        self.fail_next = False


def _outputs_for(graph: Dict[str, Any]) -> Dict[str, Any]:
    for nid, node in graph.items():
        ctype = node.get("class_type")
        if ctype in ("SaveAudioAdvanced", "SaveAudio"):
            return {nid: {"audio": [{"filename": "song_00001_.mp3", "subfolder": "SHINJUTSU", "type": "output"}]}}
        if ctype == "SaveVideo":
            return {nid: {"images": [{"filename": "clip_00001_.mp4", "subfolder": "SHINJUTSU", "type": "output"}], "animated": [True]}}
    for nid, node in graph.items():
        if node.get("class_type") == "SaveImage":
            return {nid: {"images": [{"filename": "img_00001_.png", "subfolder": "", "type": "output"}]}}
    return {}


def make_app(state: FakeComfyState) -> web.Application:
    async def object_info(_r: web.Request) -> web.Response:
        return web.json_response(OBJECT_INFO)

    async def system_stats(_r: web.Request) -> web.Response:
        return web.json_response({"system": {"os": "fake"}, "devices": [{"name": "Fake GPU", "vram_total": 24 << 30, "vram_free": 20 << 30}]})

    async def prompt(r: web.Request) -> web.Response:
        body = await r.json()
        graph = body.get("prompt") or {}
        missing = [n.get("class_type") for n in graph.values() if n.get("class_type") not in OBJECT_INFO]
        if missing:
            return web.json_response(
                {"error": {"type": "invalid_prompt", "message": f"Cannot execute because node {missing[0]} does not exist."}, "node_errors": {}},
                status=400,
            )
        pid = str(body.get("prompt_id") or uuid.uuid4())
        state.prompts.append(body)
        failing = state.fail_next
        state.fail_next = False
        state.jobs[pid] = {"t0": time.time(), "graph": graph, "fail": failing}
        return web.json_response({"prompt_id": pid, "number": len(state.jobs), "node_errors": {}})

    async def history(r: web.Request) -> web.Response:
        pid = r.match_info["id"]
        job = state.jobs.get(pid)
        if not job or time.time() - job["t0"] < state.complete_after:
            return web.json_response({})
        if job["fail"]:
            entry = {
                "outputs": {},
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "messages": [["execution_error", {"node_type": "KSampler", "exception_message": "CUDA out of memory"}]],
                },
            }
        else:
            entry = {
                "outputs": _outputs_for(job["graph"]),
                "status": {"status_str": "success", "completed": True, "messages": [["execution_cached", {"nodes": []}]]},
            }
        return web.json_response({pid: entry})

    async def queue(_r: web.Request) -> web.Response:
        now = time.time()
        running = [[0, pid] for pid, j in state.jobs.items() if now - j["t0"] < state.complete_after]
        return web.json_response({"queue_running": running, "queue_pending": []})

    async def view(r: web.Request) -> web.Response:
        name = r.query.get("filename", "")
        ctype = "video/mp4" if name.endswith(".mp4") else "audio/mpeg" if name.endswith(".mp3") else "image/png"
        return web.Response(body=_PNG, content_type=ctype)

    async def upload_image(r: web.Request) -> web.Response:
        post = await r.post()
        image = post.get("image")
        name = getattr(image, "filename", None) or "upload.png"
        state.uploads[name] = image.file.read() if hasattr(image, "file") else b""
        return web.json_response({"name": name, "subfolder": str(post.get("subfolder", "") or ""), "type": "input"})

    async def cancel(r: web.Request) -> web.Response:
        return web.json_response({"cancelled": r.match_info["job_id"] in state.jobs})

    async def ws(r: web.Request) -> web.WebSocketResponse:
        sock = web.WebSocketResponse()
        await sock.prepare(r)
        async for _msg in sock:
            pass
        return sock

    app = web.Application()
    app.add_routes(
        [
            web.get("/object_info", object_info),
            web.get("/system_stats", system_stats),
            web.post("/prompt", prompt),
            web.get("/history/{id}", history),
            web.get("/queue", queue),
            web.get("/view", view),
            web.post("/upload/image", upload_image),
            web.post("/api/jobs/{job_id}/cancel", cancel),
            web.get("/ws", ws),
        ]
    )
    return app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeComfyServer:
    """Runs the fake ComfyUI in a background thread: `with FakeComfyServer() as srv: srv.url`."""

    def __init__(self, port: Optional[int] = None) -> None:
        self.port = port or free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.state = FakeComfyState()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._runner = web.AppRunner(make_app(self.state))
        self._loop.run_until_complete(self._runner.setup())
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        self._loop.run_until_complete(site.start())
        self._ready.set()
        self._loop.run_forever()

    def __enter__(self) -> "FakeComfyServer":
        self._thread.start()
        self._ready.wait(10)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._loop and self._runner:
            fut = asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop)
            try:
                fut.result(5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8188)
    args = ap.parse_args()
    web.run_app(make_app(FakeComfyState()), host="127.0.0.1", port=args.port)
