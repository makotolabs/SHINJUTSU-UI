#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHINJUTSU UI — E2E Smoke Test Driver (`scripts/smoke_e2e.py`)

Drives the real SHINJUTSU HTTP API end-to-end:
  1. Uploads media via `POST /shinjutsu/api/upload`
  2. Queues jobs via `POST /shinjutsu/api/queue` with exported UI graph
  3. Polls status via `GET /shinjutsu/api/job-status`
  4. Downloads outputs, computes SHA256, and fetches ComfyUI `/history/<prompt_id>`
  5. Records code manifest (SHA256 of all project files) and writes `smoke_report.md` + `smoke_report.json`
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PICKERS = {
    "shinjutsu": "shinjutsu_16gb_turbo",
    "shinjutsu_w6a8": "shinjutsu_16gb_turbo",
    "shinjutsu_int8": "shinjutsu_svd_33mb",
    "cinema": "ltx23_22b_fp8",
    "video": "minimax_h3_ref2va_int8",
    "soul": "flux3_klein",
    "images": "flux3_klein",
    "audio": "minimax_music_3",
}

SMOKE_PRESETS = {
    "shinjutsu": {"width": 640, "height": 864, "frames": 17, "fps": 24, "steps": 4},
    "shinjutsu_w6a8": {"width": 640, "height": 864, "frames": 17, "fps": 24, "steps": 4},
    "shinjutsu_int8": {"width": 640, "height": 864, "frames": 17, "fps": 24, "steps": 4},
    "cinema": {"width": 512, "height": 512, "frames": 9, "fps": 24, "steps": 8},
    "video": {"width": 512, "height": 512, "frames": 9, "fps": 24, "steps": 8},
    "soul": {"width": 512, "height": 512, "frames": 1, "fps": 1, "steps": 4},
    "images": {"width": 512, "height": 512, "frames": 1, "fps": 1, "steps": 4},
    "audio": {"duration": 5, "steps": 10},
}

FULL_PRESETS = {
    "shinjutsu": {"width": 640, "height": 864, "frames": 311, "fps": 24, "steps": 20},
    "cinema": {"width": 768, "height": 512, "frames": 25, "fps": 24, "steps": 20},
    "video": {"width": 768, "height": 1344, "frames": 25, "fps": 24, "steps": 20},
    "soul": {"width": 768, "height": 1344, "frames": 1, "fps": 1, "steps": 20},
    "images": {"width": 768, "height": 1344, "frames": 1, "fps": 1, "steps": 20},
    "audio": {"duration": 13, "steps": 30},
}


MODE_EXTENSIONS = {
    "shinjutsu": (".mp4", ".webm", ".mov"),
    "shinjutsu_w6a8": (".mp4", ".webm", ".mov"),
    "shinjutsu_int8": (".mp4", ".webm", ".mov"),
    "cinema": (".mp4", ".webm", ".mov"),
    "video": (".mp4", ".webm", ".mov"),
    "audio": (".mp3", ".flac", ".wav", ".opus"),
    "soul": (".png", ".jpg", ".jpeg", ".webp"),
    "images": (".png", ".jpg", ".jpeg", ".webp"),
}


def _extract_history_filenames(entry: Dict[str, Any]) -> set:
    found = set()
    for node_out in (entry.get("outputs") or {}).values():
        if isinstance(node_out, dict):
            for items in node_out.values():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "filename" in item:
                            found.add(str(item["filename"]))
                        elif isinstance(item, str):
                            found.add(item)
    return found


def _find_history_item(entry: Dict[str, Any], filename: str) -> Optional[Dict[str, Any]]:
    for node_out in (entry.get("outputs") or {}).values():
        if isinstance(node_out, dict):
            for items in node_out.values():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get("filename") == filename:
                            return item
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_code_manifest(root: Path) -> Dict[str, str]:
    """Computes SHA256 of every .py, .js, .json excluding runtime/models/outputs."""
    ignored_dirs = {
        "runtime",
        "models",
        "outputs",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".idea",
        ".vscode",
        "node_modules",
        ".system_generated",
    }
    manifest = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Filter out ignored directories in-place so os.walk does not recurse into them
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs and not d.startswith(".")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in (".py", ".js", ".json"):
                full_path = Path(dirpath) / fn
                try:
                    rel_str = full_path.relative_to(root).as_posix()
                    manifest[rel_str] = sha256_file(full_path)
                except Exception:
                    pass
    return dict(sorted(manifest.items()))


