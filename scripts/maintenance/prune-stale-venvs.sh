#!/usr/bin/env bash
#
# 使われなくなった世代の venv を回収する
#
# ## 使い方
#
#   bash scripts/maintenance/prune-stale-venvs.sh            # 候補の一覧だけ（既定）
#   bash scripts/maintenance/prune-stale-venvs.sh --apply    # 実際に削除する
#   bash scripts/maintenance/prune-stale-venvs.sh --days 60  # 猶予を変える（既定 30 日）
#
# ## なぜ必要か
#
# venv のパスには requirements の md5 が埋まっているため、requirements を更新するたびに
# 新しい世代ができる。旧世代は誰も消さないので永久に残る。
#
# ## 実行・改修する前に知っておくこと
#
#   - **起動経路に入れない。** 判定材料は mtime しかなく、猶予より前に起動して今も
#     動いているサービスの venv と、放置された venv を区別できない。デプロイ中に
#     自動で走らせると稼働中プロセスの venv を消しうるので、人間が明示的に叩く
#   - **判定は「最終使用」であって「作成日時」ではない。** これが成立するのは
#     `scripts/launch/common/python-setup.sh` が起動のたびに世代を touch しているため。
#     touch を外すと、毎日使っている世代が放置と同じ見え方になる
#   - **稼働中サービスは猶予より長く動きうる。** 猶予を超えて再起動していない
#     サービスがあるなら、削除後に再起動すること。symlink が宙づりのまま遅延 import に
#     入ると落ちる
#   - 現在のチェックアウトの `api/venv`・`camera/venv` が指す先は、古くても消さない
#   - **消すのは venv だけ。** `pyvenv.cfg` を持つディレクトリに限る。置き場の直下に
#     置かれただけの無関係なディレクトリを、古いというだけで消さないため
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

STALE_DAYS=30
APPLY=false

while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=true; shift ;;
        --days) STALE_DAYS="$2"; shift 2 ;;
        *) echo "不明な引数: $1" >&2; exit 2 ;;
    esac
done

# 非数値を渡すと find -mtime が黙って何も返さず「候補なし」に見えるので、ここで弾く
case "$STALE_DAYS" in
    ''|*[!0-9]*) echo "--days は 0 以上の整数で指定してください: $STALE_DAYS" >&2; exit 2 ;;
esac

log() { printf '%s\n' "$*"; }

# 走査する venv 置き場。python-setup.sh の環境判定と同じ 3 系統を見る。
VENV_ROOTS=(
    "${PROJECT_ROOT}/.venvs"
    "${HOME}/.coordinate-recorder-venvs"
    "/home/pi/.coordinate-recorder-venvs"
)

# 実在するものだけを物理パスに直して重複を畳む。本番 Pi は HOME が /home/pi なので、
# 畳まないと同じ場所を 2 回数え、回収見込みが 2 倍に見える。
resolved_roots() {
    local root physical
    for root in "$@"; do
        [ -d "$root" ] || continue
        physical=$(cd "$root" && pwd -P) || continue
        printf '%s\n' "$physical"
    done | sort -u
}

ROOTS=()
while IFS= read -r resolved; do
    [ -n "$resolved" ] || continue
    ROOTS+=("$resolved")
done < <(resolved_roots "${VENV_ROOTS[@]}")

# 現在のチェックアウトが参照している世代。古くても消さない。
# symlink を辿った先の物理パスで持つ。readlink の文字列のままだと、symlink を張った
# python-setup.sh 側と PROJECT_ROOT の表記が揺れたときに一致せず、防壁が黙って外れる。
in_use_targets() {
    local link target
    for link in "${PROJECT_ROOT}/api/venv" "${PROJECT_ROOT}/camera/venv"; do
        [ -L "$link" ] || continue
        # 指す先が既に消えている symlink は珍しくない（世代を手で消した後など）。
        # cd の失敗を表に出さず、単に守る対象なしとして扱う
        target=$(cd "$link" 2>/dev/null && pwd -P) || continue
        printf '%s\n' "$target"
    done
}

IN_USE="$(in_use_targets || true)"

is_in_use() {
    [ -n "$IN_USE" ] && printf '%s\n' "$IN_USE" | grep -Fxq -- "$1"
}

total_kb=0
found=0

if [ ${#ROOTS[@]} -eq 0 ]; then
    log "venv の置き場が見つかりません。"
    exit 0
fi

for root in "${ROOTS[@]}"; do
    while IFS= read -r venv; do
        [ -n "$venv" ] || continue

        # python3 -m venv が必ず置く印。これが無いものは venv ではないので触らない
        if [ ! -f "$venv/pyvenv.cfg" ]; then
            log "  skip (venv ではない): $venv"
            continue
        fi

        if is_in_use "$venv"; then
            log "  skip (使用中): $venv"
            continue
        fi

        size_kb="$(du -sk "$venv" 2>/dev/null | awk 'NR==1 {print $1}' || true)"
        [ -n "$size_kb" ] || continue
        mtime="$(date -r "$venv" +%Y-%m-%d 2>/dev/null || echo unknown)"

        total_kb=$((total_kb + size_kb))
        found=$((found + 1))

        if [ "$APPLY" = true ]; then
            if rm -rf "$venv" 2>/dev/null; then
                log "  削除: $venv ($((size_kb / 1024))MB・最終使用 $mtime)"
            else
                log "  削除できず: $venv ($((size_kb / 1024))MB)"
            fi
        else
            log "  候補: $venv ($((size_kb / 1024))MB・最終使用 $mtime)"
        fi
    done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -mtime "+${STALE_DAYS}" 2>/dev/null)
done

log ""
if [ "$found" -eq 0 ]; then
    log "${STALE_DAYS} 日以上使われていない venv はありません。"
    exit 0
fi

log "${STALE_DAYS} 日以上使われていない venv: ${found} 件 / $(awk -v kb="$total_kb" 'BEGIN { printf "%.1f", kb / 1024 / 1024 }')GB"

if [ "$APPLY" = true ]; then
    log ""
    log "猶予を超えて再起動していないサービスがあるなら、いま再起動すること。"
else
    log "削除するには --apply を付けて再実行してください。"
fi
