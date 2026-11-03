# -*- coding: utf-8 -*-
"""FLUX 3 Image Klein graphs (Images + Soul ID) — the FLUX 3 bonus-track workflows."""
import json

from conftest import ROOT
from core.comfy_client import validate_api_prompt
from core.model_manager import compile_ui_workflow_to_api_prompt

SOUL_WF = ROOT / "workflows" / "03_soul_id_flux3_klein.json"


def _soul():
    return json.loads(SOUL_WF.read_text(encoding="utf-8"))


def test_bundled_soul_id_workflow_uses_flux3_klein_core_nodes(object_info):
    wf = _soul()
    classes = {n["class_type"] for n in wf.values()}
    assert "ReferenceMultiLatent" in classes and "EmptyFlux2LatentImage" in classes
    assert wf["1"]["inputs"]["unet_name"].startswith("flux3-image-klein")
    report = validate_api_prompt(wf, object_info)
    assert report["ok"], report["errors"]
    assert report["partner_nodes"] == []


def test_dynamic_v3_sub_inputs_are_not_type_checked_as_their_parent(object_info):
    # "images.image0" (IMAGE) lives under an Autogrow parent; it must not be compared to COMFY_AUTOGROW_V3
    report = validate_api_prompt(_soul(), object_info)
    assert not any("images.image0" in e for e in report["errors"])


def test_soul_id_injection_keeps_negative_prompt_empty_and_binds_face():
    out = compile_ui_workflow_to_api_prompt(_soul(), user_prompt="the person in <ref_image_0> as an astronaut", slot1_file="me.png")
    assert out["4"]["inputs"]["text"] == "the person in <ref_image_0> as an astronaut"
    assert out["5"]["inputs"]["text"] == ""  # wired into ReferenceMultiLatent.negative -> untouched
    assert out["11"]["inputs"]["image"] == "me.png"


def test_missing_flux3_weights_are_reported(object_info):
    wf = _soul()
    wf["1"]["inputs"]["unet_name"] = "flux3-image-klein-base-int8-convrot.safetensors"  # not in fixture list
    report = validate_api_prompt(wf, object_info)
    assert report["missing_models"][0]["value"] == "flux3-image-klein-base-int8-convrot.safetensors"


def test_bundled_audio_workflow_matches_comfyui_node_schema(object_info):
    wf = json.loads((ROOT / "workflows" / "05_audio_minimax_music3.json").read_text(encoding="utf-8"))
    report = validate_api_prompt(wf, object_info)
    assert report["ok"], report["errors"]
    assert not report["warnings"], report["warnings"]  # no stray/undeclared inputs such as "cfg"/"steps"


def test_bundled_cinema_ltx23_workflow_matches_official_template_schema(object_info):
    wf = json.loads((ROOT / "workflows" / "02_cinema_studio_ltx23_vfx.json").read_text(encoding="utf-8"))
    classes = {n["class_type"] for n in wf.values()}
    assert {
        "CheckpointLoaderSimple",
        "LTXAVTextEncoderLoader",
        "LTXVAudioVAELoader",
        "LatentUpscaleModelLoader",
        "LTXVLatentUpsampler",
        "VAEDecodeTiled",
        "LTXVAudioVAEDecode",
    } <= classes
    report = validate_api_prompt(wf, object_info)
    assert report["ok"], report["errors"]
    assert not report["warnings"], report["warnings"]

    # Compiling with target 1280x704 and 97 frames sets Pass-1 latent to half-res (640x352) and syncs audio frames
    compiled = compile_ui_workflow_to_api_prompt(
        wf, user_prompt="dolly zoom", slot1_file="frame.png", width=1280, height=704, frames=97
    )
    assert compiled["11"]["inputs"]["width"] == 640
    assert compiled["11"]["inputs"]["height"] == 352
    assert compiled["11"]["inputs"]["length"] == 97
    assert compiled["13"]["inputs"]["frames_number"] == 97
    assert compiled["8"]["inputs"]["text"] == "dolly zoom"
    assert "ugly" in compiled["9"]["inputs"]["text"]  # negative prompt preserved


