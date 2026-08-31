#!/bin/bash
set -euo pipefail

# Periodic health monitor for API and UI services.
# Intended to run as a systemd oneshot service triggered by a timer.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common-logging.sh"

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ENV_FILE"
    set +a
fi

PORTS_CONF="${SCRIPT_DIR}/service-ports.conf"
if [ -f "$PORTS_CONF" ]; then
    # shellcheck disable=SC1090
    source "$PORTS_CONF"
fi

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-3000}"

DEFAULT_API_URL="http://localhost:${API_PORT}/health"
DEFAULT_UI_URL="http://localhost:${UI_PORT}/"

API_URL="${API_HEALTH_URL:-$DEFAULT_API_URL}"
UI_URL="${UI_HEALTH_URL:-$DEFAULT_UI_URL}"
RETRY=2
SLEEP_BETWEEN=5
EXIT_CODE=0

GOOGLE_PHOTOS_STATUS_CACHE="/tmp/coordinate-google-photos-auth-status"
GOOGLE_PHOTOS_DISCORD_CACHE="/tmp/coordinate-google-photos-discord-alert"
GOOGLE_PHOTOS_PRE_ALERT_CACHE="/tmp/coordinate-google-photos-pre-alert"
GOOGLE_PHOTOS_ALERT_TITLE="[Alert] Google Photos 連携の再認証が必要です"
GOOGLE_PHOTOS_HEALTH_MAX_RETRIES="${GOOGLE_PHOTOS_MAX_RETRIES:-3}"
GOOGLE_PHOTOS_HEALTH_RETRY_DELAY="${GOOGLE_PHOTOS_RETRY_DELAY:-1.0}"
DISCORD_WEBHOOK_URL="${DISCORD_ALERT_WEBHOOK_URL:-}"
DISCORD_USERNAME="${DISCORD_ALERT_USERNAME:-Coordinate Recorder Monitor}"
DISCORD_AVATAR_URL="${DISCORD_ALERT_AVATAR_URL:-}"
DISCORD_ALERT_MENTION="${DISCORD_ALERT_MENTION:-}"
GOOGLE_PHOTOS_DISCORD_MESSAGE="${GOOGLE_PHOTOS_DISCORD_MESSAGE:-":warning: Google Photos の認証状態が失効しました。Discord 通知のリンクから再認証を開始してください。"}"
GOOGLE_PHOTOS_PRE_ALERT_MESSAGE="${GOOGLE_PHOTOS_PRE_ALERT_MESSAGE:-":alarm_clock: Google Photos のリフレッシュトークンが期限間近です。"}"
GOOGLE_PHOTOS_RECOVERY_MESSAGE="${GOOGLE_PHOTOS_RECOVERY_MESSAGE:-":white_check_mark: Google Photos の認証が復旧しました。"}"
GOOGLE_PHOTOS_AUTH_GUIDE="${GOOGLE_PHOTOS_AUTH_GUIDE:-docs/setup/google-photos-auth-guide.md}"
GOOGLE_PHOTOS_TOKEN_WARNING_DAYS="${GOOGLE_PHOTOS_TOKEN_WARNING_DAYS:-6}"
GOOGLE_PHOTOS_TOKEN_EXPIRY_DAYS="${GOOGLE_PHOTOS_TOKEN_EXPIRY_DAYS:-7}"
GOOGLE_PHOTOS_LOCAL_CALLBACK="${GOOGLE_PHOTOS_LOCAL_CALLBACK:-http://localhost:${API_PORT}/api/v2/google-photos/oauth2callback}"
GOOGLE_PHOTOS_REMOTE_CALLBACK="${GOOGLE_PHOTOS_REMOTE_CALLBACK:-https://coordinate.unicco.app/api/v2/google-photos/oauth2callback}"
GOOGLE_PHOTOS_AUTH_URL_ENDPOINT="http://localhost:${API_PORT}/api/v2/google-photos/auth-url"
GOOGLE_PHOTOS_TOKEN_FILE_PATH="${GOOGLE_TOKEN_FILE:-google_photos_token.json}"
if [[ "$GOOGLE_PHOTOS_TOKEN_FILE_PATH" != /* ]]; then
    GOOGLE_PHOTOS_TOKEN_FILE_PATH="${PROJECT_ROOT}/${GOOGLE_PHOTOS_TOKEN_FILE_PATH}"
fi

GH_BIN="$(command -v gh || true)"
HAVE_GH=false
if [ -n "$GH_BIN" ]; then
    if "$GH_BIN" auth status >/dev/null 2>&1; then
        HAVE_GH=true
    fi
fi

check_endpoint() {
    local url="$1"
    local label="$2"

    local attempt=1
    while [ $attempt -le $RETRY ]; do
        if curl -fs --max-time 8 "$url" >/dev/null 2>&1; then
            log_info "${label} responding"
            return 0
        fi

        log_warn "${label} not responding (attempt ${attempt}/${RETRY})"
        attempt=$((attempt + 1))
        sleep "$SLEEP_BETWEEN"
    done

    log_error "${label} did not respond after ${RETRY} attempts"
    return 1
}

remediate_service() {
    local service_name="$1"
    local action_label="$2"

    if systemctl is-enabled "$service_name" >/dev/null 2>&1; then
        log_warn "${action_label}"
        if ! sudo systemctl restart "$service_name"; then
            log_error "Failed to restart ${service_name}"
            while IFS= read -r status_line; do
                log_error "  status: ${status_line}"
            done < <(sudo systemctl status "$service_name" --no-pager 2>/dev/null | tail -n 10 || true)
            while IFS= read -r journal_line; do
                log_error "  journal: ${journal_line}"
            done < <(sudo journalctl -u "$service_name" -n 10 --no-pager 2>/dev/null || true)
            EXIT_CODE=1
        fi
    else
        log_warn "${service_name} is not enabled; skipping restart"
        EXIT_CODE=1
    fi
}

log_info "Running coordinate health monitor"

send_discord_message() {
    local message="$1"

    if [ -z "$DISCORD_WEBHOOK_URL" ]; then
        log_warn "Discord webhook URL is not configured; skipping Discord alert"
        return 1
    fi

    if [ -z "$message" ]; then
        log_warn "Discord message content is empty; skipping alert"
        return 1
    fi

    local content="$message"
    if [ -n "$DISCORD_ALERT_MENTION" ]; then
        content="${DISCORD_ALERT_MENTION} ${content}"
    fi

    local payload
    if ! payload=$(
        printf '%s' "$content" | DISCORD_USERNAME_VALUE="$DISCORD_USERNAME" DISCORD_AVATAR_URL_VALUE="$DISCORD_AVATAR_URL" python3 - <<'PY'
import json
import os
import sys

message = sys.stdin.read()
username = os.environ.get("DISCORD_USERNAME_VALUE", "")
avatar = os.environ.get("DISCORD_AVATAR_URL_VALUE", "")

message = message.rstrip("\n")
if not message:
    sys.exit(1)

payload = {"content": message}
if username:
    payload["username"] = username
if avatar:
    payload["avatar_url"] = avatar

print(json.dumps(payload))
PY
    ); then
        log_error "Failed to build Discord payload; skipping alert"
        return 1
    fi

    if [ -z "$payload" ]; then
        log_error "Discord payload is empty; skipping alert"
        return 1
    fi

    if ! curl -fsS -H "Content-Type: application/json" -d "$payload" "$DISCORD_WEBHOOK_URL" >/dev/null; then
        log_error "Failed to send Discord alert"
        return 1
    fi

    return 0
}

fetch_google_photos_auth_url() {
    local redirect_uri="$1"
    local request_url="$GOOGLE_PHOTOS_AUTH_URL_ENDPOINT"

    if [ -n "$redirect_uri" ]; then
        local encoded_redirect
        if ! encoded_redirect=$(REDIRECT_URI="$redirect_uri" python3 - <<'PY'
import os
import urllib.parse

redirect = os.environ.get("REDIRECT_URI", "")
print(urllib.parse.quote_plus(redirect))
PY
        ); then
            log_warn "Failed to encode Google Photos redirect URI"
            return 1
        fi
        request_url="${request_url}?redirect_uri=${encoded_redirect}"
    fi

    local response
    if ! response=$(curl -fsS --max-time 10 "$request_url" 2>/dev/null); then
        log_warn "Failed to request Google Photos auth URL (${request_url})"
        return 1
    fi

    local auth_url
    if ! auth_url=$(printf '%s' "$response" | python3 - <<'PY'
import json
import sys

try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    sys.exit(1)

value = data.get("auth_url") or data.get("authUrl")
if not value:
    sys.exit(1)
print(value)
PY
    ); then
        log_warn "Failed to parse Google Photos auth URL response"
        return 1
    fi

    if [ -z "$auth_url" ]; then
        log_warn "Google Photos auth URL response is empty"
        return 1
    fi

    printf '%s\n' "$auth_url"
}

build_google_photos_reauth_links() {
    local links=()

    if [ -n "$GOOGLE_PHOTOS_LOCAL_CALLBACK" ]; then
        local local_auth_url=""
        if local_auth_url=$(fetch_google_photos_auth_url "$GOOGLE_PHOTOS_LOCAL_CALLBACK"); then
            links+=("- ローカル (${GOOGLE_PHOTOS_LOCAL_CALLBACK}): ${local_auth_url}")
        else
            links+=("- ローカル (${GOOGLE_PHOTOS_LOCAL_CALLBACK}): 再認証 URL の取得に失敗しました。手動で `/api/v2/google-photos/auth-url` を実行してください。")
        fi
    fi

    if [ -n "$GOOGLE_PHOTOS_REMOTE_CALLBACK" ]; then
        local remote_auth_url=""
        if remote_auth_url=$(fetch_google_photos_auth_url "$GOOGLE_PHOTOS_REMOTE_CALLBACK"); then
            links+=("- Cloudflare (${GOOGLE_PHOTOS_REMOTE_CALLBACK}): ${remote_auth_url}")
        else
            links+=("- Cloudflare (${GOOGLE_PHOTOS_REMOTE_CALLBACK}): 再認証 URL の取得に失敗しました。Cloudflare 越しに `/api/v2/google-photos/auth-url` を実行してください。")
        fi
    fi

    if [ ${#links[@]} -eq 0 ]; then
        return 1
    fi

    printf '%s\n' "${links[@]}"
}

send_google_photos_discord_alert() {
    local cache_file="$GOOGLE_PHOTOS_DISCORD_CACHE"
    if [ -f "$cache_file" ]; then
        return
    fi

    local reauth_links
    reauth_links=$(build_google_photos_reauth_links || true)

    local content="$GOOGLE_PHOTOS_DISCORD_MESSAGE"
    if [ -n "$reauth_links" ]; then
        content="${content}\n\n再認証リンク:\n${reauth_links}"
    fi
    if [ -n "$GOOGLE_PHOTOS_AUTH_GUIDE" ]; then
        content="${content}\n\n手順: ${GOOGLE_PHOTOS_AUTH_GUIDE}"
    fi

    if send_discord_message "$content"; then
        log_warn "Sent Discord alert for Google Photos authentication failure"
        echo "sent" >"$cache_file"
    fi
}

send_google_photos_recovery_alert() {
    local content="$GOOGLE_PHOTOS_RECOVERY_MESSAGE"
    if [ -n "$GOOGLE_PHOTOS_AUTH_GUIDE" ]; then
        content="${content}\n手順: ${GOOGLE_PHOTOS_AUTH_GUIDE}"
    fi

    if send_discord_message "$content"; then
        log_info "Sent Discord recovery notification for Google Photos"
    fi
}

send_google_photos_pre_alert() {
    local age_days="$1"
    local issued_at="$2"
    local expiry_at="$3"

    local reauth_links
    reauth_links=$(build_google_photos_reauth_links || true)

    local content
    content=$(cat <<EOF
${GOOGLE_PHOTOS_PRE_ALERT_MESSAGE}
- 最終再認証: ${issued_at}
- 経過日数: ${age_days} 日
- 想定失効: ${expiry_at}
EOF
)

    if [ -n "$reauth_links" ]; then
        content="${content}\n\n再認証リンク:\n${reauth_links}"
    fi
    if [ -n "$GOOGLE_PHOTOS_AUTH_GUIDE" ]; then
        content="${content}\n\n手順: ${GOOGLE_PHOTOS_AUTH_GUIDE}"
    fi

    if send_discord_message "$content"; then
        log_info "Sent Discord warning for Google Photos token expiry"
        echo "sent" >"$GOOGLE_PHOTOS_PRE_ALERT_CACHE"
    fi
}

maybe_warn_google_photos_token_expiry() {
    if [ ! -f "$GOOGLE_PHOTOS_TOKEN_FILE_PATH" ]; then
        if [ -f "$GOOGLE_PHOTOS_PRE_ALERT_CACHE" ]; then
            rm -f "$GOOGLE_PHOTOS_PRE_ALERT_CACHE"
        fi
        log_debug "Google Photos token file not found; skipping expiry warning"
        return
    fi

    local metadata
    if ! metadata=$(
        TOKEN_FILE="$GOOGLE_PHOTOS_TOKEN_FILE_PATH" \
        TOKEN_EXPIRY_DAYS="$GOOGLE_PHOTOS_TOKEN_EXPIRY_DAYS" \
        python3 - <<'PY'
import datetime
import os
import time

token_file = os.environ.get("TOKEN_FILE")
expiry_days = float(os.environ.get("TOKEN_EXPIRY_DAYS", "7"))
if not token_file or not os.path.exists(token_file):
    raise SystemExit(1)
mtime = os.path.getmtime(token_file)
age_seconds = int(time.time() - mtime)
age_days = age_seconds / 86400
tz = datetime.timezone(datetime.timedelta(hours=9))
issued_at = datetime.datetime.fromtimestamp(mtime, tz).strftime("%Y-%m-%d %H:%M:%S %Z")
expected_expiry = datetime.datetime.fromtimestamp(
    mtime + expiry_days * 86400,
    tz,
).strftime("%Y-%m-%d %H:%M:%S %Z")
print(f"{age_seconds}|{age_days:.1f}|{issued_at}|{expected_expiry}")
PY
    ); then
        log_warn "Failed to calculate Google Photos token metadata"
        return
    fi

    IFS='|' read -r age_seconds age_days issued_at expiry_at <<<"$metadata"
    if [ -z "$age_seconds" ]; then
        return
    fi

    local warning_threshold_seconds
    if ! warning_threshold_seconds=$(python3 - <<PY
print(int(float("$GOOGLE_PHOTOS_TOKEN_WARNING_DAYS") * 86400))
PY
    ); then
        log_warn "Failed to calculate Google Photos token warning threshold"
        return
    fi

    if [ "$age_seconds" -ge "$warning_threshold_seconds" ]; then
        if [ ! -f "$GOOGLE_PHOTOS_PRE_ALERT_CACHE" ]; then
            send_google_photos_pre_alert "$age_days" "$issued_at" "$expiry_at"
        fi
    else
        if [ -f "$GOOGLE_PHOTOS_PRE_ALERT_CACHE" ]; then
            rm -f "$GOOGLE_PHOTOS_PRE_ALERT_CACHE"
        fi
    fi
}

if ! check_endpoint "$API_URL" "API"; then
    remediate_service "coordinate-api.service" "Restarting coordinate-api.service..."
fi

if ! check_endpoint "$UI_URL" "UI"; then
    remediate_service "coordinate-ui.service" "Restarting coordinate-ui.service..."
fi

check_google_photos_health() {
    local status_url="http://localhost:${API_PORT}/api/v2/google-photos/auth-status"

    local attempt=1
    local max_attempts="${GOOGLE_PHOTOS_HEALTH_MAX_RETRIES:-3}"
    local base_delay="${GOOGLE_PHOTOS_HEALTH_RETRY_DELAY:-1.0}"
    local response
    local is_authenticated="error"

    while [ "$attempt" -le "$max_attempts" ]; do
        if ! response=$(curl -fsS --max-time 8 "$status_url" 2>/dev/null); then
            log_warn "Google Photos auth status request failed (attempt ${attempt}/${max_attempts})"
        else
            is_authenticated=$(printf '%s' "$response" | python3 - <<'PY'
import json, sys
try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    print("error")
    sys.exit(0)
value = data.get("isAuthenticated")
if value is None:
    value = data.get("is_authenticated")
print("true" if value else "false")
PY
)
            if [ "$is_authenticated" != "error" ]; then
                break
            fi
            log_warn "Google Photos auth status parse error (attempt ${attempt}/${max_attempts})"
        fi

        attempt=$((attempt + 1))
        sleep "$base_delay"
    done

    if [ "$is_authenticated" = "error" ]; then
        log_error "Google Photos auth status check did not succeed after ${max_attempts} attempts"
        return
    fi

    if [ "$is_authenticated" != "true" ]; then
        log_warn "Google Photos auth status is false"
        send_google_photos_discord_alert
        if [ "$HAVE_GH" = true ]; then
            create_google_photos_issue
        else
            log_warn "gh CLI not available or not authenticated; skipping automatic issue creation"
        fi
    else
        log_info "Google Photos authentication OK"
        if [ -f "$GOOGLE_PHOTOS_DISCORD_CACHE" ]; then
            send_google_photos_recovery_alert
        fi
        if [ -f "$GOOGLE_PHOTOS_STATUS_CACHE" ]; then
            rm -f "$GOOGLE_PHOTOS_STATUS_CACHE"
        fi
        if [ -f "$GOOGLE_PHOTOS_DISCORD_CACHE" ]; then
            rm -f "$GOOGLE_PHOTOS_DISCORD_CACHE"
        fi
        maybe_warn_google_photos_token_expiry
    fi
}

create_google_photos_issue() {
    local cache_file="$GOOGLE_PHOTOS_STATUS_CACHE"
    if [ -f "$cache_file" ]; then
        return
    fi

    local existing
    if ! existing=$($GH_BIN issue list --state open --search "\"$GOOGLE_PHOTOS_ALERT_TITLE\"" --limit 1 --json number --jq '.[0].number' 2>/dev/null); then
        existing=""
    fi

    if [ -n "$existing" ]; then
        log_info "Existing Google Photos alert issue #$existing already open"
        echo "open" >"$cache_file"
        return
    fi

    local body
    body=$(cat <<'EOF'
## 概要
- coordinate-health-monitor が Google Photos API の認証状態を `false` と検知しました。
- 再認証手順は `docs/setup/google-photos-auth-guide.md` を参照してください。

## 推奨対応
1. `curl http://localhost:8000/api/v2/google-photos/auth-status` で状態を再確認する。
2. `docs/setup/google-photos-auth-guide.md` に沿ってトークンを再生成して再認証する。

## 補足
- この Issue は自動起票されています。対応後は手動でクローズしてください。
EOF
)

    if $GH_BIN issue create --title "$GOOGLE_PHOTOS_ALERT_TITLE" --body "$body" --label "type:bug" --label "area:api" >/dev/null 2>&1; then
        log_warn "Opened GitHub issue for Google Photos authentication alert"
        echo "open" >"$cache_file"
    else
        log_error "Failed to create GitHub issue for Google Photos authentication alert"
    fi
}

check_google_photos_health

exit "$EXIT_CODE"
