#!/usr/bin/env python3
"""CI Error Analyzer のテスト."""

import os
import sys

# プロジェクトルートを PYTHONPATH に追加
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import json

from scripts.utils.ci.error_analyzer import AutoFixer, CIErrorAnalyzer


def test_deprecated_actions():
    """非推奨アクションの検出テスト."""
    log_content = """
    Run actions/checkout@v3
    Warning: Node.js 16 actions are deprecated. Please update the following actions to use Node.js 20: actions/checkout@v3

    Run actions/upload-artifact@v3
    Warning: Node.js 16 actions are deprecated. Please update the following actions to use Node.js 20: actions/upload-artifact@v3
    """

    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(log_content)

    print("=== 非推奨アクションテスト ===")
    print(f"検出されたエラー: {len(analysis['errors'])}")
    print(f"自動修正可能: {analysis['auto_fixable']}")

    for error in analysis["errors"]:
        print(f"- {error['description']}: {error['name']}")

    assert len(analysis["errors"]) >= 2
    assert analysis["auto_fixable"]


def test_pytest_markers():
    """Pytest マーカーエラーの検出テスト."""
    log_content = """
    ============================= test session starts ==============================
    platform linux -- Python 3.11.0, pytest-7.4.0, pluggy-1.2.0
    rootdir: /home/runner/work/coordinate-recorder/coordinate-recorder
    collected 0 items / 1 error

    ==================================== ERRORS ====================================
    _________________ ERROR collecting tests/test_integration.py __________________
    Unknown pytest.mark.integration - is this a typo?  You can register custom marks to avoid this warning

    ============================= no tests ran in 0.12s =============================
    Error: Process completed with exit code 1.
    """

    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(log_content)

    print("\n=== pytest マーカーテスト ===")
    print(f"検出されたエラー: {len(analysis['errors'])}")

    for error in analysis["errors"]:
        print(f"- {error['description']}: {error['details']}")

    assert any(e["type"] == "pytest_marker" for e in analysis["errors"])


def test_missing_dependencies():
    """依存関係エラーの検出テスト."""
    log_content = """
    Traceback (most recent call last):
      File "test.py", line 1, in <module>
        import numpy
    ModuleNotFoundError: No module named 'numpy'

    Error: Cannot find module 'express'
    Require stack:
    - /app/server.js
    """

    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(log_content)

    print("\n=== 依存関係エラーテスト ===")
    print(f"検出されたエラー: {len(analysis['errors'])}")

    for error in analysis["errors"]:
        print(f"- {error['description']}: {error.get('details', {})}")

    assert any(e["type"] == "missing_dependency" for e in analysis["errors"])


def test_fix_script_generation():
    """修正スクリプト生成テスト."""
    log_content = """
    Warning: actions/checkout@v3 is deprecated
    Black would reformat test.py
    """

    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(log_content)
    script = analyzer.generate_fix_script(analysis)

    print("\n=== 修正スクリプト生成テスト ===")
    print("生成されたスクリプト:")
    print(script)

    assert "#!/bin/bash" in script
    assert "set -e" in script


def test_auto_fixer():
    """AutoFixer のテスト（ドライラン）."""
    print("\n=== AutoFixer テスト（ドライラン）===")

    fixer = AutoFixer(dry_run=True)

    # テスト用の解析結果
    analysis = {
        "errors": [
            {
                "type": "deprecated_action",
                "name": "deprecated_checkout",
                "description": "非推奨の checkout アクション",
                "fixable": True,
                "fix_command": "sed -i 's/actions\\/checkout@v3/actions\\/checkout@v4/g'",
            },
            {
                "type": "pytest_marker",
                "name": "unknown_pytest_marker",
                "description": "未定義の pytest マーカー",
                "fixable": True,
                "details": {"group_0": "integration"},
            },
        ],
        "auto_fixable": True,
    }

    results = fixer.apply_fixes(analysis)

    print(f"修正成功: {results['success']}")
    print(f"修正件数: {results['fixed_count']}")
    print(f"失敗件数: {results['failed_count']}")


if __name__ == "__main__":
    print("CI Error Analyzer テスト実行中...\n")

    test_deprecated_actions()
    test_pytest_markers()
    test_missing_dependencies()
    test_fix_script_generation()
    test_auto_fixer()

    print("\n✅ すべてのテストが成功しました!")

    # 実際のワークフローログでのテスト例
    print("\n=== 実際のログでのテスト例 ===")
    sample_log = """
    Run actions/upload-artifact@v3
    Warning: Node.js 16 actions are deprecated. Please update the following actions to use Node.js 20: actions/upload-artifact@v3

    pytest -m integration
    ERROR: Unknown pytest.mark.integration

    ModuleNotFoundError: No module named 'requests'

    ruff check .
    Found 5 errors

    black --check .
    would reformat main.py
    """

    analyzer = CIErrorAnalyzer()
    analysis = analyzer.analyze_log(sample_log)

    print("\n解析結果:")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
