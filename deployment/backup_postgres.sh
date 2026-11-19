#!/usr/bin/env bash
set -euo pipefail

# Automated PostgreSQL backup script for AK DeviceLock (run via cron/systemd timer)
BACKUP_DIR="${AKDL_BACKUP_DIR:-/var/backups/akdl}"
RETENTION_DAYS="${AKDL_BACKUP_RETENTION_DAYS:-14}"
ENV_FILE="${AKDL_ENV_FILE:-/etc/akdl/akdl.env}"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/akdl-${STAMP}.sql.gz"

PGPASSWORD="${AKDL_DB_PASSWORD:-}" pg_dump \
  -h "${AKDL_DB_HOST:-127.0.0.1}" \
  -p "${AKDL_DB_PORT:-5432}" \
  -U "${AKDL_DB_USER:-akdl}" \
  "${AKDL_DB_NAME:-akdl}" | gzip > "$OUT"

chmod 600 "$OUT"
find "$BACKUP_DIR" -name 'akdl-*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete
echo "Backup written: $OUT"
