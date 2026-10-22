"""API routers. Each module exposes `router`; main.create_app includes them."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile


def read_upload(file: UploadFile, max_mb: int) -> bytes:
    limit = max_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Image is larger than {max_mb} MB")
    if not data:
        raise HTTPException(status_code=422, detail="Empty upload")
    return data

