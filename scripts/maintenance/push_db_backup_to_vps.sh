#!/usr/bin/env bash
set -euo pipefail

# coordinate-recorder の DB バックアップを VPS にオフサイト複製する
# Tailscale + scp で VPS に転送

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/coordinate-recorder}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/tmp}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

LIFELOG_HOST="${LIFELOG_HOST:-100.64.0.10}"
LIFELOG_USER="${LIFELOG_USER:-lifelog-sync}"
LIFELOG_DEST_DIR="${LIFELOG_DEST_DIR:-/home/lifelog-sync/inbox/db_backups}"
LIFELOG_SSH_KEY="${LIFELOG_SSH_KEY:-$HOME/.ssh/lifelog_push_key}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/coordinate_db_${TIMESTAMP}.sql.gz"

cd "$PROJECT_ROOT"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source ./.env
  set +a
fi

mkdir -p "$BACKUP_DIR"

# 1. pg_dump + gzip
echo "[$(date -Is)] Starting pg_dump..."
pg_dump coordinate_recorder | gzip > "$DUMP_FILE"
DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "[$(date -Is)] pg_dump completed: $DUMP_FILE ($DUMP_SIZE)"

# 2. VPS 側のディレクトリ確保 + 転送
echo "[$(date -Is)] Pushing to VPS..."
ssh -i "$LIFELOG_SSH_KEY" \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=accept-new \
  "$LIFELOG_USER@$LIFELOG_HOST" \
  "mkdir -p $LIFELOG_DEST_DIR"

scp -O \
  -i "$LIFELOG_SSH_KEY" \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=accept-new \
  "$DUMP_FILE" \
  "$LIFELOG_USER@$LIFELOG_HOST:$LIFELOG_DEST_DIR/"

echo "[$(date -Is)] Push completed: $LIFELOG_USER@$LIFELOG_HOST:$LIFELOG_DEST_DIR/$(basename "$DUMP_FILE")"

# 3. ローカルの古いダンプを削除
find "$BACKUP_DIR" -name "coordinate_db_*.sql.gz" -mtime +${BACKUP_RETENTION_DAYS} -delete 2>/dev/null || true

# 4. VPS 側の古いダンプも削除（30日以上）
ssh -i "$LIFELOG_SSH_KEY" \
  -o IdentitiesOnly=yes \
  "$LIFELOG_USER@$LIFELOG_HOST" \
  "find $LIFELOG_DEST_DIR -name 'coordinate_db_*.sql.gz' -mtime +30 -delete 2>/dev/null || true"

echo "[$(date -Is)] Cleanup done. DB backup offsite push completed successfully."
