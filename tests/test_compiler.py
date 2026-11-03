# -*- coding: utf-8 -*-
"""UI-graph / API-graph compiler (core/model_manager.compile_ui_workflow_to_api_prompt)."""
from core.model_manager import compile_ui_workflow_to_api_prompt


def _shinjutsu_like_api_graph():
    # Mirrors the studio's SHINJUTSU graph: depth video (174) appears BEFORE the source video (300).
    return {
        "174": {"class_type": "LoadVideo", "inputs": {"file": "dance_crisp_depth.mp4"}},
        "200": {"class_type": "LoadImage", "inputs": {"image": "hero_clean_white_bg.png"}},
        "300": {"class_type": "LoadVideo", "inputs": {"file": "dance.mp4"}},
    }


def test_api_graph_keeps_already_bound_uploads_untouched():
    out = compile_ui_workflow_to_api_prompt(
        _shinjutsu_like_api_graph(), slot1_file="hero_clean_white_bg.png", slot2_file="dance.mp4"
    )
    assert out["174"]["inputs"]["file"] == "dance_crisp_depth.mp4"  # depth control video must survive
    assert out["300"]["inputs"]["file"] == "dance.mp4"
    assert out["200"]["inputs"]["image"] == "hero_clean_white_bg.png"


def test_api_template_gets_uploads_in_first_matching_loaders_only():
    graph = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "example2.png"}},
        "3": {"class_type": "LoadVideo", "inputs": {"file": "a.mp4"}},
        "4": {"class_type": "LoadVideo", "inputs": {"file": "b.mp4"}},
    }
    out = compile_ui_workflow_to_api_prompt(graph, slot1_file="me.png", slot2_file="moves.mp4")
    assert out["1"]["inputs"]["image"] == "me.png"
    assert out["2"]["inputs"]["image"] == "example2.png"
    assert out["3"]["inputs"]["file"] == "moves.mp4"
    assert out["4"]["inputs"]["file"] == "b.mp4"


def test_api_template_second_image_slot():
    graph = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "a.png"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "b.png"}},
    }
    out = compile_ui_workflow_to_api_prompt(graph, slot1_file="face.png", slot2_file="scene.jpg")
    assert out["1"]["inputs"]["image"] == "face.png"
    assert out["2"]["inputs"]["image"] == "scene.jpg"


def test_api_graph_prompt_and_negative_prompt():
    graph = {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old prompt", "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality", "clip": ["2", 0]}},
    }
    out = compile_ui_workflow_to_api_prompt(graph, user_prompt="a neon samurai")
    assert out["4"]["inputs"]["text"] == "a neon samurai"
    assert out["5"]["inputs"]["text"] == "blurry, low quality"


def _ui_ksampler_graph(widgets):
    return {
        "nodes": [
            {"id": 1, "type": "UNETLoader", "mode": 0, "inputs": [], "widgets_values": ["flux1-dev-fp8.safetensors", "default"]},
            {
                "id": 7,
                "type": "KSampler",
                "mode": 0,
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 1},
                    {"name": "positive", "type": "CONDITIONING", "link": None},
                    {"name": "negative", "type": "CONDITIONING", "link": None},
                    {"name": "latent_image", "type": "LATENT", "link": None},
                ],
                "widgets_values": widgets,
            },
            {"id": 99, "type": "MarkdownNote", "mode": 0, "inputs": [], "widgets_values": ["notes"]},
        ],
        "links": [[1, 1, 0, 7, 0, "MODEL"]],
    }


def test_ui_graph_uses_live_object_info_widget_order(object_info):
    out = compile_ui_workflow_to_api_prompt(
        _ui_ksampler_graph([42, "randomize", 28, 4.5, "er_sde", "beta", 0.9]), object_info=object_info
    )
    ks = out["7"]["inputs"]
    assert ks["seed"] == 42 and "control_after_generate" not in ks
    assert ks["steps"] == 28 and ks["cfg"] == 4.5
    assert ks["sampler_name"] == "er_sde" and ks["scheduler"] == "beta" and ks["denoise"] == 0.9
    assert ks["model"] == ["1", 0]
    assert out["1"]["inputs"] == {"unet_name": "flux1-dev-fp8.safetensors", "weight_dtype": "default"}
    assert "99" not in out  # frontend-only notes are dropped


def test_ui_graph_still_compiles_offline_without_object_info():
    out = compile_ui_workflow_to_api_prompt(_ui_ksampler_graph([42, "randomize", 28, 4.5, "er_sde", "beta", 0.9]))
    assert out["7"]["class_type"] == "KSampler"
    assert out["7"]["inputs"]["model"] == ["1", 0]


def test_muted_and_bypassed_nodes_are_skipped(object_info):
    g = _ui_ksampler_graph([1, "fixed", 20, 7.0, "euler", "normal", 1.0])
    g["nodes"][1]["mode"] = 4
    out = compile_ui_workflow_to_api_prompt(g, object_info=object_info)
    assert "7" not in out
