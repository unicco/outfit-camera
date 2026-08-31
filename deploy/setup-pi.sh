#!/usr/bin/env bash
# Coordinate Recorder — Raspberry Pi セットアップスクリプト
# Pi はカメラ専用機。API・DB・UI は VPS で動作する。
#
# Usage:
#   ssh user@pi-camera.local
#   cd ~/coordinate-recorder
#   bash deploy/setup-pi.sh                    # 手動セットアップ・デプロイ用
#   bash deploy/setup-pi.sh --provision-only   # 起動時（git-sync-on-boot.sh から）
#
# --provision-only は unit の配置・enable・旧サービスと旧 sudoers の掃除だけを実施し、
# サービスの起動と古いデータの掃除を行わない。理由は 2 つ:
#   - 起動は systemd の責務。unit は target（graphical / multi-user）から起こされる。
#     スクリプトが重ねて start する必要がない
#   - データ掃除（[5/6]）は 1 台構成からの移行で一度やれば済む性質。毎 boot で
#     rm 系を回すのは事故ったときの被害が大きい
#
# Prerequisites:
#   - coordinate-recorder repo cloned to ~/coordinate-recorder
#   - .env に BACKEND_API_URL（VPS の Tailscale IP）を設定済
#   - Picamera2 がシステム Python で利用可能
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PROVISION_ONLY=false
case "${1:-}" in
    --provision-only) PROVISION_ONLY=true ;;
    "") ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
esac

# サービスが動いていなければ起動する。--provision-only では何もしない。
start_if_stopped() {
    local svc=$1
    if [ "$PROVISION_ONLY" = true ]; then
        echo "  $svc: start skipped (provision-only)"
        return 0
    fi
    if systemctl is-active "$svc" &>/dev/null; then
        echo "  $svc: already running"
    else
        sudo systemctl start "$svc"
        echo "  $svc: started"
    fi
}

echo "=== Coordinate Recorder — Pi Camera Setup ==="
echo "Project: $PROJECT_DIR"
if [ "$PROVISION_ONLY" = true ]; then
    echo "Mode: provision-only (起動と旧データ掃除はしない)"
fi

# ---------------------------------------------------------------
# 1. 不要サービス・旧 sudoers の停止・無効化・削除
# ---------------------------------------------------------------
echo ""
echo "--- [1/6] 不要サービス・旧 sudoers の整理 ---"

# 旧 kiosk（touchscreen-kiosk）は user unit として入るか、`@` 付きテンプレートの
# system unit として入るかの 2 通りだった。system スコープの素の名前だけを見ると
# どちらも取りこぼす。下のループで 3 通りすべてを当たる。
OBSOLETE_SERVICES=(
    coordinate-recorder-camera.service
    coordinate-recorder-api.service
    coordinate-recorder-ui.service
    coordinate-recorder-startup.service
    touchscreen-kiosk.service
    "touchscreen-kiosk@${USER:-$(id -un)}.service"
    # インスタンスを disable してもテンプレート本体は残るので明示的に消す
    touchscreen-kiosk@.service
    kiosk-browser.service
    coordinate-kiosk-managed.service
    coordinate-api.service
    coordinate-api-deploy.service
    coordinate-api-deploy.timer
    coordinate-ui.service
    coordinate-db-backup-push.service
    coordinate-db-backup-push.timer
    coordinate-health-check.service
    coordinate-health-monitor.service
    coordinate-health-monitor.timer
    coordinate-photo-cleanup.service
    coordinate-photo-cleanup.timer
    cloudflare-tunnel.service
    nginx.service

    # リポジトリに実体のない unit。disabled + inactive で害はないが、
    # 「どれが正なのか」を読む人が判断できなくなるので消す。
    cage-kiosk.service
    camera-health-monitor.service
    camera-restart.service
    compositor-keepalive.service
    display-always-on.service
    display-autofix.service
    display-keepalive.service
    display-no-timeout.service
    kiosk-chromium.service
    prevent-display-timeout.service
    touchscreen-app.service
    # 同じ tunnel を使っており稼働中。coordinate-recorder 分の ingress 整理は別 Issue。
)

