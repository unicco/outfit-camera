#!/usr/bin/env bash
#
# 玄関 Pi の user site-packages を `camera/pi-user-site.lock` の通りに作り直す
#
# ## 方式: ステージングで検証してから入れ替える（本番を壊してから確かめない）
#
# 1. 別ディレクトリ（ステージング）にロックの内容を入れる
# 2. `PYTHONNOUSERSITE=1` で user site を sys.path から外し、`PYTHONPATH` でステージングを
#    指して import を検証する。**これで入れ替え後の状態を camera を止めずに再現できる**
# 3. 検証が全部通ってから、はじめて user site を退避してステージングを配置する
#
# **検証が失敗したら user site には指一本触れずに中止する。** camera は動き続けるので、
# その日の撮影が失われることはない。
#
# 個別の `pip uninstall` は使わない。pip は依存関係を考慮しないため、消し漏れと消しすぎの
# 両方が起きる。
#
# ## 制約
#
# - **版はロックが決める。** 推移的依存まで含めて固定されているので、実行しても版は動かない
# - ロックには apt 層（picamera2 / libcamera / gpiozero / lgpio）が含まれない。それらは
#   user site の外にあり、このスクリプトの管轄外
# - `simplejpeg` はコードから import されないがロックに要る。picamera2 が内部で使う C 拡張で、
#   apt 版は numpy 1.24 ビルドのため user site の numpy 2.x と ABI 不整合になる
# - Pi は 20 時以降に起動すると cutoff 超過で数分後に自動 halt する。`.env` の
#   `AUTO_SHUTDOWN_ENABLED` を触ると戻し忘れで玄関の画面が点きっぱなしになる
#
# ## 使い方（Pi 上で実行）
#
#   bash scripts/maintenance/clean-pi-python.sh           # 検証まで実行して結果を表示（既定）
#   bash scripts/maintenance/clean-pi-python.sh --apply   # 検証が通れば入れ替えまで実行
#
# 既定モードでも**ステージングの構築と import 検証は実際に行う**（user site は無変更）。
#
# ロックを今の Pi から作り直すとき（入れ替えと検証が済んでから）:
#
#   /usr/bin/python3 -m pip list --user --format=freeze
#
# 出力をロックのヘッダコメントの下に貼る。根拠は docs/deployment/dependency-management.md。
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCK="$REPO_ROOT/camera/pi-user-site.lock"

# 入れ替え後に import できないと camera が起動しないもの
# （picamera2 / libcamera は unit の ExecStartPre でも gate されている）。
REQUIRED_IMPORTS=(numpy cv2 fastapi uvicorn piexif PIL requests psutil picamera2 libcamera simplejpeg)
# 欠けても PIR が無効化されるだけで動くもの（camera_service.py が try/except で包んでいる）。
OPTIONAL_IMPORTS=(gpiozero)

PY=/usr/bin/python3
APPLY=false
[ "${1:-}" = "--apply" ] && APPLY=true

log() { printf '%s\n' "$*"; }

SITE="$("$PY" -c 'import site; print(site.getusersitepackages())')"
STAGE="${SITE}.new"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${SITE}.bak-${STAMP}"

# ---------------------------------------------------------------
# 失敗時の案内を 1 箇所に集約する。
# 入れ替え（mv）を済ませた後にどこで落ちても必ず復旧手順を出す。`set -e` による中断・
# 明示 exit・想定外のエラーのすべてを EXIT trap で拾う（ERR trap だと明示 exit を取りこぼす）。
# 入れ替え前に落ちた場合はステージングだけ残るので、その掃除方法を出す。
# ---------------------------------------------------------------
SWAPPED=false
SUCCESS=false
on_exit() {
  local code=$?
  if [ "$SUCCESS" = true ]; then
    return 0
  fi
  if [ "$SWAPPED" = true ]; then
    log ""
    log "!!! 入れ替え後に失敗した（exit ${code}）。camera は動かない状態の可能性がある。"
    log "!!! 以下をそのまま実行して元に戻すこと:"
    log ""
    log "      rm -rf '${SITE}'"
    log "      mv '${BACKUP}' '${SITE}'"
    log "      sudo systemctl restart coordinate-camera.service"
    log ""
  elif [ -d "$STAGE" ]; then
    log ""
    log "中止した（exit ${code}）。**user site は無変更なので camera は動き続ける。**"
    log "ステージングが残っているので、不要なら消すこと:"
    log "      rm -rf '${STAGE}'"
    log ""
  fi
}
trap on_exit EXIT

