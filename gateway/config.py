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
class Settings:
    comfy_url: str = "http://127.0.0.1:8188"
    templates_dir: Path = Path("/home/dct/ComfyUI/output/templates")
    data_dir: Path = Path("./data")
    app_tokens: list[str] = field(default_factory=list)
    public_base_url: str = ""
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    max_upload_mb: int = 15

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
        )
