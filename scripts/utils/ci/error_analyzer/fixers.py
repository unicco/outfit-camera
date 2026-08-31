"""自動修正機能の実装."""

import logging
import os
import subprocess
from pathlib import Path

from .patterns import FixType


class AutoFixer:
    """エラーの自動修正を実行."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
        self.fixed_files = []

    def fix_deprecated_actions(
        self, workflow_dir: str = ".github/workflows"
    ) -> list[str]:
        """非推奨の GitHub Actions を更新."""
        fixed = []

        # アクションバージョンのマッピング
        action_updates = {
            "actions/checkout@v1": "actions/checkout@v4",
            "actions/checkout@v2": "actions/checkout@v4",
            "actions/checkout@v3": "actions/checkout@v4",
            "actions/setup-python@v1": "actions/setup-python@v5",
            "actions/setup-python@v2": "actions/setup-python@v5",
            "actions/setup-python@v3": "actions/setup-python@v5",
            "actions/setup-python@v4": "actions/setup-python@v5",
            "actions/upload-artifact@v1": "actions/upload-artifact@v4",
            "actions/upload-artifact@v2": "actions/upload-artifact@v4",
            "actions/upload-artifact@v3": "actions/upload-artifact@v4",
            "actions/download-artifact@v1": "actions/download-artifact@v4",
            "actions/download-artifact@v2": "actions/download-artifact@v4",
            "actions/download-artifact@v3": "actions/download-artifact@v4",
            "actions/setup-node@v1": "actions/setup-node@v4",
            "actions/setup-node@v2": "actions/setup-node@v4",
            "actions/setup-node@v3": "actions/setup-node@v4",
            "actions/cache@v1": "actions/cache@v4",
            "actions/cache@v2": "actions/cache@v4",
            "actions/cache@v3": "actions/cache@v4",
        }

        workflow_path = Path(workflow_dir)
        if not workflow_path.exists():
            self.logger.warning(f"Workflow directory not found: {workflow_dir}")
            return fixed

        for yaml_file in workflow_path.glob("*.yml"):
            updated = False
            content = yaml_file.read_text()

            for old_action, new_action in action_updates.items():
                if old_action in content:
                    content = content.replace(old_action, new_action)
                    updated = True
                    self.logger.info(
                        f"Updated {old_action} to {new_action} in {yaml_file}"
                    )

            if updated:
                if not self.dry_run:
                    yaml_file.write_text(content)
                fixed.append(str(yaml_file))
                self.fixed_files.append(str(yaml_file))

        return fixed

    def fix_pytest_markers(self, project_root: str = ".") -> bool:
        """Pytest マーカーの設定を修正."""
        pyproject_path = Path(project_root) / "pyproject.toml"
        pytest_ini_path = Path(project_root) / "pytest.ini"

        # 既存の設定を確認
        config_exists = False
        if pyproject_path.exists():
            content = pyproject_path.read_text()
            if "[tool.pytest.ini_options]" in content:
                config_exists = True
        elif pytest_ini_path.exists():
            config_exists = True

        if not config_exists:
            # pyproject.toml に pytest 設定を追加
            pytest_config = """
[tool.pytest.ini_options]
markers = [
    "integration: Integration tests",
    "slow: Slow running tests",
    "asyncio: Asynchronous tests",
    "unit: Unit tests",
]
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
"""

            if not self.dry_run:
                if pyproject_path.exists():
                    with open(pyproject_path, "a") as f:
                        f.write(pytest_config)
                else:
                    # pytest.ini を作成
                    pytest_ini_content = """[pytest]
markers =
    integration: Integration tests
    slow: Slow running tests
    asyncio: Asynchronous tests
    unit: Unit tests
testpaths = tests
python_files = test_*.py *_test.py
"""
                    pytest_ini_path.write_text(pytest_ini_content)

            self.fixed_files.append(
                str(pyproject_path if pyproject_path.exists() else pytest_ini_path)
            )
            return True

        return False

    def fix_missing_dependencies(
        self, package_name: str, package_type: str = "python"
    ) -> bool:
        """不足している依存関係をインストール."""
        if self.dry_run:
            self.logger.info(
                f"[DRY RUN] Would install {package_type} package: {package_name}"
            )
            return True

        try:
            if package_type == "python":
                # Poetry を使用してインストール
                result = subprocess.run(
                    ["poetry", "add", package_name], capture_output=True, text=True
                )
                if result.returncode == 0:
                    self.fixed_files.append("pyproject.toml")
                    return True
                else:
                    # pip にフォールバック
                    result = subprocess.run(
                        ["pip", "install", package_name], capture_output=True, text=True
                    )
                    return result.returncode == 0

            elif package_type == "npm":
                result = subprocess.run(
                    ["npm", "install", package_name],
                    capture_output=True,
                    text=True,
                    cwd="ui" if os.path.exists("ui") else ".",
                )
                if result.returncode == 0:
                    self.fixed_files.append("package.json")
                    return True

        except Exception as e:
            self.logger.error(f"Failed to install {package_name}: {e}")

        return False

    def apply_fixes(self, analysis: dict) -> dict[str, any]:
        """解析結果に基づいて修正を適用."""
        results = {
            "success": False,
            "fixed_count": 0,
            "failed_count": 0,
            "fixed_files": [],
            "errors": [],
        }

        for error in analysis["errors"]:
            if not error["fixable"]:
                continue

            try:
                if error["type"] == FixType.DEPRECATED_ACTION.value:
                    fixed = self.fix_deprecated_actions()
                    if fixed:
                        results["fixed_count"] += 1

                elif error["type"] == FixType.PYTEST_MARKER.value:
                    if self.fix_pytest_markers():
                        results["fixed_count"] += 1

                elif error["type"] == FixType.MISSING_DEPENDENCY.value:
                    if "details" in error and "group_0" in error["details"]:
                        package = error["details"]["group_0"]
                        package_type = (
                            "python"
                            if error["name"] == "missing_python_package"
                            else "npm"
                        )
                        if self.fix_missing_dependencies(package, package_type):
                            results["fixed_count"] += 1

            except Exception as e:
                results["failed_count"] += 1
                results["errors"].append(str(e))
                self.logger.error(f"Failed to fix {error['name']}: {e}")

        results["success"] = results["fixed_count"] > 0
        results["fixed_files"] = list(set(self.fixed_files))

        return results

    def validate_fixes(self) -> bool:
        """適用した修正が正しいか検証."""
        # TODO: 修正後のファイルの構文チェックなど
        return True
