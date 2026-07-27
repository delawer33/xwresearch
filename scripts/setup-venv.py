#!/usr/bin/env python3
"""Build or repair the shared editable venv for the whole product stack.

Why this exists: none of the `exonware-*` distributions are published to PyPI
(all 404). So they can only resolve against each other from local paths -- and
only if every one of them is passed to a *single* install command. Installing
them one at a time fails, because package N's `exonware-xwapi` dependency is not
on any registry yet.

The other failure this repairs: a library moves its Python source (the 2026-07-23
`src/` -> `ports/python/src/` relocation) and the recorded editable path goes
stale. The old directory still exists, imports as an empty namespace package, and
every dependent repo dies at test collection with "unknown location". Re-running
this points every editable install back at the real source tree.

    python scripts/setup-venv.py --dry-run     # show the plan, touch nothing
    python scripts/setup-venv.py               # build/repair repos/.venv
    python scripts/setup-venv.py --venv /tmp/v --no-deps   # fast, no PyPI

Verify afterwards with `task doctor`.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT / "repos"


def count_py(path: Path) -> int:
    """.py files under a candidate's src/, capped -- we only need a comparison."""
    src = path / "src"
    if not src.is_dir():
        return 0
    n = 0
    for _ in src.rglob("*.py"):
        n += 1
        if n > 200:
            break
    return n


def discover() -> list[tuple[str, Path, str]]:
    """(repo, package dir, dist name) for every Python package under repos/.

    A repo may carry pyproject.toml at its root AND under ports/python -- xwsystem
    does. Picking the wrong one installs an editable pointing at a directory with
    no source, which is exactly the breakage this script exists to fix. So choose
    by which tree actually holds .py files, not by position.
    """
    found = []
    for repo in sorted(p for p in REPOS.iterdir() if p.is_dir() and not p.name.startswith(".")):
        cands = [c for c in (repo, repo / "ports" / "python") if (c / "pyproject.toml").is_file()]
        if not cands:
            continue
        best = max(cands, key=count_py) if len(cands) > 1 else cands[0]
        try:
            name = tomllib.loads((best / "pyproject.toml").read_bytes().decode())["project"]["name"]
        except Exception as exc:  # noqa: BLE001 - a malformed pyproject is worth naming
            print(f"  ! {repo.name}: unreadable pyproject ({exc})", file=sys.stderr)
            continue
        found.append((repo.name, best, name))
    return found


PIN = re.compile(r"^\s*(exonware-[a-z0-9-]+)\s*==\s*([0-9][^\s,;\"']*)")


def pin_conflicts(pkgs: list[tuple[str, Path, str]]) -> dict[str, dict[str, list[str]]]:
    """Exact `exonware-x==1.2.3` pins that disagree across the workspace.

    These are unresolvable by construction and uv reports them as a wall of
    "we can conclude that..." prose naming only two of the packages involved.
    Naming every pinner up front is the difference between a 30-second fix and
    an afternoon. (Live example 2026-07-26: xwauth-connect pinned
    exonware-xwsystem==0.9.0.43 while xwbase pinned ==0.9.0.79.)
    """
    pins: dict[str, dict[str, list[str]]] = {}
    for _repo, d, name in pkgs:
        try:
            data = tomllib.loads((d / "pyproject.toml").read_bytes().decode())
        except Exception:  # noqa: BLE001 - discover() already reported it
            continue
        deps = list(data.get("project", {}).get("dependencies", []) or [])
        for group in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
            deps += list(group or [])
        for dep in deps:
            m = PIN.match(str(dep))
            if m:
                pins.setdefault(m.group(1), {}).setdefault(m.group(2), []).append(name)
    return {t: v for t, v in pins.items() if len(v) > 1}


