# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Native ComfyUI Custom Nodes (`nodes.py`)

Provides 3 drop-in nodes under the `SHINJUTSU (神術)` category when placed inside `ComfyUI/custom_nodes/SHINJUTSU`:
  1. `ShinjutsuAutoWhiteBG`: Runs `#1 BiRefNet_lite (84.84 MB, MIT)` to segment the subject onto Studio White `(235, 235, 238)` (preserving all 540 reference tokens).
  2. `ShinjutsuSVDControlLoRALoader`: Reconstructs the 10-block ControlNet patch from our `33.34 MiB` `shinjutsu_h3_control_lora_v1_flash.safetensors` (`-99.73%` vs `12.92 GB`) and outputs its filename for `ModelPatchLoader`.
  3. `ShinjutsuPromptCompilerNode`: Compiles a 1-line instruction into the official 6-Section MiniMax H3 Ref2VA prompt and snaps duration to the `17n + 5 @ 24fps` grid.
"""

from pathlib import Path
import tempfile
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image

try:
    from .core.comfy_bridge import snap_to_h3_temporal_grid
    from .core.control_lora_codec import (
        CONTROL_LORA_FILENAME,
        RECONSTRUCTED_PATCH_FILENAME,
        ensure_shinjutsu_models,
        reconstruct_controlnet_from_33mb_lora,
    )
    from .core.prep_engine import clean_reference_image_background
    from .core.prompt_compiler import H3PromptCompiler, ShinjutsuPromptConfig
except ImportError:
    from core.comfy_bridge import snap_to_h3_temporal_grid  # type: ignore
    from core.control_lora_codec import (  # type: ignore
        CONTROL_LORA_FILENAME,
        RECONSTRUCTED_PATCH_FILENAME,
        ensure_shinjutsu_models,
        reconstruct_controlnet_from_33mb_lora,
    )
    from core.prep_engine import clean_reference_image_background  # type: ignore
    from core.prompt_compiler import H3PromptCompiler, ShinjutsuPromptConfig  # type: ignore

BASE_DIR = Path(__file__).resolve().parent


class ShinjutsuAutoWhiteBG:
    """Segments a character reference image onto Studio White (235, 235, 238) via BiRefNet_lite (84.84 MB)."""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "image": ("IMAGE",),
                "bg_r": ("INT", {"default": 235, "min": 0, "max": 255}),
                "bg_g": ("INT", {"default": 235, "min": 0, "max": 255}),
                "bg_b": ("INT", {"default": 238, "min": 0, "max": 255}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("clean_white_bg_image",)
    FUNCTION = "clean_bg"
    CATEGORY = "SHINJUTSU (神術)"

    def clean_bg(self, image: Any, bg_r: int = 235, bg_g: int = 235, bg_b: int = 238) -> Tuple[Any]:
        import torch

        out_tensors = []
        batch_np = image.detach().cpu().numpy()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_p = Path(tmpdir)
            for idx in range(batch_np.shape[0]):
                arr = np.clip(batch_np[idx] * 255.0, 0, 255).astype(np.uint8)
                in_file = tmp_p / f"in_{idx}.png"
                out_file = tmp_p / f"out_{idx}.png"
                Image.fromarray(arr).save(in_file)
                clean_reference_image_background(
                    in_file,
                    out_file,
                    neutral_rgb=(int(bg_r), int(bg_g), int(bg_b)),
                )
                clean_arr = np.asarray(Image.open(out_file).convert("RGB"), dtype=np.float32) / 255.0
                out_tensors.append(torch.from_numpy(clean_arr))

        stacked = torch.stack(out_tensors, dim=0).to(image.device)
        return (stacked,)


class ShinjutsuSVDControlLoRALoader:
    """
    Reconstructs the 10-block MiniMax H3 ControlNet patch from `shinjutsu_h3_control_lora_v1_flash.safetensors` (33.34 MiB)
    and base MiniMax H3 UNet weights, returning the ready-to-load `model_patch` filename.
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "base_unet_name": (
                    "STRING",
                    {"default": "minimax_h3_ref2va_pruned_int8_convrot.safetensors"},
                ),
                "control_lora_33mb": (
                    "STRING",
                    {"default": CONTROL_LORA_FILENAME},
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("model_patch_name",)
    FUNCTION = "prepare_patch"
    CATEGORY = "SHINJUTSU (神術)"

    def prepare_patch(self, base_unet_name: str, control_lora_33mb: str) -> Tuple[str]:
        try:
            import folder_paths

            unet_path = Path(folder_paths.get_full_path("diffusion_models", base_unet_name))
            patches_dir = Path(folder_paths.get_folder_paths("model_patches")[0])
        except Exception:
            unet_path = BASE_DIR / "models" / base_unet_name
            patches_dir = BASE_DIR / "models" / "model_patches"

        patches_dir.mkdir(parents=True, exist_ok=True)
        out_patch_name = RECONSTRUCTED_PATCH_FILENAME
        out_patch_path = patches_dir / out_patch_name

        if not out_patch_path.exists():
            lora_path = BASE_DIR / "models" / control_lora_33mb
            if not lora_path.exists():
                paths = ensure_shinjutsu_models(BASE_DIR / "models")
                lora_path = paths["control_lora_33mb"] if isinstance(paths, dict) else (Path(paths) / control_lora_33mb)
            if unet_path.exists() and lora_path.exists():
                reconstruct_controlnet_from_33mb_lora(
                    lora_33mb_path=str(lora_path),
                    base_h3_path=str(unet_path),
                    out_patch_path=str(out_patch_path),
                )

        return (out_patch_name,)


class ShinjutsuPromptCompilerNode:
    """Compiles a simple instruction into the 6-Section Official MiniMax H3 Ref2VA Prompt & 17n+5 frame count."""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "instruction": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "Replace the person in <Video 1> with the character in <Picture 1>.",
                    },
                ),
                "duration_sec": (
                    "FLOAT",
                    {"default": 13.0, "min": 2.0, "max": 15.08, "step": 0.1},
                ),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("compiled_h3_prompt", "snapped_frames")
    FUNCTION = "compile"
    CATEGORY = "SHINJUTSU (神術)"

    def compile(self, instruction: str, duration_sec: float) -> Tuple[str, int]:
        frames = snap_to_h3_temporal_grid(int(round(duration_sec * 24)), max_frames=362)
        cfg = ShinjutsuPromptConfig(
            character_desc="the target character in <Picture 1>, preserving their exact facial identity, hairstyle, skin tone, and full outfit",
            outfit_desc="the exact outfit, accessories, and gloves worn by the character in <Picture 1>",
            bg_mode="video",
            extra_prompt=instruction.strip(),
            duration_sec=frames / 24.0,
        )
        prompt = H3PromptCompiler.compile(cfg)
        return (prompt, frames)


NODE_CLASS_MAPPINGS = {
    "ShinjutsuAutoWhiteBG": ShinjutsuAutoWhiteBG,
    "ShinjutsuSVDControlLoRALoader": ShinjutsuSVDControlLoRALoader,
    "ShinjutsuPromptCompilerNode": ShinjutsuPromptCompilerNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ShinjutsuAutoWhiteBG": "SHINJUTSU Auto White-BG (BiRefNet_lite 84.8MB)",
    "ShinjutsuSVDControlLoRALoader": "SHINJUTSU 33.3MB SVD Control-LoRA Loader",
    "ShinjutsuPromptCompilerNode": "SHINJUTSU 6-Section H3 Prompt Compiler",
}
