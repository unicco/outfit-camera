#!/usr/bin/env python3
"""Playwrightを使用してUIの実際の状態を確認."""

import asyncio
import os

from playwright.async_api import async_playwright


async def check_ui_with_playwright() -> None:
    """Playwrightでui確認 (Issue 260対応: メモリ最適化版)."""
    print("🎭 Playwright UI確認開始 (Issue 260対応)")

    async with async_playwright() as p:
        # Issue 260対応: メモリ使用量削減のためヘッドレスモード + リソース制限
        browser = await p.chromium.launch(
            headless=True,  # メモリ使用量削減のためヘッドレスモード
            args=[
                "--max-old-space-size=256",  # Node.js ヒープサイズ制限
                "--memory-pressure-off",  # メモリプレッシャー無効化
                "--no-sandbox",  # サンドボックス無効化
                "--disable-dev-shm-usage",  # /dev/shm 使用無効化
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ],
        )

        # Issue 260対応: ブラウザコンテキストでリソース制限
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("📱 UIページにアクセス中...")
            # Issue 260対応: about:blank 無限起動防止のため、明示的なタイムアウトと待機戦略を設定
            await page.goto(
                "http://localhost:3000", wait_until="domcontentloaded", timeout=15000
            )

            # ネットワークアイドル待機を別途実行（タイムアウト制御）
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                print("⚠️ ネットワークアイドル待機がタイムアウトしましたが続行します")

            # ページタイトル確認
            title = await page.title()
            print(f"📄 ページタイトル: {title}")

            # スクリーンショットを撮影
            project_root = os.environ.get(
                "PROJECT_ROOT",
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            )
            logs_dir = os.path.join(project_root, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            screenshot_path = os.path.join(logs_dir, "ui_state_check.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"📸 スクリーンショット保存: {screenshot_path}")

            # レコードカードの数を確認
            record_cards = await page.locator(
                '[data-testid="outfit-card"], .outfit-card, [class*="card"], [class*="record"]'
            ).count()
            print(f"🃏 レコードカード数: {record_cards}")

            # 画像要素の確認
            images = await page.locator("img").count()
            print(f"🖼️ 画像要素数: {images}")

            if images > 0:
                print("🔍 画像要素の詳細:")
                for i in range(min(images, 5)):  # 最初の5個まで
                    img = page.locator("img").nth(i)
                    src = await img.get_attribute("src")
                    alt = await img.get_attribute("alt")
                    print(f"   画像 {i + 1}: src='{src}', alt='{alt}'")

            # "No records" や "Empty" などのメッセージを探す
            empty_messages = await page.locator(
                "text=/no records|empty|nothing|見つかりません|データがありません/i"
            ).count()
            if empty_messages > 0:
                print("✅ 空状態メッセージを確認")
            else:
                print("⚠️ 空状態メッセージが見つかりません")

            # 主要なコンテンツエリアのテキストを確認
            content_text = await page.text_content("main, #root, .app, body")
            if content_text:
                # 特定のキーワードを検索
                keywords = [
                    "record",
                    "photo",
                    "outfit",
                    "レコード",
                    "写真",
                    "コーディネート",
                ]
                found_keywords = [
                    kw for kw in keywords if kw.lower() in content_text.lower()
                ]
                if found_keywords:
                    print(f"🔍 見つかったキーワード: {found_keywords}")
                else:
                    print("✅ データ関連キーワードなし（クリーン状態）")

            # 少し待機して動的ロードを確認
            print("⏳ 動的コンテンツの読み込み待機...")
            await page.wait_for_timeout(3000)

            # 再度カード数を確認
            final_record_cards = await page.locator(
                '[data-testid="outfit-card"], .outfit-card, [class*="card"], [class*="record"]'
            ).count()
            print(f"🃏 最終レコードカード数: {final_record_cards}")

            # 最終スクリーンショット
            final_screenshot_path = os.path.join(logs_dir, "ui_final_state.png")
            await page.screenshot(path=final_screenshot_path, full_page=True)
            print(f"📸 最終スクリーンショット: {final_screenshot_path}")

        except Exception as e:
            print(f"❌ エラー: {e}")

        finally:
            # Issue 260対応: 適切なリソースクリーンアップ
            await page.close()
            await context.close()
            await browser.close()
            print("🧹 Issue 260対応: ブラウザリソースをクリーンアップしました")


if __name__ == "__main__":
    asyncio.run(check_ui_with_playwright())
