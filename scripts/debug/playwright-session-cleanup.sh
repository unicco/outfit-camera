#!/bin/bash

# Playwright Session Cleanup Script
# 古いセッションと残存プロセスの自動クリーンアップ

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# MCP Chrome プロファイルパス
MCP_CHROME_PROFILE="$HOME/Library/Caches/ms-playwright/mcp-chrome-profile"
PLAYWRIGHT_CACHE_DIR="$HOME/Library/Caches/ms-playwright"

print_info "🎭 Playwright Session Cleanup Script"
print_info "=====================================\n"

# 1. 残存ブラウザプロセスの確認と終了
print_info "🔍 Checking for existing browser processes..."
browser_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)

if [ -n "$browser_pids" ]; then
    process_count=$(echo "$browser_pids" | wc -l | tr -d ' ')
    print_warn "Found $process_count browser processes running"

    # プロセス詳細表示
    print_info "Process details:"
    ps aux | grep -E "(chrome|chromium|playwright)" | grep -v grep | head -5

    # 段階的終了
    print_info "📤 Sending SIGTERM for graceful shutdown..."
    echo "$browser_pids" | xargs -r kill -TERM 2>/dev/null || true

    # 3秒待機
    sleep 3

    # 残存プロセス確認
    remaining_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)
    if [ -n "$remaining_pids" ]; then
        print_warn "Some processes still running, force killing..."
        echo "$remaining_pids" | xargs -r kill -KILL 2>/dev/null || true
        sleep 1
    fi

    # 最終確認
    final_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)
    if [ -n "$final_pids" ]; then
        print_error "Warning: Some browser processes may still be running"
        echo "$final_pids"
    else
        print_success "All browser processes cleaned up successfully"
    fi
else
    print_success "No browser processes found"
fi

# 2. MCP Chrome プロファイルのクリーンアップ
print_info "\n🧹 Cleaning up MCP Chrome profile..."
if [ -d "$MCP_CHROME_PROFILE" ]; then
    profile_size=$(du -sh "$MCP_CHROME_PROFILE" 2>/dev/null | cut -f1 || echo "unknown")
    print_warn "Found MCP Chrome profile (size: $profile_size)"

    # プロファイルが使用中かチェック
    if lsof "$MCP_CHROME_PROFILE" 2>/dev/null | grep -q "$MCP_CHROME_PROFILE"; then
        print_error "Profile is currently in use, cannot clean up"
        print_info "Please close all browsers and try again"
        exit 1
    else
        print_info "Removing old MCP Chrome profile..."
        rm -rf "$MCP_CHROME_PROFILE"
        print_success "MCP Chrome profile cleaned up"
    fi
else
    print_success "No MCP Chrome profile found"
fi

# 3. 他の古いプロファイルディレクトリもクリーンアップ
print_info "\n🗂️  Cleaning up other browser profiles..."
find "$PLAYWRIGHT_CACHE_DIR" -name "*chrome*" -type d -mtime +7 2>/dev/null | while read -r old_profile; do
    if [ -d "$old_profile" ] && [ "$old_profile" != "$MCP_CHROME_PROFILE" ]; then
        profile_name=$(basename "$old_profile")
        print_info "Removing old profile: $profile_name"
        rm -rf "$old_profile"
    fi
done

# 4. 一時ファイルのクリーンアップ
print_info "\n🧼 Cleaning up temporary files..."
temp_dirs=(
    "/tmp/playwright*"
    "/tmp/chrome*"
    "/tmp/chromium*"
    "/var/folders/*/T/playwright*"
)

for pattern in "${temp_dirs[@]}"; do
    for temp_dir in $pattern; do
        if [ -d "$temp_dir" ] && [ "$(basename "$temp_dir")" != "." ]; then
            print_info "Removing temp directory: $temp_dir"
            rm -rf "$temp_dir" 2>/dev/null || true
        fi
    done
done

# 5. 最終確認
print_info "\n📊 Final status check..."
remaining_processes=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null | wc -l | tr -d ' ')
print_info "Remaining browser processes: $remaining_processes"

if [ -d "$MCP_CHROME_PROFILE" ]; then
    print_warn "MCP Chrome profile still exists"
else
    print_success "MCP Chrome profile cleaned up"
fi

# 6. 予防的設定の提案
print_info "\n💡 Prevention recommendations:"
print_info "  1. Use this script regularly: ./scripts/debug/playwright-session-cleanup.sh"
print_info "  2. Set up automated cleanup in Claude Code hooks"
print_info "  3. Monitor browser process count with: ps aux | grep -c chrome"

print_success "\n✅ Playwright session cleanup completed!"