for svc in "${OBSOLETE_SERVICES[@]}"; do
    # system スコープ
    if systemctl is-enabled "$svc" &>/dev/null; then
        sudo systemctl stop "$svc" 2>/dev/null || true
        sudo systemctl disable "$svc" 2>/dev/null || true
        echo "  Disabled: $svc"
    fi
    if [ -f "/etc/systemd/system/$svc" ]; then
        sudo rm "/etc/systemd/system/$svc"
        echo "  Removed: /etc/systemd/system/$svc"
    fi

    # user スコープ。旧 setup-kiosk-service.sh は「推奨」として user unit を入れていた
    if systemctl --user is-enabled "$svc" &>/dev/null; then
        systemctl --user stop "$svc" 2>/dev/null || true
        systemctl --user disable "$svc" 2>/dev/null || true
        echo "  Disabled (user): $svc"
    fi
    if [ -f "$HOME/.config/systemd/user/$svc" ]; then
        rm "$HOME/.config/systemd/user/$svc"
        echo "  Removed: ~/.config/systemd/user/$svc"
    fi
done

systemctl --user daemon-reload 2>/dev/null || true

# 役目を終えた sudoers。`/etc/sudoers.d/010_pi-nopasswd`（Raspberry Pi OS 標準）が
# `unicco ALL=(ALL) NOPASSWD: ALL` を与えているため、下の 3 本はいずれも既に許可済の
# 部分集合でしかない。狭めない判断の根拠は deploy/docs/pi-sudo-policy.md。
OBSOLETE_SUDOERS=(
    # setup-sudoers.sh が毎起動で生成していた。`/bin/sh -c` にワイルドカードを付ける
    # 形は、sudoers の引数マッチが `/` も貫通するため制限として機能しない
    kiosk-display-control
    # 2025-09-02 の手作業。display-brightness.sh（unicco 所有）自体に NOPASSWD を
    # 与えており、任意コードの root 実行に等しい
    coordinate-display
    # 2025-08-14 の手作業。中身は root→root の付与で最初から無効
    coordinate-recorder-watchdog
)

for sudoers_file in "${OBSOLETE_SUDOERS[@]}"; do
    if sudo test -f "/etc/sudoers.d/$sudoers_file"; then
        sudo rm "/etc/sudoers.d/$sudoers_file"
        echo "  Removed: /etc/sudoers.d/$sudoers_file"
    fi
done

# 手作業で置かれたバックライトの udev rule。deploy/udev/99-coordinate-backlight.rules に
# 一本化した。90 番は chmod 666 で ACTION フィルタも無く、99 番は chgrp を
# video ではなく unicco に当てていた。
OBSOLETE_UDEV_RULES=(
    90-backlight-permissions.rules
    99-backlight-permissions.rules
)

# rule を触ったときだけ reload + trigger する（[4/6] で実施）。毎起動 trigger は
# backlight 以外にも再列挙の副作用が出うるので打たない。
UDEV_CHANGED=false

for rule_file in "${OBSOLETE_UDEV_RULES[@]}"; do
    if [ -f "/etc/udev/rules.d/$rule_file" ]; then
        sudo rm "/etc/udev/rules.d/$rule_file"
        UDEV_CHANGED=true
        echo "  Removed: /etc/udev/rules.d/$rule_file"
    fi
done

# PostgreSQL
if systemctl is-enabled postgresql &>/dev/null; then
    sudo systemctl stop postgresql
    sudo systemctl disable postgresql
    echo "  Disabled: postgresql"
fi

sudo systemctl daemon-reload
echo "  systemd reloaded"

# ---------------------------------------------------------------
# 2. ログの永続化
# ---------------------------------------------------------------
echo ""
echo "--- [2/6] ログの永続化 ---"

# この Pi は撮影が済むと自分で halt するので、調べたい事象はたいてい「前回の boot」で
# 起きている。既定の volatile では halt した時点で証拠が消える。
# 上限つきで persistent に上書きする。理由と経緯は conf 自身のコメントに書いてある。
JOURNALD_DROPIN=journald-coordinate.conf
sudo mkdir -p /etc/systemd/journald.conf.d
if ! sudo cmp -s "$PROJECT_DIR/deploy/journald/$JOURNALD_DROPIN" \
                 "/etc/systemd/journald.conf.d/$JOURNALD_DROPIN"; then
    sudo cp "$PROJECT_DIR/deploy/journald/$JOURNALD_DROPIN" \
            "/etc/systemd/journald.conf.d/$JOURNALD_DROPIN"
    sudo systemctl restart systemd-journald
    # restart だけでは /run に溜まっているぶんが /var へ移らず、/var/log/journal が
    # 空のままになる（実機で確認）。次の boot からは systemd-journal-flush.service が
    # 自動でやるので、明示的に叩く必要があるのは設定を入れたこの回だけ。
    sudo journalctl --flush
    echo "  Installed: /etc/systemd/journald.conf.d/$JOURNALD_DROPIN (journald restarted & flushed)"
