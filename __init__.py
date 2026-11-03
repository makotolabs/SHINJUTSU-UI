# -*- coding: utf-8 -*-
"""
SHINJUTSU UI (神術) — ComfyUI Custom Node & Embedded Studio Route (`__init__.py`)

When placed inside `ComfyUI/custom_nodes/SHINJUTSU-UI`:
  1. Registers the 3 `SHINJUTSU (神術)` custom nodes in ComfyUI (`NODE_CLASS_MAPPINGS`).
  2. Intentionally does NOT declare `WEB_DIRECTORY`: ComfyUI auto-injects every `.js` file inside a
     custom node's `WEB_DIRECTORY` into its main node-editor page as a frontend extension, which would
     run the standalone studio controller (`web/js/app.js`) inside ComfyUI's own UI. Studio assets are
     served exclusively via the namespaced `/shinjutsu/web/*` route instead.
  3. Mounts `GET /shinjutsu`, `/shinjutsu/web/*` static assets, and all `/shinjutsu/api/*` endpoints
     (including `/shinjutsu/api/upload` and `/shinjutsu/api/queue`) onto ComfyUI's own aiohttp
     web server (`http://127.0.0.1:8188/shinjutsu`) with zero route collision against ComfyUI's native `/api/*`.
"""

import asyncio
import functools
import logging
from pathlib import Path

logger = logging.getLogger("SHINJUTSU_UI")

try:
    from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
except ImportError:
    from nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS  # type: ignore

BASE_DIR = Path(__file__).resolve().parent

