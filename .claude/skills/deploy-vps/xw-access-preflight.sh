#!/usr/bin/env bash
# xw-access-preflight — report, up front, which prod-ops capabilities `shukri`
# actually has on exonware-riyadh-01, so an agent hits the wall at second 0
# instead of at the last step.
#
# WHY: lesson from 2026-07-29 — Phase 2 (enable reconcile) was fully implemented
# then died because shukri cannot read/edit /etc/mawtarx-api.env, and offline
# backfills fought the watchdog because `mask` isn't grantable. Run this BEFORE
# committing to a workstream; if the capability its last step needs shows
# BLOCKED, scope it as "prepare it, a human flips the switch" up front and say
# so — don't discover it after the work is done.
#
# Read-only. Run ON the VPS as shukri:  ./xw-access-preflight
set -uo pipefail

pass(){ printf '  \033[32mGRANTED\033[0m  %-26s %s\n' "$1" "$2"; }
fail(){ printf '  \033[31mBLOCKED\033[0m  %-26s %s\n' "$1" "$2"; }
note(){ printf '  ----     %-26s %s\n' "$1" "$2"; }

echo "== xw-access-preflight ($(hostname 2>/dev/null), $(date '+%F %T %z')) =="

# 1. Deploy lock (concurrency guard, see deploy-vps skill step 0)
if [ -x /home/shukri/xw-deploy-lock ]; then pass "deploy-lock" "single-writer lock installed"
else fail "deploy-lock" "MISSING — scp xw-deploy-lock.sh up + chmod +x (skill step 0)"; fi

# 2. Read service env files (needed to safely edit any env var, e.g. reconcile)
env_ok=1
for f in /etc/karaa-api.env /etc/markibx-api.env /etc/mawtarx-api.env; do
  [ -r "$f" ] || env_ok=0
done
if [ "$env_ok" = 1 ]; then pass "read /etc/*.env" "can round-trip env safely"
else fail "read /etc/*.env" "cannot read -> any env change is a blind full-file replace (drops other vars). Blocks: reconcile toggle, any env edit."; fi

# 3. Read a running service's env via /proc (fallback for #2)
pid=$(systemctl show mawtarx-api -p MainPID --value 2>/dev/null || echo 0)
if [ "${pid:-0}" != 0 ] && [ -r "/proc/$pid/environ" ]; then pass "/proc/<pid>/environ" "can reconstruct live env"
else fail "/proc/<pid>/environ" "cannot read (process owned by service user) — no env fallback"; fi

# 4. xw-backend-ctl allowed verbs (mask/unmask needed for safe offline ops)
ctl=$(command -v xw-backend-ctl 2>/dev/null || echo /usr/local/sbin/xw-backend-ctl)
if [ -r "$ctl" ]; then
  allowed=$(grep -oE "ALLOWED_CMDS='[^']+'" "$ctl" 2>/dev/null | sed "s/ALLOWED_CMDS=//; s/'//g")
  note "xw-backend-ctl verbs" "${allowed:-unknown}"
  case "$allowed" in
    *mask*) pass "xw-backend-ctl mask" "can mask a unit for offline work";;
    *)      fail "xw-backend-ctl mask" "no mask/unmask -> offline ops MUST fit the 2-min watchdog window";;
  esac
else note "xw-backend-ctl" "wrapper not readable at $ctl"; fi

# 5. Venv write ACL (deploys install here without sudo)
for v in /opt/markibx-api/.venv /opt/mawtarx-api/.venv /opt/mawtarx-connect-api/.venv /opt/karaa-api/.venv; do
  [ -e "$v" ] || continue
  if [ -w "$v" ]; then pass "write $v" "deployable"; else fail "write $v" "no ACL — raise as a gap, sudo won't route around it"; fi
done

# 6. xw-backend-setup (env/unit install for new services)
if command -v xw-backend-setup >/dev/null 2>&1; then pass "xw-backend-setup" "present (install-env REPLACES, not merges)"
else note "xw-backend-setup" "not found"; fi

# 7. Watchdog timers (what will restart a stopped unit under you)
wd=$(systemctl list-timers 'xw-service-watchdog@*' --all --no-pager 2>/dev/null | grep -c watchdog || echo 0)
note "watchdog timers" "$wd active (fire ~every 2 min; restart any inactive unit)"

echo "== done. BLOCKED rows = confirm a human can do that step before you start. =="
