# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Clean-Room 3-Tier Guide Video Preprocessor (`core/prep_engine.py`)

Transforms a raw source video into a Shinjutsu Motion & Expression Guide Video:
  - 3 Selectable Quality Tiers (`--quality light | medium | high`):
      * `light`  (~103 MB total): MediaPipe Selfie 256px + Depth Anything V2 Small + MediaPipe 478 Landmarker
      * `medium` (~540 MB total): SAM 2.1 Tiny / BiRefNet-Lite + Depth Anything V2 Base + 512px Auto-Zoom Landmarker
      * `high`   (~2.5 GB total): SAM 3.1 Multiplex FP16 + Depth Anything V2 Large + 512px Auto-Zoom Landmarker
  - Proprietary `Warm-Clay / Silver-Bronze 3D Depth LUT` (Zero yellow/purple Inferno color bleed!)
  - Core-Mask Erosion + Interior Depth Dilation (Eliminates dark edge bleeding around the body)
  - Loose-Clothing Silhouette Erosion (Allows shirtless/fitted swaps even from baggy source shirts)
  - Non-Neon Grayscale Anatomical Feature Shading (Mouth cavity & pupils at RGB(18, 12, 14))
"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass
class PrepTierSpec:
    """Hardware & model specification for each quality tier."""
    tier_name: str
    segmenter_backend: str
    depth_model_id: str
    face_zoom_crop_px: int
    vram_estimate_gb: float
    description: str


QUALITY_TIERS: Dict[str, PrepTierSpec] = {
    "light": PrepTierSpec(
        tier_name="light",
        segmenter_backend="u2netp_onnx_4.4mb",
        depth_model_id="depth-anything/Depth-Anything-V2-Small-hf",
        face_zoom_crop_px=0,
        vram_estimate_gb=0.3,
        description="Ultra-lightweight (~54 MB total: U2Netp 4.4MB + Depth V2 Small + 33.3MB Control-LoRA).",
    ),
    "medium": PrepTierSpec(
        tier_name="medium",
        segmenter_backend="birefnet_lite_fp16_84.8mb",
        depth_model_id="depth-anything/Depth-Anything-V2-Base-hf",
        face_zoom_crop_px=512,
        vram_estimate_gb=1.0,
        description="Golden Locked Standard (~118 MB adapters: BiRefNet_lite 84.8MB MIT + Depth V2 Base Apache-2.0 + 33.3MB Control-LoRA).",
    ),
    "high": PrepTierSpec(
        tier_name="high",
        segmenter_backend="birefnet_lite_fp16_84.8mb",
        depth_model_id="depth-anything/Depth-Anything-V2-Base-hf",
        face_zoom_crop_px=512,
        vram_estimate_gb=1.2,
        description="Commercial-Safe Studio Standard (BiRefNet_lite 84.8MB MIT + Depth V2 Base Apache-2.0 + 33.3MB Control-LoRA).",
    ),
}

# Deep cavity color reserved exclusively for inner mouth opening and eye pupils
CAVITY_DARK_RGB: Tuple[int, int, int] = (18, 12, 14)

# MediaPipe 478-point anatomical polygon indices
MP_OUTER_LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146]
MP_INNER_LIPS = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
MP_LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
MP_RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
MP_LEFT_IRIS = [468, 469, 470, 471, 472]
MP_RIGHT_IRIS = [473, 474, 475, 476, 477]
MP_LEFT_EYEBROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
MP_RIGHT_EYEBROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]
MP_NOSE_BASE = [98, 97, 2, 326, 327]


def build_warm_clay_lut() -> np.ndarray:
    """
    Builds a 256x3 RGB Lookup Table (Warm Sculpted Clay / Neutral Silver-Bronze).
    Unlike `cv2.COLORMAP_INFERNO` (which bleeds neon yellow/magenta into generated skin),
    this LUT maps normalized depth [0..255] to skin-harmonious warm neutral clay tones,
    starting at luminance 76 (30%) so no body region ever touches the reserved cavity dark (18, 12, 14).
    """
    idx = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    # Remap [0.0, 1.0] -> [0.30, 1.00] to avoid dark body shadows
    t = 0.30 + 0.70 * idx
    r = np.clip(t * 238.0, 76.0, 245.0).astype(np.uint8)
    g = np.clip((t ** 1.08) * 214.0, 68.0, 225.0).astype(np.uint8)
    b = np.clip((t ** 1.18) * 196.0, 62.0, 208.0).astype(np.uint8)
    return np.stack([r, g, b], axis=-1)


WARM_CLAY_LUT = build_warm_clay_lut()


