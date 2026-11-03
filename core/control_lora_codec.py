# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — 33.34 MiB 10-Block SVD Control-LoRA Codec (`core/control_lora_codec.py`)

Compresses the 12,923.8 MB (12.04 GiB) `MiniMax-H3-Fun-Controlnet-Union-2.0` checkpoint down to a
33.34 MiB (`34,961,624 bytes`, 34.96 MB, 99.73% smaller) standalone `.safetensors` archive
(`shinjutsu_h3_control_lora_v1_flash.safetensors`) using rank-64 projection bridges and rank-4 residual deltas
across all 10 injection blocks with zero 32x32 patch-grid artifacts.

Mathematical Principle:
  1. Across all 10 ControlNet blocks (`control_blocks.0..9`), the internal weights
     (`adaln_proj.linear`, `attn.qkv_proj`, `attn.out_proj`, `mlp.fc1`, `mlp.fc2`) stay close to
     the base `MiniMax H3` DiT blocks (`blocks.0, 5, 10, 15, 20, 25, 30, 35, 40, 45`), with a relative
     difference of only 2.47%–3.32%.
  2. Naive block pruning (e.g., keeping only `control_blocks.0..1` at `[0, 5]` and dropping `2..9`)
     leaves an uncanceled `2x2` latent (`32x32` pixel) patch-boundary grid from `patchify_video(1,2,2)`.
  3. By retaining all 10 blocks (`[0, 5, 10, 15, 20, 25, 30, 35, 40, 45]`) and storing ONLY:
       - `control_proj_in` (`[5376, 196]` exact FP16 = 2.01 MiB)
       - `before_proj` & `after_proj` across all 10 blocks via Truncated SVD (`Rank-64` = 14.65 MiB)
       - The residual delta `ΔW = W_control - W_base` via Truncated SVD (`Rank-4` = 16.48 MiB)
     we achieve a 33.34 MiB portable file that reconstructs the full 10-block ControlNet on load
     from the user's existing `MiniMax H3` base model!
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Optional

try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
except ImportError:  # torch ships with ComfyUI; only the codec functions themselves need it
    torch = None  # type: ignore[assignment]
    safe_open = save_file = None  # type: ignore[assignment]

logger = logging.getLogger("SHINJUTSU_UI")

CONTROL_LORA_FILENAME = "shinjutsu_h3_control_lora_v1_flash.safetensors"
LEGACY_CONTROL_LORA_FILENAMES = ("shinjutsu_control_lora_29mb.safetensors",)
RECONSTRUCTED_PATCH_FILENAME = "shinjutsu_h3_control_patch_v1_flash.safetensors"
DEFAULT_HF_REPO_ID = "makotolabs/SHINJUTSU-H3-Control-LoRA"


INJECTION_BLOCKS = (0, 5, 10, 15, 20, 25, 30, 35, 40, 45)
DELTA_SUBKEYS = (
    "adaln_proj.linear",
    "attn.qkv_proj",
    "attn.out_proj",
    "mlp.fc1",
    "mlp.fc2",
)
TINY_1D_SUBKEYS = (
    "adaln_proj.linear.bias",
    "after_proj.bias",
    "norm1.weight",
    "norm2.weight",
    "attn.q_norm.weight",
    "attn.k_norm.weight",
)


