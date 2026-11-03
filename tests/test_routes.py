# -*- coding: utf-8 -*-
"""
Loads the package exactly like ComfyUI does (as `custom_nodes/<pkg>/__init__.py`, CWD elsewhere) with a
mocked `server.PromptServer`, mounts the studio routes ONTO a fake ComfyUI app — the same process that
answers `/object_info`, `/prompt` and `/history` — and drives them over HTTP.

This guards three real-world regressions:
  * routes silently not registering because of absolute imports,
  * route collisions with ComfyUI's own `/api/*`,
  * event-loop deadlocks when a handler calls back into the very ComfyUI server it runs inside.
"""
import asyncio
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from conftest import ROOT, txt2img_graph  # noqa: E402
from fake_comfyui import FakeComfyState, make_app  # noqa: E402


def _load_package_with_mock_server():
    routes = web.RouteTableDef()
    server_mod = types.ModuleType("server")
    server_mod.PromptServer = type("PromptServer", (), {"instance": types.SimpleNamespace(routes=routes)})
    saved = sys.modules.get("server")
    sys.modules["server"] = server_mod
    cwd = os.getcwd()
    os.chdir(Path(ROOT).parent)  # ComfyUI never runs from inside the custom node folder
    try:
        name = "shinjutsu_ui_under_test"
        spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
        if saved is not None:
            sys.modules["server"] = saved
        else:
            sys.modules.pop("server", None)
    return mod, routes


@pytest.fixture(scope="module")
def loaded():
    return _load_package_with_mock_server()


def test_does_not_declare_web_directory(loaded):
    mod, _ = loaded
    assert not hasattr(mod, "WEB_DIRECTORY")
    assert set(mod.NODE_CLASS_MAPPINGS) >= {"ShinjutsuAutoWhiteBG", "ShinjutsuPromptCompilerNode"}


def test_all_routes_registered_and_namespaced(loaded):
    _, routes = loaded
    paths = {r.path for r in routes}
    expected = {
        "/shinjutsu", "/shinjutsu/web/{subpath:.*}", "/shinjutsu/api/status", "/shinjutsu/api/models",
        "/shinjutsu/api/queue", "/shinjutsu/api/upload", "/shinjutsu/api/job-status", "/shinjutsu/api/transport",
        "/shinjutsu/api/jobs/{job_id}/outputs/{output_id}",
    }
    assert expected <= paths
    # never shadow ComfyUI's own endpoints
    assert not any(p.startswith("/api/") for p in paths)


def _run(coro):
    return asyncio.run(coro)


def test_studio_routes_inside_the_comfyui_process(loaded, clean_transport_env):
    _, routes = loaded

    async def scenario():
        app = make_app(FakeComfyState())  # this aiohttp app plays ComfyUI itself
        app.add_routes(routes)
        async with TestClient(TestServer(app)) as client:
            comfy_url = str(client.make_url("")).rstrip("/")

            for path in ("/shinjutsu", "/shinjutsu/web/css/shinjutsu.css", "/shinjutsu/web/js/app.js"):
                r = await client.get(path)
                assert r.status == 200, path
            assert (await client.get("/shinjutsu/web/../__init__.py")).status == 404

            # Calls back into the same server: would deadlock if run on the event loop
            r = await asyncio.wait_for(client.get("/shinjutsu/api/status", params={"comfy_url": comfy_url}), 15)
            status = await r.json()
            assert status["transport"] == "direct"

            r = await asyncio.wait_for(
                client.post(
                    "/shinjutsu/api/queue",
                    json={"comfy_url": comfy_url, "mode": "images", "workflow": txt2img_graph(), "prompt": "hello"},
                ),
                15,
            )
            queued = await r.json()
            assert queued["queued"] is True and queued["validation"]["checked"] is True, queued

            for _ in range(60):
                r = await client.get(
                    "/shinjutsu/api/job-status",
                    params={"job_id": queued["job_id"], "comfy_url": comfy_url, "transport": queued["transport"]},
                )
                st = await r.json()
                if st["status"] != "running":
                    break
                await asyncio.sleep(0.1)
            assert st["status"] == "completed" and st["media_type"] == "image"
            # Result links must be same-origin paths, never ComfyUI's loopback address
            assert st["view_url"].startswith("/view?"), st["view_url"]

    _run(scenario())


def test_remote_browser_through_proxy_url(loaded, clean_transport_env):
    """
    Browser opened the studio via a public proxy (e.g. https://<pod>-8188.proxy.runpod.net/shinjutsu) and sends
    that public URL as comfy_url. Server-side calls must still hit this ComfyUI over loopback, and every link the
    browser receives must be same-origin, so previews load through the proxy.
    """
    _, routes = loaded
    public = "https://abc123-8188.proxy.runpod.net"

    async def scenario():
        app = make_app(FakeComfyState())
        app.add_routes(routes)
        async with TestClient(TestServer(app)) as client:
            st = await (await client.get("/shinjutsu/api/status", params={"comfy_url": public})).json()
            assert st["embedded"] is True and st["comfy_online"] is True, st

            queued = await (
                await asyncio.wait_for(
                    client.post("/shinjutsu/api/queue", json={"comfy_url": public, "mode": "images", "workflow": txt2img_graph()}),
                    15,
                )
            ).json()
            assert queued["queued"] is True, queued

            for _ in range(60):
                st = await (
                    await client.get("/shinjutsu/api/job-status", params={"job_id": queued["job_id"], "comfy_url": public})
                ).json()
                if st["status"] != "running":
                    break
                await asyncio.sleep(0.1)
            assert st["status"] == "completed", st
            assert st["view_url"].startswith("/view?") and public not in st["view_url"]
            assert all(o["url"].startswith("/view?") for o in st["outputs"])
            # ...and the browser can actually fetch it from the same origin
            assert (await client.get(st["view_url"])).status == 200

    _run(scenario())
