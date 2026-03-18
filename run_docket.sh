#!/bin/bash
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ_DIR"

# Load credentials from .env
if [ -f "$PROJ_DIR/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$PROJ_DIR/.env"
  set +a
fi

# Activate virtual environment
source "$PROJ_DIR/.venv/bin/activate"

# Ensure project root is on the Python path so 'import config' works
export PYTHONPATH="$PROJ_DIR"

# Append all output to logs/docket.log
LOG_DIR="$PROJ_DIR/logs"
mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/docket.log" 2>&1

echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---"
echo "Downloading AppColl CSV..."
python scripts/appcoll_downloader.py

echo "Generating docket report..."
python scripts/main.py

echo "Done."
