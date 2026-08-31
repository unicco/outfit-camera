#!/bin/bash

# Coordinate Recorder systemd デプロイスクリプト
# このスクリプトは本番環境でのデプロイ時に使用されます

set -e

# デプロイロックファイル
LOCKFILE="/tmp/coordinate-deploy.lock"

# ロックを取得（200番のファイルディスクリプタを使用）
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "❌ Another deployment is already running. Exiting..."
    exit 1
fi

# スクリプト終了時にロックを解放
trap 'flock -u 200; rm -f "$LOCKFILE"' EXIT

# スクリプトのディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 共通ログ関数を読み込み
source "$SCRIPT_DIR/common-logging.sh"

# ポート設定を読み込み
if [ -f "$SCRIPT_DIR/service-ports.conf" ]; then
    source "$SCRIPT_DIR/service-ports.conf"
else
    # デフォルト値
    API_PORT=8000
    CAMERA_PORT=8001
    UI_PORT=3000
fi

log_info "🚀 Coordinate Recorder Systemd Deployment"
echo "========================================="

# 1. サービスの停止（カメラ以外）
log_warn "⏹️  Stopping services (except camera)..."
# APIとUI関連サービスを停止
sudo systemctl stop coordinate-api.service coordinate-ui.service coordinate-health-monitor.service coordinate-api-deploy.service camera-pir-monitor.service 2>/dev/null || true
sudo systemctl stop coordinate-api-deploy.timer coordinate-health-monitor.timer coordinate-photo-cleanup.timer 2>/dev/null || true

# カメラサービスの処理を判定
RESTART_CAMERA=false
if [ "$1" = "--restart-camera" ]; then
    RESTART_CAMERA=true
    log_warn "📷 Camera restart requested"
elif git diff HEAD~1 HEAD --name-only 2>/dev/null | grep -q 'camera/'; then
    RESTART_CAMERA=true
    log_warn "📷 Camera code changed, will restart"
fi

if [ "$RESTART_CAMERA" = true ]; then
    echo -e "${YELLOW}⏹️  Stopping camera service...${NC}"
    sudo systemctl stop coordinate-camera.service 2>/dev/null || true
    # カメラプロセスを確実に終了
    for pid in $(pgrep -f "camera_service.py"); do
        echo "Killing camera process: $pid"
        sudo kill -9 "$pid" 2>/dev/null || true
    done
    sleep 3
else
    log_info "📷 Camera service will remain running"
fi

# その他のプロセスを終了
log_warn "🧹 Cleaning up other processes..."
# 開発環境のプロセス（--reload 付き）も含めて終了
pkill -f "uvicorn.*main:app" 2>/dev/null || true
pkill -f "uvicorn.*--reload" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true

# ポートを使用しているプロセスを確実に終了
log_warn "🔌 Cleaning up processes on ports..."
# 段階的にプロセスを終了（SIGTERM → SIGKILL）
for port in $API_PORT $CAMERA_PORT $UI_PORT; do
    # 通常終了を試行
    lsof -ti:$port | xargs -r kill -TERM 2>/dev/null || true
done
sleep 2
# 残ったプロセスを強制終了
for port in $API_PORT $CAMERA_PORT $UI_PORT; do
    lsof -ti:$port | xargs -r kill -9 2>/dev/null || true
done
sleep 2

# 2. systemd ファイルの更新
log_info "🔧 Updating systemd service files..."
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3. サービスの起動
log_info "🚀 Starting services..."

# カメラサービス
if [ "$RESTART_CAMERA" = true ]; then
    echo -e "${GREEN}Starting coordinate-camera.service...${NC}"
    if ! sudo systemctl start coordinate-camera.service; then
        echo -e "${YELLOW}⚠️  Camera service failed to start, retrying...${NC}"
        # 既存プロセスを強制終了
        sudo pkill -9 -f "camera_service.py" || true
        sleep 3
        # 再試行
        sudo systemctl reset-failed coordinate-camera.service
        sudo systemctl start coordinate-camera.service
    fi
else
    # カメラサービスが動いているか確認
    if ! systemctl is-active --quiet coordinate-camera.service; then
        echo -e "${YELLOW}⚠️  Camera service not running, starting it...${NC}"
        sudo systemctl start coordinate-camera.service
    else
        log_info "✅ Camera service already running"
    fi
fi

# API デプロイサービス（依存関係同期）
echo -e "${GREEN}Starting coordinate-api-deploy.service...${NC}"
sudo systemctl start coordinate-api-deploy.service
sudo systemctl start coordinate-api-deploy.timer

# APIサービス
echo -e "${GREEN}Starting coordinate-api.service...${NC}"
sudo systemctl start coordinate-api.service

# UIサービス
echo -e "${GREEN}Starting coordinate-ui.service...${NC}"
sudo systemctl start coordinate-ui.service

# ヘルスモニター
echo -e "${GREEN}Starting coordinate-health-monitor.service...${NC}"
sudo systemctl start coordinate-health-monitor.service
sudo systemctl start coordinate-health-monitor.timer