else
    echo "  journald: already persistent"
fi

# ---------------------------------------------------------------
# 3. カメラサービスの設定
# ---------------------------------------------------------------
echo ""
echo "--- [3/6] カメラサービス ---"

# 以降 enable ではなく reenable を使う。unit の [Install] WantedBy を変えても、
# enable は新しい target の symlink を足すだけで古い方を消さない。古い symlink が
# 残ると変更前の依存で引かれ続ける（kiosk-health-monitor を multi-user から
# graphical へ移す変更がまさにこれ）。reenable は disable + enable 相当で
# symlink を張り直す。

# 起動時 git 同期サービス（イベント駆動 Pi に main の変更を毎朝届ける。camera より前に実行）
sudo cp "$PROJECT_DIR/systemd/coordinate-git-sync.service" \
        /etc/systemd/system/coordinate-git-sync.service
chmod +x "$PROJECT_DIR/scripts/git-sync-on-boot.sh"
sudo systemctl reenable coordinate-git-sync.service
echo "  coordinate-git-sync: installed & enabled"

sudo cp "$PROJECT_DIR/systemd/coordinate-camera.service" \
        /etc/systemd/system/coordinate-camera.service

sudo systemctl daemon-reload
sudo systemctl reenable coordinate-camera.service

start_if_stopped coordinate-camera.service

# ---------------------------------------------------------------
# 4. Kiosk・PIR モニターサービスの設定
# ---------------------------------------------------------------
echo ""
echo "--- [4/6] Kiosk・PIR モニター ---"

# バックライトの書き込み権限。camera_service.py（PIR 連動の消灯）と
# scripts/display-brightness.sh は sudo を使わず sysfs を直接書く。
# Raspberry Pi OS 標準の 60-backlight.rules は brightness しか開放しないので、
# bl_power の分だけこの rule で足す。
BACKLIGHT_RULE=99-coordinate-backlight.rules
if ! sudo cmp -s "$PROJECT_DIR/deploy/udev/$BACKLIGHT_RULE" "/etc/udev/rules.d/$BACKLIGHT_RULE"; then
    sudo cp "$PROJECT_DIR/deploy/udev/$BACKLIGHT_RULE" "/etc/udev/rules.d/$BACKLIGHT_RULE"
    UDEV_CHANGED=true
    echo "  Installed: /etc/udev/rules.d/$BACKLIGHT_RULE"
fi

if [ "$UDEV_CHANGED" = true ]; then
    sudo udevadm control --reload-rules
    # 既定の action は change。この rule も標準の 60-backlight.rules も ACTION=="add" なので、
    # 明示しないと発火しない（実機の udevadm test で確認済）。
    # add を投げると systemd-backlight が保存値を復元して画面が点くことがあるが、rule を
    # 書き換えた回だけなので許容する。
    sudo udevadm trigger --action=add --subsystem-match=backlight
    echo "  udev rules reloaded & backlight re-triggered"
fi

