#!/usr/bin/env python
"""Check the shared repos/.venv still resolves every exonware package.

The failure this exists for: a library moves its Python source (e.g. xwapi
src/exonware/xwapi -> ports/python/src/exonware/xwapi, 2026-07-23). The editable
install in repos/.venv keeps pointing at the old path, which is still a *directory*
on disk but has no __init__.py left. Python happily treats it as an empty namespace
package, so `from exonware.xwapi import XWAPIConfig` fails with the useless
"unknown location" -- and every dependent repo's test suite dies at collection.

Run `task doctor` after any pull that touched a library's layout.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import pkgutil
import sys
from pathlib import Path


@contextlib.contextmanager
def muted():
    """Silence fd 1/2 for the whole sweep.

    Importing the API packages registers routes and prints hundreds of lines of
    XWAction signature warnings, which buries the only output that matters here.
    fd-level, not sys.stdout-level: some of that noise comes from native code.
    """
    saved = os.dup(1), os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (*saved, devnull):
            os.close(fd)


def main() -> int:
    try:
        import exonware
    except ImportError:
        print("FAIL  cannot import the `exonware` namespace at all -- is repos/.venv active?")
        return 1

    roots = list(exonware.__path__)
    print(f"exonware namespace spans {len(roots)} path entries\n")

    stale: list[str] = []
    broken: list[tuple[str, str]] = []
    optional: list[tuple[str, str]] = []
    ok = 0

    with muted():
        for _finder, name, _ispkg in pkgutil.iter_modules(roots):
            mod = f"exonware.{name}"
            try:
                m = importlib.import_module(mod)
            except ModuleNotFoundError as exc:
                # A missing *third-party* dep (protobuf, weasyprint, …) is an
                # uninstalled extra, not the layout rot this tool hunts. Keep it out
                # of the exit code -- a doctor that is always red gets ignored.
                missing = (exc.name or "").split(".")[0]
                if missing and missing != "exonware":
                    optional.append((mod, missing))
                else:
                    broken.append((mod, f"{type(exc).__name__}: {exc}"))
                continue
            except Exception as exc:  # noqa: BLE001 - report, never abort the sweep
                broken.append((mod, f"{type(exc).__name__}: {exc}"))
                continue
            # A namespace package with no real source has __file__ is None. That is
            # the stale-path signature -- an importable shell shadowing the real one.
            if getattr(m, "__file__", None) is None:
                stale.append(mod)
            else:
                ok += 1

        # xwaction's native backend imports this unconditionally at module scope and
        # no real distribution exists anywhere; repos/.venv carries xwmemory's stub.
        try:
            importlib.import_module("xwport_abi.binder")
            abi = "ok"
        except Exception as exc:  # noqa: BLE001
            abi = f"MISSING ({type(exc).__name__}) -- install xwmemory/docker/xwport_abi_stub"

    # Two repos shipping the same exonware.X both land on the namespace path, and
    # whichever editable install sorts first silently wins. The loser's functions
    # then "don't exist" (live case: kara-connect and karaa-connect-api both ship
    # exonware.karaa_connect_api; when kara-connect wins, karaa_api dies on a
    # missing build_connect_routers). Install order is not a contract -- name it.
    providers: dict[str, list[Path]] = {}
    for root in roots:
        for child in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
            if (child / "__init__.py").is_file():
                providers.setdefault(child.name, []).append(child)

    # Sharing a package across repos is fine *if* the winning __init__ calls
    # pkgutil.extend_path -- xwauth does, so xwauth/, xwauth-connect/ (.connect)
    # and xwauth-identity/ (.id) all coexist. It is only a bug when a provider's
    # directory never makes it onto the merged __path__: that repo's modules are
    # then invisible, with no error anywhere.
    dupes: dict[str, list[Path]] = {}
    for name, dirs in providers.items():
        if len(dirs) < 2:
            continue
        try:
            with muted():
                merged = {Path(p).resolve() for p in importlib.import_module(f"exonware.{name}").__path__}
        except Exception:  # noqa: BLE001 - already counted as broken above
            continue
        shadowed = [d for d in dirs if d.resolve() not in merged]
        if shadowed:
            dupes[name] = shadowed

    for mod in stale:
        print(f"STALE   {mod} -- namespace shell, no source. Reinstall its editable.")
    for name, where in sorted(dupes.items()):
        print(f"SHADOWED exonware.{name} -- these copies are on no import path:")
        for w in where:
            print(f"         {w}")
    for mod, err in broken:
        print(f"BROKEN  {mod} -- {err}")
    for mod, missing in optional:
        print(f"note    {mod} -- optional dep {missing!r} not installed (ignored)")

    print(f"\nxwport_abi: {abi}")
    print(f"{ok} ok, {len(stale)} stale, {len(dupes)} shadowed, {len(broken)} broken, {len(optional)} missing-extra")

    if stale:
        print(
            "\nFix: find the repo, check whether its pyproject moved under ports/python,\n"
            "     then `uv pip install --python repos/.venv/bin/python --no-deps -e <path>`"
        )
    # Exit only on stale/shadowed: the two faults this tool uniquely detects, and
    # the two that silently break every dependent repo at once. BROKEN is reported
    # but not fatal -- it is usually one unrelated package missing an optional
    # native backend (xwjson's Rust core, a TOML serializer), and failing a repo's
    # CI over a neighbour's missing extra just teaches everyone to skip the check.
    return 1 if (stale or dupes) else 0


if __name__ == "__main__":
    sys.exit(main())