log "=== 玄関 Pi の user site-packages を作り直す==="
if [ "$APPLY" = true ]; then
  log "※ --apply: 検証が全部通れば入れ替えまで実行します。"
else
  log "※ 既定モード: ステージング構築と検証まで行い、入れ替えはしません。"
fi
log "  user site: $SITE"
log "  ステージング: $STAGE"
log ""

if [ ! -d "$SITE" ]; then
  log "ERROR: $SITE が無い。"
  log "  過去の --apply が途中で失敗して退避されたままかもしれない。確認:"
  log "      ls -d ${SITE}.bak-* 2>/dev/null"
  exit 1
fi

if [ ! -f "$LOCK" ]; then
  log "ERROR: ロックが無い: $LOCK"
  exit 1
fi

# ---------------------------------------------------------------
# 1. 前提チェック: pip 自身が入れ替え対象の中にいないか
#
# `pip install --user --upgrade pip` を過去に実行していると pip 本体が user site に入る。
# その状態で入れ替えると pip ごと消え、以後入れ直せなくなる。
# ---------------------------------------------------------------
pip_loc="$("$PY" -m pip show pip 2>/dev/null | awk '/^Location:/ {print $2}' || true)"
if [ -z "$pip_loc" ]; then
  log "ERROR: pip が見つからない。次を確認すること: $PY -m pip --version"
  exit 1
fi
case "$pip_loc" in
  "$SITE"*)
    log "ERROR: pip 自身が入れ替え対象の中にある（${pip_loc}）。"
    log "  このまま入れ替えると pip ごと消えて入れ直せなくなる。先に apt 版へ寄せること:"
    log "      $PY -m pip uninstall -y pip"
    log "      dpkg -l python3-pip"
    exit 1
    ;;
esac
log "--- 前提チェック ---"
log "  pip: ${pip_loc}（入れ替え対象の外。安全）"
log ""

# ---------------------------------------------------------------
# 2. 現状とロックの差分
# ---------------------------------------------------------------
before_count="$("$PY" -m pip list --user --format=freeze 2>/dev/null | grep -c . || true)"
before_size="$(du -sh "$SITE" 2>/dev/null | cut -f1 || true)"
lock_count="$(grep -cE '^[^#[:space:]]' "$LOCK" || true)"
log "--- 作業前 ---"
log "  user site: ${before_count} パッケージ / ${before_size}"
log "  ロック:    ${lock_count} パッケージ（$LOCK）"
log ""

# 版まで含めた差分を出す。`pip list --format=freeze` とロックはどちらも `名前==版` なので
# そのまま突き合わせられる（ロック側はコメント行を落とす）。
log "--- ロックとの差分 ---"
diff_out="$(diff <("$PY" -m pip list --user --format=freeze 2>/dev/null | sort -f) \
                 <(grep -E '^[^#[:space:]]' "$LOCK" | sort -f) || true)"
if [ -z "$diff_out" ]; then
  log "  差分なし（user site は既にロックと一致している）"
else
  printf '%s\n' "$diff_out" | sed 's/^</  消える: /; s/^>/  入る:   /; /^[0-9-]/d'
fi
log ""

cv2_before="$("$PY" -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo "unknown")"
log "  現在読まれている cv2: ${cv2_before}"
log ""

# ---------------------------------------------------------------
# 3. ステージングを構築（user site は無変更）
# ---------------------------------------------------------------
log "--- ステージングを構築（user site には触らない）---"
# `--target` は `--user` とレイアウトが完全に同じではない（console_scripts の書き込み先など）。
# ただし衝突すれば pip 自体が非 0 で終わり、下の `if !` が捕捉して user site 無変更で中止する
# ＝ fail-safe。
rm -rf "$STAGE"
mkdir -p "$STAGE"
if ! "$PY" -m pip install --quiet --target "$STAGE" -r "$LOCK"; then
  log "  ERROR: ステージングへのインストールに失敗した。user site は無変更。"
  exit 1
