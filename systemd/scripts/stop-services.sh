#!/bin/bash

# Coordinate Recorder systemd サービス停止スクリプト
# 全てのサービスとタイマーを安全に停止します

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🛑 Coordinate Recorder サービスを停止します${NC}"

TIMERS=(
    "coordinate-photo-cleanup.timer"
    "coordinate-health-monitor.timer"
    "coordinate-api-deploy.timer"
)

SERVICES=(
    "camera-pir-monitor.service"
    "coordinate-kiosk.service"
    "coordinate-health-monitor.service"
    "coordinate-health-check.service"
    "coordinate-ui.service"
    "coordinate-api.service"
    "coordinate-camera.service"
    "coordinate-api-deploy.service"
)

for timer in "${TIMERS[@]}"; do
    echo -e "${GREEN}Stopping $timer...${NC}"
    if sudo systemctl stop "$timer"; then
        echo -e "${GREEN}✅ $timer stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  $timer was not active${NC}"
    fi
done

for service in "${SERVICES[@]}"; do
    echo -e "${GREEN}Stopping $service...${NC}"
    if sudo systemctl stop "$service"; then
        echo -e "${GREEN}✅ $service stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  $service was not running${NC}"
    fi
done

# 残存プロセスチェック
echo -e "${GREEN}🔍 残存プロセスを確認中...${NC}"

if pgrep -f "camera_service.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  カメラサービスのプロセスが残っています${NC}"
    pkill -f "camera_service.py" || true
fi

if pgrep -f "uvicorn.*main:app" > /dev/null; then
    echo -e "${YELLOW}⚠️  API サービスのプロセスが残っています${NC}"
    pkill -f "uvicorn.*main:app" || true
fi

echo -e "${GREEN}🎉 全てのサービスが停止しました${NC}"
