#!/usr/bin/env python3
"""Check that all Pydantic BaseModel imports use the custom BaseModel from schemas.base
Issue #962: Enforce API response naming convention consistency.
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple


class BaseModelImportChecker(ast.NodeVisitor):
    """AST visitor to check for direct pydantic.BaseModel imports."""

    def __init__(self, filename: str):
        self.filename = filename
        self.errors: List[Tuple[int, str]] = []
        self.has_correct_import = False
        self.has_pydantic_basemodel_usage = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check import from statements."""
        if node.module == "pydantic":
            for alias in node.names:
                if alias.name == "BaseModel":
                    self.errors.append(
                        (
                            node.lineno,
                            "Direct import of pydantic.BaseModel is not allowed. "
                            "Use 'from app.schemas.base import BaseModel' or "
                            "'from ..schemas.base import BaseModel' instead.",
                        )
                    )
                    self.has_pydantic_basemodel_usage = True

        # Check for correct import
        if node.module and (
            node.module.endswith("schemas.base")
            or node.module == "app.schemas.base"
            or node.module == ".schemas.base"
            or node.module == "..schemas.base"
        ):
            for alias in node.names:
                if alias.name == "BaseModel":
                    self.has_correct_import = True

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check class definitions for BaseModel usage."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseModel":
                # Only flag if we found pydantic import but not correct import
                if self.has_pydantic_basemodel_usage and not self.has_correct_import:
                    self.errors.append(
                        (
                            node.lineno,
                            f"Class '{node.name}' uses BaseModel but imports it from pydantic. "
                            f"Use the custom BaseModel from schemas.base instead.",
                        )
                    )
        self.generic_visit(node)


def check_file(filepath: Path) -> List[Tuple[str, int, str]]:
    """Check a single Python file for BaseModel usage."""
    errors = []

    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(filepath))

        checker = BaseModelImportChecker(str(filepath))
        checker.visit(tree)

        for lineno, message in checker.errors:
            errors.append((str(filepath), lineno, message))

    except Exception as e:
        errors.append((str(filepath), 0, f"Failed to parse file: {e}"))

    return errors


def should_check_file(filepath: Path) -> bool:
    """Determine if a file should be checked."""
    filepath_str = str(filepath)

    # Skip these specific files/patterns
    if any(
        pattern in filepath_str
        for pattern in [
            "__pycache__",
            "tests/",
            "scripts/",
            "migrations/",
            "__init__.py",
            "settings.py",
            "config.py",
            "schemas/base.py",
        ]
    ):
        return False

    # `/api/v2/` は URL の prefix であってファイルパスではない。ここを URL 側に
    # 合わせると 1 件もマッチせず、成功したように見える出力を出して exit 0 する。
    return filepath_str.endswith(".py") and "/api/app/" in filepath_str


def main():
    """Main function to check all relevant Python files."""
    root_path = Path(__file__).parent.parent
    # api/ ではなく api/app/ を歩く。api/ 直下には git 管理外の venv が置かれることが
    # あり、rglob すると依存パッケージ数百件を走査する。
    app_path = root_path / "api" / "app"

    if not app_path.exists():
        print(f"API app directory not found: {app_path}")
        return 1

    all_errors = []

    # Find all Python files
    for filepath in app_path.rglob("*.py"):
        if should_check_file(filepath):
            errors = check_file(filepath)
            all_errors.extend(errors)

    # Report errors
    if all_errors:
        print("❌ BaseModel usage errors found:\n")
        for filepath, lineno, message in all_errors:
            print(f"{filepath}:{lineno}: {message}")
        print(
            f"\n❌ Found {len(all_errors)} BaseModel usage error(s). "
            "Please use 'from app.schemas.base import BaseModel' instead of 'from pydantic import BaseModel'."
        )
        return 1
    else:
        print("✅ All BaseModel imports are using the custom schemas.base.BaseModel")
        return 0


if __name__ == "__main__":
    sys.exit(main())
