# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Dynamic ComfyUI Model, Template & Subgraph Compiler (`core/model_manager.py`)

Supports EVERY Open-Weights template in ComfyUI (`Comfy-Org/workflow_templates` & local workflows):
  1. Recursive Subgraph Model Scanner (`extract_workflow_required_models`):
     Extracts embedded `{name, url, directory}` model manifests from `extra.models`, `nodes[].properties.models`,
     AND nested `definitions.subgraphs[].nodes[].properties.models`.
  2. Dynamic Registry & Auto-Installer (`register_dynamic_models`, `start_model_download`):
     Any model discovered inside a ComfyUI template is dynamically added to the studio registry, can be
     downloaded in 1 click from its official Hugging Face URL into `models/{directory}/`, and automatically
     populates the studio menu dropdowns!
  3. Universal UI-Graph + Subgraph to API-Prompt Compiler (`compile_ui_workflow_to_api_prompt`):
     Flattens `definitions.subgraphs` and converts ComfyUI UI Graph JSONs (`nodes` + `links` + `widgets_values`)
     into executable `POST /prompt` API dictionaries while injecting the user's prompt, image, and video inputs.
"""

from pathlib import Path
import json
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

try:
    from .control_lora_codec import CONTROL_LORA_FILENAME, DEFAULT_HF_REPO_ID
except ImportError:
    from core.control_lora_codec import CONTROL_LORA_FILENAME, DEFAULT_HF_REPO_ID  # type: ignore

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_MODELS_DIR = BASE_DIR / "models"
WORKFLOWS_DIR = BASE_DIR / "workflows"
STUDIO_CONFIG_PATH = BASE_DIR / "outputs" / "_studio_config.json"


def get_studio_config() -> Dict[str, Any]:
    """Loads persistent studio settings (`outputs/_studio_config.json`) and syncs env vars."""
    cfg: Dict[str, Any] = {
        "comfy_url": os.environ.get("SHINJUTSU_COMFY_URL", "http://127.0.0.1:8188"),
        "hf_token": os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "",
        "civitai_token": os.environ.get("CIVITAI_TOKEN") or "",
        "comfy_api_key": os.environ.get("COMFY_API_KEY") or "",
        "comfy_base_url": os.environ.get("COMFY_BASE_URL") or "",
        "transport": os.environ.get("SHINJUTSU_TRANSPORT", "auto"),
        "open_weights_strict": os.environ.get("SHINJUTSU_OPEN_WEIGHTS_STRICT", "1") == "1",
        "models_dir": os.environ.get("COMFYUI_MODELS_DIR", ""),
        "turbo_download": True,
        "auto_white_bg": True,
    }
    if STUDIO_CONFIG_PATH.is_file():
        try:
            saved = json.loads(STUDIO_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    _apply_config_to_env(cfg)
    # Mask tokens in status readouts while keeping boolean flags so the UI knows whether a token is saved
    return {
        **cfg,
        "has_hf_token": bool(str(cfg.get("hf_token") or "").strip()),
        "has_civitai_token": bool(str(cfg.get("civitai_token") or "").strip()),
        "has_comfy_api_key": bool(str(cfg.get("comfy_api_key") or "").strip()),
    }


def _apply_config_to_env(cfg: Dict[str, Any]) -> None:
    if cfg.get("hf_token"):
        os.environ["HF_TOKEN"] = str(cfg["hf_token"]).strip()
    if cfg.get("civitai_token"):
        os.environ["CIVITAI_TOKEN"] = str(cfg["civitai_token"]).strip()
    if cfg.get("comfy_api_key"):
        os.environ["COMFY_API_KEY"] = str(cfg["comfy_api_key"]).strip()
    if cfg.get("comfy_base_url"):
        os.environ["COMFY_BASE_URL"] = str(cfg["comfy_base_url"]).strip()
    if cfg.get("transport"):
        os.environ["SHINJUTSU_TRANSPORT"] = str(cfg["transport"]).strip()
    if "open_weights_strict" in cfg:
        os.environ["SHINJUTSU_OPEN_WEIGHTS_STRICT"] = "1" if cfg["open_weights_strict"] else "0"
    if cfg.get("models_dir"):
        os.environ["COMFYUI_MODELS_DIR"] = str(cfg["models_dir"]).strip()


def update_studio_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Saves updated studio settings to `outputs/_studio_config.json` and applies them immediately."""
    current = get_studio_config()
    for k in (
        "comfy_url",
        "hf_token",
        "civitai_token",
        "comfy_api_key",
        "comfy_base_url",
        "transport",
        "open_weights_strict",
        "models_dir",
        "turbo_download",
        "auto_white_bg",
    ):
        if k in updates and updates[k] is not None:
            current[k] = updates[k]
    STUDIO_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STUDIO_CONFIG_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    _apply_config_to_env(current)
    return get_studio_config()


