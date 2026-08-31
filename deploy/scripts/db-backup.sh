#!/usr/bin/env bash
# Coordinate Recorder — PostgreSQL daily backup
# Keeps last 7 days of pg_dump backups.
set -euo pipefail

BACKUP_DIR="$HOME/backups/coordinate-db"
DB_NAME="coordinate_db"
RETENTION_DAYS=7
LOG_TAG="coordinate-backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

log_info()  { echo "$1" | systemd-cat -t "$LOG_TAG" -p info; }
log_error() { echo "$1" | systemd-cat -t "$LOG_TAG" -p err; }

mkdir -p "$BACKUP_DIR"

# Dump and compress
if pg_dump "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "Backup OK: $BACKUP_FILE ($SIZE)"
else
    log_error "Backup FAILED: pg_dump $DB_NAME"
    exit 1
fi

# Prune old backups
DELETED=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log_info "Pruned $DELETED old backup(s)"
fi

TOTAL=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" | wc -l)
log_info "Backup complete: $TOTAL backup(s) retained"
