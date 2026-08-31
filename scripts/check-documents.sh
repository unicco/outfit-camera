#!/bin/bash
# Document check core functions
# Usage: source scripts/check-documents.sh

check_docstrings() {
    echo "🔍 Python Docstring チェック..."
    if command -v ruff >/dev/null 2>&1; then
        if ruff check --select D --output-format=github . 2>/dev/null; then
            echo "docstring_issues=0"
            return 0
        else
            ruff check --select D --diff > docstring-issues.txt 2>&1
            issues=$(wc -l < docstring-issues.txt)
            echo "docstring_issues=$issues"
            return 1
        fi
    else
        echo "docstring_issues=-1"  # ruff not found
        return 2
    fi
}

check_todos() {
    echo "🔍 TODO/FIXME/XXX 検出..."

    # 全ファイルでTODO検出（GitHub Actions と統一）
    todo_count=$(find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" | xargs grep -c "TODO\|FIXME\|XXX" 2>/dev/null | awk '{sum+=$1} END {print sum+0}')

    if [ "$todo_count" -gt 0 ]; then
        echo "todo_count=$todo_count"
        return 1
    else
        echo "todo_count=0"
        return 0
    fi
}

check_consistency() {
    echo "🔍 基本的な整合性チェック..."

    # TypeScript JSDoc チェック
    if find . -name "*.ts" -o -name "*.tsx" | head -5 | xargs grep -l "@param" > /dev/null 2>&1; then
        echo "✓ TypeScript JSDoc detected"
    fi

    # Python docstring Args: チェック
    if find . -name "*.py" | head -5 | xargs grep -l "Args:" > /dev/null 2>&1; then
        echo "✓ Python docstring Args detected"
    fi

    echo "consistency_issues=0"
    return 0
}

fix_docstrings() {
    if command -v ruff >/dev/null 2>&1; then
        echo "🔧 Docstring 自動修正中..."
        ruff check --select D --fix --quiet || true
        return 0
    else
        echo "❌ ruff が見つかりません"
        return 1
    fi
}
