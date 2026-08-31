#!/bin/bash

# Coordinate Recorder systemd サービス状態確認スクリプト
# 主なサービスとタイマーの状態をまとめて表示します

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📊 Coordinate Recorder サービス状態${NC}"
echo "======================================"

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

for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}✅ $service: active${NC}"
        PID=$(systemctl show -p MainPID --value "$service")
        if [ "$PID" -ne 0 ]; then
            MEM=$(ps -p "$PID" -o %mem= 2>/dev/null || echo "N/A")
            echo -e "   Memory: ${MEM}%"
        fi
    else
        status=$(systemctl is-active "$service")
        echo -e "${RED}❌ $service: $status${NC}"
    fi
done

echo ""
echo -e "${BLUE}⏱  タイマー状態${NC}"
echo "=================="
for timer in "${TIMERS[@]}"; do
    if systemctl is-active --quiet "$timer"; then
        next=$(systemctl list-timers --all | grep "$timer" | awk '{print $1, $2, $3, $4, $5}' | head -n 1)
        echo -e "${GREEN}✅ $timer: active (next ${next:-unknown})${NC}"
    else
        status=$(systemctl is-active "$timer")
        echo -e "${RED}❌ $timer: $status${NC}"
    fi
done

echo ""
echo -e "${BLUE}🔗 サービス URL${NC}"
echo "=================="
echo "API: http://localhost:8000/health"
echo "Camera: http://localhost:8001/health"
echo "UI: http://localhost:3000"

echo ""
echo -e "${BLUE}🎛️  PIR センサー状態${NC}"
echo "==================="
if curl -s http://localhost:8001/health > /dev/null 2>&1; then
    pir_status=$(curl -s http://localhost:8001/health | python3 -c "
import json, sys
data = json.load(sys.stdin)
pir = data.get('pir_status', {})
print(f\"Enabled: {pir.get('enabled', 'N/A')}\")
print(f\"Detections: {pir.get('detections_count', 'N/A')}\")
print(f\"Daily photo: {pir.get('daily_photo_taken', 'N/A')}\")
" 2>/dev/null || echo "PIR status unavailable")
    echo "$pir_status"
else
    echo -e "${RED}カメラサービスに接続できません${NC}"
fi
