"""エラーパターンと修正タイプの定義."""

import re
from dataclasses import dataclass
from enum import Enum
from re import Pattern


class FixType(Enum):
    """修正タイプの分類."""

    DEPRECATED_ACTION = "deprecated_action"
    PYTEST_MARKER = "pytest_marker"
    MISSING_DEPENDENCY = "missing_dependency"
    FORMATTING = "formatting"
    SYNTAX_ERROR = "syntax_error"
    CONFIG_ERROR = "config_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorPattern:
    """エラーパターンの定義."""

    name: str
    pattern: Pattern[str]
    fix_type: FixType
    description: str
    fixable: bool = True
    fix_command: str | None = None

    def matches(self, text: str) -> bool:
        """テキストがパターンにマッチするか確認."""
        return bool(self.pattern.search(text))

    def extract_details(self, text: str) -> dict[str, str]:
        """エラーの詳細情報を抽出."""
        match = self.pattern.search(text)
        if match and match.groups():
            return {f"group_{i}": g for i, g in enumerate(match.groups()) if g}
        return {}


# エラーパターンの定義
ERROR_PATTERNS: list[ErrorPattern] = [
    # 非推奨 GitHub Actions
    ErrorPattern(
        name="deprecated_upload_artifact",
        pattern=re.compile(r"actions/upload-artifact@v\d+", re.IGNORECASE),
        fix_type=FixType.DEPRECATED_ACTION,
        description="非推奨の upload-artifact アクション",
        fix_command="sed -i 's/actions\\/upload-artifact@v3/actions\\/upload-artifact@v4/g'",
    ),
    ErrorPattern(
        name="deprecated_download_artifact",
        pattern=re.compile(r"actions/download-artifact@v\d+", re.IGNORECASE),
        fix_type=FixType.DEPRECATED_ACTION,
        description="非推奨の download-artifact アクション",
        fix_command="sed -i 's/actions\\/download-artifact@v3/actions\\/download-artifact@v4/g'",
    ),
    ErrorPattern(
        name="deprecated_setup_python",
        pattern=re.compile(r"actions/setup-python@v[1-4]", re.IGNORECASE),
        fix_type=FixType.DEPRECATED_ACTION,
        description="非推奨の setup-python アクション",
        fix_command="sed -i 's/actions\\/setup-python@v[0-9]/actions\\/setup-python@v5/g'",
    ),
    ErrorPattern(
        name="deprecated_checkout",
        pattern=re.compile(r"actions/checkout@v[1-3]", re.IGNORECASE),
        fix_type=FixType.DEPRECATED_ACTION,
        description="非推奨の checkout アクション",
        fix_command="sed -i 's/actions\\/checkout@v[0-3]/actions\\/checkout@v4/g'",
    ),
    ErrorPattern(
        name="deprecated_node_warning",
        pattern=re.compile(
            r"Node\.js \d+ actions are deprecated.*actions/\S+@v\d+",
            re.IGNORECASE | re.DOTALL,
        ),
        fix_type=FixType.DEPRECATED_ACTION,
        description="Node.js 非推奨警告",
    ),
    # pytest マーカーエラー
    ErrorPattern(
        name="unknown_pytest_marker",
        pattern=re.compile(r"Unknown pytest\.mark\.(\w+)"),
        fix_type=FixType.PYTEST_MARKER,
        description="未定義の pytest マーカー",
    ),
    ErrorPattern(
        name="pytest_mark_integration",
        pattern=re.compile(r"pytest.*-m\s+integration.*no tests ran", re.IGNORECASE),
        fix_type=FixType.PYTEST_MARKER,
        description="integration マーカーが定義されていない",
    ),
    ErrorPattern(
        name="pytest_asyncio_missing",
        pattern=re.compile(
            r"pytest\.mark\.asyncio.*not found|asyncio.*marker.*required"
        ),
        fix_type=FixType.PYTEST_MARKER,
        description="pytest-asyncio マーカーが必要",
    ),
    # 依存関係エラー
    ErrorPattern(
        name="missing_python_package",
        pattern=re.compile(r"ModuleNotFoundError:\s*No module named ['\"](\w+)['\"]"),
        fix_type=FixType.MISSING_DEPENDENCY,
        description="Python パッケージが見つからない",
    ),
    ErrorPattern(
        name="missing_npm_package",
        pattern=re.compile(r"Cannot find module ['\"](\S+)['\"]"),
        fix_type=FixType.MISSING_DEPENDENCY,
        description="npm パッケージが見つからない",
    ),
    ErrorPattern(
        name="poetry_lock_outdated",
        pattern=re.compile(
            r"poetry\.lock.*out of date|pyproject\.toml.*changed.*poetry\.lock"
        ),
        fix_type=FixType.MISSING_DEPENDENCY,
        description="poetry.lock が古い",
        fix_command="poetry lock --no-update",
    ),
    # フォーマットエラー
    ErrorPattern(
        name="black_formatting",
        pattern=re.compile(r"would reformat|Black found"),
        fix_type=FixType.FORMATTING,
        description="Black フォーマットエラー",
        fix_command="poetry run black .",
    ),
    ErrorPattern(
        name="ruff_linting",
        pattern=re.compile(r"ruff.*Found \d+ error"),
        fix_type=FixType.FORMATTING,
        description="Ruff リントエラー",
        fix_command="poetry run ruff check --fix .",
    ),
    ErrorPattern(
        name="prettier_formatting",
        pattern=re.compile(r"prettier.*not formatted"),
        fix_type=FixType.FORMATTING,
        description="Prettier フォーマットエラー",
        fix_command="npx prettier --write .",
    ),
    # 構文エラー
    ErrorPattern(
        name="yaml_syntax_error",
        pattern=re.compile(r"yaml.*syntax error|invalid yaml", re.IGNORECASE),
        fix_type=FixType.SYNTAX_ERROR,
        description="YAML 構文エラー",
        fixable=False,
    ),
    ErrorPattern(
        name="python_syntax_error",
        pattern=re.compile(r"SyntaxError:|IndentationError:"),
        fix_type=FixType.SYNTAX_ERROR,
        description="Python 構文エラー",
        fixable=False,
    ),
]


def get_pattern_by_name(name: str) -> ErrorPattern | None:
    """名前でパターンを取得."""
    for pattern in ERROR_PATTERNS:
        if pattern.name == name:
            return pattern
    return None


def find_matching_patterns(text: str) -> list[ErrorPattern]:
    """テキストにマッチするすべてのパターンを検索."""
    return [p for p in ERROR_PATTERNS if p.matches(text)]
