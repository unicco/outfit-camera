"""Upload size limits .

Endpoints that accept file uploads previously read the whole body into memory
with ``await file.read()``, so an unauthenticated client could exhaust memory
with a large upload. This helper caps the bytes read.

Callers must let the raised ``HTTPException`` (413) propagate — if a handler
wraps the read in a broad ``except Exception`` that converts to 500, add an
``except HTTPException: raise`` ahead of it so the size error is not masked.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

# Single image upload (a full-body photo is a few MB).
MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB

_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB


async def read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an UploadFile fully, aborting with 413 once it exceeds ``max_bytes``.

    Reads in chunks so an oversized upload is rejected without being fully
    buffered first.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Uploaded file exceeds the {max_bytes} byte limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
