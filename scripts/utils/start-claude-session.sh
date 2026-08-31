#!/bin/bash

# Claude Session Starter Script
# 開発環境の状態確認を自動化

set -e

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Claude Code Session Starter ===${NC}"
echo

# プロジェクトルートを推測
CURRENT_DIR=$(pwd)
if [[ "$CURRENT_DIR" == *"coordinate-recorder"* ]]; then
    PROJECT_ROOT="$CURRENT_DIR"
else
    echo -e "${YELLOW}プロジェクトディレクトリが特定できません。現在のディレクトリを使用します。${NC}"
    PROJECT_ROOT="$CURRENT_DIR"
fi

WORK_DIR="$PROJECT_ROOT"

# 作業ディレクトリに移動
cd "$WORK_DIR"

# Git 情報の表示
echo -e "\n${BLUE}作業ディレクトリ:${NC} $WORK_DIR"

if [ -d ".git" ] || git rev-parse --git-dir > /dev/null 2>&1; then
    # 現在のブランチ確認
    CURRENT_BRANCH=$(git branch --show-current)
    echo -e "${BLUE}現在のブランチ:${NC} $CURRENT_BRANCH"

    # git status の確認
    echo -e "\n${BLUE}Git ステータス:${NC}"
    git status --short
else
    echo -e "${YELLOW}Git リポジトリではありません${NC}"
fi

# 共通ガイドライン確認
echo -e "\n${BLUE}ガイドライン:${NC}"
if [ -e "CLAUDE.md" ]; then
    echo -e "  ${GREEN}✓ CLAUDE.md が存在します${NC}"
elif [ -e ".claude/CLAUDE.md" ]; then
    echo -e "  ${GREEN}✓ .claude/CLAUDE.md が存在します${NC}"
else
    echo -e "  ${RED}✗ CLAUDE.md が見つかりません${NC}"
fi

# セッション開始メッセージ
echo -e "\n${BLUE}=== セッション開始準備完了 ===${NC}"
echo -e "\n以下のコマンドで Claude Code を起動してください:"
echo -e "${GREEN}claude${NC}"
echo

echo -e "${BLUE}開発コマンド:${NC}"
echo "  ./scripts/start-development.sh"
echo "  ./scripts/start-development.sh --fast --skip-camera"
echo