# カメラPIRモニター
echo -e "${GREEN}Starting camera-pir-monitor.service...${NC}"
sudo systemctl start camera-pir-monitor.service

# 写真クリーンアップタイマー（夜間バッチ）
sudo systemctl start coordinate-photo-cleanup.timer

# User unit タイマー（DB backup push）
log_info "🔧 Setting up user unit timers..."
USER_UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR"
REPO_SYSTEMD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
for unit in coordinate-db-backup-push; do
    for ext in service timer; do
        src="$REPO_SYSTEMD_DIR/${unit}.${ext}"
        if [ -f "$src" ]; then
            cp "$src" "$USER_UNIT_DIR/"
        fi
    done
done
systemctl --user daemon-reload
systemctl --user enable --now coordinate-db-backup-push.timer 2>/dev/null || true

# 4. 起動確認
echo -e "${BLUE}⏳ Waiting for services to stabilize...${NC}"
sleep 5

# 5. ステータス確認
echo -e "${BLUE}📊 Service Status${NC}"
echo "=================="

services=(
    "coordinate-api-deploy.service"
    "coordinate-camera.service"
    "coordinate-api.service"
    "coordinate-ui.service"
    "coordinate-health-monitor.service"
    "camera-pir-monitor.service"
)

all_healthy=true
for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}✅ $service: active${NC}"
    else
        echo -e "${RED}❌ $service: $(systemctl is-active $service)${NC}"
        all_healthy=false
    fi
done

# User unit タイマー状態
echo ""
echo -e "${BLUE}⏰ User Timers${NC}"
echo "==============="
for timer in coordinate-db-backup-push.timer; do
    if systemctl --user is-active --quiet "$timer"; then
        echo -e "${GREEN}✅ $timer: active${NC}"
    else
        echo -e "${YELLOW}⚠️  $timer: $(systemctl --user is-active $timer 2>/dev/null || echo 'not found')${NC}"
    fi
done

# 6. ヘルスチェック
echo ""
echo -e "${BLUE}🏥 Health Check${NC}"
echo "==============="

# API ヘルスチェック
if curl -fs --max-time 5 http://localhost:${API_PORT}/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ API service healthy (port ${API_PORT})${NC}"
else
    echo -e "${RED}❌ API service not responding (port ${API_PORT})${NC}"
    all_healthy=false
fi

# Camera ヘルスチェック
if [ $(timeout 2 curl -s http://localhost:${CAMERA_PORT}/stream 2>/dev/null | head -c 20 | wc -c) -eq 20 ]; then
    echo -e "${GREEN}✅ Camera service healthy (port ${CAMERA_PORT})${NC}"
else
    echo -e "${RED}❌ Camera service not responding (port ${CAMERA_PORT})${NC}"
    all_healthy=false
fi

# UI ヘルスチェック
if curl -fs --max-time 5 http://localhost:${UI_PORT}/ >/dev/null 2>&1; then
    echo -e "${GREEN}✅ UI service healthy (port ${UI_PORT})${NC}"
else
    echo -e "${RED}❌ UI service not responding (port ${UI_PORT})${NC}"
    all_healthy=false
fi

# 7. 結果とカメラリロード
echo ""
if [ "$all_healthy" = true ]; then
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"

    # カメラサービスのリロードが必要な場合（他のサービスが安定してから）
    if [ "$RESTART_CAMERA" = true ]; then
        echo ""
        echo -e "${BLUE}🔄 Reloading camera service with new code...${NC}"
        echo -e "${YELLOW}Other services are stable, now updating camera...${NC}"

        # カメラサービスの停止と再起動
        echo -e "${YELLOW}⏹️  Stopping camera service...${NC}"
        sudo systemctl stop coordinate-camera.service || true
        sudo pkill -9 -f "camera_service.py" || true
        sleep 3

        echo -e "${GREEN}🚀 Starting camera service...${NC}"
        sudo systemctl reset-failed coordinate-camera.service
        if ! sudo systemctl start coordinate-camera.service; then
            echo -e "${YELLOW}⚠️  Retrying camera start...${NC}"
            sleep 5
            sudo systemctl start coordinate-camera.service
        fi

        # カメラサービスの最終確認
        sleep 5
        if curl -fs --max-time 5 http://localhost:8001/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Camera service reloaded successfully${NC}"
        else
            echo -e "${RED}⚠️  Camera service may need manual intervention${NC}"
            echo "  sudo journalctl -u coordinate-camera -n 50"
            echo "  sudo systemctl status coordinate-camera.service"
        fi
    fi

    exit 0
else
    echo -e "${RED}❌ Deployment completed with errors${NC}"
    echo -e "${YELLOW}Check logs with:${NC}"
    echo "  sudo journalctl -u coordinate-api -n 50"
    echo "  sudo journalctl -u coordinate-camera -n 50"
    echo "  sudo journalctl -u coordinate-ui -n 50"
    exit 1
fi