fi
stage_size="$(du -sh "$STAGE" 2>/dev/null | cut -f1 || true)"
log "  OK: 構築できた（${stage_size}）"

# ロックに漏れがあると pip が推移的依存を勝手に足すので、ステージングの中身がロックと
# 一致するかをここで見る。**入れ替え前なので、落ちても camera は動き続ける。**
if ! diff -q <("$PY" -m pip list --path "$STAGE" --format=freeze 2>/dev/null | sort -f) \
             <(grep -E '^[^#[:space:]]' "$LOCK" | sort -f) >/dev/null; then
  log "  ERROR: ステージングの中身がロックと一致しない（ロックに漏れがある）。user site は無変更。"
  diff <("$PY" -m pip list --path "$STAGE" --format=freeze 2>/dev/null | sort -f) \
       <(grep -E '^[^#[:space:]]' "$LOCK" | sort -f) | sed 's/^</  余分: /; s/^>/  不足: /; /^[0-9-]/d' || true
  exit 1
fi
log "  OK: ステージングがロックと一致"
log ""

# ---------------------------------------------------------------
# 4. 検証: user site を外した状態で import を試す
#
# PYTHONNOUSERSITE=1 で user site を sys.path から除外し、PYTHONPATH でステージングを指す。
# これで「入れ替え後の状態」を camera を止めずに完全再現できる。
#
# ⚠️ 再現は完全ではない: `PYTHONPATH` 経由だと `site.addsitedir()` が呼ばれないため
#    `.pth` ファイルが処理されない。入れ替え後の実 user site では `site.py` が処理する。
#    現在のロックの内容は `.pth` に依存しないので実害は無いが、将来 `.pth` を使う
#    パッケージ（namespace package 等）が入ると「検証は通るのに実配置で壊れる」余地がある。
#    そのケースは入れ替え後の再検証（下の 5 節）で捕まる。
# ---------------------------------------------------------------
log "--- 検証（入れ替え後の状態を再現。camera は動いたまま）---"
failed=()
for mod in "${REQUIRED_IMPORTS[@]}"; do
  if err="$(PYTHONNOUSERSITE=1 PYTHONPATH="$STAGE" "$PY" -c "import $mod" 2>&1)"; then
    log "  OK    $mod"
  else
    log "  FAIL  $mod"
    log "        $(printf '%s' "$err" | tail -2 | tr '\n' ' ')"
    failed+=("$mod")
  fi
done
for mod in "${OPTIONAL_IMPORTS[@]}"; do
  if PYTHONNOUSERSITE=1 PYTHONPATH="$STAGE" "$PY" -c "import $mod" 2>/dev/null; then
    log "  OK    ${mod}（任意）"
  else
    log "  !     $mod が import できない → PIR が無効化される（致命的ではない）"
  fi
done

# ロックの `opencv-python==4.12.0.88` に対し `cv2.__version__` は `4.12.0` を返す（末尾は
# opencv-python 側のビルド番号）。apt 版が勝つと別の版になるので、ここで一致を見る。
lock_cv2="$(grep -iE '^opencv-python==' "$LOCK" | cut -d= -f3 | cut -d. -f1-3 || true)"
cv2_staged="$(PYTHONNOUSERSITE=1 PYTHONPATH="$STAGE" "$PY" -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo "unknown")"
if [ -z "$lock_cv2" ]; then
  log "  FAIL  ロックに opencv-python が無い"
  failed+=("cv2-lock-missing")
elif [ "$cv2_staged" = "$lock_cv2" ]; then
  log "  OK    cv2 がロックどおり（${cv2_staged}）"
else
  log "  FAIL  cv2 がロックと違う（ロック ${lock_cv2} / 実際 ${cv2_staged}・現在は ${cv2_before}）"
  failed+=("cv2-version")
fi
log ""

