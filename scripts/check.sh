#!/usr/bin/env bash
# Quick sanity checks before restart / commit. Exit non-zero on failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== backend: compileall =="
(cd "$ROOT/backend" && uv run python -m compileall -q src)

echo "== backend: import app =="
(cd "$ROOT/backend" && uv run python -c "from src.api.main import app")

echo "== frontend: tsc =="
(cd "$ROOT/frontend" && npm run typecheck)

echo "OK"
