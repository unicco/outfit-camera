#!/usr/bin/env python3
"""CI Error Analyzer CLI."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .analyzer import CIErrorAnalyzer
from .fixers import AutoFixer


def setup_logging(verbose: bool = False):
    """ロギング設定."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def main():
    parser = argparse.ArgumentParser(
        description="CI/CD エラーログを解析し、自動修正を提案・実行します"
    )

    parser.add_argument("log_file", help="解析するログファイルのパス（'-' で標準入力）")

    parser.add_argument("-o", "--output", help="解析結果の出力ファイル（JSON形式）")

    parser.add_argument("-f", "--fix", action="store_true", help="自動修正を実行")

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="修正をシミュレートのみ（実際には適用しない）",
    )

    parser.add_argument("-s", "--script", help="修正スクリプトを生成して保存")

    parser.add_argument("-v", "--verbose", action="store_true", help="詳細なログを出力")

    args = parser.parse_args()
    setup_logging(args.verbose)

    # ログを読み込み
    if args.log_file == "-":
        log_content = sys.stdin.read()
    else:
        try:
            log_content = Path(args.log_file).read_text()
        except FileNotFoundError:
            print(
                f"エラー: ログファイルが見つかりません: {args.log_file}",
                file=sys.stderr,
            )
            return 1

    # 解析実行
    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(log_content)

    # 結果を表示
    print("\n🔍 CI エラー解析結果")
    print("=" * 50)
    print(f"検出されたエラー: {len(analysis['errors'])} 件")
    print(f"自動修正可能: {'はい' if analysis['auto_fixable'] else 'いいえ'}")

    if analysis["errors"]:
        print("\n📋 エラー詳細:")
        for i, error in enumerate(analysis["errors"], 1):
            print(f"\n{i}. {error['description']}")
            print(f"   タイプ: {error['type']}")
            print(f"   修正可能: {'はい' if error['fixable'] else 'いいえ'}")
            if "fix_command" in error:
                print(f"   修正コマンド: {error['fix_command']}")

    # 修正提案を表示
    if analysis["suggested_fixes"]:
        print("\n💡 修正提案:")
        for suggestion in analysis["suggested_fixes"]:
            print(f"\n- {suggestion['description']}")
            for cmd in suggestion.get("commands", []):
                print(f"  $ {cmd}")

    # 修正スクリプトを生成
    if args.script:
        script_content = analyzer.generate_fix_script(analysis)
        if script_content:
            Path(args.script).write_text(script_content)
            Path(args.script).chmod(0o755)
            print(f"\n📝 修正スクリプトを生成しました: {args.script}")

    # 自動修正を実行
    if args.fix and analysis["auto_fixable"]:
        print("\n🔧 自動修正を実行中...")
        fixer = AutoFixer(dry_run=args.dry_run)
        fix_results = fixer.apply_fixes(analysis)

        if fix_results["success"]:
            print(f"✅ {fix_results['fixed_count']} 件の修正を適用しました")
            if fix_results["fixed_files"]:
                print("\n修正されたファイル:")
                for f in fix_results["fixed_files"]:
                    print(f"  - {f}")
        else:
            print("❌ 修正の適用に失敗しました")
            if fix_results["errors"]:
                for err in fix_results["errors"]:
                    print(f"  - {err}")

    # 結果を保存
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        print(f"\n📊 解析結果を保存しました: {args.output}")

    return 0 if not analysis["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
