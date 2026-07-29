#!/usr/bin/env bash
# xw-deploy-lock — advisory single-writer lock for exonware-riyadh-01 deploys.
#
# WHY: multiple agent sessions share this one VPS (shared venvs, services, git).
# On 2026-07-29 a concurrent session reinstalled an OLD mawtarx build over a
# freshly-deployed one; a later restart activated it and silently regressed prod
# — detected only by luck. Same class as the 2026-07-15 karaa-api stale-deploy
# incident. This lock makes "only one agent deploys at a time" explicit and
# checkable, so the second agent is DENIED (or at least sees who holds it)
# instead of clobbering.
#
# It is ADVISORY: the scoped-sudo wrappers (xw-backend-ctl etc.) are root-owned
# and can't be made to require it without root, so enforcement lives in the
# deploy-vps skill — every deploy agent acquires this first and releases at the
# end. A holder that crashes leaves a lock that auto-expires after the TTL.
#
# Usage (run ON the VPS as shukri):
#   xw-deploy-lock acquire <holder> [reason]   # 0=got it, 1=denied, 2=usage
#   xw-deploy-lock release <holder>            # only the holder may release
#   xw-deploy-lock status                      # who holds it, and how old
#   xw-deploy-lock break                        # force-remove (last resort)
#
# <holder> should identify the session uniquely, e.g. the agent/session id.
set -euo pipefail

LOCKDIR="${XW_DEPLOY_LOCKDIR:-${HOME:-/tmp}/.xw-deploy.lock.d}"
META="$LOCKDIR/meta"
TTL="${XW_DEPLOY_LOCK_TTL:-1800}"   # seconds; a lock older than this is stale

_now() { date +%s; }
_meta() { [ -f "$META" ] && cat "$META" || echo "(no metadata)"; }
_age() { echo $(( $(_now) - $(stat -c %Y "$LOCKDIR" 2>/dev/null || _now) )); }

cmd="${1:-status}"; holder="${2:-}"; reason="${3:-}"

case "$cmd" in
  acquire)
    [ -n "$holder" ] || { echo "usage: xw-deploy-lock acquire <holder> [reason]" >&2; exit 2; }
    # Break a stale lock left by a crashed/forgotten session.
    if [ -d "$LOCKDIR" ] && [ "$(_age)" -gt "$TTL" ]; then
      echo "WARN: breaking stale lock (age $(_age)s > ${TTL}s): $(_meta | tr '\n' ' ')" >&2
      rm -rf "$LOCKDIR"
    fi
    # mkdir is atomic: exactly one racer wins, the rest get EEXIST.
    if mkdir "$LOCKDIR" 2>/dev/null; then
      printf 'holder=%s\nhost=%s\nsince=%s\nsince_epoch=%s\nreason=%s\n' \
        "$holder" "$(hostname 2>/dev/null || echo '?')" \
        "$(date '+%F %T %z')" "$(_now)" "$reason" > "$META"
      echo "ACQUIRED by '$holder'"
      exit 0
    fi
    echo "DENIED — deploy lock held by: $(_meta | tr '\n' ' ')" >&2
    exit 1
    ;;
  release)
    [ -n "$holder" ] || { echo "usage: xw-deploy-lock release <holder>" >&2; exit 2; }
    [ -d "$LOCKDIR" ] || { echo "not held (nothing to release)"; exit 0; }
    cur="$(grep '^holder=' "$META" 2>/dev/null | cut -d= -f2- || true)"
    if [ -n "$cur" ] && [ "$cur" != "$holder" ]; then
      echo "REFUSED — held by '$cur', not '$holder'. Use 'break' only if that session is dead." >&2
      exit 1
    fi
    rm -rf "$LOCKDIR"
    echo "RELEASED by '$holder'"
    ;;
  status)
    if [ -d "$LOCKDIR" ]; then echo "HELD (age $(_age)s, TTL ${TTL}s):"; _meta
    else echo "FREE"; fi
    ;;
  break)
    if [ -d "$LOCKDIR" ]; then echo "FORCE-BREAK of: $(_meta | tr '\n' ' ')"; rm -rf "$LOCKDIR"; echo "broken"
    else echo "already free"; fi
    ;;
  *)
    echo "usage: xw-deploy-lock {acquire <holder> [reason]|release <holder>|status|break}" >&2
    exit 2
    ;;
esac
