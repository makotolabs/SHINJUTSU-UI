# -*- coding: utf-8 -*-
"""
SHINJUTSU UI (`神術`) — 1-Click Self-Contained ComfyUI Bootstrapper & Studio Launcher (`setup_and_run.py`)

For users who clone `SHINJUTSU-UI` into a standalone folder and want a clean,
self-contained ComfyUI runtime inside the same directory (`./runtime/ComfyUI`) with `SHINJUTSU-UI`
automatically mounted under `./runtime/ComfyUI/custom_nodes/SHINJUTSU-UI`.

Usage:
    pip install torch torchvision torchaudio                 # Install PyTorch with CUDA first
    python setup_and_run.py --install-comfy-reqs             # First run: bootstrap ComfyUI + install its requirements
    python setup_and_run.py                                  # Subsequent runs: launch http://127.0.0.1:8188/shinjutsu
    python setup_and_run.py --setup-only --install-comfy-reqs
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from core.control_lora_codec import CONTROL_LORA_FILENAME

BASE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = BASE_DIR / "runtime"
COMFY_DIR = RUNTIME_DIR / "ComfyUI"
COMFY_GIT_URL = "https://github.com/comfyanonymous/ComfyUI.git"

MODEL_SUBFOLDERS = (
    "diffusion_models",
    "checkpoints",
    "loras",
    "vae",
    "text_encoders",
    "controlnet",
    "model_patches",
    "latent_upscale_models",
    "bg_removers",
)


def _find_python_executable(explicit_python: str = "", require_torch: bool = True) -> str:
    """
    Finds a Python 3.10+ interpreter with PyTorch installed.
    If a Python 3.10+ interpreter is found on the machine without PyTorch, automatically creates
    an isolated `./runtime/venv` and installs PyTorch CUDA inside it without touching host packages.
    """
    candidates = []
    if explicit_python:
        candidates.append(Path(explicit_python))
    env_py = os.environ.get("COMFY_PYTHON", "").strip()
    if env_py:
        candidates.append(Path(env_py))

    candidates.extend(
        [
            RUNTIME_DIR / "venv" / "Scripts" / "python.exe",
            RUNTIME_DIR / "venv" / "bin" / "python",
            BASE_DIR / ".venv" / "Scripts" / "python.exe",
            BASE_DIR / ".venv" / "bin" / "python",
            Path(sys.executable),
        ]
    )

    if os.name == "nt":
        local_py_root = Path.home() / "AppData" / "Local" / "Programs" / "Python"
        for ver in ("Python312", "Python311", "Python310", "Python313"):
            candidates.append(local_py_root / ver / "python.exe")
        candidates.append(Path.home() / "MiniConda3" / "python.exe")
    else:
        for exe_name in ("python3.12", "python3.11", "python3.10", "python3"):
            found = shutil.which(exe_name)
            if found:
                candidates.append(Path(found))

    # Pass 1: Look for a Python 3.10+ that already has torch (if require_torch=True)
    for cand in candidates:
        if cand.is_file():
            try:
                check_code = (
                    "import sys, torch; v = tuple(int(x) for x in torch.__version__.split('+')[0].split('.')[:2]); assert sys.version_info >= (3, 10) and v >= (2, 7)"
                    if require_torch
                    else "import sys; assert sys.version_info >= (3, 10)"
                )
                res = subprocess.run(
                    [str(cand), "-c", check_code],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
                if res.returncode == 0:
                    return str(cand)
            except Exception:
                continue

    # Pass 2: If require_torch=True and no candidate had torch yet, find any Python 3.10+ and bootstrap ./runtime/venv
    if require_torch:
        base_py310: str = ""
        for cand in candidates:
            if cand.is_file():
                try:
                    res = subprocess.run(
                        [str(cand), "-c", "import sys; assert sys.version_info >= (3, 10)"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                    )
                    if res.returncode == 0:
                        base_py310 = str(cand)
                        break
                except Exception:
                    continue

        if base_py310:
            venv_dir = RUNTIME_DIR / "venv"
            venv_py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not venv_py.is_file():
                print(f"[0/4] Creating isolated Python 3.10+ virtual environment at {venv_dir} ...")
                RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.check_call([base_py310, "-m", "venv", str(venv_dir)])
            print("[0/4] Installing PyTorch (CUDA 12.8) inside isolated runtime/venv ...")
            subprocess.check_call([str(venv_py), "-m", "pip", "install", "-U", "pip"])
            subprocess.check_call(
                [
                    str(venv_py),
                    "-m",
                    "pip",
                    "install",
                    "-U",
                    "torch",
                    "torchvision",
                    "torchaudio",
                    "--index-url",
                    "https://download.pytorch.org/whl/cu128",
                ]
            )
            return str(venv_py)

    raise RuntimeError(
        "Could not find a Python 3.10+ environment with PyTorch (`torch`) installed.\n"
        "Please install PyTorch first (`pip install torch torchvision torchaudio`) or pass "
        "`--python /path/to/python` (or set `COMFY_PYTHON`)."
    )


def _link_custom_node(target_repo: Path, custom_nodes_dir: Path) -> Path:
    """Syncs `target_repo` into `custom_nodes/SHINJUTSU-UI` without creating a circular junction into `./runtime`."""
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)
    dest = custom_nodes_dir / "SHINJUTSU-UI"
    if dest.exists():
        try:
            if dest.resolve() == target_repo.resolve():
                return dest
        except Exception:
            return dest
    shutil.copytree(
        target_repo,
        dest,
        ignore=shutil.ignore_patterns("runtime", ".git", "__pycache__", "outputs", "models", ".pytest_cache"),
        dirs_exist_ok=True,
    )
    return dest


def bootstrap_comfyui(python_exe: str, install_comfy_reqs: bool = False) -> Path:
    """Clones a clean ComfyUI into `./runtime/ComfyUI`, creates model folders, and mounts `SHINJUTSU-UI`."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    freshly_cloned = not (COMFY_DIR / "main.py").is_file()
    if freshly_cloned:
        print(f"[1/4] Cloning official ComfyUI ({COMFY_GIT_URL}) -> {COMFY_DIR} ...")
        subprocess.check_call(["git", "clone", "--depth", "1", COMFY_GIT_URL, str(COMFY_DIR)])
    else:
        print(f"[1/4] Clean ComfyUI already present at: {COMFY_DIR}")

    models_root = COMFY_DIR / "models"
    for sub in MODEL_SUBFOLDERS:
        (models_root / sub).mkdir(parents=True, exist_ok=True)

    local_lora = BASE_DIR / "models" / CONTROL_LORA_FILENAME
    if local_lora.is_file():
        dst_lora = models_root / "model_patches" / local_lora.name
        if not dst_lora.is_file():
            shutil.copy2(local_lora, dst_lora)

    local_biref = BASE_DIR / "models" / "bg_removers" / "birefnet_lite_fp16.safetensors"
    if local_biref.is_file():
        dst_biref = models_root / "bg_removers" / local_biref.name
        if not dst_biref.is_file():
            shutil.copy2(local_biref, dst_biref)

    print("[2/4] Mounting SHINJUTSU-UI into runtime/ComfyUI/custom_nodes/SHINJUTSU-UI ...")
    mounted = _link_custom_node(BASE_DIR, COMFY_DIR / "custom_nodes")
    print(f"      Mounted -> {mounted}")

    print(f"[3/4] Ensuring SHINJUTSU-UI requirements using Python: {python_exe} ...")
    subprocess.check_call([python_exe, "-m", "pip", "install", "-q", "-r", str(BASE_DIR / "requirements.txt")])
    if (install_comfy_reqs or freshly_cloned) and (COMFY_DIR / "requirements.txt").is_file():
        print("      Installing ComfyUI requirements.txt ...")
        subprocess.check_call([python_exe, "-m", "pip", "install", "-r", str(COMFY_DIR / "requirements.txt")])

    print(f"[4/4] Bootstrap complete! Clean ComfyUI ready at: {COMFY_DIR}")
    return COMFY_DIR


