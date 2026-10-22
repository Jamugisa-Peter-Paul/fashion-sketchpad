"""Settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Origins the app runs from: Capacitor Android/iOS webviews and the Next.js dev server.
DEFAULT_CORS_ORIGINS = [
    "https://localhost",
    "http://localhost",
    "capacitor://localhost",
    "http://localhost:3000",
]


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class RenderSettings:
    """The proven Flux + ControlNet Union Pro 2.0 recipe. Override any value with the env var in brackets."""

    unet: str = "flux1-dev-Q6_K.gguf"
    clip_l: str = "clip_l.safetensors"
    t5: str = "t5xxl_fp8_e4m3fn.safetensors"
    vae: str = "ae.safetensors"
    controlnet: str = "flux-union-pro-2/diffusion_pytorch_model.safetensors"
    steps: int = 28  # [RENDER_STEPS]
    guidance: float = 3.5  # [RENDER_GUIDANCE]
    lines_strength: float = 0.85  # [LINES_STRENGTH]
    lines_end: float = 0.85  # [LINES_END]
    depth_strength: float = 0.4  # [DEPTH_STRENGTH] 0 disables the body-shape ControlNet
    depth_end: float = 0.5  # [DEPTH_END]
    view_hint: bool = True  # [VIEW_HINT] prefix "Back view." / "Side view." to non-front prompts
    view_timeout_s: int = 600  # give up on a view after this long
    poll_interval_s: float = 1.0

    @classmethod
    def from_env(cls) -> RenderSettings:
        env = os.environ
        return cls(
            steps=int(env.get("RENDER_STEPS", cls.steps)),
            guidance=float(env.get("RENDER_GUIDANCE", cls.guidance)),
            lines_strength=float(env.get("LINES_STRENGTH", cls.lines_strength)),
            lines_end=float(env.get("LINES_END", cls.lines_end)),
            depth_strength=float(env.get("DEPTH_STRENGTH", cls.depth_strength)),
            depth_end=float(env.get("DEPTH_END", cls.depth_end)),
            view_hint=env.get("VIEW_HINT", "1").lower() not in ("0", "false", "no"),
        )


@dataclass
class Settings:
    comfy_url: str = "http://127.0.0.1:8188"
    templates_dir: Path = Path("/home/dct/ComfyUI/output/templates")
    data_dir: Path = Path("./data")
    app_tokens: list[str] = field(default_factory=list)
    public_base_url: str = ""
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    max_upload_mb: int = 15
    render: RenderSettings = field(default_factory=RenderSettings)

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            comfy_url=env.get("COMFY_URL", cls.comfy_url).rstrip("/"),
            templates_dir=Path(env.get("TEMPLATES_DIR", str(cls.templates_dir))),
            data_dir=Path(env.get("DATA_DIR", str(cls.data_dir))),
            app_tokens=_split(env.get("APP_TOKENS", "")),
            public_base_url=env.get("PUBLIC_BASE_URL", "").rstrip("/"),
            cors_origins=DEFAULT_CORS_ORIGINS + _split(env.get("CORS_ORIGINS", "")),
            max_upload_mb=int(env.get("MAX_UPLOAD_MB", cls.max_upload_mb)),
            render=RenderSettings.from_env(),
        )
