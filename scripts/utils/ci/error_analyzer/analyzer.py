"""CI エラー解析エンジン."""

import logging
from datetime import datetime

from .patterns import FixType, find_matching_patterns


class CIErrorAnalyzer:
    """CI エラーログを解析し、修正提案を生成."""

    def __init__(self, log_level: int = logging.INFO):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

    def analyze_log(self, log_content: str) -> dict[str, any]:
        """ログを解析してエラー情報を抽出."""
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "errors": [],
            "fixable": False,
            "auto_fixable": False,
            "suggested_fixes": [],
        }

        # マッチするパターンを検索
        matching_patterns = find_matching_patterns(log_content)

        for pattern in matching_patterns:
            error_info = {
                "type": pattern.fix_type.value,
                "name": pattern.name,
                "description": pattern.description,
                "fixable": pattern.fixable,
                "details": pattern.extract_details(log_content),
            }

            if pattern.fix_command:
                error_info["fix_command"] = pattern.fix_command

            analysis["errors"].append(error_info)

            if pattern.fixable:
                analysis["fixable"] = True
                if pattern.fix_command:
                    analysis["auto_fixable"] = True

        # 修正提案を生成
        analysis["suggested_fixes"] = self._generate_fix_suggestions(analysis["errors"])

        return analysis

    def _generate_fix_suggestions(self, errors: list[dict]) -> list[dict[str, str]]:
        """エラーに基づいて修正提案を生成."""
        suggestions = []

        # エラータイプごとにグループ化
        error_types = {}
        for error in errors:
            error_type = error["type"]
            if error_type not in error_types:
                error_types[error_type] = []
            error_types[error_type].append(error)

        # タイプごとの修正提案を生成
        for error_type, type_errors in error_types.items():
            if error_type == FixType.DEPRECATED_ACTION.value:
                suggestions.append(self._suggest_action_updates(type_errors))
            elif error_type == FixType.PYTEST_MARKER.value:
                suggestions.append(self._suggest_pytest_fixes(type_errors))
            elif error_type == FixType.MISSING_DEPENDENCY.value:
                suggestions.append(self._suggest_dependency_fixes(type_errors))
            elif error_type == FixType.FORMATTING.value:
                suggestions.append(self._suggest_formatting_fixes(type_errors))

        return [s for s in suggestions if s]  # None を除外

    def _suggest_action_updates(self, errors: list[dict]) -> dict[str, str]:
        """GitHub Actions の更新提案."""
        commands = []
        for error in errors:
            if "fix_command" in error:
                commands.append(error["fix_command"])

        if commands:
            return {
                "type": "action_update",
                "description": "GitHub Actions を最新バージョンに更新",
                "commands": commands,
                "files": [".github/workflows/*.yml"],
            }
        return None

    def _suggest_pytest_fixes(self, errors: list[dict]) -> dict[str, str]:
        """Pytest 関連の修正提案."""
        markers = []
        for error in errors:
            if "group_0" in error["details"]:
                markers.append(error["details"]["group_0"])

        if markers:
            return {
                "type": "pytest_config",
                "description": "pytest マーカーの設定を追加",
                "commands": [
                    f"echo '[tool.pytest.ini_options]\\nmarkers = [\\n    \"{m}: {m} tests\"\\n]' >> pyproject.toml"
                    for m in markers
                ],
                "files": ["pyproject.toml", "pytest.ini"],
            }
        return None

    def _suggest_dependency_fixes(self, errors: list[dict]) -> dict[str, str]:
        """依存関係の修正提案."""
        python_packages = []
        npm_packages = []

        for error in errors:
            if (
                error["name"] == "missing_python_package"
                and "group_0" in error["details"]
            ):
                python_packages.append(error["details"]["group_0"])
            elif (
                error["name"] == "missing_npm_package" and "group_0" in error["details"]
            ):
                npm_packages.append(error["details"]["group_0"])

        commands = []
        if python_packages:
            commands.extend([f"poetry add {pkg}" for pkg in python_packages])
        if npm_packages:
            commands.extend([f"npm install {pkg}" for pkg in npm_packages])

        if commands:
            return {
                "type": "dependency_install",
                "description": "不足している依存関係をインストール",
                "commands": commands,
                "files": ["pyproject.toml", "package.json"],
            }
        return None

    def _suggest_formatting_fixes(self, errors: list[dict]) -> dict[str, str]:
        """フォーマット関連の修正提案."""
        commands = []
        for error in errors:
            if "fix_command" in error and error["fix_command"] not in commands:
                commands.append(error["fix_command"])

        if commands:
            return {
                "type": "formatting",
                "description": "コードフォーマットの修正",
                "commands": commands,
                "files": ["**/*.py", "**/*.js", "**/*.ts"],
            }
        return None

    def generate_fix_script(self, analysis: dict) -> str:
        """解析結果から修正スクリプトを生成."""
        if not analysis["auto_fixable"]:
            return ""

        script_lines = [
            "#!/bin/bash",
            "set -e",
            "",
            "echo '🔧 CI エラー自動修正スクリプト'",
            "echo '================================'",
            "",
        ]

        for suggestion in analysis["suggested_fixes"]:
            script_lines.append(f"echo '\\n📌 {suggestion['description']}'")
            for cmd in suggestion.get("commands", []):
                script_lines.append(f"echo '実行: {cmd}'")
                script_lines.append(cmd)
                script_lines.append("")

        script_lines.extend(
            [
                "",
                "echo '\\n✅ 修正が完了しました'",
                "echo '変更内容を確認してコミットしてください:'echo 'git add -A'",
                "echo 'git commit -m \"fix: CI エラーを自動修正\"'",
            ]
        )

        return "\n".join(script_lines)
