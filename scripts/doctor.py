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

    for mod in stale:
        print(f"STALE   {mod} -- namespace shell, no source. Reinstall its editable.")
    for mod, err in broken:
        print(f"BROKEN  {mod} -- {err}")
    for mod, missing in optional:
        print(f"note    {mod} -- optional dep {missing!r} not installed (ignored)")

    print(f"\nxwport_abi: {abi}")
    print(f"{ok} ok, {len(stale)} stale, {len(broken)} broken, {len(optional)} missing-extra")

    if stale:
        print(
            "\nFix: find the repo, check whether its pyproject moved under ports/python,\n"
            "     then `uv pip install --python repos/.venv/bin/python --no-deps -e <path>`"
        )
    return 1 if (stale or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
