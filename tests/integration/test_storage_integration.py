"""ストレージハンドラー統合テスト（URL生成機能のみ）."""

import pytest
import uuid

from app.storage.storage_factory import get_storage_handler, clear_handlers
from app.storage.local_storage import LocalStorageHandler
from app.storage.gcs_storage import GCSStorageHandler


class TestStorageIntegration:
    """ストレージハンドラーの統合テスト（URL生成とバリデーション）."""

    # temp_photos_dir fixture removed - no longer needed

    @pytest.fixture
    def reset_storage_handler(self):
        """各テストの前後でストレージハンドラーをリセット."""
        clear_handlers()
        yield
        clear_handlers()

    def test_local_storage_handler_url_generation(
        self, reset_storage_handler, monkeypatch
    ):
        """LocalStorageHandler の URL 生成テスト."""
        # 環境変数を設定
        monkeypatch.setenv("STORAGE_TYPE", "local")
        monkeypatch.setenv("API_URL", "http://localhost:8000")
        clear_handlers()

        handler = get_storage_handler()
        assert isinstance(handler, LocalStorageHandler)

        # URL 生成のテスト
        photo_id = str(uuid.uuid4())
        url = handler.get_photo_url(photo_id)
        assert url == f"http://localhost:8000/photos/{photo_id}"

        # ファイル URL の生成
        file_url = handler.get_file_url(photo_id)
        assert file_url == f"http://localhost:8000/photos/{photo_id}"

    def test_gcs_storage_handler_url_generation(
        self, reset_storage_handler, monkeypatch
    ):
        """GCSStorageHandler の URL 生成テスト."""
        # 環境変数を設定
        monkeypatch.setenv("STORAGE_TYPE", "gcs")
        monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")
        clear_handlers()

        handler = get_storage_handler()
        assert isinstance(handler, GCSStorageHandler)

        # URL 生成のテスト
        photo_id = str(uuid.uuid4())
        url = handler.get_photo_url(photo_id)
        assert (
            url == f"https://storage.googleapis.com/test-bucket/photos/{photo_id}.jpg"
        )

        # ファイル URL の生成
        file_url = handler.get_file_url(photo_id)
        assert (
            file_url
            == f"https://storage.googleapis.com/test-bucket/photos/{photo_id}.jpg"
        )

    def test_storage_handler_singleton_pattern(
        self, reset_storage_handler, monkeypatch
    ):
        """ストレージハンドラーのシングルトンパターンテスト."""
        monkeypatch.setenv("STORAGE_TYPE", "local")

        # 複数回呼び出しても同じインスタンスが返される
        handler1 = get_storage_handler()
        handler2 = get_storage_handler()

        assert handler1 is handler2

        # 同じ設定を持つことを確認
        assert handler1.api_url == handler2.api_url

    def test_photo_id_validation(self, reset_storage_handler, monkeypatch):
        """写真 ID バリデーションのテスト."""
        monkeypatch.setenv("STORAGE_TYPE", "local")
        clear_handlers()

        handler = get_storage_handler()

        # 有効な UUID
        valid_id = str(uuid.uuid4())
        validated = handler.validate_photo_id(valid_id)
        assert validated == valid_id

        # 拡張子付き UUID
        with_ext = f"{valid_id}.jpg"
        validated = handler.validate_photo_id(with_ext)
        assert validated == valid_id

        # 無効な UUID
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            handler.validate_photo_id("invalid-uuid")
        assert exc_info.value.status_code == 400

    # test_photo_url_generation is now covered by the individual handler tests above