# Mount `/shinjutsu` and `/shinjutsu/api/*` routes inside ComfyUI's aiohttp PromptServer
try:
    from aiohttp import web
    import server

    try:
        from .app_ui import (
            OUTPUTS_DIR,
            UPLOADS_DIR,
            list_studio_assets,
            manage_studio_asset,
            process_studio_job_status,
            process_studio_queue,
            process_studio_upload,
        )
        from .core.comfy_client import sdk_output_download, transport_info
        from .core.model_manager import (
            clear_comfyui_queue,
            delete_local_model,
            discover_all_templates,
            free_comfyui_vram,
            get_comfy_And_system_status,
            get_studio_config,
            inspect_and_prepare_template,
            interrupt_comfyui_job,
            register_dynamic_models,
            scan_installed_models,
            start_model_download,
            update_studio_config,
        )
    except ImportError:
        from app_ui import (  # type: ignore
            OUTPUTS_DIR,
            UPLOADS_DIR,
            list_studio_assets,
            manage_studio_asset,
            process_studio_job_status,
            process_studio_queue,
            process_studio_upload,
        )
        from core.comfy_client import sdk_output_download, transport_info  # type: ignore
        from core.model_manager import (  # type: ignore
            clear_comfyui_queue,
            delete_local_model,
            discover_all_templates,
            free_comfyui_vram,
            get_comfy_And_system_status,
            get_studio_config,
            inspect_and_prepare_template,
            interrupt_comfyui_job,
            register_dynamic_models,
            scan_installed_models,
            start_model_download,
            update_studio_config,
        )

    async def _off_loop(fn, *args, **kwargs):
        """
        Runs blocking work in a thread. Essential here: these handlers live INSIDE ComfyUI's event loop and
        many of them call back into the same ComfyUI (`/object_info`, `/prompt`, `/history`, `/system_stats`).
        Doing that synchronously would block the loop that has to answer those very requests.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))

    def _download_batch(items, mode):
        reg = register_dynamic_models(items, mode_hint=mode)
        return {
            "ok": True,
            "started": [
                {"id": entry["id"], "name": entry["name"], "status": start_model_download(entry["id"]).get("status")}
                for entry in reg
            ],
        }

    def _download_one(body):
        model_id = str(body.get("model_id") or "")
        if body.get("name") and body.get("url"):
            reg = register_dynamic_models(
                [{"name": body["name"], "directory": body.get("folder", "diffusion_models"), "url": body["url"]}],
                mode_hint=str(body.get("mode") or "images"),
            )
            if reg:
                model_id = reg[0]["id"]
        return start_model_download(model_id)

    def _local_comfy_url(request) -> str:
        """
        Embedded (custom-node) mode: the studio runs INSIDE ComfyUI, so server-side calls always target this
        very ComfyUI over loopback, whatever URL the browser typed. This keeps everything working when the page
        is opened remotely (RunPod/Vast proxy, LAN, tunnel), where the browser's "comfy_url" is a public address.
        """
        try:
            from comfy.cli_args import args as comfy_args  # available inside a real ComfyUI process

            scheme = "https" if getattr(comfy_args, "tls_keyfile", None) else "http"
            listen = str(getattr(comfy_args, "listen", "127.0.0.1") or "127.0.0.1").split(",")[0].strip()
            host = "127.0.0.1" if listen in ("", "0.0.0.0", "::", "localhost") else listen
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            return f"{scheme}://{host}:{int(comfy_args.port)}"
        except Exception:
            return f"{request.scheme}://{request.host}"

    def _same_origin_media(status: dict) -> dict:
        """Rewrites output links to same-origin `/view?...` paths so the browser loads them through this server."""
        if isinstance(status, dict) and status.get("view_path"):
            status["view_url"] = status["view_path"]
            for out in status.get("outputs") or []:
                if out.get("path"):
                    out["url"] = out["path"]
        return status

    prompt_server = getattr(server, "PromptServer", None)
    if prompt_server and getattr(prompt_server, "instance", None):
        routes = prompt_server.instance.routes

        @routes.get("/shinjutsu")
        async def serve_shinjutsu_studio(_request: web.Request) -> web.FileResponse:
            return web.FileResponse(BASE_DIR / "web" / "index.html")

        @routes.get("/shinjutsu/web/{subpath:.*}")
        async def serve_shinjutsu_web_assets(request: web.Request) -> web.StreamResponse:
            rel = request.match_info.get("subpath", "")
            target = (BASE_DIR / "web" / rel).resolve()
            if not str(target).startswith(str((BASE_DIR / "web").resolve())) or not target.is_file():
                raise web.HTTPNotFound()
            return web.FileResponse(target)

        @routes.get("/outputs/{subpath:.*}")
        async def serve_uploaded_preview(request: web.Request) -> web.StreamResponse:
            rel = request.match_info.get("subpath", "")
            target = (OUTPUTS_DIR / rel).resolve()
            if not str(target).startswith(str(OUTPUTS_DIR.resolve())) or not target.is_file():
                raise web.HTTPNotFound()
            return web.FileResponse(target)

        @routes.get("/shinjutsu/api/status")
        async def shinjutsu_api_status(request: web.Request) -> web.Response:
            comfy_url = _local_comfy_url(request)
            status = await _off_loop(get_comfy_And_system_status, comfy_url)
            status.update(transport_info())
            status["embedded"] = True  # page is served by ComfyUI itself -> browser should use location.origin
            return web.json_response(status)

        @routes.get("/shinjutsu/api/transport")
        async def shinjutsu_api_transport(_request: web.Request) -> web.Response:
            return web.json_response(transport_info())

        @routes.get("/shinjutsu/api/models")
        async def shinjutsu_api_models(request: web.Request) -> web.Response:
            comfy_url = _local_comfy_url(request)
            return web.json_response(await _off_loop(scan_installed_models, comfy_url))

        @routes.get("/shinjutsu/api/templates")
        async def shinjutsu_api_templates(request: web.Request) -> web.Response:
            comfy_url = _local_comfy_url(request)
            return web.json_response({"templates": await _off_loop(discover_all_templates, comfy_url)})

        @routes.get("/shinjutsu/api/assets")
        async def shinjutsu_api_assets_get(request: web.Request) -> web.Response:
            kind_f = request.query.get("kind", "all")
            return web.json_response(await _off_loop(list_studio_assets, kind_f))

        @routes.post("/shinjutsu/api/assets")
        async def shinjutsu_api_assets_post(request: web.Request) -> web.Response:
            body = await request.json()
            body["comfy_url"] = _local_comfy_url(request)
            payload, status = await _off_loop(manage_studio_asset, body)
            return web.json_response(payload, status=status)

        @routes.get("/shinjutsu/api/job-status")
        async def shinjutsu_api_job_status(request: web.Request) -> web.Response:
            job_id = request.query.get("job_id") or request.query.get("prompt_id", "")
            comfy_url = _local_comfy_url(request)
            transport = request.query.get("transport", "")
            status = await _off_loop(process_studio_job_status, job_id, comfy_url, transport)
            return web.json_response(_same_origin_media(status))

        @routes.get("/shinjutsu/api/jobs/{job_id}/outputs/{output_id}")
        async def shinjutsu_api_job_output(request: web.Request) -> web.StreamResponse:
            try:
                redirect_url, data, ctype = await _off_loop(
                    sdk_output_download, request.match_info["job_id"], request.match_info["output_id"]
                )
            except Exception as exc:
                return web.json_response({"ok": False, "error": str(exc)}, status=404)
            if redirect_url:
                raise web.HTTPFound(redirect_url)
            return web.Response(body=data or b"", content_type=ctype.split(";")[0])

        @routes.post("/shinjutsu/api/template/inspect")
        async def shinjutsu_api_template_inspect(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response(
                await _off_loop(
                    inspect_and_prepare_template,
                    body.get("workflow") or {},
                    mode_hint=str(body.get("mode") or "images"),
                    comfy_url=_local_comfy_url(request),
                )
            )

        @routes.post("/shinjutsu/api/models/download")
        async def shinjutsu_api_models_download(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response(await _off_loop(_download_one, body))

        @routes.post("/shinjutsu/api/models/download-batch")
        async def shinjutsu_api_models_download_batch(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response(
                await _off_loop(_download_batch, body.get("models") or [], str(body.get("mode") or "images"))
            )

        @routes.post("/shinjutsu/api/models/delete")
        async def shinjutsu_api_models_delete(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response(await _off_loop(delete_local_model, str(body.get("model_id") or "")))

        @routes.post("/shinjutsu/api/free-vram")
        async def shinjutsu_api_free_vram(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response(await _off_loop(free_comfyui_vram, _local_comfy_url(request)))

        @routes.post("/shinjutsu/api/interrupt")
        async def shinjutsu_api_interrupt(request: web.Request) -> web.Response:
            return web.json_response(await _off_loop(interrupt_comfyui_job, _local_comfy_url(request)))

        @routes.post("/shinjutsu/api/clear-queue")
        async def shinjutsu_api_clear_queue(request: web.Request) -> web.Response:
            return web.json_response(await _off_loop(clear_comfyui_queue, _local_comfy_url(request)))

        @routes.get("/shinjutsu/api/config")
        async def shinjutsu_api_config_get(_request: web.Request) -> web.Response:
            return web.json_response({"ok": True, "config": await _off_loop(get_studio_config)})

        @routes.post("/shinjutsu/api/config")
        async def shinjutsu_api_config_post(request: web.Request) -> web.Response:
            body = await request.json()
            return web.json_response({"ok": True, "config": await _off_loop(update_studio_config, body)})

        @routes.post("/shinjutsu/api/upload")
        @routes.post("/shinjutsu/api/clean-bg")
        async def shinjutsu_api_upload(request: web.Request) -> web.Response:
            body = await request.json()
            body["comfy_url"] = _local_comfy_url(request)
            payload, status = await _off_loop(process_studio_upload, body)
            return web.json_response(payload, status=status)

        @routes.post("/shinjutsu/api/queue")
        async def shinjutsu_api_queue(request: web.Request) -> web.Response:
            body = await request.json()
            body["comfy_url"] = _local_comfy_url(request)
            return web.json_response(await _off_loop(process_studio_queue, body))
except ImportError as exc:
    # Expected when running standalone outside ComfyUI (no `server` module); otherwise surface the cause.
    if getattr(exc, "name", None) not in ("server", "aiohttp"):
        logger.warning("SHINJUTSU UI routes not registered (import error): %s", exc)
except Exception as exc:
    logger.warning("SHINJUTSU UI route registration warning: %s", exc)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
