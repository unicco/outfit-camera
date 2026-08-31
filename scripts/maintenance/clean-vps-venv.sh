#!/usr/bin/env bash
#
# 本番 VPS の venv から requirements-api.txt に無い残骸を落とす
#
# ## 使い方（VPS 上で実行）
#
#   bash scripts/maintenance/clean-vps-venv.sh           # 検証まで（.venv は無変更・既定）
#   bash scripts/maintenance/clean-vps-venv.sh --apply   # 検証が通れば入れ替えまで
#
# 既定モードでも複製の構築と検証は実際に実行する。
#
# ## 実行・改修する前に知っておくこと
#
#   - **venv を作り直さない。** ピンは直接依存だけで推移的依存は無ピンのため、作り直すと
#     無検証のまま本番のメジャー版が上がる。本スクリプトは現在の venv を複製して残骸だけを
#     落とし、版は 1 つも動かさない
#   - 消す対象は `check_venv_drift.py --list-stale`（requirements の依存閉包の外）で機械的に
#     決める。手で並べた名前は使わない
#   - 検証が失敗したら `.venv` に触れずに中止する。API は動き続ける
#   - `--apply` はサービスを止めてから入れ替える。生かしたまま差し替えると遅延 import が壊れる
#
# 背景・実測値・方式を選んだ理由は docs/deployment/dependency-management.md を参照。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$HOME/services/coordinate-recorder"
VENV="$SERVICE_DIR/.venv"
STAGE="$SERVICE_DIR/.venv.stage"
REQ="$SERVICE_DIR/requirements-api.txt"
DRIFT_CHECK="$SCRIPT_DIR/check_venv_drift.py"
SERVICE="coordinate-api.service"
HEALTH_URL="http://127.0.0.1:8000/health"
# venv を 2 つ並べる（実測 764MB×2）ための下限に作業余裕を足したもの。
MIN_FREE_KB=$((2 * 1024 * 1024))

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${VENV}.bak-${STAMP}"
FAILED_VENV="${VENV}.failed-${STAMP}"

APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true

log() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------
# 入れ替え後にどこで落ちても必ず元に戻す。
# `set -e` による中断・明示 exit・想定外のエラーのすべてを EXIT trap で拾う
# （ERR trap だと明示 exit を取りこぼす）。
#
# ロールバックは **mv だけ**で完結させる（`rm -rf` を本番のスクリプトに書かない）。
# 失敗した venv は消さずに退避しておくので、後から原因を調べられる。
# ---------------------------------------------------------------
# 状態フラグは「サービスを止めた」と「venv を入れ替えた」で別に持つ。1 つにまとめると、
# 停止には成功したが最初の mv で落ちた場合に「.venv は無変更」の分岐へ落ちてしまい、
# **API を止めたまま「動き続けている」と報告する**（実際にサービスが落ちたまま放置される）。
STOPPED=false
SWAPPED=false
SUCCESS=false

start_service() {
  if systemctl --user start "$SERVICE"; then
    log "    ${SERVICE} を起動した。応答を確認すること: curl -s ${HEALTH_URL}"
  else
    log "!!! ${SERVICE} の起動に失敗した。手動で確認すること:"
    log "        systemctl --user status ${SERVICE}"
  fi
}

on_exit() {
  local code=$?
  if [ "$SUCCESS" = true ]; then
    return 0
  fi
  if [ "$SWAPPED" = true ]; then
    log ""
    log "!!! 入れ替え後に失敗した（exit ${code}）。元の venv に戻す。"
    # 2 つ目の mv（複製の配置）で落ちた場合は $VENV が存在しない。無条件に退避しようとすると
    # 空振りし、`&&` の右辺＝本当に必要な「バックアップを戻す」が実行されないまま失敗扱いになる。
    if [ -e "$VENV" ]; then
      if mv "$VENV" "$FAILED_VENV"; then
        log "    失敗した venv は調査用に残してある: ${FAILED_VENV}"
      else
        log "!!! 失敗した venv を退避できなかった（${VENV}）。手で確認すること。"
      fi
    fi
    if [ ! -e "$VENV" ] && mv "$BACKUP" "$VENV"; then
      log "    戻した: ${BACKUP} → ${VENV}"
      start_service
    else
      log "!!! 自動ロールバックに失敗した。以下を手で実行すること:"
      log ""
      log "      ls -d '${VENV}' '${BACKUP}' '${FAILED_VENV}'   # 今どれがあるか確認"
      log "      mv '${BACKUP}' '${VENV}'                       # \$VENV が無い状態にしてから"
      log "      systemctl --user start ${SERVICE}"
      log ""
    fi
  elif [ "$STOPPED" = true ]; then
    log ""
    log "!!! 停止した後・入れ替えの前に失敗した（exit ${code}）。"
    log "    **venv は無変更**なので、そのまま起こせば元どおりになる。"
    start_service
  elif [ -d "$STAGE" ]; then
    log ""
    log "中止した（exit ${code}）。**.venv は無変更なので API は動き続ける。**"
    log "複製が残っているので、不要なら消すこと:"
    log "      rm -rf '${STAGE}'"
    log ""
  fi
}
trap on_exit EXIT

