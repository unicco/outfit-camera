#!/usr/bin/env bash
# Coordinate Recorder — VPS セットアップスクリプト
# VPS は API + UI サーバー。カメラは Pi で動作する。
#
# Usage:
#   ssh -i ~/.ssh/your-vps-key.pem deploy@vps.example.com
#   cd ~/services/coordinate-recorder
#   bash deploy/setup-vps.sh
#
# Prerequisites:
#   - coordinate-recorder repo cloned to ~/services/coordinate-recorder
#   - .env configured (DATABASE_URL, GEMINI_API_KEY, GCS credentials, etc.)
#   - PostgreSQL installed and coordinate_db created
#   - Caddy installed (shared with life-log)
#   - libgl1 installed (for OpenCV: sudo apt install libgl1 libglib2.0-0)
#   - Domain: coordinate.unicco.app (A record -> VPS IP, Cloudflare Origin Cert)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_DIR="$HOME/services/coordinate-recorder"

echo "=== Coordinate Recorder — VPS Setup ==="
echo "Project: $PROJECT_DIR"

# ---------------------------------------------------------------
# 1. システム依存パッケージ
# ---------------------------------------------------------------
echo ""
echo "--- [1/7] System dependencies ---"
if ! dpkg -s libgl1 &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq libgl1 libglib2.0-0
    echo "Installed libgl1, libglib2.0-0"
else
    echo "System deps OK"
fi

# ---------------------------------------------------------------
# 2. Python venv + dependencies
# ---------------------------------------------------------------
echo ""
echo "--- [2/7] Python venv ---"
if [ ! -d "$SERVICE_DIR/.venv" ]; then
    python3 -m venv "$SERVICE_DIR/.venv"
    echo "Created .venv"
else
    echo ".venv already exists"
fi
"$SERVICE_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$SERVICE_DIR/.venv/bin/pip" install --quiet -r "$SERVICE_DIR/requirements-api.txt"
echo "Dependencies installed"

