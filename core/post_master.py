# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Post-Processing, Pearson MAR Lip-Sync Alignment & Cut-Aware LAB Grading (`core/post_master.py`)

Implements the 3-stage post-render mastering pipeline:
  1. Pearson Correlation Mouth-Aspect-Ratio (MAR) Lip-Sync Lag Detector & Auto-Shift (±6 frames)
  2. Cut-Aware Reinhard/LAB Background Color Space Transfer (5-frame median window with scene-cut guard)
  3. Frame-Locked 24fps Conforming & Pristine Original Audio Restoration (`ffmpeg -crf 14 -tune grain`)
"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import List, Optional, Tuple
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass
class LipSyncReport:
    """Result of Pearson correlation lip-sync analysis between source and generated video."""
    best_lag_frames: int
    correlation: float
    applied_shift_frames: int
    status_note: str


def compute_mouth_aspect_ratio_series(landmarks_per_frame: List[Optional[np.ndarray]]) -> np.ndarray:
    """
    Computes normalized inner-lip opening ratio (MAR) for each frame using MediaPipe 478 indices:
      - Upper/Lower inner lip center: points 13 and 14
      - Forehead-to-chin vertical reference: points 10 and 152
    Returns an array of float32 with NaN where no face is detected.
    """
    series = np.full(len(landmarks_per_frame), np.nan, dtype=np.float32)
    for idx, pts in enumerate(landmarks_per_frame):
        if pts is None or len(pts) < 153:
            continue
        mouth_gap = float(np.linalg.norm(pts[14] - pts[13]))
        face_height = max(float(np.linalg.norm(pts[152] - pts[10])), 1e-5)
        series[idx] = mouth_gap / face_height
    return series


def detect_optimal_lip_sync_lag(
    source_mar: np.ndarray,
    generated_mar: np.ndarray,
    max_lag_frames: int = 6,
    min_correlation: float = 0.30,
) -> LipSyncReport:
    """
    Evaluates Pearson correlation across lags [-max_lag_frames .. +max_lag_frames].
    Positive lag means the generated video's mouth opens `lag` frames LATER than the source.
    If `correlation >= min_correlation` and `1 <= best_lag <= 3`, recommends shifting earlier.
    """
    n = min(len(source_mar), len(generated_mar))
    if n < 16:
        return LipSyncReport(0, 0.0, 0, "Clip too short for statistical MAR correlation.")

    s = source_mar[:n]
    g = generated_mar[:n]

    best_lag = 0
    best_corr = -1.0

    for lag in range(-max_lag_frames, max_lag_frames + 1):
        if lag < 0:
            s_slice = s[-lag:]
            g_slice = g[: len(s_slice)]
        elif lag > 0:
            s_slice = s[: n - lag]
            g_slice = g[lag:]
        else:
            s_slice = s
            g_slice = g

        valid = (~np.isnan(s_slice)) & (~np.isnan(g_slice))
        if int(np.sum(valid)) < 12:
            continue

        sv = s_slice[valid]
        gv = g_slice[valid]
        if np.std(sv) < 1e-6 or np.std(gv) < 1e-6:
            continue

        corr = float(np.corrcoef(sv, gv)[0, 1])
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    applied_shift = best_lag if (best_corr >= min_correlation and 1 <= best_lag <= 3) else 0
    note = (
        f"Auto-shifted {applied_shift} frame(s) earlier (r={best_corr:.3f})"
        if applied_shift > 0
        else f"No frame shift needed (best_lag={best_lag}, r={best_corr:.3f})"
    )
    return LipSyncReport(
        best_lag_frames=best_lag,
        correlation=max(best_corr, 0.0),
        applied_shift_frames=applied_shift,
        status_note=note,
    )


