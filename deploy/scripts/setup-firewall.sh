#!/usr/bin/env bash
# Coordinate Recorder — Cloudflare-only ingress firewall (UFW)
#
# 目的: オリジン(VPS)への公開 80/443 を Cloudflare の公開 IP レンジからのみ許可し、
#       オリジン IP を直叩きして Cloudflare Access を迂回する攻撃を封じる（多層防御 Layer 1）
#
# 背景: 本番は Caddy + Cloudflare Origin 証明書で稼働し、認証はエッジの Cloudflare Access 頼み。
#       UFW が 80/443 を Anywhere に開けているため、オリジン IP が判明すると
#       Host ヘッダを付けた直アクセスで Cloudflare Access を丸ごと迂回できる。
#       全公開トラフィックを Cloudflare 経由に強制することで、この迂回経路を塞ぐ。
#
# 特徴:
#   - 冪等: 既存の cf-ingress-web ルールを削除してから現在の CF レンジで貼り直す
#   - ロックアウト防止: tailscale0 を先に許可し、既存 SSH ルールは削除しない（公開 SSH は
#     既定で追加せず露出を広げない。Tailscale 非利用時のみ ALLOW_PUBLIC_SSH=true で opt-in）
#   - egress 非改変: incoming のみ deny に設定し、outgoing ポリシーには触れない
#   - フェイルセーフ: CF レンジの取得に失敗したら何も変更せず中断（空の許可リストで締め出さない）
#   - 事後検証: 「CF レンジ→80/443」「SSH」「Tailscale」以外の inbound ALLOW が残れば ERROR。
#     送信元・宛先カラムで判定しコメントは信頼しない（偽装・特定 IP・非 web ポート露出も検出）
#   - デフォルトは dry-run（実行内容を表示するだけ）。実適用は --apply
#
# Usage（VPS 上で実行）:
#   bash deploy/scripts/setup-firewall.sh              # dry-run: 実行される内容を確認
#   sudo bash deploy/scripts/setup-firewall.sh --apply # 実適用
#
# 注意:
#   - auto-deploy（setup-vps.sh）には組み込まない。毎デプロイでの UFW 変更は
#     ロックアウト事故のリスクがあるため、本スクリプトは人間が一度だけ手動で流す。
#   - この VPS は life-log 等と同居している。default deny incoming を適用すると
#     未把握の公開ポートは締め出される。適用前に必ず現在の listen ポートを確認すること
#     （下の [1/6] で `ss -tlnp` の結果を表示する）。
set -euo pipefail

CF_IPV4_URL="https://www.cloudflare.com/ips-v4"
CF_IPV6_URL="https://www.cloudflare.com/ips-v6"
INGRESS_PORTS=(80 443)
SSH_PORT=22
TAILSCALE_IFACE="tailscale0"

# ルールコメント（UFW status で識別・冪等な貼り直しに使う）
WEB_COMMENT="cf-ingress-web"   # CF レンジ限定の 80/443（毎回貼り直す）
SSH_COMMENT="cf-ingress-ssh"   # SSH 保全（削除しない）
TS_COMMENT="cf-ingress-ts"     # Tailscale 保全（削除しない）

APPLY=false
if [ "${1:-}" = "--apply" ]; then
    APPLY=true
fi

# run: --apply 時のみ実際に実行し、常にコマンドを表示する
run() {
    echo "+ $*"
    if [ "$APPLY" = true ]; then
        "$@"
    fi
}

# ---------------------------------------------------------------
# 0. 前提チェック
# ---------------------------------------------------------------
if ! command -v ufw &>/dev/null; then
    echo "ERROR: ufw が見つかりません。sudo apt-get install ufw で導入してください。" >&2
    exit 1
