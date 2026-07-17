#!/usr/bin/env bash
# Launch / stop / inspect the karaa stack locally, each service under a cgroup
# memory cap so a runaway is OOM-killed instead of freezing the machine.
#
#   run-stack.sh start [mawtarx|kara-api|kara-web|all]
#   run-stack.sh stop  [ ... | all ]
#   run-stack.sh status
#   run-stack.sh logs  <mawtarx|kara-api|kara-web>
#
# Supported backend is xwstorage-db (xwjson). Postgres is force-disabled
# (MAWTARX_PG_DSN="") - it is the DANGEROUS store that OOMs the box.
set -uo pipefail

# repos/ dir = two levels up from this script (.claude/skills/run-local-stack/).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../repos" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin"

# unit-name : port : health-path
MAWTARX_UNIT=mawtarx-api-run;  MAWTARX_PORT=8250; MAWTARX_HEALTH=/api/mawtarx/v1/health
KARA_UNIT=karaa-api-run;       KARA_PORT=8130;    KARA_HEALTH=/api/karaa/v1/health
WEB_UNIT=kara-web-run;         WEB_PORT=8135

log(){ printf '\033[1;36m» %s\033[0m\n' "$*"; }
err(){ printf '\033[1;31m! %s\033[0m\n' "$*" >&2; }

_stop(){ systemctl --user stop "$1" 2>/dev/null; systemctl --user reset-failed "$1" 2>/dev/null; }

_wait_health(){ # url
  for _ in $(seq 1 40); do curl -sf "$1" >/dev/null 2>&1 && return 0; sleep 1; done; return 1
}

start_mawtarx(){
  _stop "$MAWTARX_UNIT"
  log "mawtarx-api :$MAWTARX_PORT  (xwjson, PG disabled, cap 2G)"
  # Real scraped Saudi inventory (xwstorage-db, collections/listings.xwjson ~20 MB),
  # produced by mawtarx-connect — NOT the 200-row synthetic seed. Seeding is off so
  # the engine never injects fake rows into the real DB.
  systemd-run --user -u "$MAWTARX_UNIT" -p MemoryMax=2G -p MemorySwapMax=0 \
    -E MAWTARX_PG_DSN= \
    -E MAWTARX_SYSTEM_DB_DIR="$ROOT/mawtarx-connect/mawtarx-data/xwdb-saudi-v2" \
    -E MAWTARX_STORE_FILE="$ROOT/mawtarx-connect/mawtarx-data/xwdb-saudi-v2/collections/listings.xwjson" \
    -E MAWTARX_CATALOG_FILE="$ROOT/mawtarx-connect/mawtarx-data/xwdb-saudi-v2/collections/catalog.xwjson" \
    -E MAWTARX_SEED_ON_EMPTY=0 \
    "$PY/mawtarx-api" --host 127.0.0.1 --port "$MAWTARX_PORT" >/dev/null 2>&1
  _wait_health "http://127.0.0.1:$MAWTARX_PORT$MAWTARX_HEALTH" \
    && log "  up: $(curl -s http://127.0.0.1:$MAWTARX_PORT$MAWTARX_HEALTH)" \
    || err "  mawtarx-api did not become healthy - see: $0 logs mawtarx"
}

start_kara(){
  _stop "$KARA_UNIT"
  log "kara-api :$KARA_PORT  (listings_mode from its .env.local -> proxies mawtarx, cap 2G)"
  # kara-api reads repos/kara-api/.env.local for KARAA_LISTINGS_MODE + MAWTARX_API_URL.
  systemd-run --user -u "$KARA_UNIT" -p MemoryMax=2G -p MemorySwapMax=0 \
    -E KARAA_SYSTEM_DB_DIR="$ROOT/karaa-data/system" \
    -E KARAA_STORE_FILE="$ROOT/karaa-data/listings.xwjson" \
    -E KARAA_CATALOG_FILE="$ROOT/karaa-data/catalog.xwjson" \
    -E KARAA_SYNC_TOKENS_DIR="$ROOT/karaa-data/sync-tokens" \
    "$PY/karaa-api" --host 127.0.0.1 --port "$KARA_PORT" >/dev/null 2>&1
  _wait_health "http://127.0.0.1:$KARA_PORT$KARA_HEALTH" \
    && log "  up: $(curl -s http://127.0.0.1:$KARA_PORT$KARA_HEALTH)" \
    || err "  kara-api did not become healthy - see: $0 logs kara-api"
}

start_web(){
  _stop "$WEB_UNIT"
  log "kara-web (Vite) :$WEB_PORT  (proxies /api -> kara-api, cap 2.5G)"
  systemd-run --user -u "$WEB_UNIT" \
    -p WorkingDirectory="$ROOT/kara-web" -p MemoryMax=2500M -p MemorySwapMax=0 \
    -E PATH=/usr/bin:/bin -E HOME="$HOME" \
    /usr/bin/npm run dev >/dev/null 2>&1
  _wait_health "http://127.0.0.1:$WEB_PORT/" \
    && log "  up: http://127.0.0.1:$WEB_PORT/" \
    || err "  kara-web did not become healthy - see: $0 logs kara-web"
}

case "${1:-}" in
  start)
    case "${2:-all}" in
      mawtarx) start_mawtarx;;
      kara-api) start_kara;;
      kara-web) start_web;;
      all) start_mawtarx; start_kara; start_web
           log "Open the site: http://127.0.0.1:$WEB_PORT";;
      *) err "unknown target ${2:-}"; exit 2;;
    esac;;
  stop)
    case "${2:-all}" in
      mawtarx) _stop "$MAWTARX_UNIT";;
      kara-api) _stop "$KARA_UNIT";;
      kara-web) _stop "$WEB_UNIT";;
      all) _stop "$WEB_UNIT"; _stop "$KARA_UNIT"; _stop "$MAWTARX_UNIT"; log "stopped all";;
      *) err "unknown target ${2:-}"; exit 2;;
    esac;;
  status)
    for u in "$MAWTARX_UNIT" "$KARA_UNIT" "$WEB_UNIT"; do
      st=$(systemctl --user is-active "$u" 2>/dev/null)
      mem=$(systemctl --user show "$u" -p MemoryCurrent --value 2>/dev/null | awk '{if($1+0>0)printf "%.0fMB",$1/1048576; else print "-"}')
      printf '  %-16s %-10s %s\n' "$u" "${st:-inactive}" "$mem"
    done;;
  logs)
    case "${2:-}" in
      mawtarx) journalctl --user -u "$MAWTARX_UNIT" -n 60 --no-pager;;
      kara-api) journalctl --user -u "$KARA_UNIT" -n 60 --no-pager;;
      kara-web) journalctl --user -u "$WEB_UNIT" -n 60 --no-pager;;
      *) err "usage: $0 logs <mawtarx|kara-api|kara-web>"; exit 2;;
    esac;;
  *) err "usage: $0 {start|stop|status|logs} [target]"; exit 2;;
esac
