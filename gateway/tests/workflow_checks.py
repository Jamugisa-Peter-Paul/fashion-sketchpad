"""Structural checks for generated ComfyUI workflows (shared by the workflow and end-to-end tests)."""

from __future__ import annotations

from typing import Any

# Nodes that would put an image into the latent (img2img / inpainting) or blend it into the result.
IMAGE_TO_LATENT = {"VAEEncode", "VAEEncodeForInpaint", "InpaintModelConditioning", "SetLatentNoiseMask", "ImageCompositeMasked", "ImageBlend", "LatentComposite"}


def consumers(workflow: dict[str, Any], node_id: str) -> list[tuple[str, str]]:
    """(consumer node id, input name) for every input linked to `node_id`."""
    found = []
    for other_id, node in workflow.items():
        for name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) == node_id:
                found.append((other_id, name))
    return found


def assert_pure_text_to_image(workflow: dict[str, Any]) -> None:
    """Sketch and depth images may only reach the model as ControlNet hints, never as an init image."""
    types = {node_id: node["class_type"] for node_id, node in workflow.items()}
    assert not set(types.values()) & IMAGE_TO_LATENT, f"image-to-latent/blend node present: {types}"

    samplers = [node for node in workflow.values() if node["class_type"] == "KSampler"]
    assert len(samplers) == 1
    sampler = samplers[0]["inputs"]
    assert types[sampler["latent_image"][0]] == "EmptySD3LatentImage"
    assert sampler["denoise"] == 1.0

    load_images = [node_id for node_id, kind in types.items() if kind == "LoadImage"]
    assert load_images, "expected the sketch to be loaded"
    for node_id in load_images:
        uses = consumers(workflow, node_id)
        assert uses, f"LoadImage {node_id} is unused"
        for consumer, input_name in uses:
            assert (types[consumer], input_name) == ("ControlNetApplyAdvanced", "image"), (
                f"LoadImage {node_id} feeds {types[consumer]}.{input_name}"
            )
