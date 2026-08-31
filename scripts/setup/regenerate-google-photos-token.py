#!/usr/bin/env python3
"""Google Photos API トークンを再生成するスクリプト.

既存のトークンを削除し、新しいスコープで再認証を行います。
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path

# プロジェクトルートを Python パスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()


def main():
    """Google Photos トークンを再生成."""
    print("=== Google Photos トークン再生成スクリプト ===")
    print()

    # 既存のトークンファイルを確認
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "google_photos_token.json")
    token_path = Path(token_file)

    if token_path.exists():
        print(f"既存のトークンファイルが見つかりました: {token_path}")
        response = input("削除して再生成しますか？ (y/N): ")
        if response.lower() != "y":
            print("キャンセルしました。")
            return

        # 既存のトークンを削除
        token_path.unlink()
        print(f"✅ 既存のトークンファイルを削除しました: {token_path}")
    else:
        print(f"既存のトークンファイルは見つかりません: {token_path}")

    print()
    print("新しいトークンを生成するには、以下の手順を実行してください：")
    print()
    print("1. 本番環境で以下のコマンドを実行:")
    print("   python3 -m api.app.storage.google_photos_storage")
    print()
    print("2. 表示される URL をブラウザで開く")
    print()
    print("3. Google アカウントでログイン")
    print()
    print("4. 以下の権限を許可:")
    print("   - Google フォト ライブラリの表示")
    print("   - Google フォト ライブラリへの追加")
    print("   - Google フォト ライブラリ内のアイテムの共有")
    print()
    print("5. 認証コードをコピーしてターミナルに貼り付け")
    print()
    print("6. トークンファイルが生成されることを確認")
    print()
    print("注意: 新しいスコープが追加されているため、")
    print(
        "      既存の認証済アプリケーションをリセットする必要があるかもしれません。"
    )
    print(
        "      Google アカウント設定 > セキュリティ > サードパーティ製アプリのアクセス"
    )
    print("      で確認してください。")


if __name__ == "__main__":
    main()
