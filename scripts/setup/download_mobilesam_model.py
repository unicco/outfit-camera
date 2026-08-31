#!/usr/bin/env python3
"""MobileSAM モデルファイルのダウンロードスクリプト
複数のソースから自動的にダウンロードを試みる.
"""

import importlib.util
import logging
import os
import sys
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MobileSAMDownloader:
    """MobileSAM モデルのダウンローダー."""

    # モデルのダウンロードソース（優先順位順）
    DOWNLOAD_SOURCES = [
        {
            "name": "Google Drive - MobileSAMv2",
            "type": "gdrive",
            "id": "1dE-YAG-1mFCBmao2rHDp0n-PP4eH7SjE",
            "filename": "mobile_sam.pt",
        },
        {
            "name": "Hugging Face - MobileSAM",
            "type": "direct",
            "url": "https://huggingface.co/datasets/tianrun-chen/sam-1.0/resolve/main/mobile_sam.pt",
            "filename": "mobile_sam.pt",
        },
        {
            "name": "GitHub Release (fallback)",
            "type": "direct",
            "url": "https://github.com/ChaoningZhang/MobileSAM/releases/download/MobileSAM/mobile_sam.pt",
            "filename": "mobile_sam.pt",
        },
    ]

    def __init__(self, target_dir: str = "~/.cache/mobilesam"):
        """初期化.

        Args:
            target_dir: モデルを保存するディレクトリ

        """
        self.target_dir = Path(target_dir).expanduser()
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def download_model(self, force: bool = False) -> Path:
        """モデルをダウンロード.

        Args:
            force: 既存のファイルを強制的に上書き

        Returns:
            ダウンロードしたモデルファイルのパス

        """
        target_path = self.target_dir / "mobile_sam.pt"

        # 既にファイルが存在する場合
        if target_path.exists() and not force:
            logger.info(f"モデルファイルは既に存在します: {target_path}")
            if self._verify_model(target_path):
                return target_path
            else:
                logger.warning(
                    "既存のモデルファイルが破損している可能性があります。再ダウンロードします。"
                )

        # 各ソースから順番にダウンロードを試みる
        for source in self.DOWNLOAD_SOURCES:
            logger.info(f"\n{source['name']} からダウンロードを試みています...")

            try:
                if source["type"] == "gdrive":
                    success = self._download_from_gdrive(source["id"], target_path)
                else:
                    success = self._download_direct(source["url"], target_path)

                if success and self._verify_model(target_path):
                    logger.info(f"✅ ダウンロード成功: {target_path}")
                    return target_path

            except Exception as e:
                logger.error(f"❌ ダウンロード失敗: {e}")
                if target_path.exists():
                    target_path.unlink()  # 失敗したファイルを削除

        raise RuntimeError("すべてのダウンロードソースで失敗しました")

    def _download_from_gdrive(self, file_id: str, target_path: Path) -> bool:
        """Google Drive からダウンロード."""
        try:
            import gdown

            url = f"https://drive.google.com/uc?id={file_id}"
            gdown.download(url, str(target_path), quiet=False)
            return target_path.exists()
        except ImportError:
            logger.warning(
                "gdown がインストールされていません。pip install gdown を実行してください。"
            )
            return False
        except Exception as e:
            logger.error(f"Google Drive ダウンロードエラー: {e}")
            return False

    def _download_direct(self, url: str, target_path: Path) -> bool:
        """直接 URL からダウンロード."""
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(target_path, "wb") as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = downloaded / total_size * 100
                            print(f"\rダウンロード中: {progress:.1f}%", end="")

            print()  # 改行
            return True

        except Exception as e:
            logger.error(f"直接ダウンロードエラー: {e}")
            return False

    def _verify_model(self, model_path: Path) -> bool:
        """モデルファイルの検証."""
        if not model_path.exists():
            return False

        # ファイルサイズをチェック（MobileSAM は約 5-10MB）
        file_size = model_path.stat().st_size
        if file_size < 1_000_000:  # 1MB 未満は異常
            logger.warning(f"モデルファイルが小さすぎます: {file_size} bytes")
            return False

        if file_size > 100_000_000:  # 100MB 以上は異常
            logger.warning(f"モデルファイルが大きすぎます: {file_size} bytes")
            return False

        # PyTorch モデルとして読み込めるか確認
        try:
            import torch

            state_dict = torch.load(model_path, map_location="cpu", weights_only=True)
            logger.info(f"モデルの検証成功: {len(state_dict)} 個のパラメータ")
            return True
        except Exception as e:
            logger.error(f"モデルの読み込みエラー: {e}")
            return False


def main():
    """メイン関数."""
    import argparse

    parser = argparse.ArgumentParser(description="MobileSAM モデルをダウンロード")
    parser.add_argument(
        "--target-dir", default="~/.cache/mobilesam", help="モデルの保存先ディレクトリ"
    )
    parser.add_argument(
        "--force", action="store_true", help="既存のファイルを強制的に上書き"
    )

    args = parser.parse_args()

    # gdown のインストール確認
    if importlib.util.find_spec("gdown") is None:
        logger.warning("gdown がインストールされていません。インストールします...")
        os.system("pip install gdown")

    downloader = MobileSAMDownloader(args.target_dir)

    try:
        model_path = downloader.download_model(force=args.force)
        print(f"\n✅ MobileSAM モデルを正常にダウンロードしました: {model_path}")

        # 使用例を表示
        print("\n使用例:")
        print("```python")
        print("from mobile_sam import sam_model_registry, SamPredictor")
        print("")
        print(f'model_path = "{model_path}"')
        print('mobile_sam = sam_model_registry["vit_t"](checkpoint=model_path)')
        print("mobile_sam.eval()")
        print("```")

    except Exception as e:
        print(f"\n❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