def create_synthetic_png(path: Path) -> Path:
    """Creates a minimal valid 1x1 PNG file if none exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal 1x1 transparent PNG
    png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==")
    path.write_bytes(png_bytes)
    return path


def export_mode_graph(root_dir: Path, mode: str, model_picker_id: str) -> Dict[str, Any]:
    """Runs export_graphs.js or falls back to workflows/<mode>.json."""
    js_script = root_dir / "scripts" / "export_graphs.js"
    if js_script.is_file():
        try:
            cmd = ["node", str(js_script), str(root_dir), model_picker_id, mode]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
            graphs = json.loads(proc.stdout)
            if mode in graphs and "__error__" not in graphs[mode]:
                return graphs[mode]
        except Exception:
            pass

    # Fallback to bundled workflow file
    wf_mapping = {
        "shinjutsu": root_dir / "workflows" / "01_shinjutsu_h3_motion_transfer.json",
        "cinema": root_dir / "workflows" / "02_cinema_studio_ltx23_vfx.json",
        "soul": root_dir / "workflows" / "03_soul_id_flux3_klein.json",
        "video": root_dir / "workflows" / "04_video_minimax_h3_i2v.json",
        "audio": root_dir / "workflows" / "05_audio_minimax_music3.json",
    }
    wf_path = wf_mapping.get(mode)
    if wf_path and wf_path.is_file():
        return json.loads(wf_path.read_text(encoding="utf-8"))

    raise RuntimeError(f"Could not export or locate workflow graph for mode: {mode}")


def upload_media_to_studio(base_url: str, file_path: Path, mode: str, role: str = "character") -> Dict[str, Any]:
    """Uploads an image or video to /shinjutsu/api/upload."""
    file_bytes = file_path.read_bytes()
    b64 = base64.b64encode(file_bytes).decode("ascii")
    ext = file_path.suffix.lower()
    mime = "image/png"
    kind = "image"
    if ext in (".mp4", ".webm", ".mov"):
        mime = "video/mp4"
        kind = "video"
    elif ext in (".mp3", ".wav", ".flac"):
        mime = "audio/mpeg"
        kind = "audio"
    elif ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext in (".webp",):
        mime = "image/webp"

    payload = {
        "file_data": f"data:{mime};base64,{b64}",
        "filename": file_path.name,
        "kind": kind,
        "mode": mode,
        "role": role,
    }

    url = f"{base_url.rstrip('/')}/shinjutsu/api/upload"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_smoke_mode(
    base_url: str,
    mode: str,
    preset: str,
    inputs_dir: Optional[Path],
    out_dir: Path,
    model_override: Optional[str] = None,
    poll_timeout: float = 600.0,
    poll_interval: float = 2.0,
    min_size_bytes: int = 10 * 1024,
) -> Dict[str, Any]:
    """Runs a single mode smoke test and returns the execution report dictionary."""
    mode_out = out_dir / mode
    mode_out.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "mode": mode,
        "preset": preset,
        "status": "failed",
        "wall_time_sec": 0.0,
        "job_id": None,
        "output_file": None,
        "output_size_bytes": 0,
        "output_sha256": None,
        "error": None,
        "history_path": None,
        "compiled_graph_path": None,
    }

    t0 = time.time()
    try:
        # 1. Prepare Inputs
        slot1_file = ""
        slot2_file = ""
        uploaded_input_hashes = set()

        # Find or create candidate inputs
        char_img = None
        motion_vid = None
        if inputs_dir and inputs_dir.is_dir():
            for p in inputs_dir.rglob("*"):
                if not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext in (".png", ".jpg", ".jpeg", ".webp") and char_img is None:
                    char_img = p
                elif ext in (".mp4", ".mov") and motion_vid is None:
                    motion_vid = p

        # Check default uploads if not found
        default_uploads = PROJECT_ROOT / "outputs" / "_uploads"
        if char_img is None and default_uploads.is_dir():
            for p in (default_uploads / "characters").glob("*.png"):
                if p.is_file():
                    char_img = p
                    break
        if motion_vid is None and default_uploads.is_dir():
            for p in (default_uploads / "motions").glob("*.mp4"):
                if p.is_file():
                    motion_vid = p
                    break

        if char_img is None:
            char_img = create_synthetic_png(mode_out / "synth_character.png")

        backend_mode = "shinjutsu" if mode.startswith("shinjutsu") else mode

        # Upload inputs according to mode requirements
        if backend_mode in ("shinjutsu", "video", "soul", "images", "cinema"):
            up1 = upload_media_to_studio(base_url, char_img, mode=backend_mode, role="character")
            slot1_file = str(up1.get("comfy_filename") or up1.get("filename") or char_img.name)
            if char_img.is_file():
                uploaded_input_hashes.add(sha256_file(char_img))

        depth_file = ""
        if backend_mode == "shinjutsu":
            if motion_vid and motion_vid.is_file():
                up2 = upload_media_to_studio(base_url, motion_vid, mode=mode, role="motion")
                slot2_file = str(up2.get("comfy_filename") or up2.get("filename") or motion_vid.name)
                depth_file = str(up2.get("depth_filename") or slot2_file)
                uploaded_input_hashes.add(sha256_file(motion_vid))
            else:
                slot2_file = "source_motion.mp4"
                depth_file = "source_motion.mp4"

        # Free VRAM / unload models before run to guarantee fresh execution
        try:
            free_req = urllib.request.Request(
                f"{base_url.rstrip('/')}/free",
                data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(free_req, timeout=5) as fr_resp:
                pass
        except Exception:
            pass

        # 2. Export Graph
        picker_id = DEFAULT_PICKERS.get(mode, "")
        ui_graph = export_mode_graph(PROJECT_ROOT, backend_mode, picker_id)

        # Randomize seed across all seed-bearing nodes to prevent caching
        run_seed = int(time.time() * 1000) % 2147483647
        for n in ui_graph.values():
            if isinstance(n, dict) and "inputs" in n:
                inps = n["inputs"]
                for s_key in ("noise_seed", "seed"):
                    if s_key in inps:
                        inps[s_key] = run_seed

        # Inject staged filenames into UI graph nodes
        if backend_mode == "shinjutsu":
            if "200" in ui_graph and "inputs" in ui_graph["200"]:
                ui_graph["200"]["inputs"]["image"] = slot1_file
            if "174" in ui_graph and "inputs" in ui_graph["174"]:
                ui_graph["174"]["inputs"]["file"] = depth_file
            if "300" in ui_graph and "inputs" in ui_graph["300"]:
                ui_graph["300"]["inputs"]["file"] = slot2_file
        elif backend_mode == "soul":
            if "11" in ui_graph and "inputs" in ui_graph["11"]:
                ui_graph["11"]["inputs"]["image"] = slot1_file
        elif backend_mode == "cinema":
            if "6" in ui_graph and "inputs" in ui_graph["6"]:
                ui_graph["6"]["inputs"]["image"] = slot1_file

        # 3. Geometry & steps based on preset
        presets = SMOKE_PRESETS if preset == "smoke" else FULL_PRESETS
        spec = presets.get(mode, {"width": 512, "height": 512, "frames": 1, "fps": 24, "steps": 4})

        if mode == "shinjutsu_int8" and not model_override:
            model_override = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"

        queue_body: Dict[str, Any] = {
            "comfy_url": base_url,
            "mode": backend_mode,
            "workflow": ui_graph,
            "prompt": f"SHINJUTSU smoke test {mode} {preset} neutral scene",
            "slot1_file": slot1_file,
            "slot2_file": slot2_file,
            "width": spec.get("width", 512),
            "height": spec.get("height", 512),
            "frames": spec.get("frames", 1),
            "fps": spec.get("fps", 24),
            "steps": spec.get("steps", 4),
            "control_strength": 0.68,
            "selected_model_name": model_override or "",
            "client_id": f"smoke_{mode}_{int(t0)}",
        }

        # Save request body
        (mode_out / "request_body.json").write_text(json.dumps(queue_body, indent=2), encoding="utf-8")

        # 4. POST /shinjutsu/api/queue
        q_url = f"{base_url.rstrip('/')}/shinjutsu/api/queue"
        req = urllib.request.Request(
            q_url,
            data=json.dumps(queue_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            q_res = json.loads(resp.read().decode("utf-8"))

        if not q_res.get("queued"):
            result["error"] = q_res.get("error") or q_res.get("message") or "Workflow rejected before ComfyUI"
            result["wall_time_sec"] = round(time.time() - t0, 2)
            return result

        job_id = str(q_res.get("job_id") or q_res.get("prompt_id") or "")
        result["job_id"] = job_id

        # Save compiled graph if available
        saved_rel = q_res.get("saved")
        if saved_rel and (PROJECT_ROOT / saved_rel).is_file():
            compiled_content = (PROJECT_ROOT / saved_rel).read_text(encoding="utf-8")
            (mode_out / "compiled_api_graph.json").write_text(compiled_content, encoding="utf-8")
            result["compiled_graph_path"] = str(mode_out / "compiled_api_graph.json")

        # 5. Poll /shinjutsu/api/job-status
        deadline = time.time() + poll_timeout
        completed_status: Optional[Dict[str, Any]] = None

        while time.time() < deadline:
            time.sleep(poll_interval)
            qs = urllib.parse.urlencode({"job_id": job_id, "comfy_url": base_url})
            st_url = f"{base_url.rstrip('/')}/shinjutsu/api/job-status?{qs}"
            try:
                with urllib.request.urlopen(st_url, timeout=10) as s_resp:
                    st_data = json.loads(s_resp.read().decode("utf-8"))
            except Exception as poll_exc:
                continue

            status = st_data.get("status")
            if status == "error":
                result["error"] = st_data.get("error") or "ComfyUI execution error"
                break
            if status == "completed":
                completed_status = st_data
                break

        if completed_status is None and result["error"] is None:
            result["error"] = f"Job timed out after {poll_timeout} seconds"

        if completed_status:
            # 6. Fetch ComfyUI /history/<prompt_id> JSON
            hist_data = None
            try:
                h_url = f"{base_url.rstrip('/')}/history/{job_id}"
                with urllib.request.urlopen(h_url, timeout=10) as h_resp:
                    hist_data = json.loads(h_resp.read().decode("utf-8"))
                hist_file = mode_out / "history.json"
                hist_file.write_text(json.dumps(hist_data, indent=2), encoding="utf-8")
                result["history_path"] = str(hist_file)
            except Exception as h_exc:
                result["history_error"] = str(h_exc)

            # 7. Download output media
            v_url = completed_status.get("view_url") or ""
            fname = Path(completed_status.get("filename") or f"{mode}_output.bin").name
            if v_url:
                if v_url.startswith("/"):
                    v_url = f"{base_url.rstrip('/')}{v_url}"
                out_media_path = mode_out / fname
                try:
                    with urllib.request.urlopen(v_url, timeout=30) as dl_resp:
                        out_media_path.write_bytes(dl_resp.read())
                    if out_media_path.is_file():
                        result["output_file"] = out_media_path.name
                        result["output_size_bytes"] = out_media_path.stat().st_size
                        result["output_sha256"] = sha256_file(out_media_path)
                except Exception as dl_exc:
                    result["error"] = f"Failed to download output media: {dl_exc}"

            # Strict verification: ALL conditions (a), (b), (c) must hold for PASS
            hist_entry = None
            if isinstance(hist_data, dict):
                hist_entry = hist_data.get(job_id) or (hist_data if "outputs" in hist_data else None)

            # Check execution details from history
            t_start = None
            t_end = None
            cached_nodes = set()
            if isinstance(hist_entry, dict):
                for msg in (hist_entry.get("status") or {}).get("messages") or []:
                    if isinstance(msg, list) and len(msg) == 2:
                        m_type, m_val = msg[0], msg[1]
                        if m_type == "execution_start" and isinstance(m_val, dict):
                            t_start = m_val.get("timestamp")
                        elif m_type == "execution_success" and isinstance(m_val, dict):
                            t_end = m_val.get("timestamp")
                        elif m_type == "execution_cached" and isinstance(m_val, dict):
                            cached_nodes.update(str(x) for x in (m_val.get("nodes") or []))

                if t_start and t_end:
                    result["gpu_execution_time_sec"] = round((t_end - t_start) / 1000.0, 2)
                result["node_173_executed"] = ("173" not in cached_nodes) if "173" in ui_graph else None

            if hist_entry is None:
                result["status"] = "failed"
                result["error"] = result["error"] or f"ComfyUI /history/{job_id} missing or failed to fetch"
            else:
                hist_status = hist_entry.get("status") or {}
                status_ok = hist_status.get("status_str") == "success" or hist_status.get("completed") is True
                hist_files = _extract_history_filenames(hist_entry)
                out_fname = Path(completed_status.get("filename") or "").name

                if not status_ok:
                    result["status"] = "failed"
                    result["error"] = f"ComfyUI execution status in history is not success ({hist_status.get('status_str')})"
                elif out_fname not in hist_files and not any(out_fname in hf for hf in hist_files):
                    result["status"] = "failed"
                    result["error"] = f"Output file '{out_fname}' not listed in ComfyUI history outputs ({hist_files})"
                else:
                    out_item = _find_history_item(hist_entry, out_fname)
                    out_item_type = str(out_item.get("type") or "output") if out_item else "unknown"

                    ext = Path(out_fname).suffix.lower()
                    allowed_exts = MODE_EXTENSIONS.get(mode, ())

                    if out_item is None:
                        result["status"] = "failed"
                        result["error"] = f"Output file '{out_fname}' not found in ComfyUI history outputs"
                    elif out_item_type != "output":
                        result["status"] = "failed"
                        result["error"] = f"Output file '{out_fname}' has history type '{out_item_type}' (expected 'output'; previews/inputs rejected)"
                    elif result["output_sha256"] in uploaded_input_hashes:
                        result["status"] = "failed"
                        result["error"] = f"Output file '{out_fname}' has identical SHA256 to uploaded input (echoed input, not a real output)"
                    elif allowed_exts and ext not in allowed_exts:
                        result["status"] = "failed"
                        result["error"] = f"Output extension '{ext}' does not match mode '{mode}' (expected {allowed_exts})"
                    elif result["output_size_bytes"] < min_size_bytes:
                        result["status"] = "failed"
                        result["error"] = f"Output file size {result['output_size_bytes']} bytes is below minimum threshold ({min_size_bytes} bytes)"
                    else:
                        result["status"] = "passed"
                        result["error"] = None

    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["wall_time_sec"] = round(time.time() - t0, 2)
        (mode_out / "meta.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def generate_reports(
    out_dir: Path,
    base_url: str,
    preset: str,
    mode_results: Dict[str, Dict[str, Any]],
    code_manifest: Dict[str, str],
    system_info: Dict[str, Any],
) -> Tuple[Path, Path]:
    """Writes smoke_report.md and smoke_report.json."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    passed_count = sum(1 for r in mode_results.values() if r.get("status") == "passed")
    total_count = len(mode_results)

    manifest_hash = hashlib.sha256(json.dumps(code_manifest, sort_keys=True).encode("utf-8")).hexdigest()

    report_data = {
        "timestamp_utc": timestamp,
        "base_url": base_url,
        "preset": preset,
        "code_manifest_sha256": manifest_hash,
        "code_manifest_files_count": len(code_manifest),
        "system": system_info,
        "summary": {
            "total": total_count,
            "passed": passed_count,
            "failed": total_count - passed_count,
        },
        "results": mode_results,
        "manifest": code_manifest,
    }

    json_path = out_dir / "smoke_report.json"
    json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    # Generate Markdown Report
    lines = [
        "# SHINJUTSU UI — E2E Smoke Test Report",
        "",
        f"- **Timestamp (UTC):** `{timestamp}`",
        f"- **Target Engine:** `{base_url}`",
        f"- **Preset:** `{preset}`",
        f"- **Code Manifest SHA256:** `{manifest_hash}` ({len(code_manifest)} files tracked)",
        f"- **Overall Result:** **{passed_count}/{total_count} Passed**",
        "",
        "## Pass / Fail Matrix",
        "",
        "| Mode | Status | Time (s) | Output Filename | Size (Bytes) | SHA256 (first 12) | Notes / Error |",
        "|---|:---:|:---:|---|:---:|---|---|",
    ]

    for mode, r in mode_results.items():
        st = "✅ PASS" if r.get("status") == "passed" else "❌ FAIL"
        wtime = r.get("wall_time_sec", 0.0)
        fname = r.get("output_file") or "-"
        fsize = r.get("output_size_bytes", 0)
        fhash = (r.get("output_sha256") or "")[:12] or "-"
        err = r.get("error") or "None"
        err_clean = str(err).replace("|", "\\|").replace("\n", " ")[:60]
        lines.append(f"| `{mode}` | {st} | {wtime}s | `{fname}` | {fsize:,} | `{fhash}` | {err_clean} |")

    lines.extend([
        "",
        "## Environment & Hardware",
        "",
        f"- **OS:** `{system_info.get('os')}`",
        f"- **Python:** `{system_info.get('python')}`",
        f"- **GPU:** `{system_info.get('gpu_name', 'N/A')}` ({system_info.get('vram_total_gb', 0)} GB VRAM)",
        "",
        "## Evidence Files Structure",
        "",
        "For every tested mode, the following raw evidence files are stored on disk:",
        "- `request_body.json`: The exact parameters passed to `/shinjutsu/api/queue`",
        "- `compiled_api_graph.json`: The compiled ComfyUI API workflow graph",
        "- `history.json`: ComfyUI native `/history/<prompt_id>` JSON verification",
        "- `output_media.*`: The output image/video/audio rendered by ComfyUI",
        "- `meta.json`: Execution metadata, timing, and SHA256",
        "",
    ])

    md_path = out_dir / "smoke_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return md_path, json_path


