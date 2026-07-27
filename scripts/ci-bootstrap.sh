#!/usr/bin/env bash
# Reconstruct enough of the workspace to test ONE product repo, from a bare
# checkout of just that repo. This is what CI runs; it is also runnable locally,
# which is the only reason it can be trusted.
#
# The problem it solves: every product repo depends on ~9 sibling `exonware-*`
# distributions, none of which are published (all 404 on PyPI). A CI job that
# checks out one repo and runs `pip install -e .` cannot work, ever. So CI has to
# clone the siblings first and build the shared editable venv over them.
#
#   scripts/ci-bootstrap.sh <repo-name> [workspace-dir]
#
# Auth: clones over HTTPS. In CI set GH_TOKEN (a PAT or App token with read
# access to the Exonware org) -- the repos are private. Locally your existing
# git credential helper is used and GH_TOKEN can stay unset.
set -euo pipefail

REPO="${1:?usage: ci-bootstrap.sh <repo-name> [workspace-dir]}"
WORK="${2:-$PWD/.ci-workspace}"
ORG="${XW_GITHUB_ORG:-Exonware}"
TOOLS_REF="${XW_TOOLS_REF:-main}"

# Every Python platform library, not a computed closure. Two reasons the closure
# approach fails: dependency names do not match repo names (exonware-xwauth-id
# lives in xwauth-identity), and the transitive set is deep enough that any
# hand-written subset comes up short -- the first attempt here missed xwdata and
# xwnode and produced four BROKEN packages. Depth-1 clones are cheap; guessing
# is not. xwui/xw3d/xwgis are excluded: not Python packages.
COMMON="xwaction xwapi xwauth xwauth-connect xwauth-identity xwbase xwbase-media
        xwbots xwchat xwdata xwencrypt xwentity xwjson xwmemory xwmodels xwnode
        xwquery xwrouter xwschema xwscript xwstorage xwstorage-connect
        xwstorage-db xwstorage-db-api xwsyntax xwsystem"
case "$REPO" in
    mawtarx*) SIBLINGS="$COMMON mawtarx mawtarx-connect markibx markibx-connect" ;;
    markibx*) SIBLINGS="$COMMON markibx markibx-connect" ;;
    kara*)    SIBLINGS="$COMMON kara kara-connect karaa-connect-api mawtarx mawtarx-connect markibx markibx-connect" ;;
    *)        SIBLINGS="$COMMON" ;;
esac

# Refuse to run against the real workspace. Below, existing clones are brought to
# origin/HEAD with `reset --hard` -- correct for a disposable CI checkout, and a
# way to destroy unpushed work anywhere else. The markibx family alone carries
# ~25 unpushed commits.
if [ -d "$WORK/repos" ] && [ -e "$WORK/repos/.venv" ] && [ -z "${XW_CI_ALLOW_DIRTY:-}" ]; then
    echo "refusing: $WORK/repos looks like the live workspace (has .venv)." >&2
    echo "This script hard-resets checkouts. Point it at a scratch dir." >&2
    exit 1
fi

mkdir -p "$WORK/repos"

# Bounded and retried. A single hung clone otherwise blocks the whole job for the
# git default (no timeout at all -- one run here sat 300s on xwstorage-connect
# before failing). Fail fast, retry, move on.
CLONE_TIMEOUT="${XW_CLONE_TIMEOUT:-60}"
clone_one() {
    local name="$1" dest="$WORK/repos/$1" url attempt
    # Already present: refresh it, but a failed refresh is not fatal -- the
    # checkout on disk is still usable. In CI every clone is fresh, so this path
    # only ever runs on a local re-run, where flaky network should not restart
    # a 25-repo bootstrap from zero.
    if [ -d "$dest/.git" ]; then
        if timeout "$CLONE_TIMEOUT" git -C "$dest" fetch --quiet origin 2>/dev/null; then
            git -C "$dest" reset --quiet --hard origin/HEAD 2>/dev/null || true
        else
            echo "    (offline? keeping existing $name)" >&2
        fi
        return 0
    fi
    url="https://github.com/$ORG/$name.git"
    [ -n "${GH_TOKEN:-}" ] && url="https://x-access-token:${GH_TOKEN}@github.com/$ORG/$name.git"
    for attempt in 1 2 3; do
        rm -rf "$dest"
        if timeout "$CLONE_TIMEOUT" git clone --quiet --depth 1 "$url" "$dest"; then
            return 0
        fi
        echo "    retry $attempt/3: $name" >&2
        sleep $((attempt * 3))
    done
    return 1
}

echo "==> cloning $REPO + $(echo "$SIBLINGS" | wc -w) siblings into $WORK/repos"
for name in $REPO $SIBLINGS; do
    [ -d "$WORK/repos/$name" ] || echo "    $name"
    clone_one "$name" || { echo "clone failed: $name" >&2; exit 1; }
done

# The tooling (setup-venv.py, doctor.py) lives in the xwresearch workspace, which
# is not a dependency of any product repo. Prefer a local copy when this script
# is run from inside that workspace; otherwise fetch it.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/setup-venv.py" ]; then
    mkdir -p "$WORK/scripts" && cp "$HERE"/setup-venv.py "$HERE"/doctor.py "$HERE"/find-python.sh "$WORK/scripts/"
else
    echo "==> fetching workspace tooling ($ORG/xwresearch@$TOOLS_REF)"
    clone_one xwresearch
    mkdir -p "$WORK/scripts" && cp "$WORK/repos/xwresearch/scripts/"* "$WORK/scripts/" 2>/dev/null || true
fi

echo "==> building the editable venv"
python3 "$WORK/scripts/setup-venv.py" --venv "$WORK/repos/.venv"

echo "==> doctor"
"$WORK/repos/.venv/bin/python" "$WORK/scripts/doctor.py"

echo "==> pytest ($REPO)"
cd "$WORK/repos/$REPO"
"$WORK/repos/.venv/bin/python" -m pytest --no-header -o addopts=-q