def resolve_models_root(target_root: Optional[Path] = None) -> Path:
    """
    Resolves the active ComfyUI `models/` directory so 1-click downloads and local scans
    work seamlessly whether running inside `ComfyUI/custom_nodes/SHINJUTSU-UI`, via the
    local `./runtime/ComfyUI` bootstrapper, or standalone.
    """
    if target_root is not None:
        return Path(target_root)
    env_dir = os.environ.get("COMFYUI_MODELS_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    try:
        import folder_paths  # type: ignore

        models_dir = getattr(folder_paths, "models_dir", None)
        if models_dir and Path(models_dir).is_dir():
            return Path(models_dir)
    except Exception:
        pass
    if BASE_DIR.parent.name == "custom_nodes":
        cand = BASE_DIR.parent.parent / "models"
        if cand.is_dir():
            return cand
    runtime_cand = BASE_DIR / "runtime" / "ComfyUI" / "models"
    if runtime_cand.is_dir():
        return runtime_cand
    return LOCAL_MODELS_DIR


# Master Open-Weights Model Registry across all 5 Studio Tabs
OPEN_WEIGHTS_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "shinjutsu_svd_33mb",
        "name": CONTROL_LORA_FILENAME,
        "title": "SHINJUTSU Motion Engine",
        "category": "shinjutsu",
        "folder": "model_patches",
        "local_rel_path": CONTROL_LORA_FILENAME,
        "size_mb": 33.34,
        "license": "MIT",
        "url": f"https://huggingface.co/{DEFAULT_HF_REPO_ID}/resolve/main/{CONTROL_LORA_FILENAME}",
        "description": "Built-in 10-block SVD motion adapter (33.34 MB)",
    },
    {
        "id": "birefnet_lite_84mb",
        "name": "birefnet_lite_fp16.safetensors",
        "title": "SHINJUTSU Background Cleaner",
        "category": "shinjutsu",
        "folder": "bg_removers",
        "local_rel_path": "bg_removers/birefnet_lite_fp16.safetensors",
        "size_mb": 84.84,
        "license": "MIT",
        "url": "https://huggingface.co/ZhengPeng7/BiRefNet_lite/resolve/main/model.safetensors",
        "description": "Built-in automatic subject cutout onto Studio White (84.84 MB)",
    },
    {
        "id": "u2netp_4mb",
        "name": "u2netp.onnx",
        "title": "U2Netp Fast Cutout Fallback",
        "category": "shinjutsu",
        "folder": "bg_removers",
        "local_rel_path": "bg_removers/u2netp.onnx",
        "size_mb": 4.36,
        "license": "Apache-2.0",
        "url": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        "description": "Instant CPU fallback background remover (4.36 MB)",
    },
    {
        "id": "minimax_h3_ref2va_w6a8",
        "name": "minimax_h3_ref2va_pruned_w6a8.safetensors",
        "title": "MiniMax H3 Ref2VA Lite (W6A8 · 16GB VRAM)",
        "category": "shinjutsu",
        "folder": "diffusion_models",
        "size_mb": 15247.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_w6a8.safetensors",
        "description": "Compact 6-bit/8-bit Pruned Ref2VA UNet (14.89 GB) for 16GB–24GB GPUs",
    },
    {
        "id": "minimax_h3_ref2va_int8",
        "name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "title": "MiniMax H3 Ref2VA (Pruned INT8 · 24–32GB 5090)",
        "category": "shinjutsu",
        "folder": "diffusion_models",
        "size_mb": 20000.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "description": "Full-reference Audio+Video DiT backbone (19.53 GB) for RTX 4090 / 5090",
    },
    {
        "id": "minimax_h3_ref2va_unpruned",
        "name": "minimax_h3_ref2va_int8_convrot.safetensors",
        "title": "MiniMax H3 Ref2VA Pro (Unpruned INT8 · Cloud Pod)",
        "category": "shinjutsu",
        "folder": "diffusion_models",
        "size_mb": 32460.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_int8_convrot.safetensors",
        "description": "Unpruned 31.70 GB Reference-to-Video Audio+Video DiT for 48GB–96GB Cloud Pods",
    },
    {
        "id": "minimax_h3_fl2va_int8",
        "name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "title": "MiniMax H3 FL2VA / I2V (Pruned INT8)",
        "category": "video",
        "folder": "diffusion_models",
        "size_mb": 20000.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "description": "Official MiniMax H3 First/Last-Frame & Image-to-Video Audio+Video DiT backbone (19.53 GB)",
    },
    {
        "id": "minimax_h3_fl2v_turbo_lora",
        "name": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "title": "MiniMax H3 I2V 8-Step Turbo LoRA",
        "category": "video",
        "folder": "loras",
        "size_mb": 1860.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "description": "Official 8-step distillation LoRA for MiniMax H3 I2V / FL2VA (1.82 GB)",
    },
    {
        "id": "minimax_h3_ref2v_turbo_lora",
        "name": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
        "title": "MiniMax H3 Ref2V 4-Step Turbo LoRA",
        "category": "shinjutsu",
        "folder": "loras",
        "size_mb": 1860.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
        "description": "Official 4/8-step distillation LoRA for MiniMax H3 Ref2VA (1.82 GB)",
    },
    {
        "id": "qwen3vl_32b_h3_int8",
        "name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "title": "Qwen3-VL 32B Multimodal Encoder (NVFP4 · 14.6GB)",
        "category": "shinjutsu",
        "folder": "text_encoders",
        "size_mb": 14960.0,
        "license": "Apache-2.0",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "description": "Compact NVFP4 AWQ multimodal vision-language encoder for MiniMax H3 (14.61 GB)",
    },
    {
        "id": "minimax_h3_video_vae",
        "name": "minimax_h3_video_vae_int8_convrot.safetensors",
        "title": "MiniMax H3 Video VAE (INT8)",
        "category": "shinjutsu",
        "folder": "vae",
        "size_mb": 1250.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors",
        "description": "Video VAE for MiniMax H3 Ref2VA & FL2VA",
    },
    {
        "id": "minimax_h3_audio_vae",
        "name": "minimax_h3_audio_vae_fp32.safetensors",
        "title": "MiniMax H3 Audio VAE (FP32)",
        "category": "shinjutsu",
        "folder": "vae",
        "size_mb": 480.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors",
        "description": "Stereo Audio VAE for MiniMax H3 Ref2VA & FL2VA",
    },
    {
        "id": "ltx23_22b_fp8",
        "name": "ltx-2.3-22b-dev-fp8.safetensors",
        "title": "LTX-2.3 22B Dev (FP8 Checkpoint)",
        "category": "cinema",
        "folder": "checkpoints",
        "size_mb": 23500.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors",
        "description": "Lightricks 22B Joint Audio-Video & Cinema Studio checkpoint",
    },
    {
        "id": "ltx23_distilled_lora",
        "name": "ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors",
        "title": "LTX-2.3 22B Distilled 1.1 LoRA",
        "category": "cinema",
        "folder": "loras",
        "size_mb": 1450.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/ltx-2.3/resolve/main/split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors",
        "description": "Official LTX-2.3 22B distilled step-reduction LoRA",
    },
    {
        "id": "ltx23_gemma3_te",
        "name": "gemma_3_12B_it_fp4_mixed.safetensors",
        "title": "Gemma 3 12B IT (FP4 Mixed Text Encoder)",
        "category": "cinema",
        "folder": "text_encoders",
        "size_mb": 8200.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
        "description": "Official multimodal text encoder for LTX-2.3 Audio-Video",
    },
    {
        "id": "ltx23_spatial_upscaler",
        "name": "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        "title": "LTX-2.3 Spatial Upscaler x2 (1.1)",
        "category": "cinema",
        "folder": "latent_upscale_models",
        "size_mb": 980.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        "description": "Official 2x latent spatial upscaler for LTX-2.3 Cinema Studio",
    },
    {
        "id": "krea2_turbo_fp8",
        "name": "flux1-krea-dev_fp8_scaled.safetensors",
        "title": "Krea 2 / FLUX.1 Krea Dev",
        "category": "images",
        "folder": "diffusion_models",
        "size_mb": 11900.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/FLUX.1-Krea-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-krea-dev_fp8_scaled.safetensors",
        "description": "Photorealistic DSLR portrait & Character ID backbone",
    },
    {
        "id": "flux1_dev_fp8",
        "name": "flux1-dev-fp8.safetensors",
        "title": "FLUX.1 Dev",
        "category": "images",
        "folder": "diffusion_models",
        "size_mb": 11900.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors",
        "description": "Black Forest Labs FLUX.1 Dev image generation model",
    },
    {
        "id": "wan22_animate_14b",
        "name": "wan2.2_animate_14B_int8_convrot.safetensors",
        "title": "Wan 2.2 Animate 14B",
        "category": "video",
        "folder": "diffusion_models",
        "size_mb": 14200.0,
        "license": "Apache-2.0",
        "url": "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_animate_14B_int8_convrot.safetensors",
        "description": "Alibaba Wan 2.2 14B video & character animation model",
    },
    # FLUX 3 Image Klein Fast Distilled FP8 (Images + Character ID) — 100% Public (No HF_TOKEN needed!), 4-Step, 9.57 GB total
    {
        "id": "flux2_klein_4b",
        "name": "flux-2-klein-4b-fp8.safetensors",
        "title": "FLUX 3 Image Klein (Fast 4-Step FP8)",
        "category": "images",
        "folder": "diffusion_models",
        "size_mb": 3882.0,
        "license": "Apache-2.0",
        "url": "https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors",
        "description": "4-step lightweight image generation & reference character editing (3.88 GB, 16 GB VRAM friendly)",
    },
    {
        "id": "flux2_klein_te",
        "name": "qwen_3_4b_fp8_mixed.safetensors",
        "title": "FLUX 3 Klein Text Encoder (Qwen3 4B FP8)",
        "category": "images",
        "folder": "text_encoders",
        "size_mb": 5371.0,
        "license": "Apache-2.0",
        "url": "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors",
        "description": "Compact FP8 Qwen3 4B text encoder for FLUX 3 Image Klein",
    },
    # FLUX 3 Image Klein (Images + Character ID) — files from the official ComfyUI templates.
    # The Hugging Face repo for the 8 GB UNet is gated: accept the license on the model page, then set HF_TOKEN.
    {
        "id": "flux3_klein",
        "name": "flux3-image-klein-int8-convrot.safetensors",
        "title": "FLUX 3 Image Klein (distilled)",
        "category": "images",
        "folder": "diffusion_models",
        "size_mb": 8000.0,
        "license": "FLUX 3 Klein license (gated on Hugging Face)",
        "url": "https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy/resolve/main/diffusion_models/flux3-image-klein-int8-convrot.safetensors",
        "description": "Black Forest Labs FLUX 3 Image Klein: text-to-image & reference edit (Character ID)",
    },
    {
        "id": "flux3_klein_te",
        "name": "qwen3vl_4b_int8_convrot.safetensors",
        "title": "FLUX 3 Klein Text Encoder (Qwen3-VL 4B)",
        "category": "images",
        "folder": "text_encoders",
        "size_mb": 4633.0,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors",
        "description": "Text encoder for FLUX 3 Image Klein & Krea 2",
    },
    {
        "id": "flux3_klein_vae",
        "name": "flux2-vae.safetensors",
        "title": "FLUX 2/3 VAE",
        "category": "images",
        "folder": "vae",
        "size_mb": 320.6,
        "license": "Open-Weights",
        "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors",
        "description": "Official AutoencoderKL VAE for FLUX 3 Image Klein",
    },
    # Audio mode — exact files used by the official ComfyUI template `audio_minimax_music_3`
    {
        "id": "minimax_music3_dit",
        "name": "minimax_music3_dit_fp16.safetensors",
        "title": "MiniMax Music 3 (DiT)",
        "category": "audio",
        "folder": "diffusion_models",
        "size_mb": 4687.0,
        "license": "Open-Weights (see model card)",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/diffusion_models/minimax_music3_dit_fp16.safetensors",
        "description": "Text-to-music with vocals (diffusion transformer)",
    },
    {
        "id": "minimax_music3_te",
        "name": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
        "title": "MiniMax Music 3 Text Encoder",
        "category": "audio",
        "folder": "text_encoders",
        "size_mb": 8771.0,
        "license": "Open-Weights (see model card)",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
        "description": "Caption & lyrics encoder for MiniMax Music 3",
    },
    {
        "id": "minimax_music3_vae",
        "name": "minimax_music3_dav.safetensors",
        "title": "MiniMax Music 3 Audio VAE",
        "category": "audio",
        "folder": "vae",
        "size_mb": 207.0,
        "license": "Open-Weights (see model card)",
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/vae/minimax_music3_dav.safetensors",
        "description": "Audio decoder for MiniMax Music 3",
    },
]