def apply_cut_aware_lab_grading(
    source_frames_rgb: List[np.ndarray],
    generated_frames_rgb: List[np.ndarray],
    subject_masks: List[np.ndarray],
    scene_cut_threshold: float = 12.0,
) -> List[np.ndarray]:
    """
    Matches the generated video's ambient color cast back to the source video's background
    in CIE LAB space while respecting hard scene cuts:
      - Erodes inverse background mask with a 25x25 kernel so character edges never pollute stats
      - Smooths background mean/std with a 5-frame median window ONLY across frames whose LAB delta < 12.0
      - Locks luminance scale `scale_L = 1.0` (preserving subject contrast) and clamps `scale_a, scale_b` to [0.7, 1.5]
    """
    if cv2 is None or not source_frames_rgb or not generated_frames_rgb:
        return generated_frames_rgb

    n = min(len(source_frames_rgb), len(generated_frames_rgb), len(subject_masks))
    kernel_25 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))

    src_means, src_stds = [], []
    gen_means, gen_stds = [], []

    for i in range(n):
        src_lab = cv2.cvtColor(source_frames_rgb[i], cv2.COLOR_RGB2LAB).astype(np.float32)
        gen_lab = cv2.cvtColor(generated_frames_rgb[i], cv2.COLOR_RGB2LAB).astype(np.float32)

        fg_u8 = (subject_masks[i] > 0.25).astype(np.uint8) * 255
        dilated_fg = cv2.dilate(fg_u8, kernel_25)
        bg_mask = dilated_fg == 0

        if int(np.sum(bg_mask)) < 256:
            bg_mask = np.ones(src_lab.shape[:2], dtype=bool)

        src_means.append(np.mean(src_lab[bg_mask], axis=0))
        src_stds.append(np.maximum(np.std(src_lab[bg_mask], axis=0), 1.0))
        gen_means.append(np.mean(gen_lab[bg_mask], axis=0))
        gen_stds.append(np.maximum(np.std(gen_lab[bg_mask], axis=0), 1.0))

    graded_frames: List[np.ndarray] = []
    for i in range(n):
        # Collect 5-frame neighborhood that does not cross a scene cut
        valid_neighbors = [i]
        for j in range(max(0, i - 2), min(n, i + 3)):
            if j != i and float(np.linalg.norm(src_means[j] - src_means[i])) < scene_cut_threshold:
                valid_neighbors.append(j)

        s_mean = np.median([src_means[k] for k in valid_neighbors], axis=0)
        s_std = np.median([src_stds[k] for k in valid_neighbors], axis=0)
        g_mean = np.median([gen_means[k] for k in valid_neighbors], axis=0)
        g_std = np.median([gen_stds[k] for k in valid_neighbors], axis=0)

        scale = np.clip(s_std / g_std, 0.70, 1.50)
        scale[0] = 1.0  # Lock L* luminance contrast scale to 1.0

        gen_lab = cv2.cvtColor(generated_frames_rgb[i], cv2.COLOR_RGB2LAB).astype(np.float32)
        out_lab = (gen_lab - g_mean) * scale + s_mean
        out_lab = np.clip(out_lab, 0.0, 255.0).astype(np.uint8)
        graded_frames.append(cv2.cvtColor(out_lab, cv2.COLOR_LAB2RGB))

    return graded_frames


def finalize_master_video(
    rendered_video: Path,
    original_audio_source: Path,
    output_mp4: Path,
    shift_frames_earlier: int = 0,
    fps: int = 24,
    crf: int = 14,
) -> Path:
    """
    Conforms the generated video to exact 24fps, applies optional lip-sync frame trim/pad,
    and muxes the untouched original audio track using `libx264 -crf 14 -tune grain`.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg binary not found in PATH.")

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf_filters = [f"fps={fps}"]
    if shift_frames_earlier > 0:
        trim_sec = shift_frames_earlier / float(fps)
        vf_filters.insert(0, f"trim=start={trim_sec:.4f},setpts=PTS-STARTPTS")
        vf_filters.append(f"tpad=stop={shift_frames_earlier}:stop_mode=clone")

    vf_chain = ",".join(vf_filters)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(rendered_video),
        "-i", str(original_audio_source),
        "-map", "0:v:0",
        "-map", "1:a:0?",
        "-vf", vf_chain,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "slow",
        "-tune", "grain",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_mp4
