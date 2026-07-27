#!/usr/bin/env python3
"""Write .github/workflows/ci.yml into each product repo from the template.

One template, N repos: the repos are independent clones, so the workflow has to
be a copy in each -- but it should never be a hand-edited copy. Change
scripts/ci-workflow.yml.template and re-run this.

    python scripts/gen-ci-workflows.py --dry-run
    python scripts/gen-ci-workflows.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT / "repos"
TEMPLATE = ROOT / "scripts" / "ci-workflow.yml.template"

# Python product repos only. The three Vite front-ends need a different job
# (npm, no venv) and get no workflow here rather than a broken one.
TARGETS = [
    "kara", "kara-api", "kara-connect", "karaa-connect-api",
    "mawtarx", "mawtarx-api", "mawtarx-connect", "mawtarx-connect-api",
    "markibx", "markibx-api", "markibx-connect", "markibx-connect-api",
]


def tools_repo() -> str:
    """owner/name of this workspace, for the tooling checkout step."""
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return "OWNER/REPO"
    return url.removesuffix(".git").split("github.com")[-1].lstrip(":/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not TEMPLATE.is_file():
        print(f"missing template: {TEMPLATE}", file=sys.stderr)
        return 1
    body = TEMPLATE.read_text()
    tools = tools_repo()

    written = 0
    for name in TARGETS:
        repo = REPOS / name
        if not (repo / ".git").exists():
            print(f"  skip {name} (not cloned)")
            continue
        out = repo / ".github" / "workflows" / "ci.yml"
        text = body.replace("{{REPO}}", name).replace("{{TOOLS_REPO}}", tools)
        print(f"  {'would write' if args.dry_run else 'write'} {out.relative_to(REPOS)}")
        if not args.dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
        written += 1

    print(f"\n{written} workflows; XW_TOOLS_REPO defaults to {tools}")
    if not args.dry_run:
        print("Set secrets.XW_CI_TOKEN and vars.XW_TOOLS_REPO on each repo before this can pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
