# -*- coding: utf-8 -*-
"""`/object_info` introspection + pre-flight validation (core/comfy_client.py)."""
import copy

from conftest import txt2img_graph
from core.comfy_client import is_partner_node, summarize_validation, validate_api_prompt, widget_names_for


def test_widget_names_follow_object_info_order_with_seed_control(object_info):
    assert widget_names_for("KSampler", object_info) == [
        "seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise",
    ]


def test_widget_names_support_new_combo_format_and_optional_inputs(object_info):
    assert widget_names_for("KSamplerSelect", object_info) == ["sampler_name"]
    assert widget_names_for("CLIPLoader", object_info) == ["clip_name", "type", "device"]


def test_widget_names_unknown_class_returns_none(object_info):
    assert widget_names_for("NotARealNode", object_info) is None
    assert widget_names_for("KSampler", None) is None


def test_partner_node_detection(object_info):
    assert is_partner_node("GeminiImageNode", object_info)
    assert not is_partner_node("KSampler", object_info)


def test_valid_graph_passes(object_info):
    report = validate_api_prompt(txt2img_graph(), object_info)
    assert report["checked"] and report["ok"], report["errors"]
    assert report["partner_nodes"] == []


def test_missing_node_is_reported_with_install_hint(object_info):
    g = txt2img_graph()
    g["10"] = {"class_type": "SomeCustomPackNode", "inputs": {}}
    report = validate_api_prompt(g, object_info)
    assert not report["ok"]
    assert report["missing_nodes"] == ["SomeCustomPackNode"]
    assert "ComfyUI Manager" in summarize_validation(report)


def test_missing_model_is_reported(object_info):
    report = validate_api_prompt(txt2img_graph(unet="not_downloaded.safetensors"), object_info)
    assert not report["ok"]
    assert report["missing_models"] == [{"node": "1", "input": "unet_name", "value": "not_downloaded.safetensors"}]
    assert "not_downloaded.safetensors" in summarize_validation(report)


def test_missing_required_input(object_info):
    g = txt2img_graph()
    del g["7"]["inputs"]["latent_image"]
    report = validate_api_prompt(g, object_info)
    assert any("missing required input 'latent_image'" in e for e in report["errors"])


def test_dangling_link(object_info):
    g = txt2img_graph()
    g["8"]["inputs"]["vae"] = ["99", 0]
    report = validate_api_prompt(g, object_info)
    assert any("node 99, which does not exist" in e for e in report["errors"])


def test_link_type_mismatch_is_caught(object_info):
    # e.g. a "music" graph wiring CONDITIONING into SaveAudio's AUDIO input
    g = txt2img_graph()
    g["10"] = {"class_type": "SaveAudioAdvanced", "inputs": {"audio": ["4", 0], "filename_prefix": "x", "format": "flac"}}
    report = validate_api_prompt(g, object_info)
    assert any("expects AUDIO" in e and "CONDITIONING" in e for e in report["errors"])


def test_output_slot_out_of_range(object_info):
    g = txt2img_graph()
    g["8"]["inputs"]["samples"] = ["7", 3]
    report = validate_api_prompt(g, object_info)
    assert any("output #3" in e for e in report["errors"])


def test_partner_nodes_are_flagged_but_not_blocking(object_info):
    g = copy.deepcopy(txt2img_graph())
    g["10"] = {"class_type": "GeminiImageNode", "inputs": {"prompt": "x"}}
    report = validate_api_prompt(g, object_info)
    assert report["ok"]
    assert report["partner_nodes"] == ["GeminiImageNode"]


def test_validation_is_skipped_without_object_info():
    report = validate_api_prompt(txt2img_graph(), None)
    assert report["checked"] is False and report["ok"] is True


def test_empty_graph_fails():
    assert validate_api_prompt({}, None)["ok"] is False