def _dequantize_base_h3_weight(f_bs, block_idx: int, subkey: str, target_shape: tuple) -> torch.Tensor:
    """Dequantizes a base MiniMax H3 weight (`int8_convrot`, `w6a8_int8`, `fp8_scaled`, or BF16/FP16) to BF16."""
    w_key = f"blocks.{block_idx}.{subkey}.weight"
    s_key = f"blocks.{block_idx}.{subkey}.weight_scale"
    q_key = f"blocks.{block_idx}.{subkey}.comfy_quant"
    w_t = f_bs.get_tensor(w_key)
    bs_keys = set(f_bs.keys())
    if q_key not in bs_keys and s_key not in bs_keys:
        return w_t.to(torch.bfloat16)

    try:
        import comfy.quant_ops as qo
    except ImportError:
        repo_root = Path(__file__).resolve().parent.parent
        for cand in (repo_root / "runtime" / "ComfyUI", repo_root.parent.parent):
            if (cand / "comfy" / "quant_ops.py").is_file() and str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
        import comfy.quant_ops as qo

    cq_meta = json.loads(bytes(f_bs.get_tensor(q_key).cpu().numpy().tolist()).decode()) if q_key in bs_keys else {}
    fmt = cq_meta.pop("format", "int8_tensorwise")

    if fmt in ("w6a8_int8", "asym_w4a8_int8") or f"{w_key}_s_rel" in bs_keys:
        cq_meta.pop("convrot", None)
        s_rel = f_bs.get_tensor(f"{w_key}_s_rel")
        s_channel = f_bs.get_tensor(f"{w_key}_s_channel")
        corr = f_bs.get_tensor(f"{w_key}_correction") if f"{w_key}_correction" in bs_keys else None
        cb = f_bs.get_tensor(f"{w_key}_codebook") if f"{w_key}_codebook" in bs_keys else None
        params = qo.AsymW4A8Int8Layout.Params(
            scale=s_rel,
            s_channel=s_channel,
            correction=corr,
            codebook=cb,
            orig_dtype=torch.bfloat16,
            orig_shape=tuple(target_shape),
            **cq_meta,
        )
        return qo.AsymW4A8Int8Layout.dequantize(w_t, params)

    w_s = f_bs.get_tensor(s_key)
    algo = qo.QUANT_ALGOS.get(fmt, qo.QUANT_ALGOS["int8_tensorwise"])
    layout_cls = getattr(qo, algo["comfy_tensor_layout"], qo.TensorWiseINT8Layout)
    params = layout_cls.Params(
        scale=w_s,
        orig_dtype=torch.bfloat16,
        orig_shape=tuple(target_shape),
        **cq_meta,
    )
    return layout_cls.dequantize(w_t, params)


def _svd_lowrank_pair(mat_f32: torch.Tensor, rank: int):
    """Computes fast randomized Truncated SVD (`lora_up`, `lora_down`) in FP16."""
    q = min(rank + 8, min(mat_f32.shape))
    u, s, v = torch.svd_lowrank(mat_f32, q=q, niter=3)
    u = u[:, :rank]
    s = s[:rank]
    vh = v[:, :rank].T
    sq = torch.sqrt(s)
    lora_up = (u * sq.unsqueeze(0)).to(torch.float16).contiguous().cpu()
    lora_down = (vh * sq.unsqueeze(1)).to(torch.float16).contiguous().cpu()
    return lora_up, lora_down


