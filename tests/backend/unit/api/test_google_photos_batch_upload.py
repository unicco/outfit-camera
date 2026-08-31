import io
import json
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from app.routers import google_photos
from app.routers.google_photos import BatchUploadResult


@pytest.fixture
def app() -> FastAPI:
    """Create a FastAPI app that only mounts the Google Photos router."""
    app = FastAPI()
    app.include_router(google_photos.router)
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Expose a TestClient for the Google Photos router."""
    with TestClient(app) as test_client:
        yield test_client


def test_batch_upload_requires_authentication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure authentication is required before processing a batch upload."""
    handler = SimpleNamespace(is_authenticated=lambda: False)
    monkeypatch.setattr(google_photos, "get_google_photos_handler", lambda: handler)

    response = client.post(
        "/api/v2/google-photos/batch-upload",
        data={"metadata_json": json.dumps([{"clientId": "photo-1"}])},
        files=[("files", ("photo-1.jpg", b"data", "image/jpeg"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Not authenticated with Google Photos"


def test_batch_upload_processes_files_and_returns_results(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that uploaded files are processed and ordered results are returned."""
    handler = SimpleNamespace(is_authenticated=lambda: True)
    monkeypatch.setattr(google_photos, "get_google_photos_handler", lambda: handler)

    captured_client_ids: list[str | None] = []

    async def fake_process_single_upload(handler_obj, upload_file, metadata):
        assert handler_obj is handler
        captured_client_ids.append(metadata.client_id)
        body = await upload_file.read()
        assert body in {b"photo-one", b"photo-two"}
        return BatchUploadResult(
            file_name=metadata.file_name or (upload_file.filename or "photo"),
            client_id=metadata.client_id,
            success=True,
            media_item_id=f"media-{metadata.client_id}",
        )

    monkeypatch.setattr(
        google_photos, "_process_single_upload", fake_process_single_upload
    )

    metadata_payload = [
        {
            "clientId": "photo-1",
            "fileName": "photo-1.jpg",
            "captureTime": "2024-01-05T12:00:00+09:00",
            "latitude": 35.0,
            "longitude": 139.0,
        },
        {
            "clientId": "photo-2",
            "fileName": "photo-2.jpg",
            "captureTime": "2024-02-10T12:00:00+09:00",
        },
    ]

    response = client.post(
        "/api/v2/google-photos/batch-upload",
        data={"metadata_json": json.dumps(metadata_payload)},
        files=[
            ("files", ("photo-1.jpg", b"photo-one", "image/jpeg")),
            ("files", ("photo-2.jpg", b"photo-two", "image/jpeg")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert [item["fileName"] for item in payload["results"]] == [
        "photo-1.jpg",
        "photo-2.jpg",
    ]
    assert captured_client_ids == ["photo-1", "photo-2"]


def test_batch_upload_rejects_metadata_length_mismatch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return a 400 when metadata entries do not match the number of files."""
    handler = SimpleNamespace(is_authenticated=lambda: True)
    monkeypatch.setattr(google_photos, "get_google_photos_handler", lambda: handler)

    response = client.post(
        "/api/v2/google-photos/batch-upload",
        data={"metadata_json": json.dumps([{"clientId": "photo-1"}])},
        files=[
            ("files", ("photo-1.jpg", b"photo-one", "image/jpeg")),
            ("files", ("photo-2.jpg", b"photo-two", "image/jpeg")),
        ],
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Number of metadata entries must match number of files"
    )


@pytest.mark.asyncio
async def test_process_single_upload_passes_album_id_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """album_id は handler にそのまま渡す（既定値の解決は storage 側の責務）.

    router 側で既定アルバムを解決してしまうと、env を見る storage 側のフォールバックと
    二重管理になる。metadata.album_id が None のときは None のまま渡すのが正しい。
    """
    captured: dict[str, object] = {}

    handler = SimpleNamespace(
        upload_photo=lambda path, description, album_id: captured.update(
            path=path, description=description, album_id=album_id
        )
        or "MEDIA_ITEM_ID"
    )
    monkeypatch.setattr(google_photos, "_apply_exif_metadata", lambda *a, **kw: None)

    for given, expected in ((None, None), ("EXPLICIT_ALBUM", "EXPLICIT_ALBUM")):
        upload = UploadFile(filename="photo.jpg", file=io.BytesIO(b"photo-bytes"))
        metadata = google_photos.BatchPhotoMetadata(client_id="c1", album_id=given)

        result = await google_photos._process_single_upload(handler, upload, metadata)

        assert result.success is True
        assert captured["album_id"] == expected
