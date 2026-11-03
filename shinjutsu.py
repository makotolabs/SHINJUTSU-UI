#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — 33.34 MB SVD Control-LoRA Character, Outfit & Scene Replacement Engine for MiniMax H3
Main Command-Line Interface (`shinjutsu.py`)

Production-Locked Standard (`v1_flash`):
  - 100% Zero Base-UNet LoRA (`swap_lora_strength=0.0`, `photoreal_lora_strength=0.0`) — future-proof across H3 releases
  - 33.34 MB SVD Control-LoRA (`shinjutsu_h3_control_lora_v1_flash.safetensors`, `strength=0.68`, `start=0.0`, `end=0.50`)
    for 1:1 frame-accurate motion transfer from Frame 0 with zero grey skin cast and zero old-clothing edge bleed
  - Universal All-Video Official H3 6-Section Prompt (`<Subject 1> fully_preserved`, `<Subject 2> attribute_transfer`,
    `<Subject 3> fully_preserved`, zero negative words!)
  - Automatic Reference Background Cleaning via `BiRefNet_lite` (84.84 MB MIT) onto Studio White `(235, 235, 238)`
"""

import argparse
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")

from core.prompt_compiler import (
    H3PromptCompiler,
    LED_WALL_PALETTES,
    SMARTPHONE_IMPERFECTIONS,
    ShinjutsuPromptConfig,
)
from core.prep_engine import (
    QUALITY_TIERS,
    clean_reference_image_background,
    generate_depth_control_video,
    generate_shinjutsu_guide_video,
)
from core.comfy_bridge import (
    HARDWARE_PROFILES,
    build_shinjutsu_comfy_workflow,
    plan_relay_windows,
    snap_to_h3_temporal_grid,
)


def cmd_tiers(_args: argparse.Namespace) -> None:
    print("=" * 80)
    print("SHINJUTSU (神術) — 33.34 MB SVD CONTROL-LORA + BIREFNET_LITE 84.8 MB STANDARD")
    print("=" * 80)
    print("\n[1] Default Production Formula (Locked):")
    print("  * Base UNet LoRA    : 0.0 (100% Zero Swap/Turbo LoRA)")
    print("  * 33.34MB SVD CN    : strength=0.68-0.70, start_percent=0.0, end_percent=0.50-0.55 (10 Blocks [0..45])")
    print("  * Reference BG Clean: #1 BiRefNet_lite (84.8 MB MIT) onto Studio White (235, 235, 238)")
    print("  * Single-Pass Limit : Up to 362 frames (15.08s @ 24fps) in 1 Pass")

    print("\n[2] Preprocessing Quality Tiers (--quality):")
    for key, spec in QUALITY_TIERS.items():
        print(f"  * {key.upper():6s} | VRAM ~{spec.vram_estimate_gb:.1f} GB | {spec.depth_model_id}")
        print(f"           | {spec.description}")

    print("\n[3] MiniMax H3 Hardware Profiles (--hw-profile):")
    for key, hw in HARDWARE_PROFILES.items():
        print(f"  * {key:10s} | Max Single-Pass: {hw.max_single_pass_frames} frames (~{hw.max_single_pass_frames/24:.1f}s)")
        print(f"               | {hw.description}")


def cmd_compile_prompt(args: argparse.Namespace) -> None:
    cfg = ShinjutsuPromptConfig(
        character_desc=args.character,
        outfit_desc=args.outfit,
        bg_mode=args.bg_mode,
        scene_desc=args.scene,
        led_palette=args.led_palette,
        mouth_mode=args.mouth_mode,
        custom_mouth_desc=args.custom_mouth,
        extra_prompt=args.extra_prompt,
        imperfection_preset=args.imp,
        duration_sec=args.duration,
        dialogue_text=args.dialogue,
    )
    compiled = H3PromptCompiler.compile(cfg)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(compiled, encoding="utf-8")
        print(f"[SHINJUTSU] Saved 6-section Universal Official H3 prompt -> {out_path}")
    else:
        print(compiled)


def cmd_export_workflow(args: argparse.Namespace) -> None:
    hw = HARDWARE_PROFILES.get(args.hw_profile, HARDWARE_PROFILES["pro_98gb"])
    raw_frames = int(round(args.duration * 24))
    snapped_frames = snap_to_h3_temporal_grid(raw_frames, max_frames=hw.max_single_pass_frames)
    cfg = ShinjutsuPromptConfig(
        character_desc=args.character,
        outfit_desc=args.outfit,
        bg_mode=args.bg_mode,
        scene_desc=args.scene,
        led_palette=args.led_palette,
        mouth_mode=args.mouth_mode,
        custom_mouth_desc=args.custom_mouth,
        extra_prompt=args.extra_prompt,
        imperfection_preset=args.imp,
        duration_sec=snapped_frames / 24.0,
    )
    prompt_text = H3PromptCompiler.compile(cfg)
    wf = build_shinjutsu_comfy_workflow(
        prompt_text=prompt_text,
        character_image_name=args.ref_image,
        guide_video_name=args.guide_video,
        depth_control_video_name=args.depth_video or args.guide_video,
        use_fun_controlnet=not args.no_controlnet,
        cn_strength=args.cn_strength,
        cn_start_percent=0.0,
        cn_end_percent=args.cn_end,
        width=args.width,
        height=args.height,
        num_frames=snapped_frames,
        seed=args.seed,
        steps=args.steps,
        sampler_name=args.sampler,
        scheduler=args.scheduler,
        swap_lora_strength=0.0,
        photoreal_lora_strength=0.0,
        hardware_profile=args.hw_profile,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[SHINJUTSU] Exported Hybrid Early-CN {args.cn_end:.2f} Zero-LoRA workflow "
        f"({snapped_frames} frames @ 24fps, profile={args.hw_profile}) -> {out_path}"
    )


def cmd_plan_relay(args: argparse.Namespace) -> None:
    total_frames = int(round(args.duration * 24))
    hw = HARDWARE_PROFILES.get(args.hw_profile, HARDWARE_PROFILES["pro_98gb"])
    windows = plan_relay_windows(
        total_frames=total_frames,
        window_frames=hw.max_single_pass_frames,
        overlap_guide_frames=39,
    )
    print(f"[SHINJUTSU] Relay Plan for {args.duration:.2f}s ({total_frames} frames @ 24fps) on `{args.hw_profile}`:")
    for idx, (start_f, end_f, overlap_f) in enumerate(windows, start=1):
        seg_len = end_f - start_f
        print(
            f"  Pass {idx}: frames {start_f:4d} .. {end_f:4d} "
            f"(length={seg_len} [17n+5 grid], overlap_guide={overlap_f}f, "
            f"time={start_f/24:.2f}s - {end_f/24:.2f}s)"
        )


def cmd_prep(args: argparse.Namespace) -> None:
    if args.clean_ref_in and args.clean_ref_out:
        clean_reference_image_background(Path(args.clean_ref_in), Path(args.clean_ref_out))
        print(f"[SHINJUTSU PREP] Auto-cleaned reference background -> {args.clean_ref_out}")

    if args.depth_only:
        out_p = generate_depth_control_video(
            source_video=Path(args.video),
            output_depth_mp4=Path(args.out),
            quality=args.quality,
            max_frames=args.max_frames,
            fps=24,
        )
        print(json.dumps({"depth_control_mp4": str(out_p), "max_frames": args.max_frames}, indent=2))
        return

    res = generate_shinjutsu_guide_video(
        source_video=Path(args.video),
        output_guide_mp4=Path(args.out),
        comparison_mp4=Path(args.compare_out) if args.compare_out else None,
        quality=args.quality,
        guide_mode=args.guide_mode,
        loose_clothing_erosion_px=args.erode_clothes,
        max_frames=args.max_frames,
        fps=24,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_ui(args: argparse.Namespace) -> None:
    from app_ui import launch_studio_ui
    launch_studio_ui(host=args.host, port=args.port, share=args.share)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shinjutsu",
        description="SHINJUTSU (神術) — 100% Zero-LoRA Character & Scene Replacement Engine for MiniMax H3",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_tiers = sub.add_parser("tiers", help="Show production standard, quality tiers, and hardware profiles")
    p_tiers.set_defaults(func=cmd_tiers)

    p_comp = sub.add_parser("compile-prompt", help="Compile user options into the Official H3 6-Section Universal Prompt")
    p_comp.add_argument(
        "--character",
        default="the target person in <Picture 1>, featuring their exact facial structure, hairstyle, clear unobstructed eyes, fair natural skin tone, and body proportions",
    )
    p_comp.add_argument("--outfit", default="the exact outfit shown in <Picture 1>")
    p_comp.add_argument("--bg-mode", default="video", choices=["video", "ref_image", "custom"])
    p_comp.add_argument("--scene", default="", help="Custom background description when --bg-mode=custom")
    p_comp.add_argument("--led-palette", default="ice_cyan", choices=list(LED_WALL_PALETTES.keys()))
    p_comp.add_argument("--mouth-mode", default="follow_video", choices=["follow_video", "closed_smirk", "custom"])
    p_comp.add_argument("--custom-mouth", default="", help="Custom expression/mouth instruction when --mouth-mode=custom")
    p_comp.add_argument("--extra-prompt", default="", help="Optional extra action or detail instructions")
    p_comp.add_argument("--imp", default="imp1", choices=list(SMARTPHONE_IMPERFECTIONS.keys()))
    p_comp.add_argument("--duration", type=float, default=8.00)
    p_comp.add_argument("--dialogue", default=None)
    p_comp.add_argument("--out", default=None)
    p_comp.set_defaults(func=cmd_compile_prompt)

    p_wf = sub.add_parser("export-workflow", help="Export a ComfyUI API workflow JSON (Hybrid Early-CN 0.35 + Zero-LoRA)")
    p_wf.add_argument("--ref-image", default="girl_face1_clean_bg.png")
    p_wf.add_argument("--guide-video", default="dance_source.mp4")
    p_wf.add_argument("--depth-video", default=None, help="Precomputed depth video (defaults to guide-video)")
    p_wf.add_argument(
        "--character",
        default="the target person in <Picture 1>, featuring their exact facial structure, hairstyle, clear unobstructed eyes, fair natural skin tone, and body proportions",
    )
    p_wf.add_argument("--outfit", default="the exact outfit shown in <Picture 1>")
    p_wf.add_argument("--bg-mode", default="video", choices=["video", "ref_image", "custom"])
    p_wf.add_argument("--scene", default="")
    p_wf.add_argument("--led-palette", default="ice_cyan", choices=list(LED_WALL_PALETTES.keys()))
    p_wf.add_argument("--mouth-mode", default="follow_video", choices=["follow_video", "closed_smirk", "custom"])
    p_wf.add_argument("--custom-mouth", default="")
    p_wf.add_argument("--extra-prompt", default="")
    p_wf.add_argument("--imp", default="imp1", choices=list(SMARTPHONE_IMPERFECTIONS.keys()))
    p_wf.add_argument("--duration", type=float, default=8.00)
    p_wf.add_argument("--cn-strength", type=float, default=0.68, help="33.3MB SVD Control-LoRA strength (default 0.68)")
    p_wf.add_argument("--cn-end", type=float, default=0.50, help="33.3MB SVD Control-LoRA end_percent (default 0.50)")
    p_wf.add_argument("--no-controlnet", action="store_true")
    p_wf.add_argument("--width", type=int, default=576)
    p_wf.add_argument("--height", type=int, default=1024)
    p_wf.add_argument("--steps", type=int, default=20)
    p_wf.add_argument("--sampler", default="er_sde")
    p_wf.add_argument("--scheduler", default="beta")
    p_wf.add_argument("--seed", type=int, default=20272008)
    p_wf.add_argument("--hw-profile", default="pro_98gb", choices=list(HARDWARE_PROFILES.keys()))
    p_wf.add_argument("--out", default="workflows/shinjutsu_compiled_api.json")
    p_wf.set_defaults(func=cmd_export_workflow)

    p_relay = sub.add_parser("plan-relay", help="Plan 17n+5 temporal grid windows and 39-frame overlap relays")
    p_relay.add_argument("--duration", type=float, default=14.37)
    p_relay.add_argument("--hw-profile", default="pro_98gb", choices=list(HARDWARE_PROFILES.keys()))
    p_relay.set_defaults(func=cmd_plan_relay)

    p_prep = sub.add_parser("prep", help="Generate Depth Control video, Clean Reference BG, or 3D Guide video")
    p_prep.add_argument("--video", required=True, help="Input source video path")
    p_prep.add_argument("--out", default="outputs/shinjutsu_depth_control.mp4", help="Output video path")
    p_prep.add_argument("--depth-only", action="store_true", help="Generate 3-channel Depth Control video for FunControlNet 2.0")
    p_prep.add_argument("--clean-ref-in", default=None, help="Optional reference image to auto-clean background")
    p_prep.add_argument("--clean-ref-out", default=None, help="Output path for cleaned reference image")
    p_prep.add_argument("--compare-out", default=None)
    p_prep.add_argument("--quality", default="medium", choices=list(QUALITY_TIERS.keys()))
    p_prep.add_argument("--guide-mode", default="clay_3d", choices=["clay_3d", "grey_mannequin"])
    p_prep.add_argument("--erode-clothes", type=int, default=0)
    p_prep.add_argument("--max-frames", type=int, default=192)
    p_prep.set_defaults(func=cmd_prep)

    p_ui = sub.add_parser("ui", help="Launch the Shinjutsu Gradio Web Studio")
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=7865)
    p_ui.add_argument("--share", action="store_true")
    p_ui.set_defaults(func=cmd_ui)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