def extract_shinjutsu_control_lora_33mb(
    full_cn_path: str,
    base_h3_path: str,
    out_lora_path: str,
    rank_bridge: int = 64,
    rank_delta: int = 4,
    device: str = "cuda",
) -> Path:
    """Extracts the 33.34 MB 10-Block SVD Control-LoRA from the 12.92 GB Fun-ControlNet 2.0 checkpoint."""
    f_cn = safe_open(str(full_cn_path), framework="pt", device=device)
    f_bs = safe_open(str(base_h3_path), framework="pt", device=device)

    lora_sd = {
        "control_proj_in.weight": f_cn.get_tensor("control_proj_in.weight").to(torch.float16).contiguous().cpu(),
        "control_proj_in.bias": f_cn.get_tensor("control_proj_in.bias").to(torch.float16).contiguous().cpu(),
    }

    for i, b_idx in enumerate(INJECTION_BLOCKS):
        pfx = f"control_blocks.{i}"
        for k1d in TINY_1D_SUBKEYS:
            lora_sd[f"{pfx}.{k1d}"] = f_cn.get_tensor(f"{pfx}.{k1d}").to(torch.float16).contiguous().cpu()

        if i == 0:
            lora_sd[f"{pfx}.before_proj.bias"] = f_cn.get_tensor(f"{pfx}.before_proj.bias").to(torch.float16).contiguous().cpu()
            up, dn = _svd_lowrank_pair(f_cn.get_tensor(f"{pfx}.before_proj.weight").float(), rank_bridge)
            lora_sd[f"{pfx}.before_proj.lora_up"] = up
            lora_sd[f"{pfx}.before_proj.lora_down"] = dn

        up, dn = _svd_lowrank_pair(f_cn.get_tensor(f"{pfx}.after_proj.weight").float(), rank_bridge)
        lora_sd[f"{pfx}.after_proj.lora_up"] = up
        lora_sd[f"{pfx}.after_proj.lora_down"] = dn

        for sub in DELTA_SUBKEYS:
            w_cn = f_cn.get_tensor(f"{pfx}.{sub}.weight").bfloat16()
            w_bs = _dequantize_base_h3_weight(f_bs, b_idx, sub, w_cn.shape)
            dw = (w_cn - w_bs).float()
            up, dn = _svd_lowrank_pair(dw, rank_delta)
            lora_sd[f"{pfx}.{sub}.lora_up"] = up
            lora_sd[f"{pfx}.{sub}.lora_down"] = dn

        if device == "cuda":
            torch.cuda.empty_cache()

    out_p = Path(out_lora_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    save_file(
        lora_sd,
        str(out_p),
        metadata={
            "format": "pt",
            "arch": "shinjutsu_control_lora_v1",
            "rank_bridge": str(rank_bridge),
            "rank_delta": str(rank_delta),
            "control_blocks_places": "[0, 5, 10, 15, 20, 25, 30, 35, 40, 45]",
        },
    )
    return out_p


def reconstruct_controlnet_from_33mb_lora(
    lora_33mb_path: str,
    base_h3_path: str,
    out_patch_path: str,
    device: str = "cuda",
    quantize_int8: bool = True,
) -> Path:
    """Reconstructs a ready-to-load 10-block ComfyUI ModelPatch from `W_base` + `CONTROL_LORA_FILENAME`."""
    f_lora = safe_open(str(lora_33mb_path), framework="pt", device=device)
    f_bs = safe_open(str(base_h3_path), framework="pt", device=device)

    qo_mod = None
    if quantize_int8 and device == "cuda":
        try:
            import comfy.quant_ops as qo_mod
        except ImportError:
            repo_root = Path(__file__).resolve().parent.parent
            for cand in (repo_root / "runtime" / "ComfyUI", repo_root.parent.parent):
                if (cand / "comfy" / "quant_ops.py").is_file() and str(cand) not in sys.path:
                    sys.path.insert(0, str(cand))
            try:
                import comfy.quant_ops as qo_mod
            except ImportError:
                qo_mod = None

    cq_bytes = torch.tensor(
        list(b'{"format": "int8_tensorwise", "convrot": true, "convrot_groupsize": 256}'),
        dtype=torch.uint8,
    )

    bs_keys = set(f_bs.keys())
    is_adaln_basis = (
        "adaln_t_table" in bs_keys
        or f_bs.get_tensor("blocks.0.adaln_proj.linear.weight").shape[-1] == 8
    )

    recon_sd = {
        "control_proj_in.weight": f_lora.get_tensor("control_proj_in.weight").to(torch.float32).contiguous().cpu(),
        "control_proj_in.bias": f_lora.get_tensor("control_proj_in.bias").to(torch.float32).contiguous().cpu(),
    }

    for i, b_idx in enumerate(INJECTION_BLOCKS):
        pfx = f"control_blocks.{i}"
        for k1d in TINY_1D_SUBKEYS:
            if k1d == "adaln_proj.linear.bias" and is_adaln_basis:
                recon_sd[f"{pfx}.{k1d}"] = (
                    f_bs.get_tensor(f"blocks.{b_idx}.adaln_proj.linear.bias").to(torch.float32).contiguous().cpu()
                )
            else:
                recon_sd[f"{pfx}.{k1d}"] = f_lora.get_tensor(f"{pfx}.{k1d}").to(torch.bfloat16).contiguous().cpu()

        if i == 0:
            recon_sd[f"{pfx}.before_proj.bias"] = f_lora.get_tensor(f"{pfx}.before_proj.bias").to(torch.bfloat16).contiguous().cpu()
            up = f_lora.get_tensor(f"{pfx}.before_proj.lora_up").float()
            dn = f_lora.get_tensor(f"{pfx}.before_proj.lora_down").float()
            recon_sd[f"{pfx}.before_proj.weight"] = (up @ dn).to(torch.bfloat16).contiguous().cpu()

        up = f_lora.get_tensor(f"{pfx}.after_proj.lora_up").float()
        dn = f_lora.get_tensor(f"{pfx}.after_proj.lora_down").float()
        recon_sd[f"{pfx}.after_proj.weight"] = (up @ dn).to(torch.bfloat16).contiguous().cpu()

        for sub in DELTA_SUBKEYS:
            if sub == "adaln_proj.linear" and is_adaln_basis:
                # Pruned adaln_basis checkpoints store [96768, 8] curve-basis projections in FP32/FP16
                recon_sd[f"{pfx}.{sub}.weight"] = (
                    f_bs.get_tensor(f"blocks.{b_idx}.{sub}.weight").to(torch.float32).contiguous().cpu()
                )
                continue
            up = f_lora.get_tensor(f"{pfx}.{sub}.lora_up").float()
            dn = f_lora.get_tensor(f"{pfx}.{sub}.lora_down").float()
            w_bs = _dequantize_base_h3_weight(f_bs, b_idx, sub, (up.shape[0], dn.shape[1]))
            w_merged = (w_bs.float() + (up @ dn)).to(torch.bfloat16)
            if qo_mod is not None and w_merged.is_cuda:
                try:
                    qdata, qparams = qo_mod.TensorWiseINT8Layout.quantize(
                        w_merged, is_weight=True, per_channel=True, convrot=True, convrot_groupsize=256
                    )
                    recon_sd[f"{pfx}.{sub}.weight"] = qdata.contiguous().cpu()
                    recon_sd[f"{pfx}.{sub}.weight_scale"] = qparams.scale.contiguous().cpu()
                    recon_sd[f"{pfx}.{sub}.comfy_quant"] = cq_bytes.clone()
                    continue
                except Exception:
                    pass
            recon_sd[f"{pfx}.{sub}.weight"] = w_merged.contiguous().cpu()

        if device == "cuda":
            torch.cuda.empty_cache()

    out_p = Path(out_patch_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "format": "pt",
        "control_blocks_places": "[0, 5, 10, 15, 20, 25, 30, 35, 40, 45]",
        "inpaint_masked_pixel_mode": "post_norm",
    }
    if is_adaln_basis:
        meta["minimax_h3_fun_controlnet"] = "adaln_basis"
    save_file(recon_sd, str(out_p), metadata=meta)
    return out_p


def _migrate_legacy_adapter_if_needed(target_dir: Path) -> Optional[Path]:
    """If `CONTROL_LORA_FILENAME` is missing in `target_dir` but a legacy file exists, renames it in place."""
    new_f = target_dir / CONTROL_LORA_FILENAME
    if new_f.is_file() and new_f.stat().st_size > 1_000_000:
        return new_f
    for leg_name in LEGACY_CONTROL_LORA_FILENAMES:
        leg_f = target_dir / leg_name
        if leg_f.is_file() and leg_f.stat().st_size > 1_000_000:
            try:
                os.replace(str(leg_f), str(new_f))
                logger.info("Migrated legacy adapter %s -> %s", leg_f, new_f)
                return new_f
            except Exception:
                return leg_f
    return None


def ensure_shinjutsu_models(
    models_dir: Optional[Path] = None,
    hf_repo_id: str = DEFAULT_HF_REPO_ID,
) -> Dict[str, Path]:
    """
    Ensures `CONTROL_LORA_FILENAME` (33.34 MiB) exists locally
    (bundled in `models/` or downloaded from Hugging Face), while `BiRefNet_lite`
    is pulled directly from the official public `ZhengPeng7/BiRefNet_lite` repo.
    """
    import urllib.request

    base_dir = Path(models_dir) if models_dir else (Path(__file__).resolve().parent.parent / "models")
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "bg_removers").mkdir(parents=True, exist_ok=True)

    _migrate_legacy_adapter_if_needed(base_dir)
    if (base_dir / "model_patches").is_dir():
        _migrate_legacy_adapter_if_needed(base_dir / "model_patches")

    lora_f = base_dir / CONTROL_LORA_FILENAME
    biref_f = base_dir / "bg_removers/birefnet_lite_fp16.safetensors"

    if not lora_f.exists() or lora_f.stat().st_size < 1_000_000:
        url = f"https://huggingface.co/{hf_repo_id}/resolve/main/{CONTROL_LORA_FILENAME}"
        try:
            print(f"[SHINJUTSU] Downloading {CONTROL_LORA_FILENAME} from {url} ...")
            urllib.request.urlretrieve(url, str(lora_f))
        except Exception as exc:
            print(f"[SHINJUTSU] Warning: Could not download Control-LoRA ({exc})")

    return {
        "control_lora_33mb": lora_f,
        "birefnet_lite": biref_f,
    }


