# -*- coding: utf-8 -*-
"""
SHINJUTSU (神術) — Official MiniMax H3 Universal All-Video Ref2VA Prompt Compiler (`core/prompt_compiler.py`)

Strictly follows the official MiniMax H3 Full-Reference (`Ref2VA`) specification:
  - `subject_definitions`:
      * `<Subject 1>` : Target person identity, hair, body proportions, and outfit from `<Picture 1>` (`fully_preserved`)
      * `<Subject 2>` : Complete physical performance, body turns, hand/arm actions, head motion, lip articulation,
                        expressions, eye gaze, and blinks of the source person in `<Video 1>` (`attribute_transfer` -> `<Subject 1> (S1)`)
      * `<Subject 3>` : Environment, spatial layout, and lighting from `<Video 1>`, `<Picture 1>`, or custom scene (`fully_preserved`)
      * `<Video 1>`   : Camera framing, camera movement, and temporal pacing structure (`fully_preserved`)
      * `<Audio 1>`   : Synchronized audio track (`fully_copy`)
  - `summary`: Starts with `[reference generation + audio reuse]`
  - `retention_analysis`: Uses only official H3 relationship markers (`fully_preserved`, `partially_preserved`,
                          `attribute_transfer`, `weak_reference`, `fully_copy`, `partially_copy`, `reference`)
  - `detailed_description`: Establishes style before `[Shot 1]` (no timestamp on `[Shot 1]`), enforces invariant mapping
                            `source person in <Video 1> → <Subject 2> → <Subject 1> (S1) → <Audio 1>`, and supports
                            user options (`bg_mode`, `mouth_mode`, `extra_prompt`).
"""

from dataclasses import dataclass
from typing import Dict, Optional


SMARTPHONE_IMPERFECTIONS: Dict[str, str] = {
    "imp1": (
        "The target video is in a natural live-action smartphone video style with authentic unretouched human skin texture, "
        "organic ambient light wrap across shoulders and facial contours, and realistic handheld motion cadence."
    ),
    "imp2": (
        "The target video is in an unedited live-action mobile video style with natural ambient exposure, "
        "authentic skin pore micro-texture, and subtle natural motion blur on fast-moving hands and hair."
    ),
    "imp3": (
        "The target video is in a front-facing smartphone camera style with crisp central focus on the subject, "
        "gentle optical falloff toward the background edges, and natural unpolished skin fidelity."
    ),
    "imp4": (
        "The target video is in a raw ungraded mobile video style with natural skin subsurface scattering, "
        "soft highlight roll-off on collarbones and shoulders, and cohesive live-action sensor texture."
    ),
}


