#!/usr/bin/env bash
# Run the Quran Reels Generator using the project virtualenv.
# No extract/migration commands needed.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Virtualenv not found at .venv/bin/python" >&2
  echo "Create it: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

exec .venv/bin/python main.py "$@"
