#!/bin/sh
# Print the interpreter that has the exonware stack installed, or fail loudly.
#
# The repos are independent git clones: `repos/.venv` is this workspace's
# convention, not a guarantee. Someone can clone markibx-api on its own, keep
# their venv somewhere else entirely, or run this in CI with no venv at all.
# So: resolve, don't assume.
#
# Precedence (first hit wins):
#   1. $XW_PYTHON            -- explicit override, always wins
#   2. $VIRTUAL_ENV          -- a venv the caller already activated
#   3. .venv walking upward  -- covers repo-local and repos/.venv layouts
#   4. python3 / python      -- CI, Docker, system installs
#
# Usage: scripts/find-python.sh          -> prints path, exit 0
#        scripts/find-python.sh --check  -> also verify it imports exonware
set -eu

# Windows/msys venvs put the interpreter in Scripts/, POSIX in bin/.
try() {
    [ -n "${1:-}" ] || return 1
    for sub in bin/python bin/python3 Scripts/python.exe; do
        [ -x "$1/$sub" ] && { echo "$1/$sub"; return 0; }
    done
    return 1
}

# Walk up from cwd looking for $1 (a path relative to each ancestor).
walk_up() {
    dir=$(pwd)
    i=0
    while [ "$i" -lt 6 ]; do
        try "$dir/$1" && return 0
        [ "$dir" = "/" ] && break
        dir=$(dirname "$dir")
        i=$((i + 1))
    done
    return 1
}

found=""
if [ -n "${XW_PYTHON:-}" ] && [ -x "${XW_PYTHON}" ]; then
    found="$XW_PYTHON"
elif [ -n "${VIRTUAL_ENV:-}" ] && found=$(try "$VIRTUAL_ENV"); then
    :
# Two passes, and the order matters. `repos/.venv` is the workspace marker -- it
# only matches the real xwresearch layout. A bare `.venv` pass would happily grab
# an unrelated venv sitting anywhere above the checkout (there is one at
# ~/all/.venv on the author's box) and then fail with a confusing import error.
elif found=$(walk_up repos/.venv); then
    :
# Standalone clone of a single repo: its own .venv is all there is.
elif found=$(walk_up .venv); then
    :
fi

[ -n "$found" ] || found=$(command -v python3 || command -v python || true)

if [ -z "$found" ]; then
    echo "no Python interpreter found -- set XW_PYTHON or activate a venv" >&2
    exit 1
fi

if [ "${1:-}" = "--check" ]; then
    # The failure this catches: a real interpreter that simply has none of the
    # editable installs, which otherwise surfaces as a pytest collection error
    # and gets misread as broken code.
    if ! "$found" -c 'import exonware' >/dev/null 2>&1; then
        echo "$found cannot import 'exonware' -- wrong interpreter, or the" >&2
        echo "editable installs are missing. Expected the shared venv (repos/.venv" >&2
        echo "in the xwresearch workspace). Override with XW_PYTHON=/path/to/python." >&2
        exit 1
    fi
fi

echo "$found"