# ---------------------------------------------------------------
# 3. Database migrations
# ---------------------------------------------------------------
echo ""
echo "--- [3/7] Database migrations ---"
cd "$SERVICE_DIR"
export PYTHONPATH="$SERVICE_DIR/api:$SERVICE_DIR/src:$SERVICE_DIR"
if [ -f "$SERVICE_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$SERVICE_DIR/.env"
    set +a
fi
"$SERVICE_DIR/.venv/bin/python" -m alembic -c api/alembic.ini upgrade head
echo "Migrations applied"

# ---------------------------------------------------------------
# 4. UI build
# ---------------------------------------------------------------
echo ""
echo "--- [4/7] UI build ---"
if command -v node &>/dev/null && [ -d "$SERVICE_DIR/ui" ]; then
    cd "$SERVICE_DIR/ui"
    npm ci --quiet
    VITE_API_URL="https://coordinate.unicco.app" npm run build
    echo "UI built to ui/dist/"
else
    echo "Node.js not found or ui/ missing. Skipping UI build."
    echo "Upload pre-built ui/dist/ manually if needed."
fi

# ---------------------------------------------------------------
# 5. Systemd services (user mode)
# ---------------------------------------------------------------
echo ""
echo "--- [5/7] Systemd services ---"
mkdir -p "$HOME/.config/systemd/user"

# API service
cp "$SERVICE_DIR/deploy/systemd/coordinate-api.service" \
   "$HOME/.config/systemd/user/coordinate-api.service"

# Health check timer
cp "$SERVICE_DIR/deploy/systemd/coordinate-health-check.service" \
   "$HOME/.config/systemd/user/coordinate-health-check.service"
cp "$SERVICE_DIR/deploy/systemd/coordinate-health-check.timer" \
   "$HOME/.config/systemd/user/coordinate-health-check.timer"

# DB backup timer
cp "$SERVICE_DIR/deploy/systemd/coordinate-db-backup.service" \
   "$HOME/.config/systemd/user/coordinate-db-backup.service"
cp "$SERVICE_DIR/deploy/systemd/coordinate-db-backup.timer" \
   "$HOME/.config/systemd/user/coordinate-db-backup.timer"

systemctl --user daemon-reload
systemctl --user enable coordinate-api.service
systemctl --user enable coordinate-health-check.timer
systemctl --user enable coordinate-db-backup.timer
systemctl --user restart coordinate-api.service
systemctl --user start coordinate-health-check.timer
systemctl --user start coordinate-db-backup.timer
echo "Services enabled: api, health-check (5min), db-backup (daily 03:00)"

# Enable linger so user services survive logout
loginctl enable-linger "$(whoami)" 2>/dev/null || true

# ---------------------------------------------------------------
# 6. Caddy (TLS with Cloudflare Origin Certificate)
# ---------------------------------------------------------------
echo ""
echo "--- [6/7] Caddy ---"
# Origin Certificate: Cloudflare Access が ACME challenge をブロックするため明示指定
if [ -f /etc/caddy/certs/origin.pem ]; then
    echo "Cloudflare Origin Certificate: OK"
else
    echo "WARNING: /etc/caddy/certs/origin.pem not found"
    echo "  Cloudflare Origin Certificate を設定してください"
fi

# sites-enabled パターン: 各サービスが自分の設定だけを管理し、他を上書きしない
sudo mkdir -p /etc/caddy/sites-enabled
if ! grep -q 'import /etc/caddy/sites-enabled/\*.caddy' /etc/caddy/Caddyfile 2>/dev/null; then
    echo 'import /etc/caddy/sites-enabled/*.caddy' | sudo tee /etc/caddy/Caddyfile
fi
# Layer 2の client_auth スニペット置き場。空でも import はエラーに
# ならない（enforcement なし）。CA 配置後に人間が client-auth.caddy を作成する。
sudo mkdir -p /etc/caddy/aop.d
sudo cp "$SERVICE_DIR/deploy/caddy/coordinate.caddy" /etc/caddy/sites-enabled/coordinate.caddy
# 不正設定での reload（公開断）を防ぐ: validate に通った時だけ reload する。
# reload の失敗も握りつぶさず表面化させる（旧: 2>/dev/null || true で沈黙していた）。
# 初回ブートストラップ（origin.pem 未配置）では validate が必ず落ちるため、cp のみで
# reload をスキップする（従来の非致命 warning 挙動を維持・証明書配置後に手動 reload）。
if [ ! -f /etc/caddy/certs/origin.pem ]; then
    echo "SKIP: origin.pem 未配置のため caddy validate/reload をスキップしました（初回ブートストラップ）。"
    echo "  origin.pem 配置後に手動で:"
    echo "    sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy"
elif sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
    sudo systemctl reload caddy
    echo "coordinate.caddy deployed to sites-enabled and Caddy reloaded"
else
    echo "ERROR: caddy validate に失敗。reload をスキップし既存設定を維持しました。" >&2
    echo "  Layer 2 の CA 証明書欠落等が原因の可能性。" >&2
    echo "  deploy/docs/cloudflare-authenticated-origin-pulls.md を参照。" >&2
    exit 1
fi

# ---------------------------------------------------------------
# 7. Verify
# ---------------------------------------------------------------
echo ""
echo "--- [7/7] Verification ---"
sleep 3

# API
if systemctl --user is-active coordinate-api.service &>/dev/null; then
    echo "OK: coordinate-api is running"
else
    echo "NG: coordinate-api failed"
    systemctl --user status coordinate-api.service --no-pager | tail -5
fi

# Health endpoint
if curl -sf -o /dev/null http://127.0.0.1:8000/health; then
    echo "OK: API responding on localhost:8000"
else
    echo "NG: API not responding (may need a few seconds)"
fi

# Timers
echo ""
echo "Timers:"
systemctl --user list-timers --no-pager | grep coordinate || echo "  (none)"

# Disk
echo ""
echo "Disk usage:"
du -sh "$SERVICE_DIR" --exclude='.venv' --exclude='.git' --exclude='node_modules' 2>/dev/null || true

echo ""
echo "=== VPS Setup Complete ==="
echo ""
echo "API:  https://coordinate.unicco.app/health"
echo "UI:   https://coordinate.unicco.app/"
echo "Docs: https://coordinate.unicco.app/docs"
echo ""
echo "セキュリティ: 公開 80/443 を Cloudflare レンジのみに絞る（オリジン直叩き迂回の封鎖）は"
echo "  別途手動で: sudo bash deploy/scripts/setup-firewall.sh --apply"
echo "  （auto-deploy には組み込まない。詳細: deploy/docs/cloudflare-ingress-firewall.md）"
