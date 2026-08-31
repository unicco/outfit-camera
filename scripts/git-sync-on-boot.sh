#!/usr/bin/env bash
# 起動時に origin/main へ同期する。
#
# 玄関 Pi はイベント駆動運用で普段はオフ（[[]]）。そのため CI/CD の自動デプロイが
# 届きにくい（マージ時に Pi が落ちていると反映されない）。これを補い、毎朝の起動時に
# main の最新コードへ自動追従させる。coordinate-git-sync.service から呼ばれ、camera/kiosk/pir
# サービスより前に実行される（Before= 指定）。
#
# 設計方針:
# - 認証は SSH（git@github.com）。SSH はクロック非依存なので、起動直後の NTP 未同期でも
#   問題なく fetch できる（HTTPS だと TLS 証明書検証がクロックずれで失敗しうるが、本リポは SSH）。
# - ベストエフォート。ネットワーク不通・fetch 失敗でも boot を止めない（必ず exit 0）。
#   呼び出し側 unit は順序依存（Before=）のみで、本サービスの成否に依存しない。
# - main 固定運用なので reset --hard で強制同期（ローカルドリフトも解消）。
# - コード同期だけでなく provisioning（unit の配置・enable・旧サービスと旧 sudoers の
#   掃除）も毎起動で流す。コードだけ追従させると unit の新設が Pi に届かない。
# - **新規** unit の enable は、その boot の target ジョブ集合が確定した後になるため
#   当該 boot では起動しない。次回起動から有効になる。
set -uo pipefail

REPO="/home/pi/coordinate-recorder"
# fetch 失敗を journal 以外にも残す。誰も journal を見ないまま Pi が古いコードで
# 動き続けるのを避けるため、直近の同期結果をファイルに落として setup-pi.sh の
# 確認節から読めるようにする。
STATUS_FILE="$REPO/.git-sync-status"
log() { logger -t coordinate-git-sync "$*"; echo "coordinate-git-sync: $*"; }

write_status() { echo "$1" > "$STATUS_FILE" 2>/dev/null || true; }

# コードの同期に失敗しても provisioning は流す（ネットワーク不要のため）。
provision() {
    local script="$REPO/deploy/setup-pi.sh"

    # 新しい本スクリプトと古い setup-pi.sh が同居する状態（main を revert した直後など）を弾く。
    # 古い setup-pi.sh は引数を解釈せず --provision-only を黙って無視するため、full 実行になって
    # `systemctl start coordinate-camera` を呼ぶ。本サービスは Before= でそれより前に順序づけ
    # られているので、start ジョブが本サービスの完了待ちに入り相互に詰まる。
    if ! grep -q -- '--provision-only' "$script" 2>/dev/null; then
        log "setup-pi.sh does not support --provision-only — skipping provisioning"
        return 0
    fi

    if bash "$script" --provision-only >/dev/null 2>&1; then
        log "provisioned (setup-pi.sh --provision-only)"
    else
        log "provisioning failed (best-effort)"
    fi
}

cd "$REPO" || { log "repo not found: $REPO"; exit 0; }

OLD="$(git rev-parse HEAD 2>/dev/null || echo none)"

# 非対話・短いタイムアウト（boot をブロックしないため）。SSH 鍵は unicco の ~/.ssh を使う。
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new"
if ! timeout 30 git fetch --quiet origin; then
    log "fetch failed (best-effort) — keeping current code $OLD"
    write_status "fetch-failed $OLD"
    provision
    exit 0
fi

if ! git reset --hard origin/main >/dev/null 2>&1; then
    log "reset failed — keeping $OLD"
    write_status "reset-failed $OLD"
    provision
    exit 0
fi

NEW="$(git rev-parse HEAD 2>/dev/null || echo none)"
if [ "$OLD" != "$NEW" ]; then
    log "updated $OLD -> $NEW"
else
    log "already up to date ($NEW)"
fi
write_status "ok $NEW"

# unit の配置・enable・旧サービスと旧 sudoers の掃除をここで揃える。本サービスは camera 等より
# 前に走るので、後続は新しい unit で起動する。差分の有無に関わらず毎回流して provisioning の
# ドリフトを自己修復させる（実測 3 秒）。
provision

exit 0
