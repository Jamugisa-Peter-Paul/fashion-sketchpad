"""A fake ComfyUI for tests and for app development without the GPU server.

    python -m gateway.tools.fake_comfy --port 8188 --seconds 5

It implements the endpoints the gateway uses (/system_stats, /upload/image, /prompt, /queue,
/history/{id}, /view), checks that submitted workflows are wired correctly, renders prompts one after
another taking `seconds` each, and returns the control image recoloured with the prompt's #hex colour.
Put "FAIL" in the extra notes to simulate a ComfyUI execution error.
"""

from __future__ import annotations

import argparse
import io
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw

KNOWN_NODES = {
    "UnetLoaderGGUF",
    "DualCLIPLoader",
    "VAELoader",
    "CLIPTextEncode",
    "FluxGuidance",
    "ControlNetLoader",
    "LoadImage",
    "ControlNetApplyAdvanced",
    "EmptySD3LatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
}


@dataclass
class FakePrompt:
    id: str
    workflow: dict[str, Any]
    done_at: float
    error: str | None = None


@dataclass
class FakeState:
    seconds: float
    uploads: dict[str, bytes] = field(default_factory=dict)
    prompts: dict[str, FakePrompt] = field(default_factory=dict)
    outputs: dict[str, bytes] = field(default_factory=dict)


def validate(workflow: dict[str, Any], uploads: dict[str, bytes]) -> list[str]:
    errors = []
    for node_id, node in workflow.items():
        if node.get("class_type") not in KNOWN_NODES:
            errors.append(f"{node_id}: unknown node {node.get('class_type')}")
        for name, value in node.get("inputs", {}).items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) not in workflow:
                errors.append(f"{node_id}.{name}: links to missing node {value[0]}")
        if node.get("class_type") == "LoadImage" and node["inputs"].get("image") not in uploads:
            errors.append(f"{node_id}: image {node['inputs'].get('image')} was never uploaded")
    if not any(n.get("class_type") == "SaveImage" for n in workflow.values()):
        errors.append("no SaveImage node")
    return errors


def fake_render(workflow: dict[str, Any], uploads: dict[str, bytes]) -> bytes:
    """Control lines drawn in the prompt's colour on a light grey 'studio'."""
    prompt = next((n["inputs"]["text"] for n in workflow.values() if n["class_type"] == "CLIPTextEncode" and n["inputs"]["text"]), "")
    match = re.search(r"#([0-9A-Fa-f]{6})", prompt)
    colour = tuple(int(match.group(1)[i : i + 2], 16) for i in (0, 2, 4)) if match else (120, 120, 120)
    lines_name = workflow["8"]["inputs"]["image"]
    lines = np.asarray(Image.open(io.BytesIO(uploads[lines_name])).convert("L")).astype(np.float32) / 255
    base = np.full((*lines.shape, 3), 225, np.float32)
    image = base * (1 - lines[..., None]) + np.array(colour, np.float32) * lines[..., None]
    out = Image.fromarray(image.clip(0, 255).astype(np.uint8))
    ImageDraw.Draw(out).text((12, 12), f"FAKE RENDER seed {workflow['11']['inputs']['seed']}", fill=(60, 60, 60))
    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def create_fake_comfy(seconds: float = 0.0) -> FastAPI:
    app = FastAPI(title="Fake ComfyUI")
    state = FakeState(seconds=seconds)
    app.state.fake = state

    @app.get("/system_stats")
    def system_stats() -> dict[str, Any]:
        return {"system": {"comfyui_version": "fake"}, "devices": []}

    @app.post("/upload/image")
    def upload(image: UploadFile = File(...), overwrite: str = Form("false"), type: str = Form("input")) -> dict[str, str]:
        state.uploads[image.filename or "upload.png"] = image.file.read()
        return {"name": image.filename or "upload.png", "subfolder": "", "type": type}

    @app.post("/prompt")
    async def prompt(request: Request) -> Response:
        body = await request.json()
        workflow = body["prompt"]
        errors = validate(workflow, state.uploads)
        if errors:
            return JSONResponse({"error": {"message": "Prompt outputs failed validation"}, "node_errors": errors}, status_code=400)
        # Serial queue: each prompt finishes `seconds` after the previous one.
        last = max((p.done_at for p in state.prompts.values()), default=0.0)
        prompt_id = str(uuid.uuid4())
        text = workflow["4"]["inputs"]["text"]
        error = "Simulated failure" if "FAIL" in text else None
        state.prompts[prompt_id] = FakePrompt(prompt_id, workflow, max(last, time.time()) + state.seconds, error)
        return JSONResponse({"prompt_id": prompt_id, "number": len(state.prompts), "node_errors": {}})

    @app.get("/queue")
    def queue() -> dict[str, Any]:
        now = time.time()
        waiting = sorted((p for p in state.prompts.values() if p.done_at > now), key=lambda p: p.done_at)
        items = [[i, p.id, {}, {}, []] for i, p in enumerate(waiting)]
        return {"queue_running": items[:1], "queue_pending": items[1:]}

    @app.get("/history/{prompt_id}")
    def history(prompt_id: str) -> dict[str, Any]:
        item = state.prompts.get(prompt_id)
        if item is None or item.done_at > time.time():
            return {}
        if item.error:
            messages = [["execution_error", {"node_type": "KSampler", "exception_message": item.error}]]
            return {prompt_id: {"status": {"status_str": "error", "completed": False, "messages": messages}, "outputs": {}}}
        filename = f"{prompt_id}.png"
        if filename not in state.outputs:
            state.outputs[filename] = fake_render(item.workflow, state.uploads)
        images = [{"filename": filename, "subfolder": "fashion", "type": "output"}]
        return {
            prompt_id: {
                "status": {"status_str": "success", "completed": True, "messages": []},
                "outputs": {"13": {"images": images}},
            }
        }

    @app.get("/view")
    def view(filename: str, subfolder: str = "", type: str = "output") -> Response:
        if filename not in state.outputs:
            raise HTTPException(status_code=404)
        return Response(state.outputs[filename], media_type="image/png")

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Fake ComfyUI for local development")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--seconds", type=float, default=5.0, help="simulated render time per view")
    args = parser.parse_args()
    uvicorn.run(create_fake_comfy(args.seconds), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