if [ "${#failed[@]}" -gt 0 ]; then
  log "=== 検証に失敗した: ${failed[*]} ==="
  log ""
  log "**user site は無変更なので camera は動き続けている。** 撮影に影響はない。"
  log ""
  log "対処: 足りないパッケージをロック（${LOCK}）に追加する。"
  log "  上の FAIL のエラーに出ているモジュール名が手がかりになる。"
  log "  user site にその版があるか確認:  $PY -m pip show <モジュール名>"
  log ""
  log "ステージングを消す:  rm -rf '${STAGE}'"
  exit 1
fi

log "=== 検証は全部通った ==="
log ""

if [ "$APPLY" != true ]; then
  log "既定モードなので入れ替えはしない。実行するには --apply を付けること。"
  log "ステージングは残してある（--apply 時に作り直す）: $STAGE"
  SUCCESS=true
  exit 0
fi

# ---------------------------------------------------------------
# 5. 入れ替え（ここから先の失敗は EXIT trap が復旧手順を出す）
# ---------------------------------------------------------------
log "--- 入れ替え ---"
mv "$SITE" "$BACKUP"
SWAPPED=true
mv "$STAGE" "$SITE"
log "  OK: 退避 → 配置"
log ""

log "--- 入れ替え後の再検証 ---"
if ! "$PY" -c "import $(IFS=,; echo "${REQUIRED_IMPORTS[*]}")" 2>&1; then
  log "  NG: 必須モジュールの import に失敗した"
  exit 1
fi
log "  OK: 必須モジュールを import できた"

cv2_after="$("$PY" -c 'import cv2; print(cv2.__version__)' 2>/dev/null || echo "unknown")"
if [ "$cv2_after" != "$lock_cv2" ]; then
  log "  NG: cv2 がロックと違う（ロック ${lock_cv2} / 実際 ${cv2_after}）"
  exit 1
fi
log "  OK: cv2 がロックどおり（${cv2_after}）"

after_count="$("$PY" -m pip list --user --format=freeze 2>/dev/null | grep -c . || true)"
after_size="$(du -sh "$SITE" 2>/dev/null | cut -f1 || true)"
log "  パッケージ数: ${before_count} → ${after_count}"
log "  サイズ: ${before_size} → ${after_size}"
log ""

# ---------------------------------------------------------------
# 6. camera サービスの再起動と確認
# ---------------------------------------------------------------
log "--- camera サービスの再起動 ---"
if ! sudo systemctl restart coordinate-camera.service; then
  log "  NG: restart コマンド自体が失敗した（sudo の権限を確認）"
  exit 1
fi

# HW 初期化（unit の ExecStartPre が pipewire のカメラ解放を待つ）に時間がかかるため、
# 固定 sleep ではなくポーリングで待つ。
active=false
for _ in $(seq 1 30); do
  if systemctl is-active coordinate-camera.service >/dev/null 2>&1; then
    active=true
    break
  fi
  sleep 2
done
if [ "$active" != true ]; then
  log "  NG: coordinate-camera が 60 秒以内に active にならなかった"
  systemctl status coordinate-camera.service --no-pager -l | tail -20
  exit 1
fi
log "  OK: coordinate-camera が active"

# /health の失敗は「完了」を止めない（警告のみ）。起動直後は HW 初期化や display の初期化中で
# 応答しないことがあり、NG 扱いにすると正常な構成を誤ってロールバックしてしまう。
# 代わりに下で手動の試し撮りを促す。
if curl -sf -o /dev/null --max-time 10 "http://127.0.0.1:8001/health" 2>/dev/null; then
  log "  OK: /health が応答"
else
  log "  ! /health がまだ応答しない（起動途中の可能性）。少し待って再確認すること:"
  log "      curl -s http://127.0.0.1:8001/health"
  log "      journalctl -u coordinate-camera -n 50"
fi

SUCCESS=true

log ""
log "=== 完了 ==="
log "退避したものは残してある: $BACKUP"
log ""
log "⚠️ import が通っても実際の撮影が動くとは限らない。**手動で一枚試し撮りすること**:"
log "      curl -X POST http://127.0.0.1:8001/capture"
log ""
log "数日運用して問題が無ければ退避分を削除する:"
log "    rm -rf '$BACKUP'"
log ""
log "問題が出たら戻す:"
log "    rm -rf '$SITE' && mv '$BACKUP' '$SITE' && sudo systemctl restart coordinate-camera.service"