# Runtime-discovered models from clicked ComfyUI Official Templates
DYNAMIC_TEMPLATE_MODELS: Dict[str, Dict[str, Any]] = {}

LOADER_CLASS_TO_FOLDER: Dict[str, Tuple[str, str]] = {
    "UNETLoader": ("unet_name", "diffusion_models"),
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
    "CLIPLoader": ("clip_name", "text_encoders"),
    "DualCLIPLoader": ("clip_name1", "text_encoders"),
    "VAELoader": ("vae_name", "vae"),
    "LoraLoader": ("lora_name", "loras"),
    "LoraLoaderModelOnly": ("lora_name", "loras"),
    "ControlNetLoader": ("control_net_name", "controlnet"),
    "ModelPatchLoader": ("name", "model_patches"),
    "LatentUpscaleModelLoader": ("model_name", "latent_upscale_models"),
    "LTXVAudioVAELoader": ("ckpt_name", "checkpoints"),
    "LTXAVTextEncoderLoader": ("text_encoder", "text_encoders"),
}

# Aspect ratio dimension presets for ResolutionSelector inlining
ASPECT_RATIO_PRESETS: Dict[str, Tuple[int, int]] = {
    "1:1 (Square)": (1024, 1024),
    "16:9 (Landscape)": (1344, 768),
    "9:16 (Portrait)": (768, 1344),
    "4:3 (Landscape)": (1152, 864),
    "3:4 (Portrait)": (864, 1152),
    "3:2 (Landscape)": (1216, 832),
    "2:3 (Portrait)": (832, 1216),
    "21:9 (Ultrawide)": (1536, 640),
}