LED_WALL_PALETTES: Dict[str, str] = {
    "magenta_pink": (
        "a clean minimalist smooth matte room wall illuminated by a vibrant magenta-pink side/rim LED glow, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "ice_cyan": (
        "a clean minimalist smooth matte room wall bathed in an ice-cyan and cool aqua side/rim LED gradient, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "sunset_coral": (
        "a clean minimalist smooth matte room wall glowing with a warm sunset-coral and amber-peach side/rim LED light, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "lavender_blue": (
        "a clean minimalist smooth matte room wall washed in a dreamy lavender-violet and electric-blue side/rim LED glow, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "rose_peach": (
        "a clean minimalist smooth matte room wall lit by a soft rose-pink and warm peach side/rim LED wash, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "mint_teal": (
        "a clean minimalist smooth matte room wall accented by a fresh mint-emerald and deep teal side/rim LED glow, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "cobalt_pink": (
        "a clean minimalist smooth matte room wall with dual-tone cobalt-blue and neon-pink side/rim LED edge lighting, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "honey_gold": (
        "a clean minimalist smooth matte room wall highlighted by a warm honey-gold and champagne side/rim LED glow, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "violet_orange": (
        "a clean minimalist smooth matte room wall with a rich ultraviolet and warm tangerine side/rim LED gradient, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
    "arctic_lilac": (
        "a clean minimalist smooth matte room wall illuminated by an arctic-blue and soft lilac side/rim LED wash, "
        "paired with a soft neutral-white front fill light keeping the subject's face bright and fair-skinned"
    ),
}


@dataclass
class ShinjutsuPromptConfig:
    """Universal All-Video Configuration for MiniMax H3 Ref2VA."""
    character_desc: str = (
        "the target person whose complete visible identity, facial structure, hairstyle, "
        "fair natural skin tone, and body proportions come from <Picture 1>"
    )
    outfit_desc: str = "the exact outfit shown in <Picture 1>"
    exclusions_desc: str = "the source person's facial identity, hair, eyeglasses, or outer garments from <Video 1>"
    bg_mode: str = "video"  # "video" (keep <Video 1> bg) | "ref_image" (keep <Picture 1> bg) | "custom"
    scene_desc: str = ""
    led_palette: Optional[str] = "ice_cyan"
    mouth_mode: str = "follow_video"  # "follow_video" | "closed_smirk" | "custom"
    custom_mouth_desc: str = ""
    extra_prompt: str = ""
    imperfection_preset: str = "imp1"
    guide_mode: str = "direct"  # "direct" | "clay_3d" | "grey_mannequin"
    preserve_original_bg: bool = True
    duration_sec: float = 8.0
    outfit_action_desc: str = ""
    action_description: str = ""
    expression_rule: str = ""
    dialogue_text: Optional[str] = None
    # Multi-Reference (`1 Video + up to 9 Images`) extensions (`ref-en.txt` standard):
    bg_image_tag: str = "<Picture 1>"       # e.g. "<Picture 2>" when a separate room/scene photo is attached
    outfit_image_tag: Optional[str] = None  # e.g. "<Picture 3>" when a standalone outfit photo is attached
    crew_image_tag: Optional[str] = None    # e.g. "<Picture 2>" when a supporting group/crew photo is attached
    crew_desc: str = ""


class H3PromptCompiler:
    """Compiles user options into the official 6-Section MiniMax H3 Ref2VA Universal Performance-Transfer prompt."""

    @classmethod
    def compile(cls, cfg: ShinjutsuPromptConfig) -> str:
        style_opening = SMARTPHONE_IMPERFECTIONS.get(
            cfg.imperfection_preset.lower(), SMARTPHONE_IMPERFECTIONS["imp1"]
        )

        # Resolve <Subject 3> (Environment & Lighting)
        effective_bg_mode = "video" if cfg.preserve_original_bg and cfg.bg_mode == "video" else cfg.bg_mode
        if effective_bg_mode == "video":
            subj3_def = (
                "<Subject 3> is the complete background environment, room layout, furniture, wall geometry, "
                "and ambient lighting from <Video 1>."
            )
            subj3_ret = (
                "<Subject 3> (appears in [Shot 1]): fully_preserved - Preserve the exact background environment, "
                "spatial layout, and room lighting from <Video 1> in every frame."
            )
        elif effective_bg_mode == "ref_image":
            # LOCKED BEST PRACTICE: Use `partially_preserved` when adapting a background reference photo
            # (`<Picture k>`) so MiniMax H3 re-projects the 3D room perspective to match `<Video 1>`'s camera angle
            # instead of pasting a flat 2D floor behind the subject!
            bg_tag = cfg.bg_image_tag or "<Picture 1>"
            scene_extra = f" ({cfg.scene_desc.strip()})" if cfg.scene_desc.strip() else ""
            subj3_def = (
                f"<Subject 3> is the background environment from {bg_tag}{scene_extra}, viewed from a 3D camera "
                f"perspective matching <Video 1>."
            )
            subj3_ret = (
                f"<Subject 3> (appears in [Shot 1]): partially_preserved - Re-project and adapt the environment "
                f"from {bg_tag} into the exact 3D camera angle, horizon height, and perspective of <Video 1>, "
                f"completely replacing the original background of <Video 1>."
            )
        else:
            custom_env = (
                cfg.scene_desc.strip()
                if cfg.scene_desc.strip()
                else LED_WALL_PALETTES.get((cfg.led_palette or "ice_cyan").lower(), LED_WALL_PALETTES["ice_cyan"])
            )
            subj3_def = f"<Subject 3> is the target environment featuring {custom_env}."
            subj3_ret = (
                f"<Subject 3> (appears in [Shot 1]): fully_preserved - Maintain {custom_env} consistently "
                "across every frame."
            )

        # Resolve Mouth & Facial Expression mode
        if cfg.mouth_mode == "closed_smirk":
            mouth_clause = (
                "a composed, charismatic closed-mouth corner smirk with lips gently closed and natural periodic eyelid blinks"
            )
        elif cfg.mouth_mode == "custom" and cfg.custom_mouth_desc.strip():
            mouth_clause = cfg.custom_mouth_desc.strip()
        else:
            mouth_clause = (
                "exact lip articulation, phoneme-driven mouth shapes, jaw movement, natural smiles, "
                "facial expressions, eye gaze shifts, and blink timing"
            )

        # Optional user extra instructions or interactive clothing action
        extra_clauses = []
        if cfg.outfit_action_desc.strip():
            extra_clauses.append(
                f"Preserve the exact hand-to-fabric interaction and garment motion ({cfg.outfit_action_desc.strip()}) from <Video 1>."
            )
        if cfg.extra_prompt.strip():
            extra_clauses.append(cfg.extra_prompt.strip())
        if cfg.dialogue_text and cfg.dialogue_text.strip():
            extra_clauses.append(
                f'While performing, <Subject 1> (S1) vocalizes synchronized to <Audio 1>: <d>[English] {cfg.dialogue_text.strip()}</d>'
            )
        extra_block = (" " + " ".join(extra_clauses)) if extra_clauses else ""

        sections = [
            "subject_definitions:",
            (
                f"<Subject 1> is {cfg.character_desc}, wearing {cfg.outfit_desc}. "
                f"<Subject 1>'s complete visible identity, face design, hair, skin tone, and body proportions "
                f"come from <Picture 1>. <Subject 1> is speaker (S1).\n"
                f"<Subject 2> is the complete physical performance of the source person in <Video 1>, including "
                f"exact full-body motion, posture changes, 3D torso rotations, side and back profile turns, "
                f"hip movements, arm and hand trajectories, head motion, {mouth_clause}, and timing. "
                f"<Subject 2> transfers exclusively to <Subject 1> (S1).\n"
                f"{subj3_def}\n"
                f"<Video 1> provides the target video's camera framing, camera movement, and temporal pacing structure.\n"
                f"<Audio 1> is the synchronized audio track of <Video 1> and is reused in the target video."
            ),
            "",
            "summary:",
            (
                "[reference generation + audio reuse] Generate <Subject 1> from <Picture 1> inside <Subject 3>, "
                "following the camera framing and temporal structure of <Video 1>. Transfer <Subject 2> exclusively "
                "to <Subject 1> (S1) while reusing <Audio 1> as the complete synchronized audio track."
            ),
            "",
            "retention_analysis:",
            (
                f"<Subject 1> (appears in [Shot 1]): fully_preserved - Preserve the target person's facial identity, "
                f"hairstyle, skin tone, body proportions, and outfit ({cfg.outfit_desc}) from <Picture 1>.\n"
                f"<Subject 2> (appears in [Shot 1]): attribute_transfer - Transfer the source person's complete "
                f"physical actions, 3D body turns, side and back rotations, arm and hand movements, head motion, "
                f"and {mouth_clause} from <Video 1> exclusively onto <Subject 1> (S1).\n"
                f"{subj3_ret}\n"
                f"<Video 1> (camera and pacing structure): fully_preserved - Preserve the original camera framing, "
                f"viewpoint, camera movement, and frame-by-frame timing structure throughout [Shot 1].\n"
                f"<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio track."
            ),
            "",
            "detailed_description:",
            (
                f"{style_opening}\n"
                f"[Shot 1] A vertical shot matching the exact framing, camera distance, and perspective of <Video 1> "
                f"places <Subject 1> (S1) inside <Subject 3>. Enforce a fixed performer mapping throughout the entire shot: "
                f"source person in <Video 1> → <Subject 2> → <Subject 1> (S1) → <Audio 1>. "
                f"<Subject 1> (S1) follows <Subject 2> frame-by-frame for all physical movements, posture shifts, "
                f"full-body turns, side and back profile rotations, arm and hand trajectories, head motion, eye gaze, "
                f"eyelid blinks, and {mouth_clause} synchronized to <Audio 1>.{extra_block} "
                f"Preserve <Subject 1>'s facial identity, hairstyle, body proportions, and outfit ({cfg.outfit_desc}) from <Picture 1> "
                f"(excluding {cfg.exclusions_desc}) and <Subject 3>'s background environment consistently across every frame."
            ),
            "",
            "overall_soundscape:",
            "The copied ambience, vocal, and physical sound layer from <Audio 1> continues throughout the target video.",
            "",
            "non_diegetic_music:",
            "<Audio 1> is directly reused as the complete synchronized soundtrack.",
        ]
        return "\n".join(sections)
