#!/usr/bin/env python3
"""ワードローブアイテムを全削除するスクリプト.

このスクリプトはデータベースからすべてのワードローブアイテムを削除します。
注意: この操作は取り消せません。
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "api"))

# 環境変数をファイルから読み込み
from dotenv import load_dotenv

# First load .env.common for shared settings
env_common_path = project_root / ".env.common"
if env_common_path.exists():
    load_dotenv(env_common_path)

# Then load .env to override with session-specific settings
load_dotenv(project_root / ".env")

# 環境変数を設定（.envの値を優先）
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db"
    )

from app.database import SessionLocal
from app.wardrobe_models import ClothingItem


def clear_all_wardrobe_items(auto_confirm=False):
    """すべてのワードローブアイテムを削除."""
    print("🚨 ワードローブアイテム全削除スクリプト")
    print("⚠️  この操作はすべてのワードローブデータを削除します！")

    # 確認プロンプト
    if auto_confirm:
        print("自動確認モード: 削除を実行します")
        confirm = "yes"
    else:
        confirm = input("本当に削除しますか？ (yes/no): ")

    if confirm.lower() != "yes":
        print("❌ 削除をキャンセルしました")
        return False

    try:
        with SessionLocal() as db:
            # すべてのワードローブアイテムを取得
            items = db.query(ClothingItem).all()
            item_count = len(items)

            print(f"📊 削除対象: {item_count} 個のアイテム")

            if item_count == 0:
                print("✅ ワードローブは既に空です")
                return True

            # 最終確認
            if auto_confirm:
                print(f"自動確認モード: {item_count} 個のアイテムを削除します")
                final_confirm = "DELETE"
            else:
                final_confirm = input(
                    f"本当に {item_count} 個のアイテムを削除しますか？ (DELETE): "
                )

            if final_confirm != "DELETE":
                print("❌ 削除をキャンセルしました")
                return False

            # 削除実行
            print("🗑️  削除を実行中...")
            deleted_count = db.query(ClothingItem).delete()
            db.commit()

            print(f"✅ 削除完了: {deleted_count} 個のアイテムを削除しました")
            return True

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return False


def verify_deletion():
    """削除確認."""
    try:
        with SessionLocal() as db:
            remaining_count = db.query(ClothingItem).count()
            if remaining_count == 0:
                print("✅ 削除確認: ワードローブアイテムは0個です")
                return True
            else:
                print(f"⚠️  削除確認: まだ {remaining_count} 個のアイテムが残っています")
                return False
    except Exception as e:
        print(f"❌ 確認エラー: {e}")
        return False


if __name__ == "__main__":
    import sys

    auto_confirm = "--auto-confirm" in sys.argv

    print("=" * 50)
    success = clear_all_wardrobe_items(auto_confirm=auto_confirm)

    if success:
        print("\n" + "=" * 50)
        print("🔍 削除確認中...")
        verify_deletion()

        print("\n" + "=" * 50)
        print("💡 次のステップ:")
        print("   1. 新しいワードローブ写真をアップロード")
        print("   2. AI検出でワードローブマッチングをテスト")
        print("   3. 必要に応じて埋め込みキャッシュを構築")

    print("=" * 50)
