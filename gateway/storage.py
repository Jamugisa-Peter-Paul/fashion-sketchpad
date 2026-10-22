"""Files under DATA_DIR. Everything is plain files + JSON so it can be inspected and backed up with rsync.

    DATA_DIR/uploads/<clean_id>/   cleaned sketch waiting to be used by a design (purged after a few days)
    DATA_DIR/designs/<design_id>/  see docs/ARCHITECTURE.md
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

_ID = re.compile(r"^[0-9a-f]{16}$")
UPLOAD_MAX_AGE_S = 3 * 24 * 3600


def new_id() -> str:
    return secrets.token_hex(8)


def valid_id(value: str) -> bool:
    return bool(_ID.match(value))


def write_json(path: Path, data: Any) -> None:
    """Atomic write so a crash mid-write never leaves a half-written JSON file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Storage:
    def __init__(self, data_dir: Path) -> None:
        self.uploads = data_dir / "uploads"
        self.designs = data_dir / "designs"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.designs.mkdir(parents=True, exist_ok=True)

    def upload_dir(self, clean_id: str) -> Path | None:
        """Existing upload folder for an id, or None (also for malformed ids)."""
        if not valid_id(clean_id):
            return None
        path = self.uploads / clean_id
        return path if path.is_dir() else None

    def new_upload_dir(self) -> tuple[str, Path]:
        clean_id = new_id()
        path = self.uploads / clean_id
        path.mkdir()
        return clean_id, path

    def purge_old_uploads(self, max_age_s: int = UPLOAD_MAX_AGE_S) -> int:
        cutoff = time.time() - max_age_s
        removed = 0
        for path in self.uploads.iterdir():
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        return removed
