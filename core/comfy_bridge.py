# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — ComfyUI MiniMax H3 Workflow & Execution Bridge (`core/comfy_bridge.py`)

Production-locked to the proven **SHINJUTSU 33.34 MB 10-Block SVD Control-LoRA + BiRefNet_lite (84.8 MB) White-BG Architecture**:
  1. Zero-LoRA on base UNet (`swap_lora_strength=0.0`, `photoreal_lora_strength=0.0`).
  2. `shinjutsu_h3_control_lora_v1_flash.safetensors` (33.34 MB — 99.74% smaller than the 12.92 GB Fun-ControlNet 2.0,
     reconstructed on load via `core/control_lora_codec.py` across all 10 blocks `[0,5,10,15,20,25,30,35,40,45]`)
     active ONLY during the early pose-establishing phase (`strength=0.68–0.70`, `start_percent=0.0`,
     `end_percent=0.50–0.55`, no grey inpaint mask!) so frames 0..N lock 1:1 to the source video with zero
     white sticker outline and zero 32x32 patch grid, while steps 12..20 run pure unpruned `MiniMax H3 Ref2VA`!
  3. Dual Audio Beat-Lock (`ref_video_audios.ref_video_audio_0` + `MiniMaxH3AddGuide(frame_idx=0)`)
  4. Strict `17n + 5 @ 24fps` Temporal Grid snapping (Single-Pass up to 362 frames = 15.08s) & 39-Frame Seamless Relay Planner