def _open_browser_when_ready(url: str, studio_url: str) -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{url}/shinjutsu/api/status", timeout=1.5) as resp:
                if resp.status == 200:
                    print(f"\n✨ SHINJUTSU UI is live! Opening {studio_url} ...\n")
                    webbrowser.open(studio_url)
                    return
        except Exception:
            time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="1-Click ComfyUI + SHINJUTSU-UI Bootstrapper & Launcher")
    parser.add_argument("--setup-only", action="store_true", help="Set up ./runtime/ComfyUI without starting the server")
    parser.add_argument("--install-comfy-reqs", action="store_true", help="Also run pip install -r runtime/ComfyUI/requirements.txt")
    parser.add_argument("--python", type=str, default="", help="Explicit path to Python interpreter")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="ComfyUI bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8188, help="ComfyUI bind port (default: 8188)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on startup")
    args, extra_comfy_args = parser.parse_known_args()

    py_exe = _find_python_executable(args.python, require_torch=True)
    comfy_dir = bootstrap_comfyui(py_exe, install_comfy_reqs=args.install_comfy_reqs)

    if args.setup_only:
        return

    base_url = f"http://{args.host}:{args.port}"
    studio_url = f"{base_url}/shinjutsu"
    env = os.environ.copy()
    env["COMFYUI_MODELS_DIR"] = str(comfy_dir / "models")

    if not args.no_browser:
        threading.Thread(target=_open_browser_when_ready, args=(base_url, studio_url), daemon=True).start()

    cmd = [py_exe, "main.py", "--listen", args.host, "--port", str(args.port), *extra_comfy_args]
    print(f"🚀 Starting ComfyUI + SHINJUTSU Studio at {studio_url} ...")
    subprocess.run(cmd, cwd=str(comfy_dir), env=env, check=False)


if __name__ == "__main__":
    main()
