from __future__ import annotations

from gateway.config import RenderSettings
from gateway.tools.fake_comfy import validate
from gateway.workflow import OUTPUT_NODE, build_workflow


def test_recipe_nodes_and_values() -> None:
    wf = build_workflow("a prompt", "lines.png", 1234, RenderSettings())
    assert wf["1"]["inputs"]["unet_name"] == "flux1-dev-Q6_K.gguf"
    assert wf["2"]["inputs"] == {"clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp8_e4m3fn.safetensors", "type": "flux"}
    assert wf["5"]["inputs"]["guidance"] == 3.5
    assert wf["6"]["inputs"]["text"] == ""
    assert wf["7"]["inputs"]["control_net_name"] == "flux-union-pro-2/diffusion_pytorch_model.safetensors"
    cn = wf["9"]["inputs"]
    assert (cn["strength"], cn["start_percent"], cn["end_percent"]) == (0.85, 0.0, 0.85)
    assert cn["positive"] == ["5", 0] and cn["negative"] == ["6", 0] and cn["image"] == ["8", 0]
    assert (wf["10"]["inputs"]["width"], wf["10"]["inputs"]["height"]) == (832, 1216)
    ks = wf["11"]["inputs"]
    assert (ks["seed"], ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (1234, 28, 1.0, "euler", "simple")
    assert ks["positive"] == ["9", 0] and ks["negative"] == ["9", 1]
    assert wf[OUTPUT_NODE]["class_type"] == "SaveImage"
    assert "14" not in wf
    assert validate(wf, {"lines.png": b""}) == []


def test_depth_controlnet_is_chained_after_lines() -> None:
    wf = build_workflow("p", "lines.png", 1, RenderSettings(), depth_image="depth.png")
    depth = wf["15"]["inputs"]
    assert depth["positive"] == ["9", 0] and depth["negative"] == ["9", 1] and depth["image"] == ["14", 0]
    assert (depth["strength"], depth["end_percent"]) == (0.3, 0.4)  # light, so the garment lines win
    assert (wf["9"]["inputs"]["strength"], wf["9"]["inputs"]["end_percent"]) == (0.85, 0.85)
    assert wf["11"]["inputs"]["positive"] == ["15", 0] and wf["11"]["inputs"]["negative"] == ["15", 1]
    assert validate(wf, {"lines.png": b"", "depth.png": b""}) == []


def test_depth_strength_zero_disables_depth() -> None:
    wf = build_workflow("p", "lines.png", 1, RenderSettings(depth_strength=0), depth_image="depth.png")
    assert "15" not in wf and wf["11"]["inputs"]["positive"] == ["9", 0]