def resolve_model_patches_dir(models_root: Optional[Path] = None) -> Path:
    """
    Returns the target model_patches directory used by both the reconstruction writer
    and the local loopback probe.
    Priority:
      1. Explicit models_root (if given)
      2. folder_paths.get_folder_paths("model_patches")[0] (if folder_paths importable)
      3. COMFYUI_MODELS_DIR environment variable / model_patches
      4. ComfyUI parent directory if installed inside custom_nodes
      5. repo_root / runtime / ComfyUI / models / model_patches (if exists)
      6. repo_root / models / model_patches
    """
    if models_root:
        mr = Path(models_root)
        return (mr / "model_patches") if (mr / "model_patches").is_dir() else mr

    try:
        import folder_paths  # type: ignore
        p_dirs = folder_paths.get_folder_paths("model_patches")
        if p_dirs:
            return Path(p_dirs[0])
    except Exception:
        pass

    env_dir = os.environ.get("COMFYUI_MODELS_DIR", "").strip()
    if env_dir:
        cand = Path(env_dir) / "model_patches" if (Path(env_dir) / "model_patches").is_dir() else Path(env_dir)
        if cand.is_dir():
            return cand

    repo_root = Path(__file__).resolve().parent.parent
    if repo_root.parent.name == "custom_nodes":
        cand = repo_root.parent.parent / "models" / "model_patches"
        if cand.parent.is_dir():
            return cand

    runtime_cand = repo_root / "runtime" / "ComfyUI" / "models" / "model_patches"
    if runtime_cand.parent.is_dir():
        return runtime_cand

    return repo_root / "models" / "model_patches"