# ---------------------------------------------------------------
# 検証の中身
#
# systemd の ExecStart（`python -m uvicorn api.app.main:app`）と同じ形でアプリを import する。
# これが通れば「残骸を落としてもアプリが立ち上がる」ことの実証になる。
#
# さらに `ALL_FEATURE_ROUTERS` と `loaded_routers` を突き合わせる。main.py は cv2/libGL 依存の
# 3 router（upload / wardrobe / ai_detection）の import 失敗を握り潰して起動を
# 継続する設計なので、**import が通っただけでは cv2 が壊れていても気づけない**。
# ---------------------------------------------------------------
VERIFY_PY='
import api.app.main as m
missing = sorted(m.ALL_FEATURE_ROUTERS - set(m.loaded_routers))
if missing:
    raise SystemExit("feature router が欠落している: " + ", ".join(missing))
print("  OK    api.app.main を import・feature router %d 本すべてロード" % len(m.loaded_routers))
'

verify_venv() {
  # $1: 検証する venv のパス, $2: 表示名
  local venv="$1" label="$2"
  log "--- 検証（${label}）---"

  # .env は settings の必須項目（DATABASE_URL 等）を供給する。
  # subshell に閉じ込めて、呼び出し元の環境に .env を漏らさない。
  (
    if [ -f "$SERVICE_DIR/.env" ]; then
      set -a
      # shellcheck disable=SC1091
      source "$SERVICE_DIR/.env"
      set +a
    fi
    export PYTHONPATH="$SERVICE_DIR/api:$SERVICE_DIR/src:$SERVICE_DIR"

    "$venv/bin/python" -c "$VERIFY_PY"

    for mod in cv2 sklearn skimage scipy PIL piexif alembic psycopg google.cloud.storage; do
      if "$venv/bin/python" -c "import $mod" 2>/dev/null; then
        log "  OK    import ${mod}"
      else
        log "  FAIL  import ${mod}"
        exit 1
      fi
    done

    # 最後に drift 検査そのものを通す。上の import 群は「足りているか」しか見ないので、
    # 「余計なものが残っていないか」はこれで確かめる。
    "$venv/bin/python" "$DRIFT_CHECK" "$REQ"
  )
  log ""
}

# ---------------------------------------------------------------
# 0. 前提チェック
# ---------------------------------------------------------------
log "=== 本番 VPS の venv から残骸を落とす==="
if [ "$APPLY" = true ]; then
  log "※ --apply: 検証が通れば ${SERVICE} を止めて venv を入れ替えます。"
else
  log "※ 既定モード: 複製の構築と検証まで。.venv は変更しません。"
fi
log "  venv:         $VENV"
log "  複製:         $STAGE"
log "  requirements: $REQ"
log ""

if [ ! -d "$VENV" ]; then
  log "ERROR: $VENV が無い。VPS 上で実行しているか確認すること。"
  exit 1
fi
if [ ! -f "$REQ" ]; then
  log "ERROR: $REQ が無い。"
  exit 1
fi
if [ ! -f "$DRIFT_CHECK" ]; then
  log "ERROR: $DRIFT_CHECK が無い（このスクリプトと同じディレクトリに置くこと）。"
  exit 1
fi

free_kb="$(df -Pk "$SERVICE_DIR" | awk 'NR==2 {print $4}')"
if [ "$free_kb" -lt "$MIN_FREE_KB" ]; then
  log "ERROR: 空きディスクが足りない（${free_kb} KB < ${MIN_FREE_KB} KB）。"
  log "  venv を 2 つ並べる余裕が要る。古い .venv.bak-* が残っていないか確認すること:"
  log "      ls -d ${VENV}.bak-* 2>/dev/null"
  exit 1
fi

# ---------------------------------------------------------------
# 1. 消す対象を機械的に確定する
#
# 手で名前を並べない。requirements の依存閉包の外にあるもの＝どのパッケージからも要求されて
# いないものだけを消す。extras 由来の依存（uvicorn[standard] の PyYAML 等）を巻き込まないのは
# check_venv_drift.py が閉包を extras 込みで計算しているため。
# ---------------------------------------------------------------
log "--- 消す対象（requirements の依存閉包の外にあるもの）---"
# ⚠️ `mapfile -t STALE < <(cmd)` と書かないこと。プロセス置換の終了コードはシェルに伝わらず、
#    検査が exit 2（＝検査不能。packaging 欠落・requirements の解釈失敗など）で落ちても
#    「出力が空 ＝ 残骸なし ＝ 一致している」と読み違えて成功終了してしまう。
#    コマンド置換なら終了コードを見られる。
if ! stale_out="$("$VENV/bin/python" "$DRIFT_CHECK" --list-stale "$REQ")"; then
  log "ERROR: drift 検査自体が失敗した。何を消すべきか確定できないので中止する。"
  log "  単体で回して原因を見ること:"
  log "      ${VENV}/bin/python ${DRIFT_CHECK} ${REQ}"
  exit 1
