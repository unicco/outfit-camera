#!/usr/bin/env bash
set -euo pipefail

MODE=${1:-daily}
DAYS_TO_KEEP=${2:-90}

PROJECT_ROOT=${PROJECT_ROOT:-"${HOME}/coordinate-recorder"}

if [ ! -d "$PROJECT_ROOT" ]; then
  echo "❌ Project root not found: $PROJECT_ROOT"
  exit 1
fi

cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
  echo "❌ .env file not found"
  exit 1
fi

# Load DATABASE_URL without sourcing .env to support multiline secrets
DATABASE_URL="$(
  python - <<'PYTHON'
import os
import sys
from pathlib import Path

db_url = os.environ.get("DATABASE_URL", "").strip()
if not db_url:
    values = {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        pass
    else:
        values = dotenv_values(".env")

    if "DATABASE_URL" in values and values["DATABASE_URL"]:
        db_url = values["DATABASE_URL"].strip()
    else:
        env_path = Path(".env")
        if env_path.exists():
            for raw_line in env_path.read_text().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("DATABASE_URL=") or line.startswith("export DATABASE_URL="):
                    value = raw_line.split("=", 1)[1].strip()
                    if (
                        value
                        and len(value) >= 2
                        and value[0] == value[-1]
                        and value[0] in {'"', "'"}
                    ):
                        value = value[1:-1]
                    db_url = value
                    break

print(db_url.strip(), end="")
PYTHON
)"

if [ -z "$DATABASE_URL" ]; then
  echo "❌ DATABASE_URL is not set (environment or .env)"
  exit 1
fi

export DATABASE_URL

if [ -d venv ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
else
  echo "⚠️  venv directory not found; falling back to system Python"
fi

export PYTHONUNBUFFERED=1

case "$MODE" in
  daily)
    python <<'PYTHON'
import os
import sys
from datetime import datetime

sys.path.append(os.path.join(os.getcwd(), 'api'))

from api.app.co_occurrence_batch import CoOccurrenceBatchProcessor
from api.app.database import SessionLocal
from sqlalchemy.exc import SQLAlchemyError

start_time = datetime.now()
print(f"Running daily co-occurrence batch update... (started at {start_time.isoformat()})")

db = SessionLocal()
try:
    processor = CoOccurrenceBatchProcessor(db)
    stat = processor.process_daily_batch()
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    print(
        f"✅ Batch completed: {stat.records_processed} records processed in {duration_ms} ms"
    )
except (SQLAlchemyError, AttributeError, ValueError, RuntimeError) as exc:
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    print(f"❌ Batch failed after {duration_ms} ms: {exc}")
    raise
finally:
    db.close()
PYTHON
    ;;
  cleanup)
    export DAYS_TO_KEEP
    cleanup_status=0
    python <<'PYTHON' || cleanup_status=$?
import os
import sys
from datetime import datetime

sys.path.append(os.path.join(os.getcwd(), 'api'))

from api.app.co_occurrence_batch import CoOccurrenceBatchProcessor
from api.app.database import SessionLocal
from sqlalchemy.exc import SQLAlchemyError

start_time = datetime.now()
days_to_keep = int(os.environ.get("DAYS_TO_KEEP", "90"))
print(
    f"Running monthly co-occurrence cleanup (started at {start_time.isoformat()} | days_to_keep={days_to_keep})"
)

db = SessionLocal()
cleanup_failed = False
try:
    processor = CoOccurrenceBatchProcessor(db)
    processor.cleanup_old_data(days_to_keep=days_to_keep)
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    print(f"✅ Cleanup completed in {duration_ms} ms")
except (SQLAlchemyError, AttributeError, ValueError, RuntimeError) as exc:
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    print(f"⚠️  Cleanup failed after {duration_ms} ms: {exc}")
    cleanup_failed = True
finally:
    db.close()

if cleanup_failed:
    print("⚠️  Monthly cleanup completed with warnings (continuing without failure)")
PYTHON
    if [ "$cleanup_status" -ne 0 ]; then
      echo "⚠️  Cleanup Python script exited with status $cleanup_status"
    fi
    ;;
  *)
    echo "❌ Unknown mode: $MODE"
    exit 1
    ;;
esac
