# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — ComfyUI Client Layer (`core/comfy_client.py`)

One place for everything that talks to ComfyUI, following the Comfy Developer Platform best practices:

  1. `/object_info` introspection (`fetch_object_info`, `widget_names_for`):
     Widget names are read from the *running* ComfyUI instead of a hard-coded table, so UI-format
     templates compile correctly even after a ComfyUI update re-orders or adds widgets.

  2. Pre-flight graph validation (`validate_api_prompt`):
     Before anything is queued, every node class, required input, link target, link type and model
     filename is checked against `/object_info`. Users get one clear message ("node X is not installed",
     "model Y is missing") instead of a silent ComfyUI failure. Partner/API nodes are detected so the
     studio can guarantee the Open-Weights-only promise.

  3. Two transports behind one interface (`submit_job`, `get_job_status`):
       - `sdk`    : Official Comfy SDK (`comfy-sdk`) speaking Comfy API v2 — inputs are uploaded as
                    content-hashed assets, graphs are submitted as jobs, results come back as job outputs.
                    Works against a local ComfyUI through `comfy-api-proxy` (fully offline) or, unchanged,
                    against Comfy Cloud / serverless by changing `COMFY_BASE_URL` / `COMFY_API_KEY`.
       - `direct` : Native ComfyUI `POST /prompt` + `GET /history` (zero extra dependencies). Used as the
                    automatic fallback whenever the SDK is not installed or not configured.

     Selection (`SHINJUTSU_TRANSPORT` env var): `auto` (default) | `sdk` | `direct`.
     `auto` picks `sdk` only when `comfy-sdk` is importable AND `COMFY_BASE_URL` or `COMFY_API_KEY` is set.

Environment variables:
  SHINJUTSU_TRANSPORT              auto | sdk | direct
  COMFY_BASE_URL                   e.g. http://127.0.0.1:8189 (local comfy-api-proxy) — read by comfy-sdk
  COMFY_API_KEY                    Comfy Cloud / serverless key — read by comfy-sdk
  SHINJUTSU_OPEN_WEIGHTS_STRICT    1 = refuse to queue graphs containing partner/API nodes
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request
import uuid

logger = logging.getLogger("SHINJUTSU_UI")

try:
    from .control_lora_codec import RECONSTRUCTED_PATCH_FILENAME, resolve_model_patches_dir
except ImportError:
    try:
        from core.control_lora_codec import RECONSTRUCTED_PATCH_FILENAME, resolve_model_patches_dir  # type: ignore
    except ImportError:
        RECONSTRUCTED_PATCH_FILENAME = "shinjutsu_h3_control_patch_v1_flash.safetensors"
        resolve_model_patches_dir = lambda mr=None: Path("models/model_patches") 

# Widget-capable primitive types (anything else, e.g. MODEL / IMAGE / LATENT, is a socket-only input).
_WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}

# Inputs whose combo values are model files on disk: a value that is not in the list means "not installed".
_MODEL_INPUT_KEYS = {
    "ckpt_name",
    "unet_name",
    "vae_name",
    "clip_name",
    "clip_name1",
    "clip_name2",
    "clip_name3",
    "text_encoder",
    "lora_name",
    "control_net_name",
    "model_name",
    "upscale_model",
    "style_model_name",
    "clip_vision",
}
# Node classes whose `name` input is a model file (e.g. `ModelPatchLoader`).
_MODEL_NAME_NODES = {"ModelPatchLoader"}

_SDK_TERMINAL_OK = {"succeeded", "success", "completed"}
_SDK_TERMINAL_FAIL = {"failed", "canceled", "cancelled", "expired", "error"}


# --------------------------------------------------------------------------------------
# 1. /object_info introspection
# --------------------------------------------------------------------------------------

_OBJECT_INFO_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_OBJECT_INFO_TTL_SEC = 120.0
_OBJECT_INFO_LOCK = threading.Lock()


