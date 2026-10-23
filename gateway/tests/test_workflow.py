from __future__ import annotations

import pytest

from gateway.config import RenderSettings
from gateway.tests.workflow_checks import assert_pure_text_to_image
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
    assert cn["positive"] == ["5", 0] and cn["negative"] == ["6", 0] and cn["image"] == ["8", 0]
    assert (wf["10"]["inputs"]["width"], wf["10"]["inputs"]["height"]) == (832, 1216)
    ks = wf["11"]["inputs"]
    assert (ks["seed"], ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (1234, 28, 1.0, "euler", "simple")
    assert ks["positive"] == ["9", 0] and ks["negative"] == ["9", 1]
    assert wf[OUTPUT_NODE]["class_type"] == "SaveImage"
    assert "14" not in wf
    assert validate(wf, {"lines.png": b""}) == []


@pytest.mark.parametrize(("source", "expected"), [("paper", (0.7, 0.6)), ("drawn", (0.8, 0.7))])
def test_lines_controlnet_strength_depends_on_sketch_source(source: str, expected: tuple[float, float]) -> None:
    cn = build_workflow("p", "lines.png", 1, RenderSettings(), source=source)["9"]["inputs"]
    assert (cn["strength"], cn["start_percent"], cn["end_percent"]) == (expected[0], 0.0, expected[1])


def test_depth_controlnet_is_chained_after_lines() -> None:
    wf = build_workflow("p", "lines.png", 1, RenderSettings(), depth_image="depth.png")
    depth = wf["15"]["inputs"]
    assert depth["positive"] == ["9", 0] and depth["negative"] == ["9", 1] and depth["image"] == ["14", 0]
    assert (depth["strength"], depth["end_percent"]) == (0.6, 0.6)  # mannequin templates: shape and pose
    assert wf["11"]["inputs"]["positive"] == ["15", 0] and wf["11"]["inputs"]["negative"] == ["15", 1]
    assert validate(wf, {"lines.png": b"", "depth.png": b""}) == []


def test_depth_strength_zero_disables_depth() -> None:
    wf = build_workflow("p", "lines.png", 1, RenderSettings(depth_strength=0), depth_image="depth.png")
    assert "15" not in wf and wf["11"]["inputs"]["positive"] == ["9", 0]


@pytest.mark.parametrize("source", ["paper", "drawn"])
@pytest.mark.parametrize("depth", [None, "depth.png"])
def test_images_are_only_controlnet_hints(source: str, depth: str | None) -> None:
    """No LoadImage may feed a latent or VAEEncode: the render starts from an empty latent at denoise 1.0."""
    assert_pure_text_to_image(build_workflow("p", "lines.png", 1, RenderSettings(), depth_image=depth, source=source))


def test_pure_text_to_image_check_catches_img2img() -> None:
    wf = build_workflow("p", "lines.png", 1, RenderSettings())
    wf["20"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["3", 0]}}
    wf["11"]["inputs"]["latent_image"] = ["20", 0]
    with pytest.raises(AssertionError):
        assert_pure_text_to_image(wf)


@pytest.mark.parametrize(("source", "expected"), [("paper", (0.8, 0.75)), ("drawn", (0.85, 0.8))])
def test_lines_are_held_tighter_on_a_mannequin(source: str, expected: tuple[float, float]) -> None:
    cn = build_workflow("p", "lines.png", 1, RenderSettings(), source=source, on_mannequin=True)["9"]["inputs"]
    assert (cn["strength"], cn["end_percent"]) == expected
