# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Open-Weights Multi-Modal Creative Studio Server for ComfyUI (`app_ui.py`)

Serves the ultra-clean `index.html` studio UI and exposes REST endpoints that bridge directly
to ComfyUI's native APIs (`POST /upload/image`, `GET /history/{prompt_id}`, `GET /view`,
`GET /models/{folder}`, `GET /workflow_templates`, `GET /system_stats`, `POST /free`, `POST /prompt`)
+ automatic `BiRefNet_lite (84.84 MB)` White-BG cutout and `Depth Anything V2` Crisp Depth video generation.
"""

import base64
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import shutil
from typing import Any, Dict, Optional, Tuple
import urllib.parse
import urllib.request
import uuid

try:
    # Package-relative imports: required when loaded by ComfyUI as `custom_nodes/SHINJUTSU-UI`
    # (ComfyUI's CWD is its own root, so bare `core.*` would not resolve there).
    from .core.prep_engine import clean_reference_image_background, generate_depth_control_video
    from .core.model_manager import (
        clear_comfyui_queue,
        compile_ui_workflow_to_api_prompt,
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
    from .core.comfy_client import (
        direct_job_status,
        get_job_status,
        queue_studio_job,
        sdk_output_download,
        stage_input_file,
        transport_info,
    )
except ImportError:
    # Standalone mode: `python app_ui.py` from the repository root
    from core.prep_engine import clean_reference_image_background, generate_depth_control_video  # type: ignore
    from core.model_manager import (  # type: ignore
        clear_comfyui_queue,
        compile_ui_workflow_to_api_prompt,
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
    from core.comfy_client import (  # type: ignore
        direct_job_status,
        get_job_status,
        queue_studio_job,
        sdk_output_download,
        stage_input_file,
        transport_info,
    )

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = OUTPUTS_DIR / "_uploads"
COMPILED_DIR = OUTPUTS_DIR / "_compiled"
RENDERS_DIR = OUTPUTS_DIR / "renders"
WORKFLOWS_DIR = BASE_DIR / "workflows"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
COMPILED_DIR.mkdir(parents=True, exist_ok=True)
RENDERS_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)


def upload_file_to_comfyui(file_path: Path, comfy_url: str = "http://127.0.0.1:8188") -> str:
    """
    Uploads a local image or video file to ComfyUI's native `POST /upload/image` endpoint
    using standard multipart/form-data and returns the server-assigned filename inside `ComfyUI/input/`.
    """
    boundary = f"----ShinjutsuBoundary{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"true\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{comfy_url.rstrip('/')}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2.5) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        return str(res_data.get("name") or file_path.name)


def check_comfy_job_history(prompt_id: str, comfy_url: str = "http://127.0.0.1:8188") -> Dict[str, Any]:
    """
    Polls ComfyUI's native `GET /history/{prompt_id}` and returns the best image / video / audio output.
    (Thin wrapper kept for backward compatibility — see `core.comfy_client.direct_job_status`.)
    """
    return direct_job_status(prompt_id, comfy_url)


DEFAULT_ASSET_FOLDERS = ("characters", "outfits", "scenes", "motions")
for _sub in DEFAULT_ASSET_FOLDERS:
    (UPLOADS_DIR / _sub).mkdir(parents=True, exist_ok=True)


def _safe_folder_name(raw: str) -> str:
    clean = "".join(ch for ch in (raw or "").strip() if ch.isalnum() or ch in ("_", "-", " ")).strip()
    return clean.replace(" ", "_")[:40]


def _detect_media_kind(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return "image"
    if ext in (".mp4", ".webm", ".mov", ".mkv", ".gif"):
        return "video"
    if ext in (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".opus"):
        return "audio"
    return "other"


def _stage_existing_asset_file(
    src_file: Path,
    mode: str,
    role: str,
    comfy_url: str,
) -> Dict[str, Any]:
    kind = _detect_media_kind(src_file)
    final_path = src_file
    depth_name: Optional[str] = None
    parent_dir = src_file.parent

    video_duration_sec: Optional[float] = None
    if kind == "video":
        try:
            import cv2  # type: ignore
            cap = cv2.VideoCapture(str(src_file))
            v_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            v_cnt = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            cap.release()
            if v_fps > 0 and v_cnt > 0:
                video_duration_sec = round(float(v_cnt) / float(v_fps), 2)
        except Exception:
            pass

    if kind == "image" and mode in ("shinjutsu", "soul") and role not in ("scene", "background", "room", "scenes"):
        clean_path = parent_dir / f"{src_file.stem}_clean_white_bg.png"
        if not clean_path.is_file():
            try:
                clean_reference_image_background(src_file, clean_path, neutral_rgb=(235, 235, 238))
            except Exception:
                pass
        if clean_path.is_file():
            final_path = clean_path
    elif kind == "video" and mode == "shinjutsu":
        try:
            from .core.prep_engine import conform_video_to_24fps
        except ImportError:
            from core.prep_engine import conform_video_to_24fps  # type: ignore
        final_path = conform_video_to_24fps(src_file, target_fps=24)
        depth_path = parent_dir / f"{src_file.stem}_crisp_depth.mp4"
        if not depth_path.is_file():
            try:
                generate_depth_control_video(final_path, depth_path, quality="fast", max_frames=362, fps=24)
            except Exception:
                pass
        if depth_path.is_file():
            try:
                depth_name = stage_input_file(depth_path, comfy_url, upload_file_to_comfyui)
            except Exception:
                depth_name = depth_path.name

    try:
        staged_name = stage_input_file(final_path, comfy_url, upload_file_to_comfyui)
    except Exception:
        staged_name = final_path.name

    try:
        rel_final = final_path.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
        rel_raw = src_file.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
        cleaned_url = f"/outputs/{rel_final}"
        preview_url = f"/outputs/{rel_raw}"
    except Exception:
        cleaned_url = f"/outputs/_uploads/{final_path.name}"
        preview_url = f"/outputs/_uploads/{src_file.name}"

    return {
        "ok": True,
        "comfy_filename": staged_name,
        "depth_filename": depth_name or staged_name,
        "cleaned_url": cleaned_url,
        "preview_url": preview_url,
        "filename": final_path.name,
        "raw_filename": src_file.name,
        "media_type": kind,
        "role": role,
        "duration_sec": video_duration_sec,
    }


def list_studio_assets(kind_filter: str = "all") -> Dict[str, Any]:
    """
    Lists user-saved library files (`outputs/_uploads/`) organized by folder and
    generated creations (`outputs/renders/` + `runtime/ComfyUI/output/`), strictly
    filtered by `kind_filter` (`image` | `video` | `audio` | `all`).
    """
    kf = (kind_filter or "all").lower().strip()
    for sub in DEFAULT_ASSET_FOLDERS:
        (UPLOADS_DIR / sub).mkdir(parents=True, exist_ok=True)

    folders = [d.name for d in sorted(UPLOADS_DIR.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    library_items = []

    def _scan_upload_dir(d_path: Path, folder_label: str) -> None:
        for f in sorted(d_path.iterdir(), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
            if not f.is_file() or f.name.startswith("."):
                continue
            if f.stem.endswith("_clean_white_bg") or f.stem.endswith("_crisp_depth") or f.stem.endswith("_24fps"):
                continue
            mtype = _detect_media_kind(f)
            if mtype == "other":
                continue
            if kf in ("image", "video", "audio") and mtype != kf:
                continue
            rel = f.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
            library_items.append(
                {
                    "id": rel,
                    "name": f.name,
                    "folder": folder_label,
                    "media_type": mtype,
                    "url": f"/outputs/{rel}",
                    "size_kb": round(f.stat().st_size / 1024.0, 1),
                    "mtime": int(f.stat().st_mtime),
                }
            )

    _scan_upload_dir(UPLOADS_DIR, "general")
    for sub_name in folders:
        _scan_upload_dir(UPLOADS_DIR / sub_name, sub_name)

    generated_items = []
    seen_gen = set()
    comfy_out_dir = BASE_DIR / "runtime" / "ComfyUI" / "output"
    gen_roots = [RENDERS_DIR]
    if comfy_out_dir.is_dir():
        gen_roots.append(comfy_out_dir)

    for g_root in gen_roots:
        if not g_root.is_dir():
            continue
        for f in sorted(g_root.rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
            if not f.is_file() or f.name.startswith(".") or f.name in seen_gen:
                continue
            if "_uploads" in f.parts or "_compiled" in f.parts:
                continue
            mtype = _detect_media_kind(f)
            if mtype == "other":
                continue
            if kf in ("image", "video", "audio") and mtype != kf:
                continue
            seen_gen.add(f.name)
            if mtype == "image" and ("soul_id" in f.name.lower() or "character_id" in f.name.lower()):
                char_dir = UPLOADS_DIR / "characters"
                char_dir.mkdir(parents=True, exist_ok=True)
                char_copy = char_dir / f.name
                if not char_copy.is_file():
                    try:
                        shutil.copy2(f, char_copy)
                    except Exception:
                        pass
            if g_root == RENDERS_DIR:
                rel = f.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
                url = f"/outputs/{rel}"
            else:
                # Mirror into RENDERS_DIR on demand so it can be served cleanly
                dst_copy = RENDERS_DIR / f.name
                if not dst_copy.is_file():
                    try:
                        shutil.copy2(f, dst_copy)
                    except Exception:
                        continue
                rel = dst_copy.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
                url = f"/outputs/{rel}"
            generated_items.append(
                {
                    "id": rel,
                    "name": f.name,
                    "folder": "renders",
                    "media_type": mtype,
                    "url": url,
                    "size_kb": round(f.stat().st_size / 1024.0, 1),
                    "mtime": int(f.stat().st_mtime),
                }
            )

    return {
        "ok": True,
        "kind_filter": kf,
        "folders": ["general", *folders],
        "library": library_items,
        "generated": generated_items,
    }


def manage_studio_asset(body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Handles `create_folder`, `move`, `delete`, and `select` for `/shinjutsu/api/assets`."""
    action = str(body.get("action") or "").lower().strip()
    comfy_url = str(body.get("comfy_url") or "http://127.0.0.1:8188")

    if action == "create_folder":
        fname = _safe_folder_name(str(body.get("folder") or ""))
        if not fname:
            return {"ok": False, "error": "Invalid folder name"}, 400
        (UPLOADS_DIR / fname).mkdir(parents=True, exist_ok=True)
        return {"ok": True, "folder": fname}, 200

    rel_id = str(body.get("asset_id") or "").lstrip("/")
    if rel_id.startswith("outputs/"):
        rel_id = rel_id[len("outputs/"):]
    target_path = (OUTPUTS_DIR / rel_id).resolve()
    if not str(target_path).startswith(str(OUTPUTS_DIR.resolve())) or not target_path.is_file():
        return {"ok": False, "error": "Asset file not found"}, 404

    if action == "delete":
        for companion_sfx in ("_clean_white_bg.png", "_crisp_depth.mp4"):
            comp = target_path.parent / f"{target_path.stem}{companion_sfx}"
            comp.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        return {"ok": True, "deleted": rel_id}, 200

    if action == "move":
        dest_folder = _safe_folder_name(str(body.get("target_folder") or "general"))
        dest_dir = UPLOADS_DIR if dest_folder in ("", "general") else (UPLOADS_DIR / dest_folder)
        dest_dir.mkdir(parents=True, exist_ok=True)
        new_path = dest_dir / target_path.name
        if target_path.resolve() != new_path.resolve():
            if "renders" in target_path.parts:
                shutil.copy2(target_path, new_path)
            else:
                shutil.move(str(target_path), str(new_path))
                for companion_sfx in ("_clean_white_bg.png", "_crisp_depth.mp4"):
                    comp = target_path.parent / f"{target_path.stem}{companion_sfx}"
                    if comp.is_file():
                        shutil.move(str(comp), str(dest_dir / comp.name))
        new_rel = new_path.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
        return {"ok": True, "asset_id": new_rel, "folder": dest_folder or "general", "url": f"/outputs/{new_rel}"}, 200

    if action == "select":
        mode = str(body.get("mode") or "shinjutsu")
        folder_hint = target_path.parent.name.lower()
        role = str(body.get("role") or ("scene" if folder_hint == "scenes" else "character")).lower()
        return _stage_existing_asset_file(target_path, mode=mode, role=role, comfy_url=comfy_url), 200

    return {"ok": False, "error": f"Unknown asset action: {action}"}, 400