# Built-in widget name ordering for standard ComfyUI nodes when converting UI Graph -> API Prompt
NODE_WIDGET_SIGNATURES: Dict[str, List[str]] = {
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CheckpointLoaderSimple": ["ckpt_name"],
    "CLIPLoader": ["clip_name", "type", "device"],
    "DualCLIPLoader": ["clip_name1", "clip_name2", "type", "device"],
    "VAELoader": ["vae_name"],
    "LoraLoader": ["lora_name", "strength_model", "strength_clip"],
    "LoraLoaderModelOnly": ["lora_name", "strength_model"],
    "ControlNetLoader": ["control_net_name"],
    "ModelPatchLoader": ["name"],
    "LatentUpscaleModelLoader": ["model_name"],
    "LTXVAudioVAELoader": ["ckpt_name"],
    "LTXAVTextEncoderLoader": ["text_encoder", "ckpt_name", "device"],
    "LTXVPreprocess": ["img_compression"],
    "LTXVImgToVideoInplace": ["strength", "bypass"],
    "LTXVEmptyLatentAudio": ["frames_number", "frame_rate", "batch_size"],
    "ManualSigmas": ["sigmas"],
    "VAEDecodeTiled": ["tile_size", "overlap", "temporal_size", "temporal_overlap"],
    "CLIPTextEncode": ["text"],
    "CLIPTextEncodeFlux": ["clip_l", "t5xxl", "guidance"],
    "TextEncodeQwenImageEdit": ["prompt"],
    "PrimitiveStringMultiline": ["value"],
    "PrimitiveFloat": ["value"],
    "PrimitiveInt": ["value", "control_after_generate"],
    "PrimitiveBoolean": ["value"],
    "PrimitiveNode": ["value", "control_after_generate"],
    "ResolutionSelector": ["aspect_ratio", "megapixels", "multiple"],
    "EmptySD3LatentImage": ["width", "height", "batch_size"],
    "EmptyLatentImage": ["width", "height", "batch_size"],
    "EmptyFlux2LatentImage": ["width", "height", "batch_size"],
    "EmptyLTXVLatentVideo": ["width", "height", "length", "batch_size"],
    "LTXVImgToVideo": ["width", "height", "length", "batch_size", "strength"],
    "LTXVConditioning": ["frame_rate"],
    "EmptyHunyuanLatentVideo": ["width", "height", "length", "batch_size"],
    "WanImageToVideo": ["width", "height", "length", "batch_size"],
    "WanAnimateToVideo": ["width", "height", "length", "batch_size", "motion_bucket_id", "video_frame_offset"],
    "MiniMaxH3ReferenceToVideo": ["prompt", "width", "height", "length", "ref_image_size"],
    "MiniMaxH3ImageToVideo": ["prompt", "width", "height", "length"],
    "MiniMaxH3SigmaShift": ["shift_video", "shift_audio"],
    "MiniMaxH3FunControlNetApply": ["strength", "start_percent", "end_percent"],
    "MiniMaxH3AddGuide": ["frame_idx"],
    "MiniMaxMusic3TextEncode": ["caption", "lyrics", "seed", "control_after_generate", "max_duration", "cfg_scale", "top_k"],
    "EmptyMiniMaxMusic3LatentAudio": ["seconds", "batch_size"],
    "LoadImage": ["image", "upload"],
    "LoadVideo": ["file", "upload"],
    "LoadAudio": ["audio", "upload"],
    "KSampler": ["seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "KSamplerSelect": ["sampler_name"],
    "BasicScheduler": ["scheduler", "steps", "denoise"],
    "SDTurboScheduler": ["steps", "denoise"],
    "Flux2Scheduler": ["steps", "width", "height"],
    "RandomNoise": ["noise_seed", "control_after_generate"],
    "CFGGuider": ["cfg"],
    "FluxGuidance": ["guidance"],
    "ModelSamplingSD3": ["shift"],
    "ModelSamplingAuraFlow": ["shift", "sampling"],
    "SamplerCustom": ["add_noise", "noise_seed", "control_after_generate", "cfg"],
    "SamplerCustomAdvanced": [],
    "CreateVideo": ["fps", "crf"],
    "SaveVideo": ["filename_prefix", "format", "codec"],
    "SaveWEBM": ["filename_prefix", "codec", "fps", "crf"],
    "SaveImage": ["filename_prefix"],
    "SaveAudioAdvanced": ["filename_prefix", "format"],
    "TrimVideoLatent": ["trim_amount"],
    "ImageScaleToTotalPixels": ["upscale_method", "megapixels", "multiple"],
    "StringReplace": ["find", "replace", "string"],
    "ComfyMathExpression": ["expression"],
    "ComfySwitchNode": ["switch"],
    "VHS_VideoCombine": ["frame_rate", "loop_count", "filename_prefix", "format", "pingpong", "save_output"],
}


class DownloadTaskState:
    """Tracks real-time download progress for the UI."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def update(self, model_id: str, **kwargs: Any) -> None:
        with self.lock:
            cur = self.tasks.get(model_id, {"model_id": model_id, "status": "idle", "percent": 0.0})
            cur.update(kwargs)
            self.tasks[model_id] = cur

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        with self.lock:
            return dict(self.tasks)


DOWNLOAD_STATE = DownloadTaskState()


def _widget_names_from_object_info(class_type: str, object_info: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Live widget order from ComfyUI's `/object_info` (see `core/comfy_client.widget_names_for`)."""
    if not object_info:
        return None
    try:
        from .comfy_client import widget_names_for
    except ImportError:
        from core.comfy_client import widget_names_for  # type: ignore
    return widget_names_for(class_type, object_info)


def _http_get_json(url: str, timeout: float = 3.5) -> Optional[Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SHINJUTSU-Studio/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_all_registered_models() -> List[Dict[str, Any]]:
    """Combines base `OPEN_WEIGHTS_REGISTRY` with any models dynamically discovered from ComfyUI templates."""
    combined = list(OPEN_WEIGHTS_REGISTRY)
    existing_names = {Path(m["name"]).name for m in combined}
    for dyn_id, dyn_item in DYNAMIC_TEMPLATE_MODELS.items():
        if Path(dyn_item["name"]).name not in existing_names:
            combined.append(dyn_item)
            existing_names.add(Path(dyn_item["name"]).name)
    return combined


def register_dynamic_models(models_list: List[Dict[str, Any]], mode_hint: str = "images") -> List[Dict[str, Any]]:
    """
    Registers models extracted from any ComfyUI Official Template (`properties.models`)
    into `DYNAMIC_TEMPLATE_MODELS` so they can be downloaded in 1 click and appear in menu dropdowns!
    """
    registered: List[Dict[str, Any]] = []
    all_curr = get_all_registered_models()

    for m in models_list:
        fname = str(m.get("name") or "").strip()
        if not fname:
            continue
        base_name = Path(fname).name
        existing = next((x for x in all_curr if Path(x["name"]).name == base_name), None)
        if existing:
            if m.get("url") and not existing.get("url"):
                existing["url"] = m["url"]
            registered.append(existing)
            continue

        folder = str(m.get("directory") or "diffusion_models")
        mod_id = f"tpl_{folder}_{Path(base_name).stem}".replace("-", "_").replace(".", "_")
        clean_title = Path(base_name).stem.replace("_", " ").replace("-", " ")
        entry = {
            "id": mod_id,
            "name": fname,
            "title": clean_title,
            "category": mode_hint if folder in ("diffusion_models", "checkpoints") else "support",
            "folder": folder,
            "local_rel_path": f"{folder}/{base_name}",
            "size_mb": float(m.get("size_mb") or 1500.0),
            "license": "Open-Weights",
            "url": str(m.get("url") or ""),
            "description": f"Required by ComfyUI template (models/{folder}/{base_name})",
        }
        DYNAMIC_TEMPLATE_MODELS[mod_id] = entry
        all_curr.append(entry)
        registered.append(entry)

    return registered


def get_comfy_And_system_status(
    comfy_url: str = "http://127.0.0.1:8188",
    comfy_root: Optional[str] = None,
) -> Dict[str, Any]:
    base = comfy_url.rstrip("/")
    stats = _http_get_json(f"{base}/system_stats", timeout=2.0)

    target_disk = Path(comfy_root) if comfy_root and Path(comfy_root).exists() else BASE_DIR
    usage = shutil.disk_usage(target_disk)
    disk_total_gb = round(usage.total / (1024**3), 2)
    disk_used_gb = round(usage.used / (1024**3), 2)
    disk_free_gb = round(usage.free / (1024**3), 2)

    result: Dict[str, Any] = {
        "comfy_online": bool(stats),
        "comfy_url": base,
        "gpu_name": "Local Studio Ready",
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "vram_used_gb": 0.0,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb": disk_used_gb,
        "disk_free_gb": disk_free_gb,
    }

    if stats and isinstance(stats, dict):
        devs = stats.get("devices") or []
        if devs:
            d0 = devs[0]
            v_tot = float(d0.get("vram_total", 0)) / (1024**3)
            v_free = float(d0.get("vram_free", 0)) / (1024**3)
            result.update(
                {
                    "gpu_name": d0.get("name", "Connected GPU"),
                    "vram_total_gb": round(v_tot, 2),
                    "vram_free_gb": round(v_free, 2),
                    "vram_used_gb": round(max(0.0, v_tot - v_free), 2),
                }
            )
    return result


def scan_installed_models(
    comfy_url: str = "http://127.0.0.1:8188",
    comfy_models_dir: Optional[str] = None,
) -> Dict[str, Any]:
    base = comfy_url.rstrip("/")
    folders_to_query = [
        "diffusion_models",
        "checkpoints",
        "loras",
        "vae",
        "text_encoders",
        "controlnet",
        "model_patches",
        "latent_upscale_models",
    ]

    comfy_live_files: Dict[str, List[str]] = {}
    for folder in folders_to_query:
        items = _http_get_json(f"{base}/models/{folder}", timeout=1.2)
        if isinstance(items, list):
            comfy_live_files[folder] = [str(x).replace("\\", "/") for x in items]
        else:
            comfy_live_files[folder] = []

    local_files_map: Dict[str, Path] = {}
    active_models_root = resolve_models_root()
    search_roots = [LOCAL_MODELS_DIR]
    if active_models_root not in search_roots and active_models_root.is_dir():
        search_roots.append(active_models_root)
    if comfy_models_dir and Path(comfy_models_dir).is_dir():
        search_roots.append(Path(comfy_models_dir))

    for root in search_roots:
        if not root.is_dir():
            continue
        for fpath in root.rglob("*"):
            if fpath.is_file() and fpath.suffix.lower() in (".safetensors", ".onnx", ".torchscript", ".pth", ".pt", ".gguf"):
                local_files_map[fpath.name] = fpath
                rel = str(fpath.relative_to(root)).replace("\\", "/")
                local_files_map[rel] = fpath

    enriched_registry: List[Dict[str, Any]] = []
    known_names = set()

    for item in get_all_registered_models():
        entry = dict(item)
        fname = entry["name"]
        fname_base = Path(fname).name
        known_names.add(fname)
        known_names.add(fname_base)

        folder = entry["folder"]
        live_list = comfy_live_files.get(folder, [])
        in_comfy = fname in live_list or fname_base in [Path(x).name for x in live_list]

        local_match = (
            local_files_map.get(entry.get("local_rel_path", ""))
            or local_files_map.get(fname)
            or local_files_map.get(fname_base)
        )

        if local_match and local_match.exists():
            actual_mb = round(local_match.stat().st_size / (1024 * 1024), 2)
            entry["installed"] = True
            entry["actual_size_mb"] = actual_mb
            entry["local_path"] = str(local_match)
            entry["source"] = "local_disk"
        elif in_comfy:
            entry["installed"] = True
            entry["actual_size_mb"] = entry["size_mb"]
            entry["local_path"] = f"ComfyUI/models/{folder}/{fname}"
            entry["source"] = "comfy_api"
        else:
            entry["installed"] = False
            entry["actual_size_mb"] = 0.0
            entry["local_path"] = None
            entry["source"] = None

        dl_info = DOWNLOAD_STATE.get_all().get(entry["id"])
        if dl_info:
            entry["download_state"] = dl_info

        enriched_registry.append(entry)

    dynamic_discovered: List[Dict[str, Any]] = []
    for folder, flist in comfy_live_files.items():
        for fname in flist:
            if fname in known_names or Path(fname).name in known_names:
                continue
            dynamic_discovered.append(
                {
                    "id": f"comfy_{folder}_{Path(fname).stem}",
                    "name": fname,
                    "title": Path(fname).stem,
                    "category": "dynamic_comfy",
                    "folder": folder,
                    "size_mb": 0.0,
                    "installed": True,
                    "source": "comfy_api",
                    "license": "Local ComfyUI",
                    "description": f"Installed in ComfyUI models/{folder}",
                }
            )

    return {
        "models": enriched_registry + dynamic_discovered,
        "comfy_live_folders": comfy_live_files,
        "downloads": DOWNLOAD_STATE.get_all(),
    }


def extract_workflow_required_models(workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Recursively scans ANY ComfyUI workflow JSON:
      1. `extra.models`
      2. Top-level `nodes[].properties.models`
      3. Nested `definitions.subgraphs[].nodes[].properties.models`
      4. Loader node `widgets_values` or API `inputs`
    """
    required: List[Dict[str, Any]] = []
    seen = set()

    def _add_model(name: str, directory: str, url: str = "") -> None:
        base = Path(name).name
        if not base or base in seen:
            return
        seen.add(base)
        if not url:
            match = next((r for r in get_all_registered_models() if Path(r["name"]).name == base), None)
            if match:
                url = match.get("url", "")
                directory = directory or match.get("folder", "diffusion_models")
        required.append({"name": name, "folder": directory or "diffusion_models", "url": url})

    if not isinstance(workflow_data, dict):
        return required

    # 1. Check `extra.models`
    extra = workflow_data.get("extra")
    if isinstance(extra, dict) and isinstance(extra.get("models"), list):
        for m in extra["models"]:
            if isinstance(m, dict) and m.get("name"):
                _add_model(str(m["name"]), str(m.get("directory") or "diffusion_models"), str(m.get("url") or ""))

    # 2. Helper to scan a list of UI Graph nodes
    def _scan_nodes_list(nodes_arr: Any) -> None:
        if not isinstance(nodes_arr, list):
            return
        for node in nodes_arr:
            if not isinstance(node, dict):
                continue
            props = node.get("properties") or {}
            if isinstance(props.get("models"), list):
                for m in props["models"]:
                    if isinstance(m, dict) and m.get("name"):
                        _add_model(str(m["name"]), str(m.get("directory") or "diffusion_models"), str(m.get("url") or ""))
            ntype = str(node.get("type") or "")
            wvals = node.get("widgets_values")
            if ntype in LOADER_CLASS_TO_FOLDER and isinstance(wvals, list) and wvals:
                _key, folder = LOADER_CLASS_TO_FOLDER[ntype]
                if isinstance(wvals[0], str) and wvals[0].endswith((".safetensors", ".ckpt", ".pth", ".gguf", ".onnx")):
                    _add_model(wvals[0], folder)

    # Scan outer `nodes`
    _scan_nodes_list(workflow_data.get("nodes"))

    # 3. Scan `definitions.subgraphs[].nodes`
    defs = workflow_data.get("definitions")
    if isinstance(defs, dict) and isinstance(defs.get("subgraphs"), list):
        for sg in defs["subgraphs"]:
            if isinstance(sg, dict):
                _scan_nodes_list(sg.get("nodes"))

    # 4. Scan flat API Prompt format
    for _node_id, node_val in workflow_data.items():
        if not isinstance(node_val, dict):
            continue
        ctype = str(node_val.get("class_type") or "")
        inputs = node_val.get("inputs") or {}
        if ctype in LOADER_CLASS_TO_FOLDER and isinstance(inputs, dict):
            key_name, folder = LOADER_CLASS_TO_FOLDER[ctype]
            m_name = inputs.get(key_name)
            if isinstance(m_name, str) and m_name:
                _add_model(m_name, folder)
            if ctype == "LTXAVTextEncoderLoader":
                ck = inputs.get("ckpt_name")
                if isinstance(ck, str) and ck:
                    _add_model(ck, "checkpoints")

    return required


def _compile_smart_h3_prompt(user_prompt: str, duration_sec: float) -> str:
    """
    Expands a short 1-line user prompt into the full 6-section MiniMax H3 Ref2VA structure,
    automatically detecting attached `<Picture k>` roles (`scene` -> `partially_preserved`,
    `outfit` -> `fully_preserved` outfit swap, `crew` -> supporting group swap).
    """
    if "subject_definitions:" in user_prompt:
        return user_prompt

    import re
    try:
        from .prompt_compiler import H3PromptCompiler, ShinjutsuPromptConfig
    except ImportError:
        from core.prompt_compiler import H3PromptCompiler, ShinjutsuPromptConfig  # type: ignore

    bg_mode = "video"
    bg_tag = "<Picture 1>"
    outfit_tag = None
    outfit_desc = "the exact outfit shown in <Picture 1>"
    crew_tag = None

    m_scene = re.search(r"(?:background|environment|room|scene)[^<]*(<Picture\s+\d+>)", user_prompt, re.IGNORECASE)
    if m_scene:
        bg_mode = "ref_image"
        bg_tag = m_scene.group(1)

    m_outfit = re.search(r"(?:outfit|clothes|clothing|hoodie|dress|suit)[^<]*(<Picture\s+\d+>)", user_prompt, re.IGNORECASE)
    if m_outfit:
        outfit_tag = m_outfit.group(1)
        outfit_desc = f"the exact outfit and accessories shown in {outfit_tag}"

    m_crew = re.search(r"(?:crew|supporting|dancers|group)[^<]*(<Picture\s+\d+>)", user_prompt, re.IGNORECASE)
    if m_crew:
        crew_tag = m_crew.group(1)

    return H3PromptCompiler.compile(
        ShinjutsuPromptConfig(
            outfit_desc=outfit_desc,
            bg_mode=bg_mode,
            bg_image_tag=bg_tag,
            outfit_image_tag=outfit_tag,
            crew_image_tag=crew_tag,
            extra_prompt=user_prompt.strip(),
            duration_sec=duration_sec,
        )
    )


def compile_ui_workflow_to_api_prompt(
    wf_data: Dict[str, Any],
    user_prompt: str = "",
    slot1_file: str = "",
    slot2_file: str = "",
    width: Optional[int] = None,
    height: Optional[int] = None,
    frames: Optional[int] = None,
    fps: Optional[int] = None,
    steps: Optional[int] = None,
    control_strength: Optional[float] = None,
    selected_model_name: str = "",
    object_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Universal ComfyUI UI-Graph + Subgraph to API-Prompt Compiler:
      - Flattens `definitions.subgraphs` with full `origin_id == -10` outer link & widget forwarding!
      - Inlines frontend-only nodes (`Primitive*`, `ResolutionSelector`, `ComfySwitchNode`, `Reroute`)
      - Injects user prompt, image/video inputs, dimensions (`width`, `height`), and timing (`frames`, `fps`).
      - When `object_info` (ComfyUI `GET /object_info`) is supplied, widget names are read from the running
        ComfyUI instead of the built-in `NODE_WIDGET_SIGNATURES` table (which remains the offline fallback).
    """
    if not isinstance(wf_data, dict):
        return {}

    # Case A: Already a flat API Prompt dictionary (no "nodes" array)
    if "nodes" not in wf_data:
        api_copy = json.loads(json.dumps(wf_data))
        api_copy.pop("extra", None)

        # Uploaded files the graph already references are bound — never overwrite them (e.g. a depth
        # video in a second LoadVideo). Only fill the FIRST matching loader, mirroring the UI-graph path.
        def _references(fname: str) -> bool:
            return bool(fname) and any(
                isinstance(n, dict) and fname in (n.get("inputs") or {}).values() for n in api_copy.values()
            )

        slot1_needed = bool(slot1_file) and not _references(slot1_file)
        slot2_needed = bool(slot2_file) and not _references(slot2_file)
        slot2_is_image = bool(
            slot2_file and any(slot2_file.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"))
        )
        load_image_seen = 0

        # Text encoders wired into a `negative` input must keep their own (often empty) text.
        negative_ids = {
            str(v[0])
            for n in api_copy.values()
            if isinstance(n, dict)
            for k, v in (n.get("inputs") or {}).items()
            if k == "negative" and isinstance(v, list) and len(v) == 2
        }
        has_ltx_upsampler = any(
            isinstance(n, dict) and n.get("class_type") == "LTXVLatentUpsampler" for n in api_copy.values()
        )

        for _nid, nval in api_copy.items():
            if not isinstance(nval, dict):
                continue
            ctype = nval.get("class_type", "")
            inp = nval.get("inputs") or {}
            if user_prompt and str(_nid) not in negative_ids:
                if ctype in ("CLIPTextEncode", "CLIPTextEncodeFlux") and "text" in inp and "blurry" not in str(inp["text"]).lower():
                    inp["text"] = user_prompt
                elif ctype == "MiniMaxH3ReferenceToVideo" and "prompt" in inp:
                    inp["prompt"] = _compile_smart_h3_prompt(
                        user_prompt,
                        float(frames or inp.get("length") or 192) / 24.0,
                    )
                elif ctype in ("MiniMaxH3ImageToVideo", "Krea2EditGroundedEncode") and "prompt" in inp:
                    inp["prompt"] = user_prompt
                elif ctype == "TextEncodeQwenImageEdit" and "prompt" in inp:
                    inp["prompt"] = user_prompt
            if ctype == "LoadImage" and "image" in inp and not isinstance(inp["image"], list):
                load_image_seen += 1
                if load_image_seen == 1 and slot1_needed:
                    inp["image"] = slot1_file
                    slot1_needed = False
                elif slot2_needed and slot2_is_image:
                    inp["image"] = slot2_file
                    slot2_needed = False
            if not slot2_is_image and ctype in ("LoadVideo", "LoadAudio"):
                if "file" in inp:
                    if slot2_needed:
                        inp["file"] = slot2_file
                        slot2_needed = False
                    elif slot2_file and str(inp["file"]).startswith(("source_motion", "shinjutsu_motion")):
                        inp["file"] = slot2_file
                elif "audio" in inp and slot2_needed:
                    inp["audio"] = slot2_file
                    slot2_needed = False
            if width and height and ("width" in inp and "height" in inp):
                if ctype == "EmptyLTXVLatentVideo" and has_ltx_upsampler:
                    inp["width"] = max(64, (int(width) // 2) // 32 * 32)
                    inp["height"] = max(64, (int(height) // 2) // 32 * 32)
                else:
                    inp["width"] = width
                    inp["height"] = height
            if frames:
                if "length" in inp:
                    inp["length"] = frames
                elif ctype == "LTXVEmptyLatentAudio" and "frames_number" in inp:
                    inp["frames_number"] = frames
            if steps and steps > 0 and "steps" in inp and not isinstance(inp["steps"], list):
                inp["steps"] = steps
            if control_strength is not None and ctype == "MiniMaxH3FunControlNetApply" and "strength" in inp:
                inp["strength"] = control_strength
            if selected_model_name:
                if ctype == "UNETLoader" and "unet_name" in inp:
                    inp["unet_name"] = selected_model_name
                elif ctype == "CheckpointLoaderSimple" and "ckpt_name" in inp:
                    inp["ckpt_name"] = selected_model_name
                elif ctype in ("LTXVAudioVAELoader", "LTXAVTextEncoderLoader") and "ckpt_name" in inp:
                    inp["ckpt_name"] = selected_model_name
            if fps:
                if "fps" in inp:
                    inp["fps"] = fps
                elif "frame_rate" in inp:
                    inp["frame_rate"] = fps
        return api_copy

    # Case B: UI Graph format (`nodes`, `links`, optional `definitions.subgraphs`)
    subgraphs_by_id: Dict[str, Dict[str, Any]] = {}
    defs = wf_data.get("definitions")
    if isinstance(defs, dict) and isinstance(defs.get("subgraphs"), list):
        for sg in defs["subgraphs"]:
            if isinstance(sg, dict) and sg.get("id"):
                subgraphs_by_id[str(sg["id"])] = sg

    all_nodes: Dict[str, Dict[str, Any]] = {}
    link_sources: Dict[str, Tuple[str, int]] = {}
    sg_output_map: Dict[Tuple[str, int], Tuple[str, int]] = {}
    injected_inner_widgets: Dict[Tuple[str, int], Any] = {}

    # 1. Expand subgraphs with outer link & widget resolution
    for n in wf_data.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id"))
        ntype = str(n.get("type") or "")
        if ntype in subgraphs_by_id:
            sg = subgraphs_by_id[ntype]
            for s_node in sg.get("nodes") or []:
                if isinstance(s_node, dict):
                    sn_id = f"{nid}_{s_node.get('id')}"
                    all_nodes[sn_id] = dict(s_node)

            # Map outer widget values to subgraph inputs
            outer_wvals = list(n.get("widgets_values") or [])
            sg_slot_to_wval: Dict[int, Any] = {}
            w_idx = 0
            for slot_idx, sgi in enumerate(sg.get("inputs", [])):
                itype = str(sgi.get("type", "")).upper()
                is_widget = itype in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO") or isinstance(sgi.get("type"), list)
                if is_widget and w_idx < len(outer_wvals):
                    sg_slot_to_wval[slot_idx] = outer_wvals[w_idx]
                    w_idx += 1

            # Map outer input connections
            outer_inps = {inp.get("name"): inp.get("link") for inp in n.get("inputs", []) if inp.get("name")}

            for s_link in sg.get("links") or []:
                if not isinstance(s_link, dict):
                    continue
                lid = f"{nid}_L{s_link.get('id')}"
                orig_id = s_link.get("origin_id")
                orig_slot = int(s_link.get("origin_slot", 0))
                targ_id = s_link.get("target_id")
                targ_slot = int(s_link.get("target_slot", 0))

                if orig_id == -10:
                    # Virtual subgraph input
                    inp_def = sg.get("inputs", [])[orig_slot] if orig_slot < len(sg.get("inputs", [])) else {}
                    inp_name = inp_def.get("name")
                    outer_link = outer_inps.get(inp_name)
                    if outer_link is not None:
                        # Forward outer connection to inner target node
                        link_sources[lid] = ("__OUTER_LINK__", str(outer_link))
                    elif orig_slot in sg_slot_to_wval:
                        # Inject outer widget value into inner target node
                        injected_inner_widgets[(f"{nid}_{targ_id}", targ_slot)] = sg_slot_to_wval[orig_slot]
                    continue
                if targ_id == -20:
                    # Virtual subgraph output
                    sg_output_map[(nid, targ_slot)] = (f"{nid}_{orig_id}", orig_slot)
                else:
                    link_sources[lid] = (f"{nid}_{orig_id}", orig_slot)

            # Remap inner node input link IDs to prefixed `lid`
            for s_node in sg.get("nodes") or []:
                if not isinstance(s_node, dict):
                    continue
                sn_id = f"{nid}_{s_node.get('id')}"
                remapped_inputs = []
                for inp_entry in all_nodes[sn_id].get("inputs") or []:
                    icopy = dict(inp_entry)
                    if icopy.get("link") is not None:
                        pref = f"{nid}_L{icopy['link']}"
                        icopy["link"] = pref if pref in link_sources else None
                    remapped_inputs.append(icopy)
                all_nodes[sn_id]["inputs"] = remapped_inputs
        else:
            all_nodes[nid] = dict(n)

    # 2. Register outer links
    for lk in wf_data.get("links") or []:
        if isinstance(lk, list) and len(lk) >= 5:
            lid_str = str(lk[0])
            orig_nid = str(lk[1])
            orig_slot = int(lk[2])
            if (orig_nid, orig_slot) in sg_output_map:
                link_sources[lid_str] = sg_output_map[(orig_nid, orig_slot)]
            else:
                link_sources[lid_str] = (orig_nid, orig_slot)

    # Resolve __OUTER_LINK__ forwardings
    for lid, src in list(link_sources.items()):
        if isinstance(src, tuple) and src[0] == "__OUTER_LINK__":
            out_lid = src[1]
            if out_lid in link_sources:
                link_sources[lid] = link_sources[out_lid]

    # 3. Helper to resolve frontend-only nodes (Primitive, ResolutionSelector, Switch, Reroute)
    def resolve_source(src_nid: str, src_slot: int) -> Tuple[Optional[str], Optional[int], Optional[Any]]:
        """Returns (node_id, slot, inlined_literal_value)"""
        node_obj = all_nodes.get(str(src_nid))
        if not node_obj:
            return (src_nid, src_slot, None)
        ntype = str(node_obj.get("type") or "")

        # A. Reroute: Follow incoming link
        if ntype == "Reroute":
            r_inps = node_obj.get("inputs") or []
            if r_inps and r_inps[0].get("link") is not None:
                upstream_lid = str(r_inps[0]["link"])
                if upstream_lid in link_sources:
                    up_nid, up_slot = link_sources[upstream_lid]
                    return resolve_source(up_nid, up_slot)
            return (None, None, None)

        # B. Primitive nodes: Inline literal value directly
        if ntype in ("PrimitiveInt", "PrimitiveFloat", "PrimitiveBoolean", "PrimitiveStringMultiline", "PrimitiveNode"):
            wvals = node_obj.get("widgets_values") or []
            val = wvals[0] if wvals else None
            return (None, None, val)

        # C. ResolutionSelector: Compute aspect ratio width/height
        if ntype == "ResolutionSelector":
            wvals = node_obj.get("widgets_values") or []
            ar = str(wvals[0]) if wvals else "1:1 (Square)"
            computed_w, computed_h = ASPECT_RATIO_PRESETS.get(ar, (1024, 1024))
            final_w = width if width and width > 0 else computed_w
            final_h = height if height and height > 0 else computed_h
            return (None, None, final_w if src_slot == 0 else final_h)

        # D. ComfySwitchNode: Branch selection
        if ntype == "ComfySwitchNode":
            wvals = node_obj.get("widgets_values") or []
            switch_state = bool(wvals[0]) if wvals else False
            chosen_name = "on_true" if switch_state else "on_false"
            for inp_item in node_obj.get("inputs") or []:
                if inp_item.get("name") == chosen_name and inp_item.get("link") is not None:
                    branch_lid = str(inp_item["link"])
                    if branch_lid in link_sources:
                        b_nid, b_slot = link_sources[branch_lid]
                        return resolve_source(b_nid, b_slot)
            return (None, None, None)

        return (src_nid, src_slot, None)

    # 4. Convert active nodes to executable API Prompt format
    api_prompt: Dict[str, Any] = {}
    frontend_ignored = {
        "MarkdownNote", "Note", "Reroute", "PrimitiveNode", "PrimitiveInt",
        "PrimitiveFloat", "PrimitiveBoolean", "PrimitiveStringMultiline",
        "ResolutionSelector", "ComfySwitchNode", "PreviewAny", "MaskPreview", "PreviewImage"
    }

    first_load_image_injected = False
    second_load_image_injected = False
    first_load_video_injected = False
    is_slot2_image = bool(
        slot2_file and any(slot2_file.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"))
    )

    for nid, node in all_nodes.items():
        if int(node.get("mode", 0)) in (2, 4):  # Muted or Bypassed
            continue
        ntype = str(node.get("type") or "")
        if not ntype or ntype in frontend_ignored or ntype in subgraphs_by_id:
            continue

        inputs_dict: Dict[str, Any] = {}
        node_inputs = node.get("inputs") or []
        live_names = _widget_names_from_object_info(ntype, object_info)
        widget_names = list(live_names if live_names else NODE_WIDGET_SIGNATURES.get(ntype, []))
        w_vals = list(node.get("widgets_values") or [])

        # Map widget values to named inputs
        if widget_names and w_vals:
            for idx_w, w_name in enumerate(widget_names):
                if idx_w < len(w_vals) and w_name != "control_after_generate":
                    inputs_dict[w_name] = w_vals[idx_w]
        elif w_vals:
            w_idx = 0
            for inp_item in node_inputs:
                w_meta = inp_item.get("widget")
                if isinstance(w_meta, dict) and w_meta.get("name") and w_idx < len(w_vals):
                    inputs_dict[w_meta["name"]] = w_vals[w_idx]
                    w_idx += 1

        # Apply values injected from outer Subgraph node
        for slot_idx, inp_item in enumerate(node_inputs):
            key_tuple = (nid, slot_idx)
            if key_tuple in injected_inner_widgets:
                iname = inp_item.get("name")
                if iname:
                    inputs_dict[iname] = injected_inner_widgets[key_tuple]

        # Override with incoming links or inlined primitive values
        for inp_item in node_inputs:
            iname = inp_item.get("name")
            ilink = inp_item.get("link")
            if iname and ilink is not None and str(ilink) in link_sources:
                src_nid, src_slot = link_sources[str(ilink)]
                final_nid, final_slot, inlined_val = resolve_source(src_nid, src_slot)
                if inlined_val is not None:
                    inputs_dict[iname] = inlined_val
                elif final_nid is not None:
                    inputs_dict[iname] = [final_nid, final_slot]

        # Inject user prompt
        if user_prompt:
            if ntype in ("CLIPTextEncode", "CLIPTextEncodeFlux") and isinstance(inputs_dict.get("text"), str):
                txt_low = str(inputs_dict.get("text", "")).lower()
                if "negative" not in str(node.get("title", "")).lower() and "blurry" not in txt_low and "ugly" not in txt_low:
                    inputs_dict["text"] = user_prompt
            elif ntype == "MiniMaxH3ReferenceToVideo" and "prompt" in inputs_dict:
                inputs_dict["prompt"] = _compile_smart_h3_prompt(
                    user_prompt,
                    float(frames or inputs_dict.get("length") or 192) / 24.0,
                )
            elif ntype in ("MiniMaxH3ImageToVideo", "Krea2EditGroundedEncode") and "prompt" in inputs_dict:
                inputs_dict["prompt"] = user_prompt
            elif ntype == "TextEncodeQwenImageEdit" and "prompt" in inputs_dict:
                inputs_dict["prompt"] = user_prompt

        # Inject uploaded image & video/audio files
        if slot1_file and ntype == "LoadImage" and not first_load_image_injected:
            inputs_dict["image"] = slot1_file
            first_load_image_injected = True
        elif slot2_file and is_slot2_image and ntype == "LoadImage" and not second_load_image_injected:
            inputs_dict["image"] = slot2_file
            second_load_image_injected = True

        if slot2_file and not is_slot2_image and ntype in ("LoadVideo", "LoadAudio"):
            if "file" in inputs_dict:
                if not first_load_video_injected:
                    inputs_dict["file"] = slot2_file
                    first_load_video_injected = True
                elif str(inputs_dict["file"]).startswith(("source_motion", "shinjutsu_motion")):
                    inputs_dict["file"] = slot2_file
            elif "audio" in inputs_dict and not first_load_video_injected:
                inputs_dict["audio"] = slot2_file
                first_load_video_injected = True

        # Dynamic Dimensions & Timing Injection
        has_ltx_upsampler_b = any(
            isinstance(nd, dict) and nd.get("type") == "LTXVLatentUpsampler" for nd in all_nodes.values()
        )
        if width and height and width > 0 and height > 0:
            if ntype in ("EmptySD3LatentImage", "EmptyLatentImage", "EmptyFlux2LatentImage",
                         "EmptyLTXVLatentVideo", "LTXVImgToVideo", "EmptyHunyuanLatentVideo",
                         "WanImageToVideo", "WanAnimateToVideo", "MiniMaxH3ReferenceToVideo",
                         "MiniMaxH3ImageToVideo"):
                target_w = max(64, (int(width) // 2) // 32 * 32) if (ntype == "EmptyLTXVLatentVideo" and has_ltx_upsampler_b) else width
                target_h = max(64, (int(height) // 2) // 32 * 32) if (ntype == "EmptyLTXVLatentVideo" and has_ltx_upsampler_b) else height
                if "width" in inputs_dict and not isinstance(inputs_dict["width"], list):
                    inputs_dict["width"] = target_w
                if "height" in inputs_dict and not isinstance(inputs_dict["height"], list):
                    inputs_dict["height"] = target_h

        if frames and frames > 0:
            if ntype in ("EmptyLTXVLatentVideo", "LTXVImgToVideo", "EmptyHunyuanLatentVideo",
                         "WanImageToVideo", "WanAnimateToVideo", "MiniMaxH3ReferenceToVideo",
                         "MiniMaxH3ImageToVideo"):
                if "length" in inputs_dict and not isinstance(inputs_dict["length"], list):
                    inputs_dict["length"] = frames
            elif ntype == "LTXVEmptyLatentAudio" and "frames_number" in inputs_dict and not isinstance(inputs_dict["frames_number"], list):
                inputs_dict["frames_number"] = frames

        if fps and fps > 0:
            if ntype in ("CreateVideo", "SaveWEBM"):
                inputs_dict["fps"] = fps
            elif ntype in ("LTXVConditioning", "VHS_VideoCombine"):
                inputs_dict["frame_rate"] = fps

        if steps and steps > 0 and "steps" in inputs_dict and not isinstance(inputs_dict["steps"], list):
            inputs_dict["steps"] = steps

        if control_strength is not None and ntype == "MiniMaxH3FunControlNetApply" and "strength" in inputs_dict:
            inputs_dict["strength"] = control_strength

        if selected_model_name:
            if ntype == "UNETLoader" and "unet_name" in inputs_dict:
                inputs_dict["unet_name"] = selected_model_name
            elif ntype == "CheckpointLoaderSimple" and "ckpt_name" in inputs_dict:
                inputs_dict["ckpt_name"] = selected_model_name

        api_prompt[nid] = {
            "class_type": ntype,
            "inputs": inputs_dict,
        }

    return api_prompt


def inspect_and_prepare_template(
    workflow_data: Dict[str, Any],
    mode_hint: str = "images",
    comfy_url: str = "http://127.0.0.1:8188",
) -> Dict[str, Any]:
    """
    1. Extracts all required models (including inside `definitions.subgraphs`).
    2. Dynamically registers them in `DYNAMIC_TEMPLATE_MODELS` (so they appear in menus & downloader).
    3. Checks which models are already installed vs missing.
    4. Returns the missing models list + ready status so the UI can guide the user to 1-Click Install!
    """
    req_raw = extract_workflow_required_models(workflow_data)
    reg_entries = register_dynamic_models(req_raw, mode_hint=mode_hint)
    scan_res = scan_installed_models(comfy_url)
    installed_by_name = {
        Path(m["name"]).name: m for m in scan_res["models"] if m.get("installed")
    }

    detailed_models: List[Dict[str, Any]] = []
    missing_models: List[Dict[str, Any]] = []

    for entry in reg_entries:
        base_name = Path(entry["name"]).name
        is_inst = base_name in installed_by_name
        item_info = {
            "id": entry["id"],
            "name": entry["name"],
            "title": entry["title"],
            "folder": entry["folder"],
            "url": entry.get("url", ""),
            "installed": is_inst,
        }
        detailed_models.append(item_info)
        if not is_inst:
            missing_models.append(item_info)

    return {
        "ok": True,
        "all_ready": len(missing_models) == 0,
        "required_models": detailed_models,
        "missing_models": missing_models,
    }


def discover_all_templates(comfy_url: str = "http://127.0.0.1:8188") -> List[Dict[str, Any]]:
    templates: List[Dict[str, Any]] = []
    if WORKFLOWS_DIR.is_dir():
        for wf_path in sorted(WORKFLOWS_DIR.glob("*.json")):
            try:
                wf_json = json.loads(wf_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            req_models = extract_workflow_required_models(wf_json)
            templates.append(
                {
                    "id": f"local_{wf_path.stem}",
                    "title": wf_path.stem.replace("_", " ").title(),
                    "filename": wf_path.name,
                    "required_models": req_models,
                }
            )
    return templates


def start_model_download(model_id: str, target_root: Optional[Path] = None) -> Dict[str, Any]:
    """Starts an asynchronous resumable download for any registered or template-discovered model."""
    all_models = get_all_registered_models()
    item = next((m for m in all_models if m["id"] == model_id), None)
    if not item:
        return {"ok": False, "error": f"Unknown model_id: {model_id}"}

    root = resolve_models_root(target_root)
    rel = item.get("local_rel_path") or f"{item['folder']}/{Path(item['name']).name}"
    dest_path = root / rel
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.exists() and dest_path.stat().st_size > 1024 * 100:
        actual_mb = round(dest_path.stat().st_size / (1024 * 1024), 2)
        DOWNLOAD_STATE.update(model_id, status="completed", percent=100.0, downloaded_mb=actual_mb, total_mb=actual_mb)
        return {"ok": True, "status": "already_installed", "path": str(dest_path)}

    def _worker() -> None:
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".downloading")
        existing = tmp_path.stat().st_size if tmp_path.exists() else 0
        url = item.get("url") or ""
        if not url:
            DOWNLOAD_STATE.update(model_id, status="error", error="No download URL specified in template")
            return

        headers = {"User-Agent": "SHINJUTSU-Studio/1.0"}
        cfg_now = get_studio_config()
        hf_token = (str(cfg_now.get("hf_token") or "") or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
        civitai_token = (str(cfg_now.get("civitai_token") or "") or os.environ.get("CIVITAI_TOKEN") or "").strip()
        host_low = (urllib.parse.urlparse(url).hostname or "").lower()
        if hf_token and host_low in ("huggingface.co", "www.huggingface.co"):
            headers["Authorization"] = f"Bearer {hf_token}"  # gated repos (e.g. FLUX 3 Klein)
        elif civitai_token and "civitai.com" in host_low:
            headers["Authorization"] = f"Bearer {civitai_token}"
            if "token=" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}token={urllib.parse.quote(civitai_token)}"
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        DOWNLOAD_STATE.update(
            model_id,
            status="downloading",
            percent=1.0,
            downloaded_mb=round(existing / (1024 * 1024), 2),
            total_mb=item.get("size_mb", 1000.0),
            speed_mbps=0.0,
        )
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_len = int(resp.headers.get("Content-Length", 0))
                total_bytes = existing + content_len if content_len > 0 else int(item.get("size_mb", 1000.0) * 1024 * 1024)
                mode = "ab" if existing > 0 and resp.status == 206 else "wb"
                if mode == "wb":
                    existing = 0

                curr = existing
                t0 = time.time()
                with open(tmp_path, mode) as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        curr += len(chunk)
                        elapsed = max(0.001, time.time() - t0)
                        speed = ((curr - existing) / (1024 * 1024)) / elapsed
                        pct = min(99.9, round((curr / max(1, total_bytes)) * 100.0, 1))
                        DOWNLOAD_STATE.update(
                            model_id,
                            status="downloading",
                            percent=pct,
                            downloaded_mb=round(curr / (1024 * 1024), 2),
                            total_mb=round(total_bytes / (1024 * 1024), 2),
                            speed_mbps=round(speed, 2),
                        )

            tmp_path.replace(dest_path)
            final_mb = round(dest_path.stat().st_size / (1024 * 1024), 2)
            DOWNLOAD_STATE.update(
                model_id,
                status="completed",
                percent=100.0,
                downloaded_mb=final_mb,
                total_mb=final_mb,
                speed_mbps=0.0,
                path=str(dest_path),
            )
        except urllib.error.HTTPError as exc:
            msg = str(exc)
            if exc.code in (401, 403) and "huggingface.co" in url:
                repo_page = url.split("/resolve/")[0]
                msg = (
                    f"Gated model (HTTP {exc.code}): open {repo_page}, accept the license, "
                    f"then set the HF_TOKEN environment variable and restart."
                )
            DOWNLOAD_STATE.update(model_id, status="error", error=msg)
        except Exception as exc:
            DOWNLOAD_STATE.update(model_id, status="error", error=str(exc))

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "status": "started", "model_id": model_id, "target": str(dest_path)}


def delete_local_model(model_id: str) -> Dict[str, Any]:
    all_models = get_all_registered_models()
    item = next((m for m in all_models if m["id"] == model_id), None)
    if not item:
        return {"ok": False, "error": f"Unknown model_id: {model_id}"}

    active_root = resolve_models_root()
    candidates = [
        active_root / item.get("local_rel_path", ""),
        active_root / item["folder"] / Path(item["name"]).name,
        active_root / Path(item["name"]).name,
        LOCAL_MODELS_DIR / item.get("local_rel_path", ""),
        LOCAL_MODELS_DIR / item["folder"] / Path(item["name"]).name,
        LOCAL_MODELS_DIR / Path(item["name"]).name,
    ]
    for p in candidates:
        if p.is_file():
            freed_mb = round(p.stat().st_size / (1024 * 1024), 2)
            p.unlink()
            DOWNLOAD_STATE.update(model_id, status="idle", percent=0.0, downloaded_mb=0.0)
            return {"ok": True, "deleted": str(p), "freed_mb": freed_mb}

    return {"ok": False, "error": "Model file not found on local disk."}


def free_comfyui_vram(comfy_url: str = "http://127.0.0.1:8188") -> Dict[str, Any]:
    comfy_ok = False
    try:
        payload = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{comfy_url.rstrip('/')}/free",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            comfy_ok = resp.status == 200
    except Exception:
        comfy_ok = False

    try:
        import gc
        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    return {
        "ok": True,
        "comfy_freed": comfy_ok,
        "message": "Cleared GPU memory",
    }


def interrupt_comfyui_job(comfy_url: str = "http://127.0.0.1:8188") -> Dict[str, Any]:
    """Calls ComfyUI's native `POST /interrupt` to cancel the currently running generation."""
    try:
        req = urllib.request.Request(
            f"{comfy_url.rstrip('/')}/interrupt",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            return {"ok": resp.status == 200, "message": "Interrupted active render"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def clear_comfyui_queue(comfy_url: str = "http://127.0.0.1:8188") -> Dict[str, Any]:
    """Calls ComfyUI's native `POST /queue` with `{"clear": true}` to flush pending jobs."""
    try:
        req = urllib.request.Request(
            f"{comfy_url.rstrip('/')}/queue",
            data=json.dumps({"clear": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            return {"ok": resp.status == 200, "message": "Cleared pending render queue"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

