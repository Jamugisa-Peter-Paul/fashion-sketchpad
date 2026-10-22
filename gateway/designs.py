"""Design folders on disk: design.json plus sketch/lines/render PNGs. See docs/ARCHITECTURE.md."""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from gateway.models import Design
from gateway.storage import read_json, valid_id, write_json


class DesignNotFound(KeyError):
    pass


class DesignStore:
    """All reads/writes of design.json go through here. One lock is plenty for a single-user app and keeps
    the API handlers and the render worker from overwriting each other's changes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._job_index: dict[str, str] = {}  # job id -> design id
        for design in self.all():
            for render in design.renders:
                self._job_index[render.id] = design.id

    def folder(self, design_id: str) -> Path:
        if not valid_id(design_id):
            raise DesignNotFound(design_id)
        return self.root / design_id

    def exists(self, design_id: str) -> bool:
        return valid_id(design_id) and (self.root / design_id / "design.json").exists()

    def load(self, design_id: str) -> Design:
        path = self.folder(design_id) / "design.json"
        if not path.exists():
            raise DesignNotFound(design_id)
        return Design.model_validate(read_json(path))

    def save(self, design: Design) -> None:
        with self._lock:
            folder = self.folder(design.id)
            folder.mkdir(exist_ok=True)
            design.updated_at = time.time()
            write_json(folder / "design.json", design.model_dump(mode="json"))
            for render in design.renders:
                self._job_index[render.id] = design.id

    @contextmanager
    def update(self, design_id: str) -> Iterator[Design]:
        """Load, let the caller modify, save, all under the lock."""
        with self._lock:
            design = self.load(design_id)
            yield design
            self.save(design)

    def all(self) -> list[Design]:
        designs = []
        for path in self.root.glob("*/design.json"):
            try:
                designs.append(Design.model_validate(read_json(path)))
            except (ValueError, OSError):
                continue  # a corrupt file shouldn't take the whole gallery down
        return sorted(designs, key=lambda d: d.updated_at, reverse=True)

    def delete(self, design_id: str) -> None:
        with self._lock:
            folder = self.folder(design_id)
            if not folder.exists():
                raise DesignNotFound(design_id)
            shutil.rmtree(folder)
            self._job_index = {j: d for j, d in self._job_index.items() if d != design_id}

    def design_for_job(self, job_id: str) -> str | None:
        return self._job_index.get(job_id)
