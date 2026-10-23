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
    # Sketch-lines ControlNet. Too strong or too long and Flux copies the lines literally (black outlines,
    # flat colour fill); paper sketches are rougher, so they are held more loosely than drawn ones.
    paper_lines_strength: float = 0.7  # [PAPER_LINES_STRENGTH]
    paper_lines_end: float = 0.6  # [PAPER_LINES_END]
    drawn_lines_strength: float = 0.8  # [DRAWN_LINES_STRENGTH]
    drawn_lines_end: float = 0.7  # [DRAWN_LINES_END]
    # Body-shape ControlNet from the template depth, on-mannequin scenes only. The templates are mannequins,
    # so this is what brings the mannequin's shape and pose through.
    depth_strength: float = 0.6  # [DEPTH_STRENGTH] 0 disables it
    depth_end: float = 0.6  # [DEPTH_END]
    # How the template depth is changed under the garment (see gateway/depth.py):
    #   fill  = the garment's drawn silhouette becomes a smooth solid, so depth and lines agree on its shape
    #   blank = no depth under the garment at all, only the lines shape it
    #   off   = the raw body depth (the old behaviour: garments hug the body)
    depth_garment: str = "fill"  # [DEPTH_GARMENT]
    # On a mannequin the lines must also win against the body, so they are held a little tighter there.
    mannequin_paper_lines_strength: float = 0.8  # [MANNEQUIN_PAPER_LINES_STRENGTH]
    mannequin_paper_lines_end: float = 0.75  # [MANNEQUIN_PAPER_LINES_END]
    mannequin_drawn_lines_strength: float = 0.85  # [MANNEQUIN_DRAWN_LINES_STRENGTH]
    mannequin_drawn_lines_end: float = 0.8  # [MANNEQUIN_DRAWN_LINES_END]
    # On a mannequin, drop the garment's outer outline from the lines (the depth gives the shape); left in,
    # it was painted as a grey edge trim. Neckline and collar lines are kept.
    strip_outline: bool = True  # [STRIP_OUTLINE]
    view_hint: bool = True  # [VIEW_HINT] prefix "Back view." / "Side view." to non-front prompts
    view_timeout_s: int = 600  # give up on a view after this long
    poll_interval_s: float = 1.0

    def lines_for(self, source: str, on_mannequin: bool = False) -> tuple[float, float]:
        """(strength, end_percent) of the sketch-lines ControlNet for a paper or drawn sketch."""
        if on_mannequin:
            if source == "paper":
                return self.mannequin_paper_lines_strength, self.mannequin_paper_lines_end
            return self.mannequin_drawn_lines_strength, self.mannequin_drawn_lines_end
        if source == "paper":
            return self.paper_lines_strength, self.paper_lines_end
        return self.drawn_lines_strength, self.drawn_lines_end

    @classmethod
    def from_env(cls) -> RenderSettings:
        env = os.environ
        return cls(
            steps=int(env.get("RENDER_STEPS", cls.steps)),
            guidance=float(env.get("RENDER_GUIDANCE", cls.guidance)),
            paper_lines_strength=float(env.get("PAPER_LINES_STRENGTH", cls.paper_lines_strength)),
            paper_lines_end=float(env.get("PAPER_LINES_END", cls.paper_lines_end)),
            drawn_lines_strength=float(env.get("DRAWN_LINES_STRENGTH", cls.drawn_lines_strength)),
            drawn_lines_end=float(env.get("DRAWN_LINES_END", cls.drawn_lines_end)),
            depth_strength=float(env.get("DEPTH_STRENGTH", cls.depth_strength)),
            depth_end=float(env.get("DEPTH_END", cls.depth_end)),
            depth_garment=env.get("DEPTH_GARMENT", cls.depth_garment).lower(),
            mannequin_paper_lines_strength=float(
                env.get("MANNEQUIN_PAPER_LINES_STRENGTH", cls.mannequin_paper_lines_strength)
            ),
            mannequin_paper_lines_end=float(env.get("MANNEQUIN_PAPER_LINES_END", cls.mannequin_paper_lines_end)),
            mannequin_drawn_lines_strength=float(
                env.get("MANNEQUIN_DRAWN_LINES_STRENGTH", cls.mannequin_drawn_lines_strength)
            ),
            mannequin_drawn_lines_end=float(env.get("MANNEQUIN_DRAWN_LINES_END", cls.mannequin_drawn_lines_end)),
            view_hint=env.get("VIEW_HINT", "1").lower() not in ("0", "false", "no"),
            strip_outline=env.get("STRIP_OUTLINE", "1").lower() not in ("0", "false", "no"),
        )


@dataclass
class LlmSettings:
    """Vision LLM (llama-swap's OpenAI-compatible API) that reads construction details off the sketch.
    Disabled when LLM_URL is empty; renders then use the sketch and the tapped choices only."""

    url: str = ""  # [LLM_URL] e.g. http://127.0.0.1:8085/v1
    model: str = "qwen3.6-35b"  # [LLM_MODEL] must be a vision model (mmproj loaded)
    api_key: str = ""  # [LLM_API_KEY]
    timeout_s: float = 240.0  # [LLM_TIMEOUT_S] generous: the first call may have to load the model

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    @classmethod
    def from_env(cls) -> LlmSettings:
        env = os.environ
        return cls(
            url=env.get("LLM_URL", "").rstrip("/"),
            model=env.get("LLM_MODEL", cls.model),
            api_key=env.get("LLM_API_KEY", ""),
            timeout_s=float(env.get("LLM_TIMEOUT_S", cls.timeout_s)),
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
    llm: LlmSettings = field(default_factory=LlmSettings)

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
            llm=LlmSettings.from_env(),
        )
