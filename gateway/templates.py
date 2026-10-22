"""Discovers body templates on disk.

Layout produced by the template generator script:
    <TEMPLATES_DIR>/<body>/<view>_photo_00001_.png
    <TEMPLATES_DIR>/<body>/<view>_depth_00001_.png
    <TEMPLATES_DIR>/<body>/<view>_mask.png
    <TEMPLATES_DIR>/<body>/<view>_guide.png
ComfyUI's SaveImage adds a counter suffix, so photo/depth are matched by glob and the newest wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

VIEWS = ("front", "back", "side")


@dataclass(frozen=True)
class ViewTemplate:
    guide: Path | None
    depth: Path | None
    mask: Path | None
    photo: Path | None

    @property
    def available(self) -> bool:
        """A view is usable when the app can draw on it (guide) and the gateway can shape the body (depth)."""
        return self.guide is not None and self.depth is not None


def _newest(folder: Path, pattern: str) -> Path | None:
    matches = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def find_view(templates_dir: Path, body: str, view: str) -> ViewTemplate:
    folder = templates_dir / body
    if view not in VIEWS or not folder.is_dir():
        return ViewTemplate(None, None, None, None)
    return ViewTemplate(
        guide=_newest(folder, f"{view}_guide.png"),
        depth=_newest(folder, f"{view}_depth_*.png"),
        mask=_newest(folder, f"{view}_mask.png"),
        photo=_newest(folder, f"{view}_photo_*.png"),
    )


def available_views(templates_dir: Path, body: str) -> list[str]:
    return [view for view in VIEWS if find_view(templates_dir, body, view).available]
