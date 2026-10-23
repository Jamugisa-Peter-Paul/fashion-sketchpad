"""ComfyUI workflow (API format) for one view. Node ids follow the original hand-built recipe."""

from __future__ import annotations

from typing import Any

from gateway.config import RenderSettings
from gateway.sketch import CANVAS_H, CANVAS_W

OUTPUT_NODE = "13"


def build_workflow(
    prompt: str,
    lines_image: str,
    seed: int,
    render: RenderSettings,
    depth_image: str | None = None,
    filename_prefix: str = "fashion/render",
    source: str = "drawn",
    on_mannequin: bool = False,
) -> dict[str, Any]:
    """Pure text-to-image: KSampler starts from an empty latent (denoise 1.0). The sketch (white lines on
    black) and the body depth are only ControlNet hints; no image is encoded into the latent or blended in.

    `lines_image` / `depth_image` are names returned by ComfyUI's /upload/image. `source` ("paper" or
    "drawn") and `on_mannequin` pick the sketch ControlNet strength.
    """
    lines_strength, lines_end = render.lines_for(source, on_mannequin)
    workflow: dict[str, Any] = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": render.unet}},
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {"clip_name1": render.clip_l, "clip_name2": render.t5, "type": "flux"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": render.vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": render.guidance}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "7": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": render.controlnet}},
        "8": {"class_type": "LoadImage", "inputs": {"image": lines_image}},
        "9": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "control_net": ["7", 0],
                "image": ["8", 0],
                "vae": ["3", 0],
                "strength": lines_strength,
                "start_percent": 0.0,
                "end_percent": lines_end,
            },
        },
        "10": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": CANVAS_W, "height": CANVAS_H, "batch_size": 1},
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": render.steps,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "positive": ["9", 0],
                "negative": ["9", 1],
                "latent_image": ["10", 0],
            },
        },
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["3", 0]}},
        OUTPUT_NODE: {"class_type": "SaveImage", "inputs": {"images": ["12", 0], "filename_prefix": filename_prefix}},
    }

    if depth_image and render.depth_strength > 0:
        # Second ControlNet (same Union Pro model) keeps the mannequin's body shape from the template. The depth
        # image has the garment's silhouette cut into it (gateway/depth.py), so it no longer fights the lines.
        workflow["14"] = {"class_type": "LoadImage", "inputs": {"image": depth_image}}
        workflow["15"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["9", 0],
                "negative": ["9", 1],
                "control_net": ["7", 0],
                "image": ["14", 0],
                "vae": ["3", 0],
                "strength": render.depth_strength,
                "start_percent": 0.0,
                "end_percent": render.depth_end,
            },
        }
        workflow["11"]["inputs"]["positive"] = ["15", 0]
        workflow["11"]["inputs"]["negative"] = ["15", 1]
    return workflow