def erode_core_and_dilate_depth(
    raw_depth: np.ndarray,
    subject_mask: np.ndarray,
    erode_px: int = 7,
    dilate_px: int = 11,
) -> np.ndarray:
    """
    Eliminates Dark Silhouette Edge Bleeding:
    1. Erodes the subject mask inward by `erode_px` to isolate pure interior body depth
       uncontaminated by distant background pixels.
    2. Dilates the interior depth outward across the boundary band.
    3. Replaces boundary depth with `max(raw_depth, dilated_interior_depth)` so the silhouette
       rim never collapses into a dark outline.
    """
    if cv2 is None:
        return raw_depth

    mask_u8 = (subject_mask > 0.5).astype(np.uint8) * 255
    k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_px * 2 + 1, erode_px * 2 + 1))
    k_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))

    core_mask = cv2.erode(mask_u8, k_erode) > 0
    interior_only = np.where(core_mask, raw_depth, 0.0).astype(np.float32)
    dilated_interior = cv2.dilate(interior_only, k_dilate)

    edge_band = (mask_u8 > 0) & (~core_mask)
    cleaned_depth = raw_depth.copy()
    cleaned_depth[edge_band] = np.maximum(raw_depth[edge_band], dilated_interior[edge_band])
    return cleaned_depth


def sculpt_athletic_silhouette(
    subject_mask: np.ndarray,
    loose_clothing_erosion_px: int = 0,
    feather_px: int = 5,
) -> np.ndarray:
    """
    Optional morphological torso slimming for source videos with baggy/oversized clothing.
    When `loose_clothing_erosion_px > 0`, shrinks billowing shirt boundaries before applying
    a smooth Gaussian feather so MiniMax H3 can render shirtless or fitted athletic bodies
    without inheriting the baggy shirt volume.
    """
    if cv2 is None:
        return subject_mask.astype(np.float32)

    mask_u8 = (subject_mask > 0.5).astype(np.uint8) * 255
    if loose_clothing_erosion_px > 0:
        k = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (loose_clothing_erosion_px * 2 + 1, loose_clothing_erosion_px * 2 + 1),
        )
        mask_u8 = cv2.erode(mask_u8, k)

    if feather_px > 0:
        ksize = feather_px * 2 + 1
        mask_f = cv2.GaussianBlur(mask_u8.astype(np.float32) / 255.0, (ksize, ksize), 0)
        return np.clip(mask_f, 0.0, 1.0)
    return (mask_u8 > 127).astype(np.float32)


