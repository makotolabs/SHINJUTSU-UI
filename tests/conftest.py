# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
for p in (str(ROOT), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(scope="session")
def object_info():
    return json.loads((TESTS / "fixtures" / "object_info_min.json").read_text(encoding="utf-8"))


@pytest.fixture()
def clean_transport_env(monkeypatch):
    """Force a known transport configuration for each test."""
    for var in ("SHINJUTSU_TRANSPORT", "COMFY_BASE_URL", "COMFY_API_KEY", "SHINJUTSU_OPEN_WEIGHTS_STRICT"):
        monkeypatch.delenv(var, raising=False)
    from core import comfy_client

    comfy_client.clear_object_info_cache()
    comfy_client.reset_sdk_client()
    yield monkeypatch
    comfy_client.clear_object_info_cache()
    comfy_client.reset_sdk_client()


@pytest.fixture()
def fake_comfy():
    from fake_comfyui import FakeComfyServer

    with FakeComfyServer() as srv:
        yield srv


def txt2img_graph(unet="flux1-dev-fp8.safetensors"):
    """A valid, minimal API-format text-to-image graph for the fixture object_info."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp8.safetensors", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality", "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "seed": 1, "steps": 20, "cfg": 3.5, "sampler_name": "euler", "scheduler": "normal",
                "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "SHINJUTSU/test"}},
    }
