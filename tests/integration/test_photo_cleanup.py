#!/usr/bin/env python3
"""写真クリーニング機能の統合テスト。.

cleanup-orphaned-photos.py スクリプトの動作を検証します。
"""

# ruff: noqa: E402

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

pytestmark = pytest.mark.integration

try:
    from app.models import Base, Photo
    from scripts.maintenance.cleanup_orphaned_photos import (
        cleanup_orphaned_photos,
        get_camera_photos,
        parse_photo_filename,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - app モジュール非対応環境
    pytest.skip(
        f"photo cleanup 依存モジュールが不足しているためスキップ: {exc}",
        allow_module_level=True,
    )

# JST タイムゾーン
JST = timezone(timedelta(hours=9))


class TestPhotoCleanup:
    """写真クリーニング機能のテストクラス."""

    @pytest.fixture
    def temp_photos_dir(self):
        """一時的な写真ディレクトリを作成."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_db(self):
        """テスト用のデータベースを作成."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        yield engine
        engine.dispose()

    def create_test_photo_file(self, photos_dir: Path, days_ago: int) -> Path:
        """テスト用の写真ファイルを作成."""
        # 指定日数前の日時を計算
        photo_time = datetime.now(JST) - timedelta(days=days_ago)
        filename = photo_time.strftime("photo_%Y%m%d_%H%M%S.jpg")

        file_path = photos_dir / filename
        file_path.write_bytes(b"dummy image data")

        # ファイルの更新時刻も設定
        timestamp = photo_time.timestamp()
        os.utime(file_path, (timestamp, timestamp))

        return file_path

    def add_photo_to_db(self, session: Session, filename: str) -> Photo:
        """データベースに写真を追加."""
        photo = Photo(
            filename=filename,
            file_path=f"photos/{filename}",
            captured_at=datetime.now(JST),
            source="test",
        )
        session.add(photo)
        session.commit()
        return photo

    def test_parse_photo_filename(self):
        """ファイル名解析のテスト."""
        # 正常なファイル名
        dt = parse_photo_filename("photo_20240101_123456.jpg")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.minute == 34
        assert dt.second == 56
        assert dt.tzinfo == JST

        # 不正なファイル名
        assert parse_photo_filename("invalid.jpg") is None
        assert parse_photo_filename("photo_invalid_123456.jpg") is None
        assert parse_photo_filename("photo_20240101_999999.jpg") is None

    def test_get_camera_photos(self, temp_photos_dir):
        """カメラ写真取得のテスト."""
        # テスト用ファイルを作成
        _ = self.create_test_photo_file(temp_photos_dir, 5)
        _ = self.create_test_photo_file(temp_photos_dir, 10)

        # 関係ないファイルも作成
        (temp_photos_dir / "not_a_photo.txt").write_text("test")
        (temp_photos_dir / "different_format.png").write_bytes(b"png data")

        # 写真を取得
        photos = get_camera_photos(temp_photos_dir)

        # 検証
        assert len(photos) == 2
        assert all(path.name.startswith("photo_") for path, _ in photos)
        assert all(path.suffix == ".jpg" for path, _ in photos)

    def test_cleanup_orphaned_photos_dry_run(self, temp_photos_dir, test_db):
        """ドライランモードのテスト."""
        # テスト用ファイルを作成
        old_photo = self.create_test_photo_file(temp_photos_dir, 10)  # 10日前
        recent_photo = self.create_test_photo_file(temp_photos_dir, 3)  # 3日前

        # データベースに1つだけ登録
        with Session(test_db) as session:
            self.add_photo_to_db(session, recent_photo.name)

        # クリーニング実行（ドライラン）
        total, target, deleted = cleanup_orphaned_photos(
            photos_dir=temp_photos_dir,
            db_url=str(test_db.url),
            retention_days=7,
            dry_run=True,
        )

        # 検証
        assert total == 2  # 総ファイル数
        assert target == 1  # 削除対象（古いファイルのみ）
        assert deleted == 1  # ドライランなので実際には削除されない

        # ファイルが実際に残っていることを確認
        assert old_photo.exists()
        assert recent_photo.exists()

    def test_cleanup_orphaned_photos_actual_delete(self, temp_photos_dir, test_db):
        """実際の削除のテスト."""
        # テスト用ファイルを作成
        old_orphan = self.create_test_photo_file(
            temp_photos_dir, 10
        )  # 10日前、DB未登録
        old_saved = self.create_test_photo_file(
            temp_photos_dir, 15
        )  # 15日前、DB登録済
        recent_orphan = self.create_test_photo_file(
            temp_photos_dir, 3
        )  # 3日前、DB未登録

        # データベースに登録
        with Session(test_db) as session:
            self.add_photo_to_db(session, old_saved.name)

        # クリーニング実行（実削除）
        total, target, deleted = cleanup_orphaned_photos(
            photos_dir=temp_photos_dir,
            db_url=str(test_db.url),
            retention_days=7,
            dry_run=False,
        )

        # 検証
        assert total == 3  # 総ファイル数
        assert target == 1  # 削除対象（古い未保存ファイルのみ）
        assert deleted == 1  # 実際に削除された数

        # ファイルの存在確認
        assert not old_orphan.exists()  # 削除された
        assert old_saved.exists()  # DB登録済なので残る
        assert recent_orphan.exists()  # 保持期間内なので残る

    def test_cleanup_with_no_files(self, temp_photos_dir, test_db):
        """ファイルがない場合のテスト."""
        total, target, deleted = cleanup_orphaned_photos(
            photos_dir=temp_photos_dir,
            db_url=str(test_db.url),
            retention_days=7,
            dry_run=False,
        )

        assert total == 0
        assert target == 0
        assert deleted == 0

    def test_cleanup_with_nonexistent_directory(self, test_db):
        """存在しないディレクトリのテスト."""
        nonexistent_dir = Path("/nonexistent/directory")

        total, target, deleted = cleanup_orphaned_photos(
            photos_dir=nonexistent_dir,
            db_url=str(test_db.url),
            retention_days=7,
            dry_run=False,
        )

        assert total == 0
        assert target == 0
        assert deleted == 0

    @patch.dict(os.environ, {"CLEANUP_ENABLED": "false"})
    def test_cleanup_disabled(self, temp_photos_dir, test_db):
        """クリーニング無効化のテスト."""
        # メイン関数をインポートしてテスト
        from scripts.maintenance.cleanup_orphaned_photos import main

        # 引数をモック
        with patch("sys.argv", ["cleanup-orphaned-photos.py"]):
            # 環境変数で無効化されている場合は何も実行されない
            main()  # エラーが発生しないことを確認


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
