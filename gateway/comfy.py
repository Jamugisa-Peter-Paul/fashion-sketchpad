"""Minimal async client for the ComfyUI HTTP API (upload, queue, history, view)."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


class ComfyError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutputImage:
    filename: str
    subfolder: str
    type: str


class ComfyClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client_id = uuid.uuid4().hex
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def ping(self) -> bool:
        try:
            response = await self._http.get("/system_stats", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def upload_image(self, data: bytes, filename: str) -> str:
        """Uploads into ComfyUI's input folder (overwriting) and returns the name LoadImage expects."""
        response = await self._http.post(
            "/upload/image",
            files={"image": (filename, data, "image/png")},
            data={"overwrite": "true", "type": "input"},
        )
        if response.status_code != 200:
            raise ComfyError(f"Upload failed ({response.status_code}): {response.text[:200]}")
        body = response.json()
        return f"{body['subfolder']}/{body['name']}" if body.get("subfolder") else body["name"]

    async def queue_prompt(self, workflow: dict[str, Any]) -> str:
        response = await self._http.post("/prompt", json={"prompt": workflow, "client_id": self.client_id})
        if response.status_code != 200:
            raise ComfyError(f"ComfyUI rejected the workflow: {response.text[:500]}")
        return response.json()["prompt_id"]

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        response = await self._http.get(f"/history/{prompt_id}")
        response.raise_for_status()
        return response.json().get(prompt_id)

    async def knows(self, prompt_id: str) -> bool:
        """True if ComfyUI has this prompt queued, running or finished (it forgets everything on restart)."""
        if await self.history(prompt_id) is not None:
            return True
        response = await self._http.get("/queue")
        response.raise_for_status()
        queue = response.json()
        return any(item[1] == prompt_id for item in queue.get("queue_running", []) + queue.get("queue_pending", []))

    async def wait_for_output(
        self, prompt_id: str, output_node: str, timeout_s: float, poll_s: float
    ) -> OutputImage:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            entry = await self.history(prompt_id)
            if entry is not None:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ComfyError(_error_message(status))
                images = entry.get("outputs", {}).get(output_node, {}).get("images", [])
                if images:
                    image = images[0]
                    return OutputImage(image["filename"], image.get("subfolder", ""), image.get("type", "output"))
                if status.get("completed"):
                    raise ComfyError("ComfyUI finished without producing an image")
            await asyncio.sleep(poll_s)
        raise ComfyError(f"Timed out after {timeout_s:.0f}s waiting for ComfyUI")

    async def download(self, image: OutputImage) -> bytes:
        response = await self._http.get(
            "/view", params={"filename": image.filename, "subfolder": image.subfolder, "type": image.type}
        )
        response.raise_for_status()
        return response.content


def _error_message(status: dict[str, Any]) -> str:
    for kind, data in status.get("messages", []):
        if kind == "execution_error":
            return f"ComfyUI error in {data.get('node_type', 'a node')}: {data.get('exception_message', '').strip()}"
    return "ComfyUI reported an error"