def third_party(pkgs: list[tuple[str, Path, str]]) -> list[str]:
    """Every non-exonware requirement across the workspace, deduped.

    Only the base `dependencies`; optional-dependency groups are per-package
    opt-ins (dev/test extras, imaging backends) and pulling all of them into one
    venv drags in conflicting toolchains.
    """
    seen: dict[str, str] = {}
    for _repo, d, _name in pkgs:
        try:
            data = tomllib.loads((d / "pyproject.toml").read_bytes().decode())
        except Exception:  # noqa: BLE001
            continue
        proj = data.get("project", {})
        deps = list(proj.get("dependencies", []) or [])
        # ...plus the `dev` group only. That is where pytest lives, and a venv you
        # cannot run the tests in is not a working venv. The other groups (`full`,
        # `report-full`, `entity`) are per-package opt-ins that drag in conflicting
        # toolchains, so they stay out.
        deps += list((proj.get("optional-dependencies", {}) or {}).get("dev", []) or [])
        for dep in deps:
            dep = str(dep).strip()
            if dep.lower().startswith(("exonware-", "xwport-abi")):
                continue
            key = re.split(r"[\s<>=!~\[;]", dep, 1)[0].lower()
            # Keep the first spelling seen; uv reconciles compatible specifiers.
            seen.setdefault(key, dep)
    return sorted(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venv", default=str(REPOS / ".venv"), help="target venv (default: repos/.venv)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")
    ap.add_argument("--no-deps", action="store_true",
                    help="skip third-party resolution -- fast repair of stale editable paths")
    ap.add_argument("--exclude", default="", help="comma-separated repo names to leave out")
    ap.add_argument("--show-pinners", action="store_true", help="list who requires which pinned version, then exit")
    ap.add_argument("--python", default=sys.executable, help="interpreter to build the venv from")
    args = ap.parse_args()

    venv = Path(args.venv).resolve()
    pkgs = discover()
    if not pkgs:
        print(f"no Python packages found under {REPOS} -- wrong directory?", file=sys.stderr)
        return 1

    skip = {s.strip() for s in args.exclude.split(",") if s.strip()}
    if skip:
        pkgs = [p for p in pkgs if p[0] not in skip]
        print(f"excluding: {', '.join(sorted(skip))}")

    conflicts = pin_conflicts(pkgs)
    if conflicts:
        print("\nnote: exonware-* exact pins disagree across the workspace --")
        for target, versions in sorted(conflicts.items()):
            vs = ", ".join(f"=={v} ({len(w)})" for v, w in sorted(versions.items()))
            print(f"  {target:<26} {vs}")
        print("  ignored below: editable local checkouts ARE the version. Release builds\n"
              "  still have to reconcile these -- `--show-pinners` names who wants what.")
    if args.show_pinners:
        for target, versions in sorted(conflicts.items()):
            print(f"\n{target}")
            for ver, who in sorted(versions.items()):
                print(f"  =={ver:<12} {', '.join(sorted(set(who)))}")
        return 0

    moved = [(r, d) for r, d, _ in pkgs if d.name == "python"]
    print(f"{len(pkgs)} packages ({len(moved)} under ports/python) -> {venv}")
    if args.dry_run:
        for repo, d, name in pkgs:
            print(f"  {name:<32} {d.relative_to(REPOS)}")

    uv = shutil.which("uv")
    if not uv:
        print("uv not found on PATH -- install it, or adapt this to pip", file=sys.stderr)
        return 1

    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        cmd = [uv, "venv", "--python", args.python, str(venv)]
        print(f"\n$ {' '.join(cmd)}")
        if not args.dry_run and subprocess.run(cmd).returncode:
            return 1

    # Two phases, and it has to be two.
    #
    # Phase 1 installs every exonware package editable with --no-deps. Their
    # inter-dependencies are exact pins that contradict each other (see above)
    # and none of them are on any registry, so any resolver run over them fails.
    # --no-deps is not a shortcut here: for editable local checkouts the working
    # tree IS the version, and the recorded pin is noise.
    #
    # Phase 2 installs the union of the *third-party* requirements, which do come
    # from PyPI and do need resolving. Skipping this leaves a venv whose paths are
    # perfect and which cannot import anything ("No module named 'colorama'").
    phase1 = [uv, "pip", "install", "--python", str(py), "--no-deps"]
    for _repo, d, _name in pkgs:
        phase1 += ["-e", str(d)]

    # xwaction/backends/native.py does an unconditional module-scope
    # `from xwport_abi.binder import ...` and no real xwport_abi exists anywhere
    # (not in repos/, not on PyPI). xwmemory carries a stub for its Docker image;
    # without it every importer of xwaction dies at collection.
    stub = REPOS / "xwmemory" / "docker" / "xwport_abi_stub"
    if stub.is_dir():
        phase1 += [str(stub)]
    else:
        print("  ! xwport_abi stub not found -- xwaction importers will fail", file=sys.stderr)

    third = third_party(pkgs)
    print(f"\nphase 1: {len(pkgs)} editable packages (--no-deps)")
    print(f"phase 2: {len(third)} third-party requirements" if not args.no_deps
          else "phase 2: skipped (--no-deps)")
    if args.dry_run:
        print("\n(dry run -- nothing installed)")
        return 0

    if subprocess.run(phase1).returncode:
        print("\nphase 1 failed -- see above", file=sys.stderr)
        return 1

    if not args.no_deps and third:
        if subprocess.run([uv, "pip", "install", "--python", str(py), *third]).returncode:
            print("\nphase 2 failed -- a third-party requirement did not resolve", file=sys.stderr)
            return 1

    print(f"\ndone. verify:  {py} {ROOT / 'scripts' / 'doctor.py'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