def test_bundled_video_minimax_h3_i2v_workflow_matches_official_template_schema(object_info):
    wf = json.loads((ROOT / "workflows" / "04_video_minimax_h3_i2v.json").read_text(encoding="utf-8"))
    assert wf["1"]["inputs"]["unet_name"] == "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    assert wf["2"]["inputs"]["lora_name"] == "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    assert "audio_vae" not in wf["7"]["inputs"]
    report = validate_api_prompt(wf, object_info)
    assert report["ok"], report["errors"]
    assert not report["warnings"], report["warnings"]


def test_bundled_shinjutsu_workflow_matches_schema_and_auto_reconstructs(object_info, tmp_path, monkeypatch):
    from core import control_lora_codec

    wf = json.loads((ROOT / "workflows" / "01_shinjutsu_h3_motion_transfer.json").read_text(encoding="utf-8"))
    assert wf["173"]["inputs"]["name"] == "shinjutsu_h3_control_patch_v1_flash.safetensors"
    assert wf["81"]["class_type"] == "SaveVideo"
    report = validate_api_prompt(wf, object_info)
    assert report["ok"], report["errors"]
    assert not report["warnings"], report["warnings"]

    # Simulate base UNet + 33MB Control-LoRA on disk and verify automatic reconstruction hook
    fake_models = tmp_path / "models"
    (fake_models / "diffusion_models").mkdir(parents=True)
    unet_file = fake_models / "diffusion_models" / "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
    unet_file.write_bytes(b"0" * 1024)
    lora_file = fake_models / "shinjutsu_h3_control_lora_v1_flash.safetensors"
    lora_file.write_bytes(b"0" * 2_000_000)

    called = {}

    def _fake_recon(lora_33mb_path, base_h3_path, out_patch_path, device="cpu"):
        called["lora"] = lora_33mb_path
        called["base"] = base_h3_path
        p = control_lora_codec.Path(out_patch_path)
        p.write_bytes(b"1" * 2_000_000)
        return p

    monkeypatch.setattr(control_lora_codec, "reconstruct_controlnet_from_33mb_lora", _fake_recon)
    monkeypatch.setattr(control_lora_codec, "torch", type("T", (), {"cuda": type("C", (), {"is_available": staticmethod(lambda: False)})()}))
    monkeypatch.setattr(control_lora_codec, "safe_open", object())

    out_patch = control_lora_codec.ensure_reconstructed_control_patch(wf, models_root=fake_models)
    assert out_patch is not None and out_patch.name == "shinjutsu_h3_control_patch_v1_flash.safetensors"
    assert out_patch.is_file()
    assert called["base"] == str(unet_file)

def test_bundled_shinjutsu_turbo_and_high_workflows_validate(object_info):
    wf_turbo = json.loads((ROOT / "workflows" / "01_shinjutsu_h3_motion_turbo_w6a8.json").read_text(encoding="utf-8"))
    assert wf_turbo["1"]["inputs"]["unet_name"] == "minimax_h3_ref2va_pruned_w6a8.safetensors"
    assert wf_turbo["500"]["inputs"]["lora_name"] == "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
    assert wf_turbo["173"]["inputs"]["name"] == "shinjutsu_h3_control_patch_v1_flash.safetensors"
    rep_turbo = validate_api_prompt(wf_turbo, object_info)
    assert rep_turbo["ok"], rep_turbo["errors"]
    assert not rep_turbo["warnings"], rep_turbo["warnings"]

    wf_high = json.loads((ROOT / "workflows" / "01_shinjutsu_h3_motion_high_unpruned.json").read_text(encoding="utf-8"))
    assert wf_high["1"]["inputs"]["unet_name"] == "minimax_h3_ref2va_int8_convrot.safetensors"
    assert wf_high["173"]["inputs"]["name"] == "shinjutsu_h3_control_patch_v1_flash.safetensors"
    rep_high = validate_api_prompt(wf_high, object_info)
    assert rep_high["ok"], rep_high["errors"]
    assert not rep_high["warnings"], rep_high["warnings"]