def process_studio_upload(body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Shared `/shinjutsu/api/upload` handler (ComfyUI route + standalone server).
    Saves the base64 payload, runs role-aware preprocessing, then stages the file for the next job:
      - character / outfit / crew images (SHINJUTSU & Character ID) -> BiRefNet_lite auto-clean onto (235, 235, 238)
      - scene / background images                               -> kept 100% raw
      - SHINJUTSU source videos                                 -> extra Depth Anything V2 control video
    """
    comfy_url = str(body.get("comfy_url") or "http://127.0.0.1:8188")
    data_url = str(body.get("file_data") or body.get("image_data") or "")
    raw_name = Path(str(body.get("filename") or "input_media.png")).name
    kind = str(body.get("kind") or "image")
    mode = str(body.get("mode") or "shinjutsu")
    folder = _safe_folder_name(str(body.get("folder") or ""))
    role = str(body.get("role") or ("scene" if folder == "scenes" else "character")).lower()

    if "," not in data_url:
        return {"ok": False, "error": "No valid base64 media payload"}, 400

    target_dir = (UPLOADS_DIR / folder) if (folder and folder != "general") else UPLOADS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_path = target_dir / raw_name
    saved_path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    return _stage_existing_asset_file(saved_path, mode=mode, role=role, comfy_url=comfy_url), 200


def process_studio_queue(body: Dict[str, Any]) -> Dict[str, Any]:
    """Shared `/shinjutsu/api/queue` handler: compile -> validate against /object_info -> submit (SDK or direct)."""
    return queue_studio_job(body, compile_ui_workflow_to_api_prompt, UPLOADS_DIR, COMPILED_DIR)


def process_studio_job_status(job_id: str, comfy_url: str, transport: str = "") -> Dict[str, Any]:
    st = get_job_status(job_id, comfy_url, transport)
    if isinstance(st, dict) and st.get("status") == "completed":
        fname = Path(str(st.get("filename") or "")).name
        vurl = str(st.get("view_url") or "")
        if fname and vurl.startswith(("http://", "https://")):
            local_dst = RENDERS_DIR / fname
            if not local_dst.is_file():
                try:
                    with urllib.request.urlopen(vurl, timeout=10) as resp:
                        local_dst.write_bytes(resp.read())
                except Exception:
                    pass
            if local_dst.is_file():
                st["local_saved_path"] = str(local_dst)
                st["local_url"] = f"/outputs/renders/{fname}"
                if "soul_id" in fname.lower() or "character_id" in fname.lower():
                    char_dir = UPLOADS_DIR / "characters"
                    char_dir.mkdir(parents=True, exist_ok=True)
                    char_dst = char_dir / fname
                    if not char_dst.is_file():
                        try:
                            shutil.copy2(local_dst, char_dst)
                        except Exception:
                            pass
    return st


class ShinjutsuStudioHandler(SimpleHTTPRequestHandler):
    """Serves `index.html`, static media in `SHINJUTSU/`, and dynamic `/api/*` endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        req_path = parsed.path[len("/shinjutsu"):] if parsed.path.startswith("/shinjutsu/api/") else parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        comfy_url = (qs.get("comfy_url") or ["http://127.0.0.1:8188"])[0]

        if req_path == "/api/status":
            status = get_comfy_And_system_status(comfy_url)
            status.update(transport_info())
            self._send_json(status)
            return

        if req_path == "/api/models":
            self._send_json(scan_installed_models(comfy_url))
            return

        if req_path == "/api/templates":
            self._send_json({"templates": discover_all_templates(comfy_url)})
            return

        if req_path == "/api/assets":
            kind_f = (qs.get("kind") or ["all"])[0]
            self._send_json(list_studio_assets(kind_f))
            return

        if req_path == "/api/config":
            self._send_json({"ok": True, "config": get_studio_config()})
            return

        if req_path == "/api/job-status":
            job_id = (qs.get("job_id") or qs.get("prompt_id") or [""])[0]
            transport = (qs.get("transport") or [""])[0]
            self._send_json(process_studio_job_status(job_id, comfy_url, transport))
            return

        if req_path == "/api/transport":
            self._send_json(transport_info())
            return

        if req_path.startswith("/api/jobs/") and "/outputs/" in req_path:
            job_part, out_part = req_path[len("/api/jobs/"):].split("/outputs/", 1)
            try:
                redirect_url, data, ctype = sdk_output_download(
                    urllib.parse.unquote(job_part), urllib.parse.unquote(out_part)
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=404)
                return
            if redirect_url:
                self.send_response(302)
                self.send_header("Location", redirect_url)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data or b"")))
            self.end_headers()
            self.wfile.write(data or b"")
            return

        if req_path in ("/", "/index.html", "/shinjutsu", "/shinjutsu/"):
            self.path = "/web/index.html"
        elif req_path.startswith("/shinjutsu/web/"):
            self.path = req_path[len("/shinjutsu"):]
        elif req_path.startswith("/css/") or req_path.startswith("/js/"):
            self.path = "/web" + req_path

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        req_path = parsed.path[len("/shinjutsu"):] if parsed.path.startswith("/shinjutsu/api/") else parsed.path
        body = self._read_json_body()
        comfy_url = str(body.get("comfy_url") or "http://127.0.0.1:8188")

        if req_path == "/api/models/download":
            model_id = str(body.get("model_id") or "")
            if body.get("name") and body.get("url"):
                reg = register_dynamic_models(
                    [{"name": body["name"], "directory": body.get("folder", "diffusion_models"), "url": body["url"]}],
                    mode_hint=str(body.get("mode") or "images"),
                )
                if reg:
                    model_id = reg[0]["id"]
            self._send_json(start_model_download(model_id))
            return

        if req_path == "/api/models/download-batch":
            items = body.get("models") or []
            reg = register_dynamic_models(items, mode_hint=str(body.get("mode") or "images"))
            started = []
            for entry in reg:
                res = start_model_download(entry["id"])
                started.append({"id": entry["id"], "name": entry["name"], "status": res.get("status")})
            self._send_json({"ok": True, "started": started})
            return

        if req_path == "/api/template/inspect":
            wf = body.get("workflow") or {}
            mode = str(body.get("mode") or "images")
            self._send_json(inspect_and_prepare_template(wf, mode_hint=mode, comfy_url=comfy_url))
            return

        if req_path == "/api/models/delete":
            model_id = str(body.get("model_id") or "")
            self._send_json(delete_local_model(model_id))
            return

        if req_path == "/api/free-vram":
            self._send_json(free_comfyui_vram(comfy_url))
            return

        if req_path == "/api/interrupt":
            self._send_json(interrupt_comfyui_job(comfy_url))
            return

        if req_path == "/api/clear-queue":
            self._send_json(clear_comfyui_queue(comfy_url))
            return

        if req_path == "/api/config":
            self._send_json({"ok": True, "config": update_studio_config(body)})
            return

        if req_path == "/api/assets":
            payload, status = manage_studio_asset(body)
            self._send_json(payload, status=status)
            return

        if req_path in ("/api/clean-bg", "/api/upload"):
            payload, status = process_studio_upload(body)
            self._send_json(payload, status=status)
            return

        if req_path == "/api/queue":
            self._send_json(process_studio_queue(body))
            return

        self._send_json({"ok": False, "error": f"Unknown endpoint {parsed.path}"}, status=404)


def launch_studio_ui(host: str = "127.0.0.1", port: int = 7865, share: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), ShinjutsuStudioHandler)
    print(f"[SHINJUTSU STUDIO] Running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    launch_studio_ui()
