#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="${DATABASE_PATH:-/var/lib/ai-sales-agent/sales_agent.db}"
TARGET_DIR="${BACKUP_DIR:-/var/backups/ai-sales-agent}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "$SOURCE" ]]; then
  echo "database not found: $SOURCE" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
TARGET="$TARGET_DIR/sales_agent-$STAMP.db"

python3 - "$SOURCE" "$TARGET" <<'PY'
import sqlite3
import sys

source, target = sys.argv[1:]
with sqlite3.connect(source, timeout=30) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok":
        raise SystemExit(f"backup integrity check failed: {check}")
print(target)
PY

find "$TARGET_DIR" -type f -name 'sales_agent-*.db' -mtime +14 -delete