def fetch_object_info(comfy_url: str, timeout: float = 8.0, force: bool = False) -> Optional[Dict[str, Any]]:
    """Returns ComfyUI's `/object_info` (cached for 2 minutes), or `None` if ComfyUI is unreachable."""
    base = (comfy_url or "").rstrip("/")
    if not base:
        return None
    now = time.time()
    with _OBJECT_INFO_LOCK:
        cached = _OBJECT_INFO_CACHE.get(base)
        if cached and not force and now - cached[0] < _OBJECT_INFO_TTL_SEC:
            return cached[1]
    try:
        with urllib.request.urlopen(f"{base}/object_info", timeout=timeout) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.info("object_info unavailable at %s (%s) — validation skipped", base, exc)
        return None
    if not isinstance(info, dict):
        return None
    with _OBJECT_INFO_LOCK:
        _OBJECT_INFO_CACHE[base] = (now, info)
    return info


def clear_object_info_cache() -> None:
    with _OBJECT_INFO_LOCK:
        _OBJECT_INFO_CACHE.clear()


def is_loopback_url(comfy_url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(comfy_url)
        host = (parsed.hostname or "").lower()
        return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")
    except Exception:
        return False


def can_reconstruct_locally(comfy_url: str) -> bool:
    """
    Returns True ONLY when target ComfyUI is the same host/process:
    1. Embedded mode (PromptServer running in this process)
    2. Or loopback URL whose ComfyUI instance shares the local models directory
    """
    # 1. Embedded mode (custom node inside ComfyUI)
    try:
        import server  # type: ignore
        if getattr(server, "PromptServer", None) is not None and getattr(server.PromptServer, "instance", None) is not None:
            return True
    except Exception:
        pass

    # 2. Must be a loopback URL
    if not is_loopback_url(comfy_url):
        return False

    # Explicit override for tests / configuration
    force_env = os.environ.get("SHINJUTSU_FORCE_LOCAL_MODELS", "").strip().lower()
    if force_env in ("1", "true", "yes"):
        return True
    if force_env in ("0", "false", "no"):
        return False

    # 3. Check target ComfyUI OS via /system_stats
    base = (comfy_url or "").rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/system_stats")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            stats = json.loads(resp.read().decode("utf-8"))
        remote_os = (stats.get("system") or {}).get("os")
        if remote_os and remote_os != "fake" and remote_os != sys.platform:
            return False
    except Exception:
        return False

    # 4. Probe shared models directory via /models/model_patches if available
    try:
        patches_cand = resolve_model_patches_dir()

        probe_name = f".probe_{uuid.uuid4().hex[:8]}.safetensors"
        probe_path = patches_cand / probe_name
        try:
            patches_cand.mkdir(parents=True, exist_ok=True)
            probe_path.write_bytes(b"")
            req = urllib.request.Request(f"{base}/models/model_patches")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                listed = json.loads(resp.read().decode("utf-8"))
            if isinstance(listed, list) and probe_name in listed:
                return True
        finally:
            if probe_path.is_file():
                try:
                    probe_path.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    return False


def _spec_type(spec: Any) -> Any:
    """`[type, options]` -> type. Combo inputs come back as a list of choices (legacy) or "COMBO"."""
    if isinstance(spec, (list, tuple)) and spec:
        return spec[0]
    return spec


def _spec_options(spec: Any) -> Dict[str, Any]:
    if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
        return spec[1]
    return {}


def _combo_choices(spec: Any) -> Optional[List[Any]]:
    t = _spec_type(spec)
    if isinstance(t, (list, tuple)):
        return list(t)
    if t == "COMBO":
        opts = _spec_options(spec).get("options")
        if isinstance(opts, (list, tuple)):
            return list(opts)
    return None


def _is_widget_spec(spec: Any) -> bool:
    t = _spec_type(spec)
    if _spec_options(spec).get("forceInput"):
        return False
    return isinstance(t, (list, tuple)) or (isinstance(t, str) and t in _WIDGET_TYPES)


def _ordered_inputs(node_info: Dict[str, Any]) -> Iterable[Tuple[str, Any, bool]]:
    """Yields `(name, spec, required)` in ComfyUI's declared order (required first, then optional)."""
    inputs = node_info.get("input") or {}
    order = node_info.get("input_order") or {}
    for section, is_req in (("required", True), ("optional", False)):
        specs = inputs.get(section) or {}
        names = order.get(section) or list(specs.keys())
        for name in names:
            if name in specs:
                yield name, specs[name], is_req


def widget_names_for(class_type: str, object_info: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """
    Reconstructs the frontend's `widgets_values` order for a node class from `/object_info`.
    Mirrors the ComfyUI frontend: one entry per widget input, plus a `control_after_generate`
    placeholder right after any INT widget that declares it (seed / noise_seed).
    Returns `None` when the class is unknown so callers can fall back to other strategies.
    """
    if not object_info or class_type not in object_info:
        return None
    names: List[str] = []
    for name, spec, _req in _ordered_inputs(object_info[class_type]):
        if not _is_widget_spec(spec):
            continue
        names.append(name)
        opts = _spec_options(spec)
        if _spec_type(spec) == "INT" and (opts.get("control_after_generate") or name in ("seed", "noise_seed")):
            names.append("control_after_generate")
    return names


def is_partner_node(class_type: str, object_info: Optional[Dict[str, Any]]) -> bool:
    """True for Comfy partner / API nodes (closed-source remote models)."""
    if not object_info or class_type not in object_info:
        return False
    info = object_info[class_type]
    if info.get("api_node"):
        return True
    category = str(info.get("category") or "").lower()
    python_module = str(info.get("python_module") or "").lower()
    return category.startswith("api node") or "comfy_api_nodes" in python_module


# --------------------------------------------------------------------------------------
# 2. Pre-flight validation
# --------------------------------------------------------------------------------------


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def _types_compatible(src_type: Any, dst_type: Any) -> bool:
    if not isinstance(src_type, str) or not isinstance(dst_type, str):
        return True  # combos / unknown shapes: let ComfyUI decide
    if "*" in (src_type, dst_type) or src_type == dst_type:
        return True
    src_set = {s.strip() for s in src_type.split(",")}
    dst_set = {s.strip() for s in dst_type.split(",")}
    return bool(src_set & dst_set)


def validate_api_prompt(api_prompt: Dict[str, Any], object_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Checks an API-format graph against `/object_info` before it is queued.

    Returns:
        {
          "checked": bool,              # False when ComfyUI's object_info was unavailable
          "ok": bool,                   # True when there are no blocking errors
          "errors": [str], "warnings": [str],
          "missing_nodes": [class_type], "missing_models": [{"node", "input", "value"}],
          "partner_nodes": [class_type],
        }
    """
    report: Dict[str, Any] = {
        "checked": bool(object_info),
        "ok": True,
        "errors": [],
        "warnings": [],
        "missing_nodes": [],
        "missing_models": [],
        "partner_nodes": [],
    }
    if not isinstance(api_prompt, dict) or not api_prompt:
        report["ok"] = False
        report["errors"].append("The compiled workflow is empty.")
        return report
    if not object_info:
        return report

    errors: List[str] = report["errors"]
    warnings: List[str] = report["warnings"]

    for nid, node in api_prompt.items():
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type") or "")
        inputs = node.get("inputs") or {}
        label = f"node {nid} ({ctype})"

        if ctype not in object_info:
            if ctype not in report["missing_nodes"]:
                report["missing_nodes"].append(ctype)
            errors.append(f"{label}: node type '{ctype}' is not installed in ComfyUI.")
            continue

        if is_partner_node(ctype, object_info) and ctype not in report["partner_nodes"]:
            report["partner_nodes"].append(ctype)

        specs: Dict[str, Tuple[Any, bool]] = {name: (spec, req) for name, spec, req in _ordered_inputs(object_info[ctype])}

        # Required inputs present? (dynamic "group.item" inputs count as present for their group)
        for name, (spec, req) in specs.items():
            if not req or name in inputs:
                continue
            if any(str(k).startswith(f"{name}.") for k in inputs):
                continue
            errors.append(f"{label}: missing required input '{name}'.")

        for key, value in inputs.items():
            base_key = str(key).split(".")[0]
            spec_req = specs.get(key) or specs.get(base_key)
            if spec_req is None:
                warnings.append(f"{label}: input '{key}' is not declared by this node (ignored by ComfyUI).")
                continue
            spec = spec_req[0]
            is_dynamic_sub_input = "." in str(key)  # V3 Autogrow / DynamicCombo slots, e.g. images.image0

            if _is_link(value):
                src_id = str(value[0])
                src = api_prompt.get(src_id)
                if not isinstance(src, dict):
                    errors.append(f"{label}: input '{key}' links to node {src_id}, which does not exist.")
                    continue
                src_type_name = str(src.get("class_type") or "")
                src_info = object_info.get(src_type_name)
                if src_info:
                    outs = src_info.get("output") or []
                    slot = int(value[1])
                    if slot >= len(outs):
                        errors.append(f"{label}: input '{key}' uses output #{slot} of node {src_id}, which has only {len(outs)}.")
                    elif not is_dynamic_sub_input and not _types_compatible(outs[slot], _spec_type(spec)):
                        errors.append(
                            f"{label}: input '{key}' expects {_spec_type(spec)} but node {src_id} ({src_type_name}) "
                            f"output #{slot} is {outs[slot]}."
                        )
                continue

            is_model_input = key in _MODEL_INPUT_KEYS or (key == "name" and ctype in _MODEL_NAME_NODES)
            if is_model_input and isinstance(value, str):
                choices = _combo_choices(spec)
                if choices is not None:
                    norm_val = value.replace("\\", "/")
                    norm_choices = {str(c).replace("\\", "/") for c in choices}
                    base_choices = {Path(str(c).replace("\\", "/")).name for c in choices}
                    if norm_val not in norm_choices and Path(norm_val).name not in base_choices:
                        report["missing_models"].append({"node": nid, "input": key, "value": value})
                        if Path(norm_val).name == RECONSTRUCTED_PATCH_FILENAME:
                            errors.append(f"{label}: missing model '{value}', reconstruct on the GPU host.")
                        else:
                            errors.append(f"{label}: model '{value}' is not installed (input '{key}').")

    if report["partner_nodes"]:
        warnings.append(
            "Partner/API nodes detected (not open-weights): " + ", ".join(report["partner_nodes"])
        )
    report["ok"] = not errors
    return report


def summarize_validation(report: Dict[str, Any], limit: int = 3) -> str:
    """Short, user-facing summary of a validation report."""
    if report.get("missing_nodes"):
        return "Missing ComfyUI nodes: " + ", ".join(report["missing_nodes"][:limit]) + " — install them via ComfyUI Manager."
    if report.get("missing_models"):
        recon_missing = [m for m in report["missing_models"] if Path(m["value"]).name == RECONSTRUCTED_PATCH_FILENAME]
        if recon_missing:
            return f"Missing model: {recon_missing[0]['value']} — reconstruct on the GPU host."
        names = [m["value"] for m in report["missing_models"][:limit]]
        return "Missing models: " + ", ".join(names) + " — download them in ⚙ Settings → Models."
    errs = report.get("errors") or []
    if errs:
        more = f" (+{len(errs) - limit} more)" if len(errs) > limit else ""
        return "; ".join(errs[:limit]) + more
    return ""


# --------------------------------------------------------------------------------------
# 3. Transports
# --------------------------------------------------------------------------------------

_SDK_CLIENT: Any = None
_SDK_LOCK = threading.Lock()
_SDK_JOBS: Dict[str, Any] = {}  # job_id -> Job handle (keeps outputs reachable without re-fetching)


def sdk_available() -> bool:
    try:
        import comfy_sdk  # noqa: F401

        return True
    except Exception:
        return False


def transport_mode() -> str:
    """`sdk` or `direct` according to `SHINJUTSU_TRANSPORT` and what is installed/configured."""
    pref = os.environ.get("SHINJUTSU_TRANSPORT", "auto").strip().lower() or "auto"
    if pref == "direct":
        return "direct"
    has_sdk = sdk_available()
    if pref == "sdk":
        if not has_sdk:
            logger.warning("SHINJUTSU_TRANSPORT=sdk but comfy-sdk is not installed; falling back to direct /prompt")
            return "direct"
        return "sdk"
    configured = bool(os.environ.get("COMFY_BASE_URL", "").strip() or os.environ.get("COMFY_API_KEY", "").strip())
    return "sdk" if (has_sdk and configured) else "direct"


def transport_info() -> Dict[str, Any]:
    mode = transport_mode()
    base = os.environ.get("COMFY_BASE_URL", "").strip()
    if mode == "sdk":
        target = base or "https://cloud.comfy.org (Comfy Cloud)"
    else:
        target = "ComfyUI native /prompt"
    return {"transport": mode, "sdk_installed": sdk_available(), "target": target}


def _sdk_client() -> Any:
    global _SDK_CLIENT
    with _SDK_LOCK:
        if _SDK_CLIENT is None:
            from comfy_sdk import Comfy

            _SDK_CLIENT = Comfy(timeout=120.0, client_info="shinjutsu-ui")
        return _SDK_CLIENT


def reset_sdk_client() -> None:
    global _SDK_CLIENT
    with _SDK_LOCK:
        _SDK_CLIENT = None
        _SDK_JOBS.clear()


def _collect_local_inputs(api_prompt: Dict[str, Any], uploads_dir: Optional[Path]) -> Dict[str, Path]:
    """Maps every string input that names a file in `uploads_dir` to its local path."""
    found: Dict[str, Path] = {}
    if not uploads_dir or not Path(uploads_dir).is_dir():
        return found
    for node in api_prompt.values():
        if not isinstance(node, dict):
            continue
        for value in (node.get("inputs") or {}).values():
            if isinstance(value, str) and value and Path(value).name == value:
                candidate = Path(uploads_dir) / value
                if candidate.is_file():
                    found[value] = candidate
    return found


def _submit_direct(api_prompt: Dict[str, Any], comfy_url: str, client_id: Optional[str]) -> str:
    body: Dict[str, Any] = {"prompt": api_prompt}
    if client_id:
        body["client_id"] = client_id
    req = urllib.request.Request(
        f"{comfy_url.rstrip('/')}/prompt",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # ComfyUI explains rejected graphs in the 400 body
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            err = payload.get("error") or {}
            detail = err.get("message") or ""
            node_errs = payload.get("node_errors") or {}
            for nid, ne in list(node_errs.items())[:2]:
                for e in (ne.get("errors") or [])[:1]:
                    detail += f" | node {nid}: {e.get('message', '')} {e.get('details', '')}".rstrip()
        except Exception:
            pass
        raise RuntimeError(f"ComfyUI rejected the workflow: {detail or exc}") from exc
    pid = str(data.get("prompt_id") or "")
    if not pid:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {data}")
    return pid


def _submit_sdk(api_prompt: Dict[str, Any], uploads_dir: Optional[Path]) -> str:
    client = _sdk_client()
    wf = client.workflows.from_json(json.loads(json.dumps(api_prompt)))
    local_inputs = _collect_local_inputs(api_prompt, uploads_dir)
    assets: Dict[str, Any] = {}
    for nid, node in api_prompt.items():
        if not isinstance(node, dict):
            continue
        for key, value in (node.get("inputs") or {}).items():
            if isinstance(value, str) and value in local_inputs:
                if value not in assets:
                    assets[value] = client.assets.from_file(str(local_inputs[value]))
                wf.set_input(str(nid), key, assets[value])
    job = client.submit(wf)
    _SDK_JOBS[job.id] = job
    return str(job.id)


def submit_job(
    api_prompt: Dict[str, Any],
    comfy_url: str,
    client_id: Optional[str] = None,
    uploads_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Queues an API-format graph through the active transport. Returns `{"job_id", "transport"}`."""
    mode = transport_mode()
    if mode == "sdk":
        return {"job_id": _submit_sdk(api_prompt, uploads_dir), "transport": "sdk"}
    return {"job_id": _submit_direct(api_prompt, comfy_url, client_id), "transport": "direct"}


def stage_input_file(local_path: Path, comfy_url: str, direct_uploader: Any) -> str:
    """
    Makes a user upload available to the next job and returns the name to put in the graph.
      - sdk    : keep it local; it is uploaded as a content-hashed asset when the job is submitted.
      - direct : push it into ComfyUI's `input/` folder via `POST /upload/image`.
    """
    if transport_mode() == "sdk":
        return Path(local_path).name
    return str(direct_uploader(Path(local_path), comfy_url))


# ---- job status ------------------------------------------------------------------------


def _media_type_from_name(name: str, declared: str = "") -> str:
    declared = (declared or "").lower()
    if declared in ("video", "image", "audio"):
        return declared
    ext = Path(name or "").suffix.lower()
    if ext in (".mp4", ".webm", ".mov", ".mkv", ".gif"):
        return "video"
    if ext in (".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a"):
        return "audio"
    return "image"


_MEDIA_PRIORITY = {"video": 0, "audio": 1, "image": 2}


def direct_job_status(prompt_id: str, comfy_url: str) -> Dict[str, Any]:
    """Polls ComfyUI's `GET /history/{prompt_id}` and returns a normalized status payload."""
    base = comfy_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/history/{urllib.parse.quote(prompt_id)}", timeout=5) as resp:
            hist = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"ok": True, "status": "running"}

    if not isinstance(hist, dict) or prompt_id not in hist:
        return {"ok": True, "status": "running"}

    entry = hist[prompt_id]
    st = entry.get("status") or {}
    if st.get("status_str") == "error":
        msg = "ComfyUI execution error"
        for item in st.get("messages") or []:
            if isinstance(item, list) and len(item) == 2 and item[0] == "execution_error":
                data = item[1] or {}
                msg = f"{data.get('node_type', 'node')}: {data.get('exception_message', msg)}".strip()
        return {"ok": False, "status": "error", "error": msg}

    outputs: List[Dict[str, Any]] = []
    temp_outputs: List[Dict[str, Any]] = []
    for node_id, node_out in (entry.get("outputs") or {}).items():
        if not isinstance(node_out, dict):
            continue
        for key in ("videos", "gifs", "audio", "images"):
            for item in node_out.get(key) or []:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                itype = str(item.get("type") or "output").lower()
                # NEVER return type == "input" (e.g. LoadVideo / LoadImage input previews)
                if itype == "input":
                    continue
                qs = urllib.parse.urlencode(
                    {"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": itype}
                )
                declared = "audio" if key == "audio" else ""
                entry_data = {
                    "node_id": str(node_id),
                    "name": item["filename"],
                    "media_type": _media_type_from_name(item["filename"], declared),
                    "url": f"{base}/view?{qs}",
                    # Same-origin path: correct whenever the studio page is served BY ComfyUI
                    # (custom-node mode), including remote GPUs behind a proxy (RunPod, Vast, ...).
                    "path": f"/view?{qs}",
                    "type": itype,
                }
                if itype == "output":
                    outputs.append(entry_data)
                elif itype == "temp":
                    temp_outputs.append(entry_data)

    # Accept only items with type == "output"; use type "temp" only as a fallback
    candidates = outputs if outputs else temp_outputs
    if candidates:
        candidates.sort(key=lambda o: _MEDIA_PRIORITY.get(o["media_type"], 9))
        best = candidates[0]
        return {
            "ok": True,
            "status": "completed",
            "filename": best["name"],
            "media_type": best["media_type"],
            "view_url": best["url"],
            "view_path": best["path"],
            "outputs": candidates,
        }

    if st.get("completed") or st.get("status_str") == "success":
        return {"ok": False, "status": "error", "error": "Workflow finished but produced no image, video or audio output."}
    return {"ok": True, "status": "running"}


def sdk_job_status(job_id: str) -> Dict[str, Any]:
    client = _sdk_client()
    job = _SDK_JOBS.get(job_id)
    try:
        job = job.refresh() if job is not None else client.jobs.get(job_id)
    except Exception:
        job = client.jobs.get(job_id)
    _SDK_JOBS[job_id] = job
    status = str(job.status or "").lower()

    if status in _SDK_TERMINAL_FAIL:
        err = job.error
        msg = err.get("message") if isinstance(err, dict) else (str(err) if err else f"Job {status}")
        return {"ok": False, "status": "error", "error": msg}
    if status not in _SDK_TERMINAL_OK:
        return {"ok": True, "status": "running", "sdk_status": status}

    outputs: List[Dict[str, Any]] = []
    for out in job.outputs:
        mtype = _media_type_from_name(out.name, out.type)
        if out.type not in ("image", "video", "audio"):
            continue
        outputs.append(
            {
                "node_id": str(out.node_id),
                "name": out.name,
                "media_type": mtype,
                "url": f"/shinjutsu/api/jobs/{urllib.parse.quote(job_id)}/outputs/{urllib.parse.quote(str(out.id))}",
            }
        )
    if not outputs:
        return {"ok": False, "status": "error", "error": "Job succeeded but produced no image, video or audio output."}
    outputs.sort(key=lambda o: _MEDIA_PRIORITY.get(o["media_type"], 9))
    best = outputs[0]
    return {
        "ok": True,
        "status": "completed",
        "filename": best["name"],
        "media_type": best["media_type"],
        "view_url": best["url"],
        "outputs": outputs,
    }


def get_job_status(job_id: str, comfy_url: str, transport: str = "") -> Dict[str, Any]:
    mode = transport or transport_mode()
    if mode == "sdk":
        try:
            return sdk_job_status(job_id)
        except Exception as exc:
            return {"ok": True, "status": "running", "warning": f"SDK status check failed: {exc}"}
    return direct_job_status(job_id, comfy_url)


def sdk_output_download(job_id: str, output_id: str) -> Tuple[Optional[str], Optional[bytes], str]:
    """
    Resolves an SDK job output for the browser.
    Returns `(redirect_url, None, content_type)` when the backend issues fetchable URLs (Comfy Cloud signed
    URLs / proxy content endpoint), otherwise `(None, bytes, content_type)`.
    """
    client = _sdk_client()
    job = _SDK_JOBS.get(job_id) or client.jobs.get(job_id)
    out = next((o for o in job.outputs if str(o.id) == str(output_id)), None)
    if out is None:
        raise KeyError("Output not found on this job.")
    ctype = out.content_type or "application/octet-stream"
    try:
        return out.get_download_url().url, None, ctype
    except Exception:
        return None, out.to_bytes(), ctype


# --------------------------------------------------------------------------------------
# 4. High-level studio job orchestration (shared by the ComfyUI route and standalone server)
# --------------------------------------------------------------------------------------


def _open_weights_strict() -> bool:
    return os.environ.get("SHINJUTSU_OPEN_WEIGHTS_STRICT", "1").strip().lower() not in ("0", "false", "no")


def queue_studio_job(
    body: Dict[str, Any],
    compile_fn: Any,
    uploads_dir: Optional[Path],
    compiled_dir: Path,
) -> Dict[str, Any]:
    """
    Compile -> validate -> submit. `compile_fn` is `compile_ui_workflow_to_api_prompt`.
    The compiled API graph is always saved to `compiled_dir` so it can be inspected or re-run in ComfyUI.
    """
    comfy_url = str(body.get("comfy_url") or "http://127.0.0.1:8188")
    mode = str(body.get("mode") or "shinjutsu")

    def _int(key: str) -> Optional[int]:
        return int(body[key]) if body.get(key) not in (None, "") else None

    object_info = fetch_object_info(comfy_url)
    api_wf = compile_fn(
        body.get("workflow") or {},
        user_prompt=str(body.get("prompt") or ""),
        slot1_file=str(body.get("slot1_file") or ""),
        slot2_file=str(body.get("slot2_file") or ""),
        width=_int("width"),
        height=_int("height"),
        frames=_int("frames"),
        fps=_int("fps"),
        steps=_int("steps"),
        control_strength=float(body["control_strength"]) if body.get("control_strength") is not None else None,
        selected_model_name=str(body.get("selected_model_name") or ""),
        object_info=object_info,
    )

    compiled_dir.mkdir(parents=True, exist_ok=True)
    out_file = compiled_dir / f"shinjutsu_{mode}_api.json"
    out_file.write_text(json.dumps(api_wf, indent=2, ensure_ascii=False), encoding="utf-8")
    saved = f"outputs/_compiled/{out_file.name}"

    # Auto-reconstruct `shinjutsu_h3_control_patch_v1_flash.safetensors` before validation when needed.
    needs_patch = False
    if isinstance(api_wf, dict):
        for node in api_wf.values():
            if isinstance(node, dict) and str(node.get("class_type") or "") == "ModelPatchLoader":
                inp_name = (node.get("inputs") or {}).get("name")
                if inp_name == RECONSTRUCTED_PATCH_FILENAME:
                    needs_patch = True
                    break

    if needs_patch:
        patch_dir = resolve_model_patches_dir()
        patch_on_disk = (patch_dir / RECONSTRUCTED_PATCH_FILENAME).is_file() and (patch_dir / RECONSTRUCTED_PATCH_FILENAME).stat().st_size > 1_000_000
        # If deleted on disk, force fresh object_info from ComfyUI
        if not patch_on_disk:
            fresh_info = fetch_object_info(comfy_url, force=True)
            if fresh_info:
                object_info = fresh_info

        mp_req = (((object_info or {}).get("ModelPatchLoader") or {}).get("input") or {}).get("required") or {}
        choices = _combo_choices(mp_req.get("name"))
        patch_already_present = choices is not None and RECONSTRUCTED_PATCH_FILENAME in choices and patch_on_disk

        if not patch_already_present and can_reconstruct_locally(comfy_url):
            try:
                try:
                    from .control_lora_codec import ensure_reconstructed_control_patch
                except ImportError:
                    from core.control_lora_codec import ensure_reconstructed_control_patch  # type: ignore

                patch_path = ensure_reconstructed_control_patch(api_wf)
                if patch_path is not None:
                    # Invalidate folder_paths cache if imported in this process
                    if "folder_paths" in sys.modules:
                        try:
                            fp = sys.modules["folder_paths"]
                            if hasattr(fp, "filename_list_cache") and isinstance(fp.filename_list_cache, dict):
                                fp.filename_list_cache.pop("model_patches", None)
                        except Exception:
                            pass
                    # Re-fetch /object_info from target ComfyUI.
                    # Only treat the patch as available if the re-fetched info actually lists it!
                    fresh_info = fetch_object_info(comfy_url, force=True)
                    if fresh_info:
                        object_info = fresh_info
            except Exception as exc:
                logger.warning("Auto-reconstruct Control-LoRA skipped: %s", exc)

    report = validate_api_prompt(api_wf, object_info)
    if not report["ok"]:
        return {
            "ok": False,
            "queued": False,
            "error": summarize_validation(report) or "Workflow validation failed.",
            "validation": report,
            "saved": saved,
        }
    if report["partner_nodes"] and _open_weights_strict():
        return {
            "ok": False,
            "queued": False,
            "error": "Open-Weights strict mode: partner/API nodes are not allowed (" + ", ".join(report["partner_nodes"]) + ").",
            "validation": report,
            "saved": saved,
        }

    try:
        res = submit_job(api_wf, comfy_url, client_id=str(body.get("client_id") or "") or None, uploads_dir=uploads_dir)
    except Exception as exc:
        msg = str(exc)
        if msg.startswith("ComfyUI rejected"):
            return {"ok": False, "queued": False, "error": msg, "validation": report, "saved": saved}
        return {
            "ok": True,
            "queued": False,
            "message": f"ComfyUI offline ({msg}) — saved compiled API workflow JSON",
            "validation": report,
            "saved": saved,
        }
    return {
        "ok": True,
        "queued": True,
        "prompt_id": res["job_id"],  # kept for backward compatibility with older frontends
        "job_id": res["job_id"],
        "transport": res["transport"],
        "validation": report,
        "saved": saved,
    }