fi
if [ "$APPLY" = true ] && [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: --apply は root で実行してください（sudo bash $0 --apply）。" >&2
    exit 1
fi

echo "=== Cloudflare-only ingress firewall ==="
if [ "$APPLY" = true ]; then
    echo "モード: APPLY（実適用）"
else
    echo "モード: DRY-RUN（表示のみ・変更なし）。実適用は --apply を付与。"
fi

# ---------------------------------------------------------------
# 1. 同居サービスのポート確認（ブラスト半径の可視化）
# ---------------------------------------------------------------
echo ""
echo "--- [1/6] 現在 listen 中のポート（default deny incoming の影響確認）---"
if command -v ss &>/dev/null; then
    ss -tlnp 2>/dev/null || ss -tln
    echo ""
    echo "↑ SSH(22) / Tailscale / 80 / 443 以外に外部公開が必要なポートがあれば、"
    echo "  適用前にこのスクリプトへ許可ルールを追記すること（同居サービスの締め出し防止）。"
else
    echo "（ss コマンドなし。手動で listen ポートを確認してください）"
fi

# ---------------------------------------------------------------
# 2. Cloudflare 公開 IP レンジを取得（IPv4 / IPv6 個別に検証）
# ---------------------------------------------------------------
echo ""
echo "--- [2/6] Cloudflare IP レンジ取得 ---"
fetch_ranges() {
    # curl の失敗（タイムアウト・切断等）を握り潰すと、途中まで取得した部分データが
    # 有効扱いされ不完全な許可リストで貼り直してしまう（正当な CF 遮断＝fail-unsafe）。
    # 出力と終了ステータスを分離し、成功(0)のときだけ本文を返す。失敗時は空 + return 1。
    local out rc=0
    out=$(curl -fsS --max-time 15 "$1" 2>/dev/null) || rc=$?
    if [ "$rc" -ne 0 ]; then
        return 1
    fi
    printf '%s' "$out"
}
read_nonempty_lines() {
    # 引数の複数行文字列から空行を除いて配列に読み込む（グローバル _LINES に格納）。
    # `[ -n "$line" ] && ...` は空行で exit 1 を返し set -e 中断を招くため if で書く
    # （入力が空文字＝取得失敗時にこの関数が空行 1 個を読むため、その経路で顕在化する）。
    _LINES=()
    while IFS= read -r line; do
        if [ -n "$line" ]; then _LINES+=("$line"); fi
    done <<< "$1"
}

# 取得失敗（return 1）時は空文字にフォールバックし、下の件数チェックで
# friendly なエラーメッセージを出して fail-safe に中断する。
cf_v4_raw=$(fetch_ranges "$CF_IPV4_URL") || cf_v4_raw=""
read_nonempty_lines "$cf_v4_raw"
# 空配列を "${arr[@]}" で展開すると古い bash + set -u で落ちるためガードする。
CF_V4=()
if [ "${#_LINES[@]}" -gt 0 ]; then CF_V4=("${_LINES[@]}"); fi
cf_v6_raw=$(fetch_ranges "$CF_IPV6_URL") || cf_v6_raw=""
read_nonempty_lines "$cf_v6_raw"
CF_V6=()
if [ "${#_LINES[@]}" -gt 0 ]; then CF_V6=("${_LINES[@]}"); fi

# フェイルセーフ: どちらか一方でも 0 件なら中断（片系統だけ全遮断されるサイレント障害を防ぐ）
if [ "${#CF_V4[@]}" -lt 1 ] || [ "${#CF_V6[@]}" -lt 1 ]; then
    echo "ERROR: Cloudflare IP レンジを取得できませんでした（IPv4: ${#CF_V4[@]} / IPv6: ${#CF_V6[@]}）。" >&2
    echo "       ネットワークを確認してください。ファイアウォールは変更していません。" >&2
    exit 1
fi

CF_RANGES=("${CF_V4[@]}" "${CF_V6[@]}")
# CIDR 形式の簡易検証
for cidr in "${CF_RANGES[@]}"; do
    if [[ ! "$cidr" =~ ^[0-9a-fA-F:.]+/[0-9]+$ ]]; then
        echo "ERROR: CF レンジに不正な値が含まれます: '$cidr'。中断します。" >&2
        exit 1
    fi
done
echo "取得: IPv4 ${#CF_V4[@]} + IPv6 ${#CF_V6[@]} = ${#CF_RANGES[@]} レンジ"

# ---------------------------------------------------------------
# 3. ロックアウト防止ルール（SSH + Tailscale）を先に投入
# ---------------------------------------------------------------
echo ""
echo "--- [3/6] SSH / Tailscale の許可（ロックアウト防止）---"
# 管理 SSH は Tailscale 経由（ssh conoha = tailscale0）を前提にする。
# 公開 SSH(22/tcp) は既定では追加しない（既存の SSH 許可を広げない）。既存の
# 公開 SSH ルールがあっても本スクリプトは削除しない（80/443 と cf-ingress-web のみ削除）。
run ufw allow in on "$TAILSCALE_IFACE" comment "$TS_COMMENT"
if [ "${ALLOW_PUBLIC_SSH:-false}" = "true" ]; then
    echo "ALLOW_PUBLIC_SSH=true: 公開 SSH(${SSH_PORT}/tcp) を明示許可します。"
    run ufw allow "${SSH_PORT}/tcp" comment "$SSH_COMMENT"
else
    echo "公開 SSH は追加しません（Tailscale 経由 + 既存ルール保全）。"
    echo "適用前に 'ssh conoha'（Tailscale）が通ることを必ず確認すること。"
    echo "Tailscale を使わず公開 SSH が必要なら ALLOW_PUBLIC_SSH=true を付けて再実行。"
fi

# ---------------------------------------------------------------
# 4. UFW を active 化（削除を可視化するため先に有効化）
# ---------------------------------------------------------------
# 重要: UFW が inactive の間 `ufw status` は保存済ルールを一覧しない。
# そのため削除ループ（[5]）より前に enable して、既存 legacy ルールを可視化する。
# ここまでで tailscale0（+ 任意で公開 SSH）は許可済なのでロックアウトしない。
# production は既に active なので再 enable せず、broad ルールも [5] の撤去まで生存
# するため 80/443 は無停止。inactive の箱では CF 許可付与（[5]）までの数秒 80/443 が
# 絞られるが、手動メンテ操作なので許容する。
echo ""
echo "--- [4/6] UFW を active 化（default deny incoming）---"
run ufw default deny incoming
if [ "$APPLY" = true ]; then
    if ufw status | grep -q "Status: active"; then
        echo "UFW は既に active"
    else
        run ufw --force enable
    fi
else
    echo "+ (dry-run) UFW が inactive なら 'ufw --force enable'"
fi

# ---------------------------------------------------------------
# 5. cf-ingress-web 貼り直し + CF レンジ許可 + 広域ルール撤去
# ---------------------------------------------------------------
echo ""
echo "--- [5/6] $WEB_COMMENT を貼り直し + Cloudflare レンジ ${INGRESS_PORTS[*]} を許可 ---"
# 既存の cf-ingress-web を削除してから現在の CF レンジで貼り直す（冪等・stale CIDR 除去）。
# UFW は「コメントで削除」ができないため numbered status を番号で削除。削除で番号が
# ずれるため毎回 head -1 を取り直す。grep 無マッチ時は pipefail で代入が exit 1 に
# なるため `|| true` を付けて num="" で break へ落とす（set -e 中断の回避）。
if [ "$APPLY" = true ]; then
    while true; do
        num=$(ufw status numbered | grep "# ${WEB_COMMENT}" | head -1 \
              | sed -E 's/^\[[[:space:]]*([0-9]+)\].*/\1/') || true
        [ -z "$num" ] && break
        run ufw --force delete "$num"
    done
else
    echo "+ (dry-run) 既存の $WEB_COMMENT ルールがあれば番号指定で削除"
fi

for cidr in "${CF_RANGES[@]}"; do
    for port in "${INGRESS_PORTS[@]}"; do
        run ufw allow from "$cidr" to any port "$port" proto tcp comment "$WEB_COMMENT"
    done
done

# 既存の「Anywhere に開いた数値 80/443」を番号指定で撤去（決め打ち文字列削除だと
# ルール表現が一致せず無言でスキップされ、対話確認でハングもするため使わない）。
# To が 80|443[/tcp][ (v6)]・From が Anywhere[ (v6)] のルールを狙い撃つ。末尾は
# 固定しない（コメント付き `80/tcp ... Anywhere # legacy` も撤去対象にする）。
# cf-ingress 自身の行は grep -v で除外。tailscale（To が "Anywhere on tailscale0"）や
# CF レンジ（From=CIDR）は To/From 条件に合致しないため対象外。
# アプリプロファイル形式（To が "Nginx Full" 等）はここでは撤去せず、[6/6] の事後検証で
# fail-loud 検出して人間に委ねる（誤削除防止）。
BROAD_WEB_RE='^\[[[:space:]]*[0-9]+\][[:space:]]+(80|443)(/tcp)?( \(v6\))?[[:space:]]+ALLOW IN[[:space:]]+Anywhere( \(v6\))?'
echo ""
echo "既存の Anywhere 80/443 ルールを撤去:"
if [ "$APPLY" = true ]; then
    while true; do
        # grep 無マッチ時の pipefail 中断を避けるため `|| true`（上と同じ理由）。
        # コメントは信頼しない（`# cf-ingress-web` を騙る偽装 broad ルールも撤去対象にする）。
        # cf-ingress-web は From=CF CIDR で BROAD_WEB_RE（From=Anywhere）に一致しないため、
        # 自分の許可ルールを誤って消すことはない。
        num=$(ufw status numbered | grep -E "$BROAD_WEB_RE" \
              | head -1 | sed -E 's/^\[[[:space:]]*([0-9]+)\].*/\1/') || true
        [ -z "$num" ] && break
        run ufw --force delete "$num"
    done
else
    echo "+ (dry-run) Anywhere の 80/443 ルールがあれば番号指定で削除"
fi

# ---------------------------------------------------------------
# 6. 事後検証
# ---------------------------------------------------------------
echo ""
echo "--- [6/6] 事後検証 ---"
if [ "$APPLY" = true ]; then
    # 事後検証（送信元照合方式・コメント非依存）: 適用後にオリジンへの inbound を
    # 許してよいのは次のいずれか。それ以外の `ALLOW IN` が 1 つでも残れば fail-loud。
    #   (1) 送信元が実際に Cloudflare CIDR（CF_RANGES に完全一致）かつ宛先が 80/443（web）
    #   (2) SSH（22/tcp または OpenSSH プロファイル・送信元は問わない）
    #   (3) Tailscale インターフェース（on tailscale0）
    #   (4) EXTRA_ALLOW_EXEMPT_RE で明示除外したもの
    # 判定は各ルールの「送信元カラム」を CF_RANGES と突き合わせて行う。コメント文字列や
    # ポート表記（数値/アプリプロファイル）を一切信頼しないため、`# cf-ingress-web` を騙る
    # 偽装 broad ルール・特定 IP 直許可・アプリプロファイル開放をすべて漏れなく捕捉する。
    # numbered 表記は "ALLOW IN"（plain status の "ALLOW" とは異なる）ため numbered を使う。
    CF_SET=$(printf '%s\n' "${CF_RANGES[@]}")
    LEFTOVER=""
    # 重要: コメントを先に除去してから照合・抽出する。コメントに `ALLOW IN <CF CIDR>` や
    # `on tailscale0 ALLOW IN`・`22/tcp ALLOW IN` を仕込むと、後段の greedy 抽出や除外 grep を
    # 騙せてしまうため（`# ...` 以降を sed で削ってから grep/抽出に渡す）。
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        # 宛先 = 行番号 `[N]` の後ろ〜"ALLOW IN" の手前（To カラム）。コメントは除去済。
        to=$(printf '%s\n' "$line" \
             | sed -E 's/^\[[0-9 ]*\][[:space:]]*//; s/[[:space:]]+ALLOW IN.*$//; s/[[:space:]]+$//')
        # 送信元 = "ALLOW IN" の後ろを取り出して trim。
        from=$(printf '%s\n' "$line" | sed -E 's/.*ALLOW IN[[:space:]]+//; s/[[:space:]]+$//')
        # 許可条件: 送信元が CF CIDR に完全一致し、かつ宛先が 80/443（web）に限定されていること。
        # 送信元だけで判定すると `5432/tcp ALLOW IN <CF CIDR>` 等の非 web ポートが共有 CF
        # レンジから到達可能になるため、宛先ポートも 80/443 に限定して確認する。
        if printf '%s\n' "$CF_SET" | grep -Fxq -- "$from" \
           && printf '%s\n' "$to" | grep -Eq '^(80|443)(/tcp)?( \(v6\))?$'; then
            continue
        fi
        LEFTOVER+="$line"$'\n'
    done < <(ufw status numbered \
                | sed -E 's/[[:space:]]*#.*$//' \
                | grep 'ALLOW IN' \
                | grep -vE 'on tailscale0[[:space:]]+ALLOW IN' \
                | grep -vE '[[:space:]]22(/tcp)?( \(v6\))?[[:space:]]+ALLOW IN' \
                | grep -vE '\][[:space:]]+OpenSSH([[:space:]]|\()')
    # 正当な非 CF 許可（同居サービスの固有ポート等）は EXTRA_ALLOW_EXEMPT_RE で除外できる（既定は空）。
    if [ -n "${EXTRA_ALLOW_EXEMPT_RE:-}" ] && [ -n "$LEFTOVER" ]; then
        # 不正な正規表現だと grep -vE がエラー終了し、後続の `|| true` が空を返して検証を
        # すり抜ける（fail-open）。それを防ぐため事前に正規表現の妥当性を検証し、不正なら
        # fail-closed で停止する。空入力への grep は 0(一致)/1(不一致)=妥当、>1=正規表現エラー。
        reg_rc=0
        printf 'x\n' | grep -E "$EXTRA_ALLOW_EXEMPT_RE" >/dev/null 2>&1 || reg_rc=$?
        if [ "$reg_rc" -gt 1 ]; then
            echo "ERROR: EXTRA_ALLOW_EXEMPT_RE が不正な正規表現です: $EXTRA_ALLOW_EXEMPT_RE" >&2
            exit 1
        fi
        # 妥当性検証済なので、ここでの非 0 は「全行除外＝空」(exit 1) のみ。`|| true` で受ける。
        LEFTOVER=$(printf '%s' "$LEFTOVER" | grep -vE "$EXTRA_ALLOW_EXEMPT_RE" || true)
    fi
    if [ -n "$LEFTOVER" ]; then
        echo "ERROR: 「CF レンジ→80/443」「SSH」「Tailscale」「明示除外」以外の inbound ALLOW が残っています:" >&2
        printf '%s' "$LEFTOVER" >&2
        echo "       送信元が非 CF、または宛先が 80/443 以外のものは CF 迂回や非 web サービス露出になりうるため、" >&2
        echo "       'sudo ufw status numbered' の番号で削除するか、正当なら EXTRA_ALLOW_EXEMPT_RE で除外してください。" >&2
        echo "       （数値 80/443 の Anywhere は本スクリプトが自動撤去するが、特定 IP 直許可や" >&2
        echo "        アプリプロファイル形式は誤削除防止のため自動削除せず、この検証で検出して停止する設計）。" >&2
        exit 1
    fi
    echo "検証 OK: inbound ALLOW は「CF レンジ→80/443」/ SSH / Tailscale のみ。非 CF 経路・非 web 露出は残っていません。"
    echo ""
    ufw status verbose
else
    echo "+ (dry-run) 事後検証: 「CF レンジ→80/443」/ SSH / Tailscale 以外の inbound ALLOW が残っていないか確認"
    echo "            （送信元・宛先で判定。偽装コメント・特定 IP 直許可・非 web ポート露出も検出。残れば ERROR）"
    echo ""
    echo "確認するには --apply 後に 'sudo ufw status verbose' を参照。"
fi

echo ""
echo "=== 完了 ==="
echo "注意: Layer 1（CF レンジ許可）は攻撃面を縮小するが単体では不十分。CF 公開レンジは"
echo "  全顧客共有のため、他ゾーン/Worker + Host 詐称で到達しうる。完全遮断にはオリジン側の"
echo "  検証（Authenticated Origin Pulls / Access JWT 検証）= Layer 2 が必須（別 Issue）。"
echo ""
echo "残タスク（人間・Cloudflare ダッシュボード）:"
echo "  全 ingress hostname（coordinate. / api. / app. / camera.）に"
echo "  Cloudflare Access ポリシー（許可メール）が適用済か確認する。"
echo "  1 つでも未適用なら該当サービスが素通しになる。"
