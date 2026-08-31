import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import piexif
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from PIL import Image

from ..storage.storage_factory import get_google_photos_handler
from ..schemas.base import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/google-photos", tags=["google-photos"])
CHUNK_SIZE = 1024 * 1024  # 1MB
JST = ZoneInfo("Asia/Tokyo")
MAX_BATCH_UPLOAD_CONCURRENCY = max(
    1, int(os.getenv("GOOGLE_PHOTOS_BATCH_CONCURRENCY", "3"))
)


class AuthStatusResponse(BaseModel):
    """Google Photos 認証状態のレスポンス."""

    is_authenticated: bool
    album_name: Optional[str] = None


class UploadRequest(BaseModel):
    """Google Photos アップロードリクエスト."""

    photo_url: str
    description: str = ""


class UploadResponse(BaseModel):
    """Google Photos アップロードレスポンス."""

    success: bool
    media_item_id: Optional[str] = None
    error: Optional[str] = None


class BatchPhotoMetadata(BaseModel):
    """バッチアップロード時に付与する個別メタデータ."""

    client_id: Optional[str] = None
    file_name: Optional[str] = None
    capture_time: Optional[datetime] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    album_id: Optional[str] = None
    description: Optional[str] = None


class BatchUploadResult(BaseModel):
    """バッチアップロード結果の1件分."""

    file_name: str
    client_id: Optional[str] = None
    success: bool
    media_item_id: Optional[str] = None
    error: Optional[str] = None


class BatchUploadResponse(BaseModel):
    """バッチアップロード結果."""

    success: bool
    results: list[BatchUploadResult]


@router.get("/auth-status", response_model=AuthStatusResponse)
async def get_auth_status():
    """Google Photos API の認証状態を取得."""
    try:
        handler = get_google_photos_handler()
        is_authenticated = handler.is_authenticated()

        return AuthStatusResponse(
            is_authenticated=is_authenticated,
            album_name=handler.album_name if is_authenticated else None,
        )

    except Exception as e:
        logger.error(f"Failed to get auth status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get authentication status"
        )


@router.get("/auth-url")
async def get_auth_url(redirect_uri: str = Query(default=None)):
    """Google Photos OAuth 2.0 認証 URL を取得."""
    try:
        # デフォルトのリダイレクト URI を環境に応じて設定
        if redirect_uri is None:
            import os

            base_url = os.getenv(
                "GOOGLE_REDIRECT_BASE_URL",
                "https://coordinate.unicco.app",
            )
            # router.prefix（/api/v2/google-photos）を含めないと実ルートに一致せず 404 になる
            redirect_uri = f"{base_url}{router.prefix}/oauth2callback"

        handler = get_google_photos_handler()
        auth_url = handler.initiate_auth_flow(redirect_uri)

        return {"auth_url": auth_url}

    except FileNotFoundError as e:
        logger.error(f"Credentials file not found: {e}")
        raise HTTPException(
            status_code=400,
            detail="Google Photos credentials not configured. Please add credentials file.",
        )
    except Exception as e:
        logger.error(f"Failed to initiate auth flow: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate authentication")


@router.get("/oauth2callback")
async def oauth_callback(
    code: str = Query(),
    state: str = Query(default=None),
    error: str = Query(default=None),
):
    """OAuth 2.0 コールバック処理."""
    if error:
        logger.error(f"OAuth error: {error}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required")

    if not state:
        # state は CSRF 対策。initiate_auth_flow が必ず付与するため、欠落は不正。
        raise HTTPException(status_code=400, detail="State parameter is required")

    try:
        handler = get_google_photos_handler()
        # リクエストから redirect_uri を推測（state が失われた場合のフォールバック）

        import os

        base_url = os.getenv(
            "GOOGLE_REDIRECT_BASE_URL", "https://coordinate.unicco.app"
        )
        # router.prefix（/api/v2/google-photos）を含めて get_auth_url と一致させる
        redirect_uri = f"{base_url}{router.prefix}/oauth2callback"

        success = handler.complete_auth_flow(code, state, redirect_uri=redirect_uri)

        if success:
            # 認証成功時はUIへリダイレクト
            import os

            ui_base_url = os.getenv("UI_BASE_URL", "https://coordinate.unicco.app")
            return RedirectResponse(
                url=f"{ui_base_url}/google-photos/auth-success", status_code=302
            )
        else:
            raise HTTPException(
                status_code=400, detail="Failed to complete authentication"
            )

    except HTTPException:
        # 明示的な 4xx（state 不一致など）はそのまま返す（500 に握り潰さない）
        raise
    except Exception as e:
        logger.error(f"Failed to complete auth flow: {e}")
        raise HTTPException(status_code=500, detail="Authentication completion failed")


