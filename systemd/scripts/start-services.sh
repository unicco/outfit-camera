#!/bin/bash

# Coordinate Recorder systemd サービス起動スクリプト
# 全てのサービスとタイマーを適切な順序で起動します

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Coordinate Recorder サービスを起動します${NC}"

# サービスリスト（起動順序）
SERVICES=(
    "coordinate-api-deploy.service"
    "coordinate-camera.service"
    "coordinate-api.service"
    "coordinate-ui.service"
    "coordinate-health-check.service"
    "coordinate-health-monitor.service"
    "coordinate-kiosk.service"
    "camera-pir-monitor.service"
)

TIMERS=(
    "coordinate-api-deploy.timer"
    "coordinate-health-monitor.timer"
    "coordinate-photo-cleanup.timer"
)

# 各サービスを起動
for service in "${SERVICES[@]}"; do
    echo -e "${GREEN}Starting $service...${NC}"
    if sudo systemctl start "$service"; then
        echo -e "${GREEN}✅ $service started${NC}"
    else
        echo -e "${RED}❌ Failed to start $service${NC}"
        exit 1
    fi
done

for timer in "${TIMERS[@]}"; do
    echo -e "${GREEN}Starting $timer...${NC}"
    if sudo systemctl start "$timer"; then
        echo -e "${GREEN}✅ $timer started${NC}"
    else
        echo -e "${RED}❌ Failed to start $timer${NC}"
        exit 1
    fi
done

echo -e "${GREEN}🎉 全てのサービスが起動しました${NC}"
echo ""
echo "サービスの状態を確認するには:"
echo "  ./systemd/scripts/status-services.sh"
echo ""
echo "ログを確認するには:"
echo "  sudo journalctl -u coordinate-camera -f"
echo "  sudo journalctl -u coordinate-api -f"
echo "  sudo journalctl -u coordinate-ui -f"