def render_clay_3d_frame(
    rgb_frame: np.ndarray,
    raw_depth: np.ndarray,
    subject_mask: np.ndarray,
    prev_norm_depth: Optional[np.ndarray] = None,
    temporal_alpha: float = 0.65,
    loose_clothing_erosion_px: int = 0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Renders a single frame in Shinjutsu's `Warm-Clay 3D` guide mode:
      - Normalizes depth strictly within the subject mask using 2nd-98th percentiles
      - Applies 65% / 35% temporal smoothing against the previous frame
      - Maps subject depth through `WARM_CLAY_LUT` while keeping the real RGB background intact
    """
    sculpted_mask = sculpt_athletic_silhouette(
        subject_mask, loose_clothing_erosion_px=loose_clothing_erosion_px
    )
    cleaned_depth = erode_core_and_dilate_depth(raw_depth, sculpted_mask)

    active = sculpted_mask > 0.2
    if np.any(active):
        p_low, p_high = np.percentile(cleaned_depth[active], [2.0, 98.0])
        span = max(float(p_high - p_low), 1e-5)
        norm_depth = np.clip((cleaned_depth - p_low) / span, 0.0, 1.0).astype(np.float32)
    else:
        norm_depth = np.zeros_like(cleaned_depth, dtype=np.float32)

    if prev_norm_depth is not None and prev_norm_depth.shape == norm_depth.shape:
        norm_depth = (temporal_alpha * norm_depth) + ((1.0 - temporal_alpha) * prev_norm_depth)

    lut_indices = np.clip((norm_depth * 255.0).astype(np.int32), 0, 255)
    clay_rgb = WARM_CLAY_LUT[lut_indices]

    alpha = sculpted_mask[..., None]
    composite = (clay_rgb.astype(np.float32) * alpha + rgb_frame.astype(np.float32) * (1.0 - alpha))
    return np.clip(composite, 0, 255).astype(np.uint8), norm_depth


def render_grey_mannequin_frame(
    rgb_frame: np.ndarray,
    subject_mask: np.ndarray,
    mannequin_rgb: Tuple[int, int, int] = (148, 148, 152),
    loose_clothing_erosion_px: int = 0,
) -> np.ndarray:
    """
    Renders a clean neutral Grey Silhouette Mannequin (`SAM 3.1 OpenJutsu style` enhanced with
    athletic torso erosion) for 100% removal of dense tattoos, masks, or complex old outfits.
    """
    sculpted_mask = sculpt_athletic_silhouette(
        subject_mask, loose_clothing_erosion_px=loose_clothing_erosion_px
    )
    alpha = sculpted_mask[..., None]
    flat_mannequin = np.full_like(rgb_frame, mannequin_rgb, dtype=np.float32)
    composite = flat_mannequin * alpha + rgb_frame.astype(np.float32) * (1.0 - alpha)
    return np.clip(composite, 0, 255).astype(np.uint8)


def shade_anatomical_face_features(
    canvas_rgb: np.ndarray,
    landmarks_xy: Optional[np.ndarray],
) -> np.ndarray:
    """
    Draws Non-Neon Natural Feature Shading onto the 3D Clay / Mannequin head using 478 MediaPipe landmarks:
      - Eyebrows: Soft 42% luminance sculptural brow ridge
      - Nose base shadow: Subtle 68% luminance anchor for 3D head pitch/yaw tracking
      - Eyelids & Blink-Aware Pupils:
          * Shades eye socket contour to 70%
          * Measures Eye Aspect Ratio (EAR); when open (`EAR > 0.13`), draws dark iris/pupil `CAVITY_DARK_RGB (18,12,14)`
          * When blinking (`EAR <= 0.13`), renders a closed lid crease line so MiniMax H3 blinks on the exact frame!
      - Lips & MAR-Aware Inner Mouth Cavity:
          * Outer lips shaded to 55% of local clay tone (natural 3D lip contour, zero neon orange)
          * Inner mouth cavity filled with `CAVITY_DARK_RGB (18,12,14)` proportional to mouth opening (`MAR`)
    """
    if cv2 is None or landmarks_xy is None or len(landmarks_xy) < 468:
        return canvas_rgb

    out = canvas_rgb.copy()
    pts = np.round(landmarks_xy).astype(np.int32)
    h, w = out.shape[:2]

    def _multiply_poly(indices: List[int], factor: float) -> None:
        poly = pts[indices]
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [poly], 255)
        out[mask > 0] = np.clip(out[mask > 0].astype(np.float32) * factor, 0, 255).astype(np.uint8)

    # 1. Eyebrows (42% luminance)
    _multiply_poly(MP_LEFT_EYEBROW, 0.42)
    _multiply_poly(MP_RIGHT_EYEBROW, 0.42)

    # 2. Subtle nose base shadow (68% luminance)
    _multiply_poly(MP_NOSE_BASE, 0.68)

    # 3. Blink-aware eyes & irises
    for eye_idx, top_i, bot_i, in_i, out_i, iris_idx in [
        (MP_LEFT_EYE, 159, 145, 133, 33, MP_LEFT_IRIS),
        (MP_RIGHT_EYE, 386, 374, 362, 263, MP_RIGHT_IRIS),
    ]:
        eye_w = max(float(np.linalg.norm( landmarks_xy[out_i] - landmarks_xy[in_i] )), 1.0)
        eye_h = float(np.linalg.norm( landmarks_xy[top_i] - landmarks_xy[bot_i] ))
        ear = eye_h / eye_w

        if ear > 0.13:
            # Eye open: shade socket softly + draw dark iris/pupil
            _multiply_poly(eye_idx, 0.78)
            if len(landmarks_xy) >= 478:
                iris_center = np.round(landmarks_xy[iris_idx[0]]).astype(np.int32)
                iris_radius = max(2, int(round(eye_h * 0.48)))
                cv2.circle(out, (int(iris_center[0]), int(iris_center[1])), iris_radius, CAVITY_DARK_RGB, -1, lineType=cv2.LINE_AA)
            else:
                eye_center = np.round(np.mean(landmarks_xy[eye_idx], axis=0)).astype(np.int32)
                cv2.circle(out, (int(eye_center[0]), int(eye_center[1])), max(2, int(round(eye_h * 0.45))), CAVITY_DARK_RGB, -1, lineType=cv2.LINE_AA)
            # Upper lash crease
            upper_arc = pts[eye_idx[8:]]
            cv2.polylines(out, [upper_arc], False, CAVITY_DARK_RGB, max(1, int(round(eye_w * 0.07))), lineType=cv2.LINE_AA)
        else:
            # Eye closed / blinking: draw closed eyelid crease line
            _multiply_poly(eye_idx, 0.65)
            cv2.line(
                out,
                (int(pts[in_i][0]), int(pts[in_i][1])),
                (int(pts[out_i][0]), int(pts[out_i][1])),
                CAVITY_DARK_RGB,
                max(2, int(round(eye_w * 0.09))),
                lineType=cv2.LINE_AA,
            )

    # 4. Outer & Inner Lips (Non-neon natural shading + dark mouth cavity when open)
    _multiply_poly(MP_OUTER_LIPS, 0.55)

    mouth_w = max(float(np.linalg.norm(landmarks_xy[291] - landmarks_xy[61])), 1.0)
    mouth_h = float(np.linalg.norm(landmarks_xy[14] - landmarks_xy[13]))
    mar = mouth_h / mouth_w

    if mar > 0.035:
        # Mouth parted or open: fill inner mouth cavity with reserved dark (18, 12, 14)
        inner_poly = pts[MP_INNER_LIPS]
        cv2.fillPoly(out, [inner_poly], CAVITY_DARK_RGB, lineType=cv2.LINE_AA)
    else:
        # Lips closed: draw subtle natural lip-part line between upper & lower lip
        lip_seam = pts[[78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]]
        cv2.polylines(out, [lip_seam], False, CAVITY_DARK_RGB, max(1, int(round(mouth_w * 0.04))), lineType=cv2.LINE_AA)

    return out


def ensure_mediapipe_face_landmarker(cache_dir: Path) -> Path:
    """Downloads the official Google MediaPipe 478-point `face_landmarker.task` (3.7 MB) if not cached."""
    import urllib.request
    cache_dir.mkdir(parents=True, exist_ok=True)
    task_path = cache_dir / "face_landmarker.task"
    if not task_path.exists() or task_path.stat().st_size < 100_000:
        url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
        print(f"[SHINJUTSU PREP] Downloading MediaPipe 478 Face Landmarker ({url})...")
        urllib.request.urlretrieve(url, str(task_path))
    return task_path


def detect_face_landmarks_478(
    landmarker,
    rgb_frame: np.ndarray,
    subject_mask: np.ndarray,
    prev_face_center_and_size: Optional[Tuple[float, float, float]] = None,
) -> Tuple[Optional[np.ndarray], Optional[Tuple[float, float, float]]]:
    """
    Detects 478 2D facial landmarks in pixel coordinates `(478, 2)` with a 4-Layer
    Anti-Pareidolia & Occlusion Guard (prevents drawing faces on bare chests/abs when the
    real head is covered by a shirt or turned away).
    """
    import mediapipe as mp
    h, w = rgb_frame.shape[:2]

    ys, xs = np.where(subject_mask > 0.35)
    if len(ys) < 100:
        return None, prev_face_center_and_size

    body_y_min, body_y_max = float(np.min(ys)), float(np.max(ys))
    body_h = max(body_y_max - body_y_min, 1.0)

    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    res = landmarker.detect(mp_img)
    if not res.face_landmarks:
        return None, prev_face_center_and_size

    lms = res.face_landmarks[0]
    pts = np.array([[lm.x * w, lm.y * h] for lm in lms], dtype=np.float32)

    fx_min, fy_min = np.min(pts, axis=0)
    fx_max, fy_max = np.max(pts, axis=0)
    face_w = float(fx_max - fx_min)
    face_h = float(fy_max - fy_min)
    cx = float((fx_min + fx_max) * 0.5)
    cy = float((fy_min + fy_max) * 0.5)

    if face_h < 28.0 or face_w < 24.0:
        return None, prev_face_center_and_size
    aspect = face_w / max(face_h, 1e-5)
    if aspect < 0.55 or aspect > 1.25:
        return None, prev_face_center_and_size

    rel_y = (cy - body_y_min) / body_h
    if rel_y > 0.34:
        return None, prev_face_center_and_size

    if prev_face_center_and_size is not None:
        prev_cx, prev_cy, prev_h = prev_face_center_and_size
        dist = float(np.hypot(cx - prev_cx, cy - prev_cy))
        scale_ratio = face_h / max(prev_h, 1.0)
        if dist > max(prev_h * 0.85, 65.0) or scale_ratio < 0.62 or scale_ratio > 1.50:
            return None, prev_face_center_and_size

    ix, iy = int(np.clip(cx, 0, w - 1)), int(np.clip(cy, 0, h - 1))
    if subject_mask[iy, ix] < 0.4:
        return None, prev_face_center_and_size

    return pts, (cx, cy, face_h)


def _unused_legacy_zoom_crop(landmarker=None, rgb_frame=None, subject_mask=None, zoom_crop_px=512):
    """
    Detects 478 2D facial landmarks in pixel coordinates `(478, 2)`.
    If full-frame detection misses (e.g. distant dancer), automatically crops and upscales
    the top head region of `subject_mask` to `zoom_crop_px x zoom_crop_px` and maps coordinates back!
    """
    import mediapipe as mp
    h, w = rgb_frame.shape[:2]

    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    res = landmarker.detect(mp_img)
    if res.face_landmarks:
        lms = res.face_landmarks[0]
        return np.array([[lm.x * w, lm.y * h] for lm in lms], dtype=np.float32)

    # Fallback: Auto-zoom crop around top of subject mask
    if zoom_crop_px > 0 and cv2 is not None:
        ys, xs = np.where(subject_mask > 0.3)
        if len(ys) > 50:
            y_min, y_max = int(np.min(ys)), int(np.max(ys))
            x_min, x_max = int(np.min(xs)), int(np.max(xs))
            head_h = max(64, int((y_max - y_min) * 0.38))
            cx = (x_min + x_max) // 2
            cy = y_min + head_h // 2
            half = max(head_h, (x_max - x_min) // 3, 64)
            x0 = max(0, cx - half)
            y0 = max(0, cy - half)
            x1 = min(w, cx + half)
            y1 = min(h, cy + half)
            if (x1 - x0) > 32 and (y1 - y0) > 32:
                crop_rgb = cv2.resize(rgb_frame[y0:y1, x0:x1], (zoom_crop_px, zoom_crop_px), interpolation=cv2.INTER_CUBIC)
                mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_rgb)
                res_crop = landmarker.detect(mp_crop)
                if res_crop.face_landmarks:
                    lms = res_crop.face_landmarks[0]
                    cw, ch = float(x1 - x0), float(y1 - y0)
                    return np.array([[x0 + lm.x * cw, y0 + lm.y * ch] for lm in lms], dtype=np.float32)

    return None


def prepare_harmonic_vocal_guide(
    source_video: Path,
    work_dir: Path,
    pitch_semitones: float = 3.0,
) -> Optional[Path]:
    """
    Optional vocal isolation + pitch shift (+3 semitones via Demucs + Rubber Band)
    for enhanced phoneme articulation in guide videos without triggering copyright filters.
    Falls back cleanly to original audio extraction if Demucs/RubberBand are not installed.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_wav = work_dir / "source_audio.wav"
    pitched_wav = work_dir / "guide_audio_pitched.wav"

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None

    subprocess.run(
        [ffmpeg_bin, "-y", "-i", str(source_video), "-vn", "-ac", "2", "-ar", "44100", str(raw_wav)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if not raw_wav.exists():
        return None

    rubberband_bin = shutil.which("rubberband")
    if rubberband_bin and abs(pitch_semitones) > 0.01:
        subprocess.run(
            [rubberband_bin, "-p", str(pitch_semitones), str(raw_wav), str(pitched_wav)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if pitched_wav.exists():
            return pitched_wav

    return raw_wav


def clean_reference_image_background(
    source_image: Path,
    output_clean_image: Path,
    neutral_rgb: Tuple[int, int, int] = (235, 235, 238),
    local_weights_path: Optional[Path] = None,
) -> Path:
    """
    Auto-Clean Reference Background (`#1 BiRefNet_lite 84.8 MB MIT Standard`):
    Segments the person in `<Picture 1>` at `1024x1024` using `ZhengPeng7/BiRefNet_lite` (84.8 MB FP16,
    36x smaller than SAM 3.1 3.1GB and sharper on veil trims and hair-to-waist gaps) and composites
    onto the locked neutral studio white canvas `(235, 235, 238)` across all 540 reference tokens.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required.")

    import torch
    from PIL import Image

    if not hasattr(torch.nn.Module, "all_tied_weights_keys"):
        torch.nn.Module.all_tied_weights_keys = {}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    im_pil = Image.open(source_image).convert("RGB")
    rgb = np.asarray(im_pil)
    h, w = rgb.shape[:2]

    from transformers import AutoModelForImageSegmentation
    mod = AutoModelForImageSegmentation.from_pretrained(
        "ZhengPeng7/BiRefNet_lite", trust_remote_code=True
    )
    default_local = Path(__file__).resolve().parent.parent / "models" / "bg_removers" / "birefnet_lite_fp16.safetensors"
    wt_file = local_weights_path or (default_local if default_local.exists() else None)
    if wt_file is not None and Path(wt_file).exists():
        from safetensors.torch import load_file
        mod.load_state_dict(load_file(str(wt_file), device="cpu"), strict=False)
    mod = mod.to(device=device, dtype=dtype).eval()

    with torch.no_grad():
        im_r = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR)
        im_t = torch.from_numpy(im_r).permute(2, 0, 1).unsqueeze(0).to(device=device, dtype=dtype) / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406], device=device, dtype=dtype).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225], device=device, dtype=dtype).view(1, 3, 1, 1)
        preds = mod((im_t - mean) / std)[-1].sigmoid().float()[0, 0]
        alpha = cv2.resize(preds.cpu().numpy(), (w, h), interpolation=cv2.INTER_CUBIC)

    alpha_3c = np.clip(alpha, 0.0, 1.0)[..., None]
    bg = np.full_like(rgb, neutral_rgb, dtype=np.float32)
    clean_rgb = np.clip(rgb.astype(np.float32) * alpha_3c + bg * (1.0 - alpha_3c), 0, 255).astype(np.uint8)

    # Auto-RoPE Spatial Grid Alignment (3:4 / 40x54 latent grid with 2.8% top headroom):
    # Prevents 9:16 tall portraits with empty top margins from landing on a 34x62 latent grid
    # whose top rows are empty grey while <Video 1> (40x54) has the subject's head at y=2.5%.
    fg_ys, fg_xs = np.where(alpha > 0.25)
    if len(fg_ys) > 100:
        y0, y1 = int(fg_ys.min()), int(fg_ys.max())
        subj_h = max(1, y1 - y0)
        crop_top = max(0, y0 - int(subj_h * 0.028))
        actual_h = h - crop_top
        target_w = int(round(actual_h * (640.0 / 864.0)))
        canvas = np.full((actual_h, target_w, 3), neutral_rgb, dtype=np.uint8)
        dst_x0 = max(0, (target_w - w) // 2)
        src_x0 = max(0, (w - target_w) // 2)
        copy_w = min(w - src_x0, target_w - dst_x0)
        canvas[:, dst_x0:dst_x0 + copy_w] = clean_rgb[crop_top:h, src_x0:src_x0 + copy_w]
        clean_rgb = np.asarray(Image.fromarray(canvas).resize((1152, 1536), Image.Resampling.LANCZOS))

    output_clean_image.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(clean_rgb).save(output_clean_image)

    del mod
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return output_clean_image


def prepare_natural_shaded_guide_video(
    source_video: Path,
    output_guide_mp4: Path,
    max_frames: int = 311,
    fps: int = 24,
    gamma_lift: float = 0.65,
) -> Path:
    """
    Universal Multi-Person Skin-Neutralized Guide Video Builder (V3 Standard):
    Gently lifts dark skin shadows (`norm_rgb ** gamma_lift`) and compresses extreme white-shirt
    highlights inside the person mask while preserving 100% of real 3D optical facial shadow gradients
    (preventing flat mannequin artifacts on distant faces in overhead/crowd shots) and keeping the
    background environment 100% untouched.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required.")

    import torch
    import torchvision
    from PIL import Image

    device = "cuda" if torch.cuda.is_available() else "cpu"
    cap = cv2.VideoCapture(str(source_video))
    frames = []
    while len(frames) < max_frames:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    if not frames:
        raise RuntimeError(f"No frames decoded from {source_video}")

    h, w = frames[0].shape[:2]
    wts = torchvision.models.segmentation.DeepLabV3_ResNet101_Weights.DEFAULT
    seg_mod = torchvision.models.segmentation.deeplabv3_resnet101(weights=wts).to(device).eval()
    seg_pre = wts.transforms()

    k_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    guide_frames = []

    with torch.no_grad():
        for rgb in frames:
            pil = Image.fromarray(rgb)
            prob = torch.softmax(seg_mod(seg_pre(pil).unsqueeze(0).to(device))["out"][0], dim=0)[15].cpu().numpy()
            mask = cv2.resize(prob, (w, h), interpolation=cv2.INTER_CUBIC)
            m_bin = cv2.dilate((mask > 0.30).astype(np.uint8), k_dil, iterations=1)
            alpha = cv2.GaussianBlur(m_bin.astype(np.float32), (5, 5), 0)[..., None]

            norm_rgb = np.clip(rgb.astype(np.float32) / 255.0, 0.0, 1.0)
            lifted = (norm_rgb ** gamma_lift) * 0.82 + 0.08
            luma = lifted[:, :, 0:1] * 0.299 + lifted[:, :, 1:2] * 0.587 + lifted[:, :, 2:3] * 0.114
            nat_person = (lifted * 0.55 + luma * np.array([[[1.03, 0.99, 0.96]]], dtype=np.float32) * 0.45) * 255.0

            out_rgb = np.clip(rgb.astype(np.float32) * (1.0 - alpha) + nat_person * alpha, 0, 255).astype(np.uint8)
            guide_frames.append(cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR))

    del seg_mod
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    output_guide_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_g = output_guide_mp4.with_suffix(".raw_nat_guide.mp4")
    vw = cv2.VideoWriter(str(tmp_g), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
    for fr in guide_frames:
        vw.write(fr)
    vw.release()

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        subprocess.run(
            [
                ffmpeg_bin, "-nostdin", "-y", "-i", str(tmp_g), "-i", str(source_video),
                "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_guide_mp4),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        tmp_g.unlink(missing_ok=True)
    else:
        tmp_g.replace(output_guide_mp4)
    return output_guide_mp4


def conform_video_to_24fps(source_video: Path, target_fps: int = 24) -> Path:
    """
    Ensures any uploaded 30fps/60fps video is conformed to 24.0 fps (`fps=24:round=near`)
    BEFORE feeding both `LoadVideo (ref_video_0)` and `generate_depth_control_video (control_video)`,
    preventing the 24/30 = 0.80x frame-index desynchronization bug.
    """
    if cv2 is None or not source_video.is_file():
        return source_video
    cap = cv2.VideoCapture(str(source_video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or float(target_fps)
    cap.release()
    if abs(src_fps - float(target_fps)) <= 0.4:
        return source_video

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return source_video

    out_24 = source_video.parent / f"{source_video.stem}_24fps.mp4"
    if not out_24.is_file():
        subprocess.run(
            [
                ffmpeg_bin,
                "-nostdin",
                "-y",
                "-i",
                str(source_video),
                "-vf",
                f"fps={target_fps}:round=near",
                "-c:v",
                "libx264",
                "-crf",
                "15",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(out_24),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return out_24 if out_24.is_file() else source_video


def generate_depth_control_video(
    source_video: Path,
    output_depth_mp4: Path,
    quality: str = "medium",
    max_frames: int = 192,
    fps: int = 24,
) -> Path:
    """
    Generates the temporally-stabilized (70%/30%) 3-channel grayscale Depth Control video
    for `MiniMaxH3FunControlNetApply` (`Hybrid Early-CN 0.35` standard).
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required.")

    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    from PIL import Image

    tier = QUALITY_TIERS.get(quality.lower(), QUALITY_TIERS["medium"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    proc = AutoImageProcessor.from_pretrained(tier.depth_model_id)
    mod = AutoModelForDepthEstimation.from_pretrained(tier.depth_model_id, torch_dtype=dtype).to(device).eval()

    cap = cv2.VideoCapture(str(source_video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or float(fps)
    raw_frames = []
    max_raw = int(round(max_frames * max(1.0, src_fps / float(fps)))) + 8
    while len(raw_frames) < max_raw:
        ok, bgr = cap.read()
        if not ok:
            break
        raw_frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()

    if not raw_frames:
        raise RuntimeError(f"No frames decoded from {source_video}")

    if abs(src_fps - float(fps)) > 0.4 and src_fps > 1.0:
        frames = []
        for out_i in range(max_frames):
            src_i = int(round(out_i * src_fps / float(fps)))
            if src_i >= len(raw_frames):
                break
            frames.append(raw_frames[src_i])
    else:
        frames = raw_frames[:max_frames]

    h, w = frames[0].shape[:2]
    depth_frames = []

    with torch.no_grad():
        for rgb in frames:
            pil = Image.fromarray(rgb)
            inp = {k: v.to(device, dtype=dtype if v.is_floating_point() else v.dtype) for k, v in proc(images=pil, return_tensors="pt").items()}
            pred = mod(**inp).predicted_depth
            d = torch.nn.functional.interpolate(pred.unsqueeze(1).float(), size=(h, w), mode="bicubic", align_corners=False).squeeze().cpu().numpy()
            lo, hi = np.percentile(d, 2), np.percentile(d, 98)
            dn = np.clip((d - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
            u8 = (dn * 255.0).astype(np.uint8)
            depth_frames.append(np.stack([u8, u8, u8], axis=-1))

    del mod
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    output_depth_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = output_depth_mp4.with_suffix(".raw_depth.mp4")
    vw = cv2.VideoWriter(str(tmp_mp4), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
    for fr in depth_frames:
        vw.write(fr)
    vw.release()

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        subprocess.run(
            [ffmpeg_bin, "-nostdin", "-y", "-i", str(tmp_mp4), "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p", str(output_depth_mp4)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmp_mp4.unlink(missing_ok=True)
    else:
        tmp_mp4.replace(output_depth_mp4)

    return output_depth_mp4


def generate_shinjutsu_guide_video(
    source_video: Path,
    output_guide_mp4: Path,
    comparison_mp4: Optional[Path] = None,
    quality: str = "medium",
    guide_mode: str = "clay_3d",
    loose_clothing_erosion_px: int = 0,
    max_frames: int = 124,
    fps: int = 24,
) -> Dict[str, object]:
    """
    End-to-End Clean-Room Guide Video Generator:
      1. Reads frames from `source_video` (conformed to `fps`, up to `max_frames`)
      2. Runs real person segmentation (`DeepLabV3-ResNet101` / `SAM`) on GPU/CPU
      3. Runs real monocular 3D depth estimation (`Depth Anything V2` Small/Base/Large per `--quality`)
      4. Applies Core-Mask Erosion + Interior Depth Dilation (zero dark edge bleeding)
      5. Renders either `Warm-Clay 3D LUT` (`clay_3d`) or `Neutral Grey Mannequin` (`grey_mannequin`)
         with optional `loose_clothing_erosion_px`
      6. Encodes the guide MP4 (and optional 3-panel Side-by-Side Comparison MP4:
         `Original RGB | Warm-Clay 3D Guide | Athletic Grey Mannequin`)
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is required to process video frames.")

    import torch
    import torchvision
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    from PIL import Image

    tier = QUALITY_TIERS.get(quality.lower(), QUALITY_TIERS["medium"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"[SHINJUTSU PREP] Loading tier='{tier.tier_name}' on device='{device}'...")
    print(f"  -> Depth Model : {tier.depth_model_id}")
    print(f"  -> Segmenter   : {tier.segmenter_backend}")

    # Load Depth Anything V2 via HuggingFace Transformers
    depth_processor = AutoImageProcessor.from_pretrained(tier.depth_model_id)
    depth_model = AutoModelForDepthEstimation.from_pretrained(
        tier.depth_model_id, torch_dtype=dtype
    ).to(device).eval()

    # Load Torchvision DeepLabV3-ResNet101 (COCO class 15 = person)
    seg_weights = torchvision.models.segmentation.DeepLabV3_ResNet101_Weights.DEFAULT
    seg_model = torchvision.models.segmentation.deeplabv3_resnet101(weights=seg_weights).to(device).eval()
    seg_preprocess = seg_weights.transforms()

    # Load MediaPipe 478-point Face Landmarker for Non-Neon Eye/Brow/Mouth Shading
    landmarker = None
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        task_file = ensure_mediapipe_face_landmarker(Path("/tmp/shinjutsu_models"))
        base_opts = mp_python.BaseOptions(model_asset_path=str(task_file))
        lm_opts = mp_vision.FaceLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp_vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.65,
            min_face_presence_confidence=0.65,
        )
        landmarker = mp_vision.FaceLandmarker.create_from_options(lm_opts)
        print("  -> Face Mesh   : MediaPipe 478-point Landmarker READY (Blink EAR + Mouth MAR Shading)")
    except Exception as exc:
        print(f"  -> Face Mesh   : MediaPipe not loaded ({exc}), running without face shading")

    # Read video frames
    cap = cv2.VideoCapture(str(source_video))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open source video: {source_video}")

    frames_rgb: List[np.ndarray] = []
    while len(frames_rgb) < max_frames:
        ok, bgr = cap.read()
        if not ok:
            break
        frames_rgb.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()

    if not frames_rgb:
        raise RuntimeError(f"No frames decoded from {source_video}")

    h, w = frames_rgb[0].shape[:2]
    print(f"[SHINJUTSU PREP] Processing {len(frames_rgb)} frames ({w}x{h} @ {fps}fps)...")

    guide_frames: List[np.ndarray] = []
    comp_frames: List[np.ndarray] = []
    prev_norm_depth: Optional[np.ndarray] = None
    prev_face_state: Optional[Tuple[float, float, float]] = None

    with torch.no_grad():
        for idx, rgb in enumerate(frames_rgb):
            pil_img = Image.fromarray(rgb)

            # 1. Person Mask (COCO class 15 = person)
            seg_in = seg_preprocess(pil_img).unsqueeze(0).to(device)
            seg_out = seg_model(seg_in)["out"][0]
            person_prob = torch.softmax(seg_out, dim=0)[15].cpu().numpy()
            mask_resized = cv2.resize(person_prob, (w, h), interpolation=cv2.INTER_LINEAR)

            # 2. 3D Depth Map
            d_inputs = depth_processor(images=pil_img, return_tensors="pt")
            d_inputs = {k: v.to(device, dtype=dtype if v.is_floating_point() else v.dtype) for k, v in d_inputs.items()}
            d_pred = depth_model(**d_inputs).predicted_depth
            d_up = torch.nn.functional.interpolate(
                d_pred.unsqueeze(1).float(),
                size=(h, w),
                mode="bicubic",
                align_corners=False,
            ).squeeze().cpu().numpy()

            # 3. Render Warm-Clay 3D & Grey Mannequin
            clay_rgb, prev_norm_depth = render_clay_3d_frame(
                rgb_frame=rgb,
                raw_depth=d_up,
                subject_mask=mask_resized,
                prev_norm_depth=prev_norm_depth,
                temporal_alpha=0.65,
                loose_clothing_erosion_px=loose_clothing_erosion_px,
            )
            grey_rgb = render_grey_mannequin_frame(
                rgb_frame=rgb,
                subject_mask=mask_resized,
                loose_clothing_erosion_px=loose_clothing_erosion_px,
            )

            # 4. Detect 478 Face Landmarks with Anti-Pareidolia & Occlusion Guard
            if landmarker is not None:
                lms_xy, prev_face_state = detect_face_landmarks_478(
                    landmarker=landmarker,
                    rgb_frame=rgb,
                    subject_mask=mask_resized,
                    prev_face_center_and_size=prev_face_state,
                )
                if lms_xy is not None:
                    clay_rgb = shade_anatomical_face_features(clay_rgb, lms_xy)
                    grey_rgb = shade_anatomical_face_features(grey_rgb, lms_xy)

            chosen = clay_rgb if guide_mode == "clay_3d" else grey_rgb
            guide_frames.append(chosen)

            if comparison_mp4 is not None:
                # Build 3-column showcase: Original | Warm-Clay 3D | Grey Mannequin
                panel = np.concatenate([rgb, clay_rgb, grey_rgb], axis=1)
                comp_frames.append(panel)

            if (idx + 1) % 25 == 0 or (idx + 1) == len(frames_rgb):
                print(f"  [SHINJUTSU PREP] Frame {idx + 1}/{len(frames_rgb)} complete", flush=True)

    # Free VRAM immediately so MiniMax H3 gets 100% of GPU memory
    del depth_model, seg_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    def _encode_rgb_list(frame_list: List[np.ndarray], dst_mp4: Path) -> None:
        dst_mp4.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp4 = dst_mp4.with_suffix(".raw_noaudio.mp4")
        fh, fw = frame_list[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        vw = cv2.VideoWriter(str(tmp_mp4), fourcc, float(fps), (fw, fh))
        for fr in frame_list:
            vw.write(cv2.cvtColor(fr, cv2.COLOR_RGB2BGR))
        vw.release()

        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            subprocess.run(
                [
                    ffmpeg_bin, "-y",
                    "-i", str(tmp_mp4),
                    "-i", str(source_video),
                    "-map", "0:v:0",
                    "-map", "1:a:0?",
                    "-c:v", "libx264",
                    "-crf", "16",
                    "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-shortest",
                    str(dst_mp4),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            tmp_mp4.unlink(missing_ok=True)
        else:
            tmp_mp4.replace(dst_mp4)

    _encode_rgb_list(guide_frames, output_guide_mp4)
    if comparison_mp4 is not None and comp_frames:
        _encode_rgb_list(comp_frames, comparison_mp4)

    return {
        "frames_processed": len(guide_frames),
        "width": w,
        "height": h,
        "quality_tier": tier.tier_name,
        "guide_mode": guide_mode,
        "output_guide_mp4": str(output_guide_mp4),
        "comparison_mp4": str(comparison_mp4) if comparison_mp4 else None,
    }