"""

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Tuple
import urllib.request


@dataclass
class HardwareProfile:
    """Model checkpoint mapping for different VRAM tiers."""
    profile_id: str
    unet_name: str
    text_encoder_name: str
    video_vae_name: str
    audio_vae_name: str
    fun_controlnet_name: str
    max_single_pass_frames: int
    description: str


HARDWARE_PROFILES: Dict[str, HardwareProfile] = {
    "pro_98gb": HardwareProfile(
        profile_id="pro_98gb",
        unet_name="MiniMaxH3/minimax_h3_ref2va_int8_convrot.safetensors",
        text_encoder_name="qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
        video_vae_name="minimax_h3_video_vae_fp16.safetensors",
        audio_vae_name="minimax_h3_audio_vae_fp32.safetensors",
        fun_controlnet_name="minimax_h3_fun_controlnet_union_2.0_unpruned_comfy.safetensors",
        max_single_pass_frames=362,
        description="Unpruned 31.7GB INT8 UNet + Unpruned Fun-ControlNet-2.0 + 25.8GB INT8 Qwen3-VL + FP16 Video VAE (Single-Pass up to 362 frames / 15.08s on G4/A100/H100).",
    ),
    "home_24gb": HardwareProfile(
        profile_id="home_24gb",
        unet_name="minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        text_encoder_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        video_vae_name="minimax_h3_video_vae_int8_convrot.safetensors",
        audio_vae_name="minimax_h3_audio_vae_fp32.safetensors",
        fun_controlnet_name="minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors",
        max_single_pass_frames=124,
        description="Pruned INT8 UNet + Pruned Fun-ControlNet-2.0 + NVFP4 Qwen3-VL + INT8 Video VAE (RTX 3090/4090/5090 24GB+).",
    ),
}


def snap_to_h3_temporal_grid(target_frames: int, max_frames: int = 362) -> int:
    """
    MiniMax H3 operates on a strict `17n + 5` temporal frame grid at 24fps
    (up to 362 frames = 17*21 + 5 = 15.083s in a single pass).
    """
    clamped = max(22, min(target_frames, max_frames))
    n = round((clamped - 5) / 17.0)
    snapped = 17 * max(1, n) + 5
    if snapped > max_frames:
        snapped -= 17
    return snapped


def plan_relay_windows(
    total_frames: int,
    window_frames: int = 362,
    overlap_guide_frames: int = 39,
) -> List[Tuple[int, int, int]]:
    """
    Unlimited-Duration Window Planner:
      - If `total_frames <= 362` (<= 15.08s @ 24fps): runs in 1 SINGLE PASS (zero splitting!).
      - If `total_frames > 362` (> 15.08s, e.g. 30s, 60s, 180s): chains seamless windows
        anchored by `overlap_guide_frames` (39 frames = 1.625s) via `MiniMaxH3AddGuide(frame_idx=0)`.
    """
    w_len = snap_to_h3_temporal_grid(window_frames, max_frames=362)
    if total_frames <= w_len:
        return [(0, snap_to_h3_temporal_grid(total_frames, max_frames=w_len), 0)]

    windows: List[Tuple[int, int, int]] = [(0, w_len, 0)]
    cursor = w_len - overlap_guide_frames

    while cursor < total_frames:
        rem = total_frames - cursor
        seg_len = snap_to_h3_temporal_grid(min(w_len, max(56, rem)), max_frames=w_len)
        end_f = cursor + seg_len
        windows.append((cursor, end_f, overlap_guide_frames))
        if end_f >= total_frames:
            break
        cursor = end_f - overlap_guide_frames

    return windows


def build_shinjutsu_comfy_workflow(
    prompt_text: str,
    character_image_name: str,
    guide_video_name: str,
    depth_control_video_name: Optional[str] = None,
    additional_reference_images: Optional[List[str]] = None,
    use_fun_controlnet: bool = True,
    cn_strength: float = 0.68,
    cn_start_percent: float = 0.0,
    cn_end_percent: float = 0.50,
    width: int = 576,
    height: int = 1024,
    num_frames: int = 192,
    seed: int = 20272008,
    steps: int = 20,
    sampler_name: str = "er_sde",
    scheduler: str = "beta",
    swap_lora_strength: float = 0.0,
    photoreal_lora_strength: float = 0.0,
    hardware_profile: str = "pro_98gb",
    overlap_guide_video_name: Optional[str] = None,
    filename_prefix: str = "SHINJUTSU_H3/shinjutsu_frame",
) -> Dict[str, Any]:
    """
    Generates the complete ComfyUI API JSON graph for SHINJUTSU's Golden Standard:
      - 100% Zero-LoRA by default (`swap_lora_strength=0.0`, `photoreal_lora_strength=0.0`)
      - Hybrid Early-Stage `MiniMaxH3FunControlNetApply` (`strength=0.55`, `end_percent=0.35`, no grey mask)
      - Dual Audio Beat-Lock (`ref_video_audio_0` + `MiniMaxH3AddGuide(frame_idx=0)`)
    """
    hw = HARDWARE_PROFILES.get(hardware_profile, HARDWARE_PROFILES["pro_98gb"])
    valid_frames = snap_to_h3_temporal_grid(num_frames, max_frames=hw.max_single_pass_frames)

    workflow: Dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": hw.unet_name, "weight_dtype": "default"},
        },
        "12": {
            "class_type": "MiniMaxH3SigmaShift",
            "inputs": {"model": ["1", 0], "shift_video": 12.0, "shift_audio": 3.0},
        },
        "85": {
            "class_type": "ModelAttentionBackend",
            "inputs": {"model": ["12", 0], "attention": "comfy kitchen attention"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": hw.text_encoder_name, "type": "minimax", "device": "default"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": hw.video_vae_name},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": hw.audio_vae_name},
        },
        "200": {
            "class_type": "LoadImage",
            "inputs": {"image": character_image_name},
        },
        "201": {
            "class_type": "ImageScaleToMaxDimension",
            "inputs": {"image": ["200", 0], "upscale_method": "lanczos", "largest_size": 1024},
        },
        "300": {
            "class_type": "LoadVideo",
            "inputs": {"file": guide_video_name},
        },
        "301": {
            "class_type": "GetVideoComponents",
            "inputs": {"video": ["300", 0]},
        },
        "106": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "audio_vae": ["4", 0],
                "prompt": prompt_text,
                "width": width,
                "height": height,
                "length": valid_frames,
                "ref_image_size": "match",
                "ref_images.ref_image_0": ["201", 0],
                "ref_videos.ref_video_0": ["301", 0],
                "ref_video_audios.ref_video_audio_0": ["301", 1],
            },
        },
        "108": {
            "class_type": "MiniMaxH3AddGuide",
            "inputs": {
                "positive": ["106", 0],
                "latent": ["106", 1],
                "audio_vae": ["4", 0],
                "audio": ["301", 1],
                "frame_idx": 0,
            },
        },
    }

    all_ref_imgs = [character_image_name] + list(additional_reference_images or [])
    all_ref_imgs = all_ref_imgs[:9]  # MiniMax H3 supports up to 9 reference images (<Picture 1>..<Picture 9>)
    for idx_img, img_name in enumerate(all_ref_imgs):
        if idx_img == 0:
            continue
        load_id = str(210 + idx_img * 2)
        scale_id = str(211 + idx_img * 2)
        workflow[load_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": img_name},
        }
        workflow[scale_id] = {
            "class_type": "ImageScaleToMaxDimension",
            "inputs": {"image": [load_id, 0], "upscale_method": "lanczos", "largest_size": 1024},
        }
        workflow["106"]["inputs"][f"ref_images.ref_image_{idx_img}"] = [scale_id, 0]

    active_model_ref = ["85", 0]

    # Optional LoRAs (disabled by default in SHINJUTSU Zero-LoRA standard)
    if swap_lora_strength > 0.0:
        workflow["500"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": active_model_ref,
                "lora_name": "h3/h3_character_swap_v1.5.safetensors",
                "strength_model": swap_lora_strength,
            },
        }
        active_model_ref = ["500", 0]

    if photoreal_lora_strength > 0.0:
        workflow["501"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": active_model_ref,
                "lora_name": "h3/h3_photoreal_ph0t0r34l_1024-step00003990.safetensors",
                "strength_model": photoreal_lora_strength,
            },
        }
        active_model_ref = ["501", 0]

    # Hybrid Early-Stage Fun-ControlNet-Union-2.0 (default: active 0.0 -> 0.35 @ strength 0.55)
    if use_fun_controlnet and cn_strength > 0.0:
        ctrl_vid = depth_control_video_name or guide_video_name
        workflow["173"] = {
            "class_type": "ModelPatchLoader",
            "inputs": {"name": hw.fun_controlnet_name},
        }
        workflow["174"] = {
            "class_type": "LoadVideo",
            "inputs": {"file": ctrl_vid},
        }
        workflow["175"] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": ["174", 0]},
        }
        workflow["172"] = {
            "class_type": "MiniMaxH3FunControlNetApply",
            "inputs": {
                "model": active_model_ref,
                "model_patch": ["173", 0],
                "vae": ["3", 0],
                "strength": cn_strength,
                "start_percent": cn_start_percent,
                "end_percent": cn_end_percent,
                "control_video": ["175", 0],
            },
        }
        active_model_ref = ["172", 0]

    workflow.update(
        {
            "6": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler_name}},
            "48": {
                "class_type": "BasicScheduler",
                "inputs": {
                    "model": active_model_ref,
                    "scheduler": scheduler,
                    "steps": steps,
                    "denoise": 1.0,
                },
            },
            "49": {
                "class_type": "BasicGuider",
                "inputs": {
                    "model": active_model_ref,
                    "conditioning": ["108", 0],
                },
            },
            "47": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["6", 0],
                    "guider": ["49", 0],
                    "sampler": ["9", 0],
                    "sigmas": ["48", 0],
                    "latent_image": ["106", 1],
                },
            },
            "45": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["47", 0], "vae": ["3", 0]},
            },
            "80": {
                "class_type": "SaveImage",
                "inputs": {"images": ["45", 0], "filename_prefix": filename_prefix},
            },
        }
    )

    if overlap_guide_video_name:
        workflow["302"] = {
            "class_type": "LoadVideo",
            "inputs": {"file": overlap_guide_video_name},
        }
        workflow["303"] = {
            "class_type": "GetVideoComponents",
            "inputs": {"video": ["302", 0]},
        }
        workflow["108"]["inputs"]["vae"] = ["3", 0]
        workflow["108"]["inputs"]["image"] = ["303", 0]

    return workflow


def submit_to_comfyui(
    workflow: Dict[str, Any],
    server_url: str = "http://127.0.0.1:8188",
    client_id: Optional[str] = None,
) -> str:
    """Submits a compiled workflow graph to a running ComfyUI endpoint and returns `prompt_id`."""
    body_dict: Dict[str, Any] = {"prompt": workflow}
    if client_id:
        body_dict["client_id"] = client_id
    payload = json.dumps(body_dict).encode("utf-8")
    req = urllib.request.Request(
        f"{server_url.rstrip('/')}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("prompt_id", ""))
