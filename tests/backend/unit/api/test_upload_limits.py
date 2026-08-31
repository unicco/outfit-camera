"""Tests for upload size limits ."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app.upload_limits import read_upload_capped


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="f.bin", file=io.BytesIO(data))


@pytest.mark.asyncio
async def test_read_within_limit_returns_all_bytes() -> None:
    data = b"x" * 1000
    result = await read_upload_capped(_upload(data), max_bytes=2000)
    assert result == data


@pytest.mark.asyncio
async def test_read_at_exactly_limit_is_allowed() -> None:
    data = b"y" * 2000
    result = await read_upload_capped(_upload(data), max_bytes=2000)
    assert len(result) == 2000


@pytest.mark.asyncio
async def test_read_over_limit_raises_413() -> None:
    data = b"z" * 3000
    with pytest.raises(HTTPException) as exc_info:
        await read_upload_capped(_upload(data), max_bytes=2000)
    assert exc_info.value.status_code == 413