def get_system_info(base_url: str) -> Dict[str, Any]:
    """Fetches system status from ComfyUI /shinjutsu/api/status or /system_stats."""
    info: Dict[str, Any] = {
        "os": sys.platform,
        "python": sys.version.split()[0],
        "gpu_name": "Unknown",
        "vram_total_gb": 0.0,
    }
    try:
        url = f"{base_url.rstrip('/')}/shinjutsu/api/status"
        with urllib.request.urlopen(url, timeout=3) as resp:
            st = json.loads(resp.read().decode("utf-8"))
        info["gpu_name"] = st.get("gpu_name") or info["gpu_name"]
        info["vram_total_gb"] = st.get("vram_total_gb") or info["vram_total_gb"]
    except Exception:
        try:
            url = f"{base_url.rstrip('/')}/system_stats"
            with urllib.request.urlopen(url, timeout=3) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
            devs = stats.get("devices") or []
            if devs:
                info["gpu_name"] = devs[0].get("name", "Connected GPU")
                info["vram_total_gb"] = round(float(devs[0].get("vram_total", 0)) / (1024**3), 2)
        except Exception:
            pass
    return info


def main():
    parser = argparse.ArgumentParser(description="SHINJUTSU UI E2E Smoke Test Driver")
    parser.add_argument("--base-url", default="http://127.0.0.1:18188", help="Base URL of studio / ComfyUI server")
    parser.add_argument("--modes", default="shinjutsu,cinema,video,soul,images,audio", help="Comma-separated modes")
    parser.add_argument("--preset", choices=["smoke", "full"], default="smoke", help="Execution preset")
    parser.add_argument("--inputs", default=None, help="Directory containing test inputs")
    parser.add_argument("--out", default=None, help="Output evidence directory")
    parser.add_argument("--model-override", default=None, help="Override model file for tested modes")
    parser.add_argument("--poll-timeout", type=float, default=600.0, help="Per-job timeout in seconds")
    parser.add_argument("--min-size-bytes", type=int, default=10 * 1024, help="Minimum output size in bytes to pass")

    args = parser.parse_args()

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_dir = Path(args.out) if args.out else (PROJECT_ROOT / "outputs" / "_smoke" / ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    inputs_path = Path(args.inputs) if args.inputs else None

    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    print(f"[SMOKE] Starting smoke suite at {args.base_url}")
    print(f"[SMOKE] Preset: {args.preset} | Modes: {', '.join(modes)}")
    print(f"[SMOKE] Evidence directory: {out_dir}")

    # Compute code manifest
    print("[SMOKE] Computing project code manifest...")
    manifest = compute_code_manifest(PROJECT_ROOT)
    sys_info = get_system_info(args.base_url)

    mode_results = {}
    for mode in modes:
        print(f"\n--- Running mode: {mode} ({args.preset}) ---")
        res = run_smoke_mode(
            base_url=args.base_url,
            mode=mode,
            preset=args.preset,
            inputs_dir=inputs_path,
            out_dir=out_dir,
            model_override=args.model_override,
            poll_timeout=args.poll_timeout,
            min_size_bytes=args.min_size_bytes,
        )
        mode_results[mode] = res
        status_sym = "PASS" if res["status"] == "passed" else "FAIL"
        print(f"[{status_sym}] Mode {mode}: {res['status'].upper()} ({res['wall_time_sec']}s)")
        if res.get("error"):
            print(f"    Error: {res['error']}")
        if res.get("output_file"):
            print(f"    Output: {res['output_file']} ({res['output_size_bytes']} bytes, SHA256: {res['output_sha256'][:16]}...)")

    md_report, json_report = generate_reports(
        out_dir=out_dir,
        base_url=args.base_url,
        preset=args.preset,
        mode_results=mode_results,
        code_manifest=manifest,
        system_info=sys_info,
    )

    print(f"\n[SMOKE] Reports generated successfully:")
    print(f"  Markdown: {md_report}")
    print(f"  JSON:     {json_report}")


if __name__ == "__main__":
    main()