# 書けなければ画面の制御が黙って死ぬ。deploy を止めるほどではないので警告に留める。
# brightness は標準の 60-backlight.rules 任せだが、そちらが失われたときも黙らせない。
for bl_dir in /sys/class/backlight/*/; do
    [ -d "$bl_dir" ] || continue
    for attr in brightness bl_power; do
        if [ -e "$bl_dir$attr" ] && [ ! -w "$bl_dir$attr" ]; then
            echo "  WARNING: $bl_dir$attr に書けない。udev rule が当たっていない可能性がある"
        fi
    done
done

for svc_file in coordinate-kiosk.service kiosk-health-monitor.service camera-pir-monitor.service; do
    if [ -f "$PROJECT_DIR/systemd/$svc_file" ]; then
        sudo cp "$PROJECT_DIR/systemd/$svc_file" "/etc/systemd/system/$svc_file"
        echo "  Installed: $svc_file"
    fi
done

sudo systemctl daemon-reload

# Kiosk（graphical.target が利用可能な場合のみ起動）
if systemctl list-units --type=target | grep -q graphical.target; then
    sudo systemctl reenable coordinate-kiosk.service
    sudo systemctl reenable kiosk-health-monitor.service
    start_if_stopped coordinate-kiosk.service
    start_if_stopped kiosk-health-monitor.service
else
    echo "  Skipped kiosk: graphical.target not available"
fi

# PIR モニター
sudo systemctl reenable camera-pir-monitor.service
start_if_stopped camera-pir-monitor.service

# ---------------------------------------------------------------
# 5. 古いデータ・ファイルの掃除
# ---------------------------------------------------------------
echo ""
echo "--- [5/6] 古いデータの掃除 ---"

cleanup_dir() {
    local dir="$1"
    local desc="$2"
    if [ -d "$dir" ]; then
        local size
        size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        rm -rf "$dir"
        echo "  Removed: $dir ($size) — $desc"
    fi
}

cleanup_file() {
    local file="$1"
    local desc="$2"
    if [ -f "$file" ]; then
        rm -f "$file"
        echo "  Removed: $file — $desc"
    fi
}

# 1 台構成からの移行で一度やれば済む処理。毎 boot で rm 系を回さない。
if [ "$PROVISION_ONLY" = true ]; then
    echo "  Skipped (provision-only)"
else

# API 用 venv（カメラはシステム Python を使用）
cleanup_dir "$PROJECT_DIR/venv" "旧 API 用 Python venv"

# 旧 DB（VPS に移行済）
cleanup_file "$PROJECT_DIR/coordinate_recorder.db" "旧 SQLite DB"

# nginx 関連
cleanup_dir "$PROJECT_DIR/nginx" "旧 nginx 設定"
cleanup_dir "$PROJECT_DIR/nginx-temp" "旧 nginx 一時ファイル"

# 旧ログ（30日以上前）
if [ -d "$PROJECT_DIR/logs" ]; then
    OLD_LOGS=$(find "$PROJECT_DIR/logs" -type f -mtime +30 | wc -l)
    if [ "$OLD_LOGS" -gt 0 ]; then
        find "$PROJECT_DIR/logs" -type f -mtime +30 -delete
        echo "  Cleaned: $OLD_LOGS old log files (>30 days)"
    fi
fi

# 旧バックアップ（VPS にバックアップ移行済）
cleanup_dir "$PROJECT_DIR/backups" "旧ローカルバックアップ"

# node_modules（Pi では UI ビルド不要）
cleanup_dir "$PROJECT_DIR/ui/node_modules" "UI node_modules"

echo "  Done"

fi

# ---------------------------------------------------------------
# 6. 確認
# ---------------------------------------------------------------
echo ""
echo "--- [6/6] 確認 ---"

# 起動時同期の結果。fetch 失敗を journal 以外からも拾えるようにしてある。
if [ -f "$PROJECT_DIR/.git-sync-status" ]; then
    echo "Last boot sync: $(cat "$PROJECT_DIR/.git-sync-status")"
    echo ""
fi

echo "Active services:"
systemctl list-units --type=service --state=running | grep -E "coordinate|kiosk|pir" || echo "  (none)"

echo ""
echo "Disk usage:"
du -sh "$PROJECT_DIR" 2>/dev/null

echo ""
# --provision-only は起動より前（boot の途中）に走るので、稼働確認をしても
# 全部 NG になるだけで意味がない。ここは通常実行時のみ。
if [ "$PROVISION_ONLY" = false ]; then
    CHECKS_OK=true
    for svc in coordinate-camera.service coordinate-kiosk.service kiosk-health-monitor.service camera-pir-monitor.service; do
        if systemctl is-active "$svc" &>/dev/null; then
            echo "OK: $svc is running"
        else
            echo "NG: $svc is not running"
            CHECKS_OK=false
        fi
    done

    if [ "$CHECKS_OK" = false ]; then
        echo ""
        echo "⚠️  一部サービスが起動していません。ログを確認してください:"
        echo "  sudo journalctl -u <service-name> -n 20 --no-pager"
    fi
fi

echo ""
echo "=== Pi Setup Complete ==="
echo ""
echo "Pi はカメラ撮影 + Kiosk 表示として動作します。"
echo "API: VPS (BACKEND_API_URL で指定)"
echo "UI:  https://coordinate.unicco.app/"
