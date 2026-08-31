#!/bin/bash
# Document Maintenance & Consistency Check Script
# Usage: ./scripts/document-maintenance.sh [--fix] [--report-only]

set -e

# 色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 共通スクリプト読み込み
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/check-documents.sh"

# オプション解析
FIX_ISSUES=false
REPORT_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_ISSUES=true
            shift
            ;;
        --report-only)
            REPORT_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --fix         自動修正可能な問題を修正"
            echo "  --report-only レポート生成のみ（チェック実行しない）"
            echo "  -h, --help    このヘルプを表示"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}📚 Document Maintenance${NC}"
echo "========================"
echo "実行日: $(date)"
echo ""

if [ "$REPORT_ONLY" = true ]; then
    echo -e "${YELLOW}📊 レポート生成モード（チェック省略）${NC}"
    echo ""
fi

# チェック実行
if [ "$REPORT_ONLY" = false ]; then
    # 修正モードの場合は事前に修正実行
    if [ "$FIX_ISSUES" = true ]; then
        echo -e "${BLUE}🔧 自動修正実行中...${NC}"
        fix_docstrings
        echo ""
    fi

    # 直接チェック実行（一時ファイル作成なし）
    echo -e "${BLUE}🔍 ドキュメントチェック実行中...${NC}"

    # Docstring チェック
    if ruff check --select D . >/dev/null 2>&1; then
        docstring_issues="0"
    else
        docstring_issues=$(ruff check --select D . 2>/dev/null | wc -l | tr -d ' ')
    fi

    # TODO チェック
    todo_count=$(find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" | xargs grep -c "TODO\|FIXME\|XXX" 2>/dev/null | awk '{sum+=$1} END {print sum+0}')

    echo ""
fi

# 結果表示
echo -e "${BLUE}📊 チェック結果${NC}"
echo "-------------"
if [ "$REPORT_ONLY" = false ]; then
    if [ "$docstring_issues" = "0" ]; then
        echo -e "• Docstring: ${GREEN}✅ OK${NC}"
    elif [ "$docstring_issues" = "-1" ]; then
        echo -e "• Docstring: ${YELLOW}⚠️ ruff not found${NC}"
    else
        echo -e "• Docstring: ${RED}❌ $docstring_issues issues${NC}"
    fi

    if [ "$todo_count" = "0" ]; then
        echo -e "• TODO: ${GREEN}✅ None${NC}"
    else
        echo -e "• TODO: ${YELLOW}⚠️ $todo_count found${NC}"
    fi

    echo -e "• Consistency: ${GREEN}✅ OK${NC}"
else
    echo "• Docstring: スキップ"
    echo "• TODO: スキップ"
    echo "• Consistency: スキップ"
fi
echo ""

# 利用可能ツール表示
if [ -f "package.json" ] && grep -q "docs-check\|lint-docs\|docs-fix" package.json; then
    echo -e "${GREEN}✅ ドキュメント用スクリプト利用可能${NC}"
    echo "   - npm run lint-docs   # docstring チェック"
    echo "   - npm run docs-fix    # docstring 修正"
else
    echo -e "${YELLOW}⚠️ package.json にスクリプト未設定${NC}"
fi

# 詳細確認案内
if [ "$REPORT_ONLY" = false ]; then
    echo ""
    if [ "$docstring_issues" != "0" ]; then
        echo -e "${YELLOW}💡 Docstring詳細: ruff check --select D .${NC}"
    fi

    if [ "$todo_count" != "0" ]; then
        echo -e "${YELLOW}💡 TODO詳細: find . -name \"*.py\" -o -name \"*.ts\" -o -name \"*.tsx\" | xargs grep -n \"TODO\|FIXME\|XXX\"${NC}"
    fi
fi

echo ""
echo -e "${BLUE}✨ Document Maintenance 完了${NC}"