def ensure_reconstructed_control_patch(
    api_prompt: Dict[str, Any],
    models_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Automatically reconstructs `RECONSTRUCTED_PATCH_FILENAME` inside
    `models/model_patches/` whenever an API graph references it and both the 33.34 MiB
    Control-LoRA and the base MiniMax H3 UNet are present on disk.
    """
    target_patch_name = RECONSTRUCTED_PATCH_FILENAME
    needs_patch = False
    base_unet_name = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"

    if not isinstance(api_prompt, dict):
        return None

    for node in api_prompt.values():
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type") or "")
        inps = node.get("inputs") or {}
        if ctype == "ModelPatchLoader" and inps.get("name") == target_patch_name:
            needs_patch = True
        elif ctype == "UNETLoader" and isinstance(inps.get("unet_name"), str) and inps["unet_name"]:
            base_unet_name = str(inps["unet_name"])

    if not needs_patch:
        return None

    repo_root = Path(__file__).resolve().parent.parent
    candidate_roots = []
    if models_root:
        candidate_roots.append(Path(models_root))
    env_dir = os.environ.get("COMFYUI_MODELS_DIR", "").strip()
    if env_dir:
        candidate_roots.append(Path(env_dir))
    # When installed inside `ComfyUI/custom_nodes/SHINJUTSU-UI`
    if repo_root.parent.name == "custom_nodes":
        candidate_roots.append(repo_root.parent.parent / "models")
    candidate_roots.append(repo_root / "models")

    patches_dir: Path = resolve_model_patches_dir(models_root)
    unet_path: Optional[Path] = None

    try:
        import folder_paths  # type: ignore
        u_full = folder_paths.get_full_path("diffusion_models", base_unet_name)
        if u_full:
            unet_path = Path(u_full)
    except Exception:
        pass

    unet_candidates = [
        base_unet_name,
        Path(base_unet_name).name,
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "minimax_h3_ref2va_pruned_w6a8.safetensors",
        "minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
        "MiniMaxH3/minimax_h3_ref2va_int8_convrot.safetensors",
        "minimax_h3_ref2va_int8_convrot.safetensors",
    ]

    for root in candidate_roots:
        if patches_dir is None and root.exists():
            patches_dir = root / "model_patches"
        if unet_path is None or not unet_path.is_file():
            for uc in unet_candidates:
                for p in (root / "diffusion_models" / uc, root / uc):
                    if p.is_file():
                        unet_path = p
                        break
                if unet_path and unet_path.is_file():
                    break

    patches_dir.mkdir(parents=True, exist_ok=True)
    out_patch_path = patches_dir / target_patch_name

    if out_patch_path.is_file() and out_patch_path.stat().st_size > 1_000_000:
        return out_patch_path

    if unet_path is None or not unet_path.is_file() or torch is None or safe_open is None:
        return None

    lora_name = CONTROL_LORA_FILENAME
    lora_path: Optional[Path] = None
    for root in candidate_roots:
        for d_cand in (root, root / "model_patches"):
            if d_cand.is_dir():
                _migrate_legacy_adapter_if_needed(d_cand)
        for lp in (root / lora_name, root / "model_patches" / lora_name):
            if lp.is_file() and lp.stat().st_size > 1_000_000:
                lora_path = lp
                break
        if lora_path:
            break

    if lora_path is None:
        paths = ensure_shinjutsu_models(repo_root / "models")
        cand = paths.get("control_lora_33mb")
        if cand and Path(cand).is_file():
            lora_path = Path(cand)

    if lora_path is None or not lora_path.is_file():
        return None

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return reconstruct_controlnet_from_33mb_lora(
        lora_33mb_path=str(lora_path),
        base_h3_path=str(unet_path),
        out_patch_path=str(out_patch_path),
        device=dev,
    )