fi
STALE=()
if [ -n "$stale_out" ]; then
  mapfile -t STALE <<<"$stale_out"
fi
if [ "${#STALE[@]}" -eq 0 ]; then
  log "  残骸なし。venv はすでに requirements と一致している。"
  SUCCESS=true
  exit 0
fi
for pkg in "${STALE[@]}"; do
  log "  ${pkg}==$("$VENV/bin/pip" show "$pkg" 2>/dev/null | awk '/^Version:/ {print $2}')"
done
log "  合計 ${#STALE[@]} 件"
log ""

before_count="$("$VENV/bin/pip" list --format=freeze 2>/dev/null | grep -c . || true)"
before_size="$(du -sh "$VENV" 2>/dev/null | cut -f1 || true)"

# ---------------------------------------------------------------
# 2. 複製を作って、そちらで残骸を落とす（.venv は無変更）
# ---------------------------------------------------------------
log "--- .venv を複製（.venv には触らない）---"
rm -rf "$STAGE"
cp -a "$VENV" "$STAGE"
log "  OK: 複製した（$(du -sh "$STAGE" | cut -f1)）"

# ⚠️ 必ず `python -m pip` で呼ぶこと。`$STAGE/bin/pip` は **複製元の .venv/bin/python** を指す
#    shebang を持っている（venv は作成時のパスが焼き付き、cp ではそこが書き変わらない）。
#    直接叩くと本番の .venv から消えてしまう。
log "--- 複製から残骸を落とす ---"
"$STAGE/bin/python" -m pip uninstall --yes --quiet "${STALE[@]}"
log "  OK: ${#STALE[@]} 件を落とした（$(du -sh "$STAGE" | cut -f1)）"
log ""

# ---------------------------------------------------------------
# 3. 複製を検証
# ---------------------------------------------------------------
if ! verify_venv "$STAGE" "複製・API は動いたまま"; then
  log "=== 検証に失敗した ==="
  log ""
  log "**.venv は無変更なので API は動き続けている。**"
  log "落としたどれかが実際には必要だった可能性がある。上の FAIL を見て、"
  log "必要なら requirements-api.txt に足すこと（そうすれば閉包に入り、次からは消えない）。"
  log "複製を消す:  rm -rf '${STAGE}'"
  exit 1
fi
log "=== 複製の検証は全部通った ==="
log ""

if [ "$APPLY" != true ]; then
  log "既定モードなので入れ替えはしない。実行するには --apply を付けること。"
  log "複製は残してある（--apply 時に作り直す）: $STAGE"
  SUCCESS=true
  exit 0
fi

# ---------------------------------------------------------------
# 4. 入れ替え（ここから先の失敗は EXIT trap が自動で戻す）
#
# 複製の中身の shebang は複製元＝`.venv/bin/python` を指したままなので、`.venv` の位置に
# mv した時点で正しい参照に戻る（新しい venv を作って mv する場合と違い、直す必要が無い）。
# ---------------------------------------------------------------
log "--- ${SERVICE} を停止 ---"
systemctl --user stop "$SERVICE"
STOPPED=true
log "  OK: 停止した"

log "--- 入れ替え ---"
mv "$VENV" "$BACKUP"
SWAPPED=true
mv "$STAGE" "$VENV"
log "  OK: 退避（${BACKUP}）→ 配置"
log ""

verify_venv "$VENV" "入れ替え後の .venv"

after_count="$("$VENV/bin/pip" list --format=freeze 2>/dev/null | grep -c . || true)"
after_size="$(du -sh "$VENV" 2>/dev/null | cut -f1 || true)"
log "  パッケージ数: ${before_count} → ${after_count}"
log "  サイズ: ${before_size} → ${after_size}"
log ""

# ---------------------------------------------------------------
# 5. サービスを起動して応答を確認
# ---------------------------------------------------------------
log "--- ${SERVICE} を起動 ---"
systemctl --user start "$SERVICE"

healthy=false
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null --max-time 5 "$HEALTH_URL" 2>/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done
if [ "$healthy" != true ]; then
  log "  NG: ${HEALTH_URL} が 60 秒以内に応答しなかった"
  systemctl --user status "$SERVICE" --no-pager | tail -20
  exit 1
fi
log "  OK: ${HEALTH_URL} が応答した"
curl -s "$HEALTH_URL"
log ""

SUCCESS=true

log ""
log "=== 完了 ==="
log "退避したものは残してある: $BACKUP"
log ""
log "⚠️ import が通っても実際の書き込み経路が動くとは限らない。**UI を開いて写真を 1 枚"
log "   アップロードして確認すること**（GCS と VLM 検出を通る経路）。"
log ""
log "数日運用して問題が無ければ削除する:"
log "    rm -rf '$BACKUP'"
log ""
log "問題が出たら戻す:"
log "    systemctl --user stop ${SERVICE}"
log "    mv '$VENV' '$FAILED_VENV' && mv '$BACKUP' '$VENV'"
log "    systemctl --user start ${SERVICE}"