@router.get("/auth-success")
async def auth_success():
    """認証成功ページ."""
    return {
        "message": "Google Photos authentication successful! You can close this window."
    }


@router.post("/upload", response_model=UploadResponse)
async def upload_photo(request: UploadRequest):
    """写真を Google Photos にアップロード."""
    try:
        handler = get_google_photos_handler()

        if not handler.is_authenticated():
            return UploadResponse(
                success=False, error="Not authenticated with Google Photos"
            )

        media_item_id = handler.upload_photo_from_url(
            request.photo_url, request.description
        )

        if media_item_id:
            logger.info(
                f"Successfully uploaded photo to Google Photos: {media_item_id}"
            )
            return UploadResponse(success=True, media_item_id=media_item_id)
        else:
            return UploadResponse(
                success=False, error="Failed to upload photo to Google Photos"
            )

    except Exception as e:
        logger.error(f"Failed to upload photo: {e}")
        return UploadResponse(success=False, error=str(e))


@router.post("/batch-upload", response_model=BatchUploadResponse)
async def batch_upload_photos(
    metadata_json: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """複数の写真をアップロードし、日時や位置情報を一括設定."""
    handler = get_google_photos_handler()

    if not handler.is_authenticated():
        raise HTTPException(
            status_code=400, detail="Not authenticated with Google Photos"
        )

    metadata_items = _parse_metadata_payload(metadata_json, len(files))

    paired_items = list(zip(files, metadata_items))
    if not paired_items:
        return BatchUploadResponse(success=True, results=[])

    semaphore = asyncio.Semaphore(MAX_BATCH_UPLOAD_CONCURRENCY)

    async def _upload_with_limit(
        index: int, upload_file: UploadFile, metadata: BatchPhotoMetadata
    ) -> tuple[int, BatchUploadResult]:
        async with semaphore:
            result = await _process_single_upload(handler, upload_file, metadata)
        return index, result

    tasks = [
        _upload_with_limit(index, upload_file, metadata)
        for index, (upload_file, metadata) in enumerate(paired_items)
    ]
    ordered_results: list[BatchUploadResult] = []
    overall_success = True

    completed = await asyncio.gather(*tasks)
    completed.sort(key=lambda item: item[0])

    for _, result in completed:
        ordered_results.append(result)
        if not result.success:
            overall_success = False

    return BatchUploadResponse(success=overall_success, results=ordered_results)


@router.post("/logout")
async def logout():
    """Google Photos 認証トークンを削除."""
    try:
        handler = get_google_photos_handler()

        # トークンファイルを削除
        from pathlib import Path

        token_file = Path(handler.token_file)
        if token_file.exists():
            token_file.unlink()

        return {"message": "Successfully logged out from Google Photos"}

    except Exception as e:
        logger.error(f"Failed to logout: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


def _parse_metadata_payload(
    metadata_json: str, expected_length: int
) -> list[BatchPhotoMetadata]:
    """メタデータ JSON 文字列を検証してパース."""
    try:
        items_raw = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse metadata payload: %s", exc)
        raise HTTPException(status_code=400, detail="metadata must be a JSON array")

    if not isinstance(items_raw, list):
        raise HTTPException(status_code=400, detail="metadata must be a JSON array")

    parsed_items = [BatchPhotoMetadata.model_validate(item) for item in items_raw]

    if len(parsed_items) != expected_length:
        raise HTTPException(
            status_code=400,
            detail="Number of metadata entries must match number of files",
        )

    return parsed_items


async def _process_single_upload(
    handler, upload_file: UploadFile, metadata: BatchPhotoMetadata
) -> BatchUploadResult:
    """単一ファイルとメタデータを処理."""
    normalized_time = _normalize_capture_time(metadata.capture_time)
    file_name = metadata.file_name or upload_file.filename or "uploaded_photo.jpg"

    temp_path: Optional[Path] = None

    try:
        suffix = Path(upload_file.filename or file_name).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                temp_file.write(chunk)
            temp_path = Path(temp_file.name)

        _apply_exif_metadata(temp_path, metadata, normalized_time)

        description = _build_description(metadata, normalized_time)

        # album_id を渡さなければ handler が GOOGLE_PHOTOS_BATCH_ALBUM_ID を使う
        media_item_id = handler.upload_photo(
            str(temp_path), description=description, album_id=metadata.album_id
        )
        if media_item_id:
            logger.info("Batch upload succeeded for %s", file_name)
            return BatchUploadResult(
                file_name=file_name,
                client_id=metadata.client_id,
                success=True,
                media_item_id=media_item_id,
            )

        return BatchUploadResult(
            file_name=file_name,
            client_id=metadata.client_id,
            success=False,
            error="Failed to upload photo to Google Photos",
        )

    except Exception as exc:
        logger.error("Batch upload failed for %s: %s", file_name, exc)
        return BatchUploadResult(
            file_name=file_name,
            client_id=metadata.client_id,
            success=False,
            error=str(exc),
        )
    finally:
        try:
            await upload_file.close()
        except Exception:
            logger.debug("Upload file close skipped for %s", file_name)
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove temp file %s", temp_path)


def _normalize_capture_time(capture_time: Optional[datetime]) -> Optional[datetime]:
    """キャプチャ時刻をJST基準に揃える."""
    if capture_time is None:
        return None

    if capture_time.tzinfo is None:
        return capture_time.replace(tzinfo=JST)

    return capture_time.astimezone(JST)


def _apply_exif_metadata(
    temp_path: Path,
    metadata: BatchPhotoMetadata,
    capture_time: Optional[datetime],
) -> None:
    """EXIF へ日時・GPS情報を書き込み."""
    has_capture_time = capture_time is not None
    has_location = metadata.latitude is not None and metadata.longitude is not None

    if not has_capture_time and not has_location:
        return

    with Image.open(temp_path) as image:
        exif_bytes = image.info.get("exif")
        if exif_bytes:
            try:
                exif_dict = piexif.load(exif_bytes)
            except Exception:
                exif_dict = {
                    "0th": {},
                    "Exif": {},
                    "GPS": {},
                    "1st": {},
                    "thumbnail": None,
                }
        else:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        if has_capture_time and capture_time:
            dt_str = capture_time.strftime("%Y:%m:%d %H:%M:%S")
            dt_bytes = dt_str.encode()
            exif_dict.setdefault("Exif", {})
            exif_dict.setdefault("0th", {})
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt_bytes
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_bytes
            exif_dict["0th"][piexif.ImageIFD.DateTime] = dt_bytes

        if (
            has_location
            and metadata.latitude is not None
            and metadata.longitude is not None
        ):
            lat_ref, lat_value = _decimal_to_dms(metadata.latitude, b"N", b"S")
            lon_ref, lon_value = _decimal_to_dms(metadata.longitude, b"E", b"W")
            exif_dict.setdefault("GPS", {})
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_ref
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_value
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lon_ref
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_value

        exif_output = piexif.dump(exif_dict)
        image_format = image.format or "JPEG"
        image.save(temp_path, format=image_format, exif=exif_output)


def _decimal_to_dms(value: float, positive_ref: bytes, negative_ref: bytes):
    """座標を度分秒へ変換."""
    ref = positive_ref if value >= 0 else negative_ref
    abs_value = abs(value)

    degrees = int(abs_value)
    minutes_float = (abs_value - degrees) * 60
    minutes = int(minutes_float)
    seconds_float = (minutes_float - minutes) * 60
    seconds = int(round(seconds_float * 1000))

    return ref, (
        (degrees, 1),
        (minutes, 1),
        (seconds, 1000),
    )


def _build_description(
    metadata: BatchPhotoMetadata, capture_time: Optional[datetime]
) -> str:
    """Google Photos の description に残す補助情報を生成."""
    parts: list[str] = []
    if metadata.description:
        parts.append(metadata.description)
    if metadata.location_name:
        parts.append(metadata.location_name)
    if capture_time:
        parts.append(capture_time.strftime("%Y-%m-%d %H:%M:%S JST"))
    if metadata.latitude is not None and metadata.longitude is not None:
        parts.append(f"{metadata.latitude:.5f}, {metadata.longitude:.5f}")

    parts.append("Uploaded via Coordinate Recorder batch tool")
    return " | ".join(parts)
