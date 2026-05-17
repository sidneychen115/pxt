#!/usr/bin/env bash
# Rebuild / restart PXT Docker stack (project: pxt).
# API (backend) and backtest-worker are separate services and separate pxt-build flags.
# Set PXT_ROOT if the repo is not at ~/projects/pxt.

set -euo pipefail

PXT_ROOT="${PXT_ROOT:-/home/imxichen/projects/pxt}"
COMPOSE_DIR="${PXT_ROOT}/docker"
COMPOSE=(docker compose)
ALEMBIC_CMD=(/app/.venv/bin/alembic upgrade head)

usage() {
  cat <<'EOF'
Usage: pxt-build [-h] [-a | -f | -b | -w | -d]

  -h, --help   Show this help and exit

  -a   Migrate DB, rebuild & restart backend + backtest-worker + frontend (full deploy)
  -b   Rebuild & restart API (backend) only — signals, scheduler, HTTP
  -w   Rebuild & restart backtest-worker only — queued backtests
  -f   Rebuild & restart frontend only
  -d   Run Alembic migrations only (no image build). Compose mounts backend/alembic
       from your repo so new revisions apply without rebuilding.

  Combine flags: e.g. pxt-build -b -w rebuilds both without frontend.

  PXT_ROOT  Repo path (default: /home/imxichen/projects/pxt)

Daily use (signals / trading): backend (+ postgres, frontend) is enough; skip -w.
Backtests need backtest-worker (pxt-build -w) or pxt-build -a.

Examples:
  pxt-build -a
  pxt-build -b
  pxt-build -w
  pxt-build -b -w
EOF
}

log() { printf '==> %s\n' "$*"; }
die() { printf 'pxt-build: %s\n' "$*" >&2; exit 1; }

worker_scale() {
  if [[ -f "${PXT_ROOT}/.env" ]]; then
    local v
    v=$(grep -E '^[[:space:]]*BACKTEST_WORKER_SCALE=' "${PXT_ROOT}/.env" | tail -1 \
      | cut -d= -f2- | tr -d ' "'"'" | tr -d '\r')
    if [[ -n "$v" ]]; then
      echo "$v"
      return
    fi
  fi
  echo "${BACKTEST_WORKER_SCALE:-1}"
}

compose() {
  (cd "$COMPOSE_DIR" && "${COMPOSE[@]}" "$@")
}

do_migrate() {
  [[ -d "$COMPOSE_DIR" ]] || die "Compose dir not found: $COMPOSE_DIR"
  [[ -f "${PXT_ROOT}/.env" ]] || die "Missing ${PXT_ROOT}/.env (copy from .env.example)"

  log "Ensuring postgres is up…"
  compose up -d postgres

  log "Waiting for postgres health…"
  local i
  for i in $(seq 1 30); do
    if compose exec -T postgres pg_isready -U cx_user -d pxt >/dev/null 2>&1; then
      break
    fi
    if [[ "$i" -eq 30 ]]; then
      die "Postgres did not become ready in time"
    fi
    sleep 1
  done

  log "Alembic upgrade head…"
  compose run --rm backend "${ALEMBIC_CMD[@]}"
  log "Migrations done."
}

do_backend() {
  [[ -d "$COMPOSE_DIR" ]] || die "Compose dir not found: $COMPOSE_DIR"
  log "Rebuild & restart API (backend) only…"
  compose build backend
  compose up -d --force-recreate backend
  log "Backend API: http://localhost:8000"
}

do_worker() {
  [[ -d "$COMPOSE_DIR" ]] || die "Compose dir not found: $COMPOSE_DIR"
  local scale
  scale=$(worker_scale)
  log "Rebuild & restart backtest-worker only (scale=${scale})…"
  compose build backtest-worker
  compose up -d --force-recreate --scale "backtest-worker=${scale}"
  log "Backtest worker replicas: ${scale} (BACKTEST_WORKER_MAX_CONCURRENT in .env)"
  log "Logs: cd docker && docker compose logs -f backtest-worker"
}

do_frontend() {
  [[ -d "$COMPOSE_DIR" ]] || die "Compose dir not found: $COMPOSE_DIR"
  log "Rebuild & restart frontend…"
  compose build frontend
  compose up -d --force-recreate frontend
  log "Frontend: http://localhost:3000"
}

if [[ $# -eq 0 ]]; then
  usage
  exit 0
fi

for arg in "$@"; do
  case "$arg" in
    -h|--help|help)
      usage
      exit 0
      ;;
  esac
done

RUN_ALL=false
RUN_MIGRATE=false
RUN_BACKEND=false
RUN_WORKER=false
RUN_FRONTEND=false

while getopts ":abfwd" opt; do
  case "$opt" in
    a) RUN_ALL=true ;;
    b) RUN_BACKEND=true ;;
    w) RUN_WORKER=true ;;
    f) RUN_FRONTEND=true ;;
    d) RUN_MIGRATE=true ;;
    *) usage >&2; exit 1 ;;
  esac
done

if [[ "$RUN_ALL" == false && "$RUN_MIGRATE" == false && "$RUN_BACKEND" == false \
  && "$RUN_WORKER" == false && "$RUN_FRONTEND" == false ]]; then
  usage >&2
  exit 1
fi

[[ -d "$PXT_ROOT" ]] || die "PXT_ROOT does not exist: $PXT_ROOT"

if [[ "$RUN_ALL" == true ]]; then
  RUN_MIGRATE=true
  RUN_BACKEND=true
  RUN_WORKER=true
  RUN_FRONTEND=true
fi

if [[ "$RUN_MIGRATE" == true && ( "$RUN_BACKEND" == true || "$RUN_WORKER" == true ) ]]; then
  log "Building backend image (shared by API + backtest-worker)…"
  compose build backend backtest-worker
fi

[[ "$RUN_MIGRATE" == true ]] && do_migrate
[[ "$RUN_BACKEND" == true ]] && do_backend
[[ "$RUN_WORKER" == true ]] && do_worker
[[ "$RUN_FRONTEND" == true ]] && do_frontend

log "Done."
