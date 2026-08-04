#!/usr/bin/env python
"""Keep concurrent agents from clobbering each other inside a shared repo checkout.

The problem this exists for: 5+ Claude sessions run against `repos/*` at once
(four transcripts were being written in the same minute on 2026-08-03). Two
agents editing one repo is fine right up until it isn't -- agent A mid-merge in
`repos/mawtarx` while agent B runs `git commit` there commits A's half-resolved
merge, because the index and MERGE_HEAD are repo-wide even though the files
aren't.

The model, in one paragraph. Worktrees are the normal way to work, and a
worktree needs no coordination at all: its own index, its own HEAD, private
files. Leases exist only for the *main* checkout -- direct edits in it, and
merges into it. Within a main checkout, a SECTION lease covers a sub-path, so
two agents in non-overlapping sections both proceed (the common case); a VCS
lease covers the repo's global git state and is held only around one git command;
a MERGE lease covers an in-flight, inconsistent transition and excludes
everything. What makes concurrent commits in one checkout safe is a pathspec:
`git commit -- <my paths>` ignores whatever else is staged or dirty, so this
hook refuses index-wide git commands while another agent holds a section.

Outcomes are ALLOW / WAIT / DENY / ASK-OWNER. WAIT applies only to a git-state
lease, which lasts one command; a section lease is held until its session ends,
so waiting on one would spend the timeout and deny anyway. ASK-OWNER is for the genuinely
undecidable ones (shared files like pyproject.toml, where whether two edits
collide depends on what they say); the owner's verdict is recorded in
decisions.jsonl and never asked again.

Failure policy is asymmetric on purpose: an unprotected Edit costs a merge
conflict, an unprotected `git merge` costs a corrupted commit. So the hook fails
OPEN for edits and CLOSED for destructive git commands. `XW_LEASE_OFF=1` (or the
file `.claude/locks/OFF`, for when an agent's classifier refuses the env prefix)
bypasses everything; `XW_LEASE_SHADOW=1` logs decisions without enforcing them.

Usage:
    repo_lease.py hook                  # reads a Claude Code hook payload on stdin
    repo_lease.py claims [--json]       # what is held right now
    repo_lease.py claim <repo>... --scope S [--kind section|vcs|merge] --intent "..."
    repo_lease.py release [--repo R] [--kind K]
    repo_lease.py reap
    repo_lease.py steal <lease-id> --reason "..."
    repo_lease.py decide <repo> <scope-a> <scope-b> allow|deny [--note "..."]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
# XW_LEASE_DIR exists so the test suite can exercise the real decision paths
# against a throwaway registry instead of the live one.
LOCKS_DIR = Path(os.environ.get("XW_LEASE_DIR") or WORKSPACE / ".claude" / "locks")
DECISIONS_PATH = LOCKS_DIR / "decisions.jsonl"
LOG_PATH = LOCKS_DIR / "decisions.log"
ERRORS_PATH = LOCKS_DIR / "errors.log"

# Path-loaded, not imported: `import exonware.xwsystem` costs ~1.4s because its
# __init__ eagerly pulls pandas/zarr/scipy via io.serialization (a violation of
# AGENTS.md:132, filed separately). This hook runs on every Edit/Write/Bash, and
# must also work while the venv is broken -- which is exactly when agents thrash
# and collide. Delete this indirection the day that __init__ goes lazy.
LEASE_MODULE = (
    WORKSPACE / "repos" / "xwsystem" / "src" / "exonware" / "xwsystem" / "io" / "common" / "lease.py"
)

TTL_SECONDS = float(os.environ.get("XW_LEASE_TTL", "1200"))
WAIT_SECONDS = float(os.environ.get("XW_LEASE_WAIT", "60"))
# A VCS lease covers ONE git command and is dropped by the PostToolUse hook. But
# PostToolUse does not fire if the command is interrupted or the session dies
# mid-call, and a stuck repo-wide lease blocks every other agent's commits. Two
# minutes is far longer than any git command here and far shorter than the
# section TTL, so the worst case self-heals instead of needing a manual steal.
VCS_TTL_SECONDS = float(os.environ.get("XW_LEASE_VCS_TTL", "120"))

# A directory this wide with no subdirectories is a plugin bag, not a module:
# mawtarx-connect's providers/ holds 663 sibling connectors. Treating it as one
# section would make every connector conflict with every other, which is the
# most common parallel task in this workspace. Such files are their own section.
FLAT_WIDE_MIN = 20

# Generated, not structure. Their presence must not make a plugin directory look
# like a package (see _is_flat_and_wide).
IGNORED_DIR_NAMES = frozenset(
    {"__pycache__", "node_modules", "dist", "build", ".venv", ".pytest_cache", ".mypy_cache"}
)

# Marks "the files directly in this directory" as distinct from its subtree. A
# segment no real path contains, so it can never be an ancestor of a deeper
# scope. See scope_for() for why an auto-acquired scope must not be recursive.
DIR_SENTINEL = "#files"

# Whether two edits to these collide depends on their content, not their path
# (two agents both bumping a version, or both appending an export). Undecidable
# from here -> ASK-OWNER, once, then remembered.
SHARED_FILES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "version.py",
        "__init__.py",
        "conftest.py",
        "Taskfile.yml",
        "uv.lock",
        "poetry.lock",
        "package.json",
        "package-lock.json",
    }
)

GIT_READONLY = frozenset(
    {
        "status", "log", "diff", "show", "rev-parse", "rev-list", "branch", "remote",
        "config", "ls-files", "ls-tree", "blame", "describe", "shortlog", "grep",
        "cat-file", "for-each-ref", "symbolic-ref", "count-objects", "fsck", "help",
        "var", "check-ignore", "verify-commit", "whatchanged", "reflog", "fetch",
        "worktree", "tag", "notes", "bisect",
    }
)
# In-flight transitions: they leave the tree inconsistent across many commands,
# so the lease is held until the transition ends, not per command.
GIT_MERGE_OPS = frozenset({"merge", "rebase", "cherry-pick", "revert", "am", "citool"})
# Destroy or move uncommitted work belonging to whoever else is in the tree.
GIT_DESTRUCTIVE = frozenset({"reset", "checkout", "switch", "restore", "clean", "stash", "pull"})
# Touch the shared index; safe concurrently only with an explicit pathspec.
GIT_INDEX_OPS = frozenset({"commit", "add", "rm", "mv", "apply", "update-index"})

MERGE_STATE_MARKERS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")

ALLOW, DENY, ASK = "allow", "deny", "ask"


def load_lease_module():
    spec = importlib.util.spec_from_file_location("xw_lease", LEASE_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load lease module at {LEASE_MODULE}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves cls.__module__ via sys.modules; skip this and the
    # module raises AttributeError on None at class-creation time.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def open_lease_system():
    """The pair every CLI command needs: the module and a registry built from it."""
    lease_mod = load_lease_module()
    return lease_mod, open_registry(lease_mod)


def open_registry(lease_mod):
    """One construction point, so every entry path shares the same TTL policy."""
    return lease_mod.LeaseRegistry(
        LOCKS_DIR,
        ttl=TTL_SECONDS,
        ttl_by_kind={lease_mod.LeaseKind.VCS: VCS_TTL_SECONDS},
    )


# ---------------------------------------------------------------- repo geometry


def find_repo(path: Path) -> tuple[Path, bool] | None:
    """
    Nearest enclosing git checkout, and whether it is a worktree.

    A worktree's `.git` is a *file* pointing at the real gitdir, a main
    checkout's is a directory -- so this needs no subprocess, which matters when
    it runs before every tool call.
    """
    for candidate in [path, *path.parents]:
        marker = candidate / ".git"
        if marker.is_dir():
            return candidate, False
        if marker.is_file():
            return candidate, True
    return None


def resource_name(repo_root: Path) -> str:
    """Stable registry key: the repo's path relative to the workspace."""
    try:
        rel = repo_root.resolve().relative_to(WORKSPACE)
    except ValueError:
        return str(repo_root.resolve())
    return str(rel) if str(rel) != "." else "<workspace>"


def scope_for(repo_root: Path, target: Path) -> str:
    """
    The logical section a file belongs to.

    Default is the containing directory -- two agents in one module do collide,
    even in different files. Two exceptions, both learned from this workspace's
    layout: a file at the repo root (CLAUDE.md, DONE_TODAY.md) is its own scope,
    because the root directory means "the whole repo"; and a file in a flat,
    wide directory is its own scope (see FLAT_WIDE_MIN).

    WHY the DIR_SENTINEL suffix. Scope containment in the registry is a subtree
    relation, so a bare directory scope claims everything beneath it -- editing
    `mawtarx_connect/runner.py` would then conflict with anyone editing any of
    the 663 files under `mawtarx_connect/providers/`, which is exactly the false
    denial the flat-wide rule exists to avoid. The sentinel is a segment no real
    path has, so `<dir>/#files` means "the files directly in <dir>" and can
    never be an ancestor of a deeper scope. An *explicit* claim
    (`task claim -- <repo> --scope src/pkg`) carries no sentinel and therefore
    still covers the whole subtree, which is what a refactor wants.
    """
    rel = target.relative_to(repo_root)
    parent = target.parent
    if parent == repo_root:
        return str(rel)
    if _is_flat_and_wide(parent):
        return str(rel)
    return f"{rel.parent}/{DIR_SENTINEL}"


def _is_flat_and_wide(directory: Path) -> bool:
    """
    Many sibling files, no real subdirectories.

    Two traps, both found by testing against the real tree rather than a fixture:
    generated directories (`__pycache__` above all) are not structure and must be
    skipped, and the scan cannot bail out early on a file count -- `os.scandir`
    yields in filesystem order, so an early `return True` makes the answer depend
    on where `__pycache__` happens to land (it sits at index 656 of 664 in
    `providers/`, which is the only reason this appeared to work). Scanning the
    whole directory is ~1ms and is deterministic.
    """
    files = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.name in IGNORED_DIR_NAMES:
                    continue
                if entry.is_dir():
                    return False
                files += 1
    except OSError:
        return False
    return files >= FLAT_WIDE_MIN


def merge_in_progress(repo_root: Path) -> bool:
    git_dir = repo_root / ".git"
    return any((git_dir / marker).exists() for marker in MERGE_STATE_MARKERS)


# ------------------------------------------------------------- bash git parsing


def _split(command: str) -> list[list[str]]:
    """Split a shell line into candidate argv lists, best-effort.

    Deliberately shallow: this only needs to find `git <subcommand>`, and a
    parser that guesses harder produces false denials on working commands --
    which is how a guardrail gets switched off for good.
    """
    try:
        tokens = shlex.split(command, comments=True)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in {"&&", "||", ";", "|", "&"}:
            segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


# Global git flags that consume the next token. Missing one here makes its value
# look like the subcommand: `git -C repos/x commit` parsed as subcommand
# "repos/x", which silently classified a bare commit as harmless.
_GIT_GLOBAL_VALUE_FLAGS = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
)


def git_subcommand(argv: list[str], cwd: Path) -> tuple[str | None, Path]:
    """The subcommand and the directory it runs in, skipping global flag values."""
    target_dir = cwd
    index = 1
    while index < len(argv):
        token = argv[index]
        if token in _GIT_GLOBAL_VALUE_FLAGS and index + 1 < len(argv):
            if token == "-C":
                candidate = Path(argv[index + 1])
                target_dir = candidate if candidate.is_absolute() else cwd / candidate
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, target_dir
    return None, target_dir


@dataclass(frozen=True)
class GitCall:
    """One git invocation found in a shell line."""

    argv: list[str]
    subcommand: str
    directory: Path
    lease_class: str | None  # "merge" | "vcs" | None (read-only / unpoliced)


def _cd_target(argv: list[str], cwd: Path) -> Path | None:
    """Where `cd` lands, or None when we can't tell (`cd -`, `cd` bare, $VARs)."""
    operands = [token for token in argv[1:] if not token.startswith("-")]
    if len(operands) != 1:
        return None
    if "$" in operands[0] or "`" in operands[0]:
        return None
    candidate = Path(operands[0])
    return candidate if candidate.is_absolute() else cwd / candidate


def git_invocations(command: str, cwd: Path) -> list[GitCall]:
    """
    Every git call in a shell line, with its target repo and lease class.

    `cd` is tracked across segments because the hook payload carries the
    *session's* cwd, not the shell's: `cd <worktree> && git rebase` was being
    attributed to the main checkout, so a rebase in a private worktree queued
    behind that checkout's section holders. When a cd target is unresolvable we
    keep the current directory rather than guess -- policing the wrong repo is
    the failure mode that gets a guardrail switched off.
    """
    found: list[GitCall] = []
    effective = cwd
    for argv in _split(command):
        if not argv:
            continue
        if Path(argv[0]).name in {"cd", "pushd"}:
            landing = _cd_target(argv, effective)
            if landing is not None:
                effective = landing
            continue
        if Path(argv[0]).name != "git":
            continue
        subcommand, target_dir = git_subcommand(argv, effective)
        if subcommand is None:
            continue
        found.append(
            GitCall(
                argv=argv,
                subcommand=subcommand,
                directory=target_dir,
                lease_class=_lease_class(subcommand),
            )
        )
    return found


def _lease_class(subcommand: str) -> str | None:
    if subcommand in GIT_MERGE_OPS:
        return "merge"
    if subcommand in GIT_DESTRUCTIVE or subcommand in GIT_INDEX_OPS:
        return "vcs"
    return None  # read-only, or something we deliberately don't police


def _operands(argv: list[str], subcommand: str) -> list[str]:
    """
    Positional arguments only.

    Flag *values* must not be mistaken for paths: in `git commit -m 'x'` the
    message is not a pathspec, and reading it as one made a bare commit look
    scoped -- the exact hole this whole check exists to close.
    """
    rest = argv[argv.index(subcommand) + 1 :]
    if "--" in rest:
        rest = rest[: rest.index("--")]
    operands: list[str] = []
    index = 0
    while index < len(rest):
        token = rest[index]
        if token.startswith("--") and "=" in token:
            index += 1
            continue
        if token in _VALUE_FLAGS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        operands.append(token)
        index += 1
    return operands


_VALUE_FLAGS = frozenset(
    {
        "-m", "--message", "-F", "--file", "--author", "--date", "-C", "--reuse-message",
        "-c", "--reedit-message", "--squash", "--fixup", "-S", "--gpg-sign", "--cleanup",
        "--pathspec-from-file", "-t", "--template", "--trailer", "-b", "--branch",
    }
)


def is_index_wide(argv: list[str]) -> bool:
    """
    True when a git command sweeps whatever is in the index or the whole tree.

    `git commit -- path` and `git add path` are scoped to the caller's own
    files; `git commit`, `git commit -a`, `git add .`, `git add -A` are not, and
    will pick up another agent's half-written work.
    """
    subcommand, _ = git_subcommand(argv, Path("."))
    if subcommand is None:
        return False
    flags = {token for token in argv if token.startswith("-")}
    operands = _operands(argv, subcommand)
    if "--" in argv:
        tail = argv[argv.index("--") + 1 :]
        if tail:
            return False
    if subcommand == "commit":
        if flags & {"-a", "--all", "-am", "-A"}:
            return True
        return not operands  # bare `git commit` commits the shared index
    if subcommand == "add":
        if flags & {"-A", "--all", "-u", "--update"}:
            return True
        return any(operand in {".", "./", "*"} for operand in operands) or not operands
    if subcommand in GIT_DESTRUCTIVE:
        return True
    return False


# ------------------------------------------------------------------- decisions


def decision_key(resource: str, scope_a: str, scope_b: str) -> str:
    first, second = sorted([scope_a, scope_b])
    return f"{resource}|{first}|{second}"


def recorded_decision(key: str) -> str | None:
    """The owner's standing verdict for this scope pair, if they gave one."""
    if not DECISIONS_PATH.exists():
        return None
    verdict = None
    try:
        for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("key") == key:
                verdict = record.get("verdict")  # last write wins
    except (OSError, json.JSONDecodeError):
        return None
    return verdict


def record_decision(key: str, verdict: str, note: str = "") -> None:
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "key": key,
        "verdict": verdict,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with DECISIONS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def log_line(**fields) -> None:
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    fields["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(fields, sort_keys=True) + "\n")
    except OSError:
        pass


# ----------------------------------------------------------------------- output


def emit(decision: str, reason: str, event: str) -> int:
    """Answer the harness. Exit 2 + stderr is what actually blocks; the JSON is
    the documented channel and is emitted too so either mechanism suffices."""
    if decision == ALLOW:
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event,
            # ASK reports "deny" deliberately. The blocking mechanism is the exit
            # code, and a nonzero exit means the JSON's own decision is not what
            # the harness acts on -- so claiming "ask" here would describe a
            # prompt that never appears. ASK's *text* is what makes it an ask: it
            # tells the agent to stop and put the question to the owner.
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }
    print(json.dumps(payload))
    print(reason, file=sys.stderr)
    return 2


def worktree_hint(repo_root: Path) -> str:
    rel = resource_name(repo_root)
    slug = "my-change"
    return (
        f"Work in a worktree instead:\n"
        f"  git -C {rel} worktree add .claude/worktrees/{slug} -b feat/{slug}\n"
        f"Your merge back into main will queue on the same lease."
    )


def describe(lease, now: float) -> str:
    minutes = int(lease.age(now) // 60)
    intent = f' "{lease.intent}"' if lease.intent else ""
    return f"{lease.holder} holds {lease.kind.value}:{lease.scope or '<whole repo>'}{intent} ({minutes}m, id {lease.id})"


# -------------------------------------------------------------------- hook mode


class Hook:
    def __init__(self, payload: dict, lease_mod):
        self.payload = payload
        self.mod = lease_mod
        self.event = payload.get("hook_event_name", "PreToolUse")
        self.tool = payload.get("tool_name", "")
        self.input = payload.get("tool_input") or {}
        self.holder = payload.get("session_id") or "unknown-session"
        self.cwd = Path(payload.get("cwd") or Path.cwd())
        self.registry = open_registry(lease_mod)
        self.shadow = os.environ.get("XW_LEASE_SHADOW") == "1"

    # -- entry

    def run(self) -> int:
        if self.event == "SessionEnd":
            released = self.registry.release(self.holder)
            if released:
                log_line(event=self.event, holder=self.holder, released=released)
            return 0
        if self.event in {"Stop", "SubagentStop"}:
            # NOT a release point. Stop fires at the end of every turn, and a
            # subagent shares its parent's session id -- releasing on either
            # would drop leases the agent is still working under. Treat as a
            # liveness ping instead.
            self.registry.heartbeat(self.holder)
            return 0
        if self.event == "PostToolUse":
            self.release_finished_git_leases()
            return 0
        if self.tool in {"Edit", "Write", "NotebookEdit", "MultiEdit"}:
            decision, reason = self.check_edit()
        elif self.tool == "Bash":
            decision, reason = self.check_bash()
        else:
            return 0
        if decision != ALLOW:
            log_line(
                event=self.event, holder=self.holder, tool=self.tool,
                decision=decision, reason=reason, shadow=self.shadow,
            )
        if self.shadow:
            return 0
        return emit(decision, reason, self.event)

    def release_finished_git_leases(self) -> None:
        """
        A git command has finished. Drop what it needed; keep what is still true.

        Section leases survive -- the agent is still editing. The VCS lease is
        per-command and always goes. The MERGE lease goes only when git says the
        transition is over (no MERGE_HEAD / rebase dir left): otherwise a merge
        that stopped for conflict resolution would lose its exclusivity halfway
        through. Nothing else ends a merge lease, and `Stop` refreshes it every
        turn, so without this check one `git merge` would hold a repo exclusively
        for the rest of the session.
        """
        self.registry.release(self.holder, kind=self.mod.LeaseKind.VCS)
        held_merges = [
            lease
            for lease in self.registry.leases()
            if lease.holder == self.holder and lease.kind is self.mod.LeaseKind.MERGE
        ]
        for lease in held_merges:
            repo_root = WORKSPACE / lease.resource if lease.resource != "<workspace>" else WORKSPACE
            if not merge_in_progress(repo_root):
                self.registry.release(self.holder, lease.resource, kind=self.mod.LeaseKind.MERGE)
                log_line(event="merge-done", holder=self.holder, resource=lease.resource)

    # -- edits

    def check_edit(self) -> tuple[str, str]:
        raw = self.input.get("file_path") or self.input.get("notebook_path") or ""
        if not raw:
            return ALLOW, ""
        target = Path(raw)
        if not target.is_absolute():
            target = (self.cwd / target).resolve()
        else:
            target = target.resolve()
        if not _within(target, WORKSPACE):
            return ALLOW, ""
        located = find_repo(target)
        if located is None:
            return ALLOW, ""
        repo_root, is_worktree = located
        if is_worktree:
            return ALLOW, ""  # private tree: own index, own HEAD, nothing shared

        resource = resource_name(repo_root)
        if merge_in_progress(repo_root) and not self._holds_merge(resource):
            return DENY, (
                f"{resource} has a merge/rebase in progress -- the tree is mid-transition and "
                f"a pathspec commit is impossible there.\n{worktree_hint(repo_root)}"
            )

        scope = scope_for(repo_root, target)
        request = self.mod.LeaseRequest(
            resource=resource, scope=scope, kind=self.mod.LeaseKind.SECTION
        )
        result = self.registry.acquire(
            self.holder, [request], intent=self._intent(), pid=_agent_pid()
        )
        if result.granted:
            return ALLOW, ""

        others = result.conflicts
        if target.name in SHARED_FILES:
            conflicting_scope = _conflict_scope(others)
            verdict = recorded_decision(decision_key(resource, scope, conflicting_scope))
            if verdict == "allow":
                # The owner has ruled these two scopes independent. Take a lease on
                # the file alone rather than just waving the edit through: a lease
                # the registry doesn't hold is an agent that `task claims` cannot
                # see and that the index-wide git check will not protect. The file
                # path is a sibling of the other holder's scope, so it does not
                # re-trigger the same conflict.
                narrow = self.mod.LeaseRequest(
                    resource=resource,
                    scope=str(target.relative_to(repo_root)),
                    kind=self.mod.LeaseKind.SECTION,
                )
                granted = self.registry.acquire(
                    self.holder,
                    [narrow],
                    intent=f"{self._intent()} (owner-approved shared file)",
                    pid=_agent_pid(),
                )
                if granted.granted:
                    return ALLOW, ""
                return DENY, (
                    f"{resource}: {target.name} itself is already held:\n  "
                    + "\n  ".join(describe(lease, time.time()) for lease in granted.conflicts)
                )
            if verdict != "deny":
                return ASK, self._ask_owner_text(resource, scope, others, target)

        # Deliberately no wait here, even for a same-file conflict. Waiting only
        # pays when the holder is about to release, and a section lease is held
        # until its session ends -- so polling would burn the timeout and then
        # deny anyway, turning every collision into a minute of silence. Only VCS
        # leases, which last one git command, are worth waiting on.
        now = time.time()
        holders = "\n  ".join(describe(lease, now) for lease in others)
        return DENY, (
            f"{resource}: your scope '{scope}' overlaps another agent's.\n  {holders}\n"
            f"{worktree_hint(repo_root)}\n"
            f"Or, if you are certain they are unrelated, have the owner run:\n"
            f"  task claims:decide -- {resource} '{scope}' '{_conflict_scope(others)}' allow"
        )

    # -- bash

    def check_bash(self) -> tuple[str, str]:
        """
        One decision for the whole shell line.

        Leases for every repo the line touches are taken in a SINGLE acquire, so
        `git -C a merge && git -C b merge` can never end up holding a and denied
        on b -- a half-held set blocks other agents while being useless to this
        one, which is precisely what the registry's all-or-nothing acquire is for.
        Checking repo-by-repo silently threw that guarantee away.
        """
        command = self.input.get("command") or ""
        targets: list[tuple[GitCall, Path]] = []
        for call in git_invocations(command, self.cwd):
            if call.lease_class is None:
                continue
            located = find_repo(call.directory.resolve())
            if located is None:
                continue
            repo_root, is_worktree = located
            if is_worktree:
                continue  # a worktree has its own index; commits there are private
            if not _within(repo_root, WORKSPACE):
                continue  # another project on this machine; not ours to police
            targets.append((call, repo_root))
        if not targets:
            return ALLOW, ""

        now = time.time()
        # Someone else's sections are live, and this command would sweep the whole
        # index or discard uncommitted work. Checked before acquiring: there is no
        # point holding leases for a command we are about to refuse.
        for call, repo_root in targets:
            if not is_index_wide(call.argv):
                continue
            foreign = [
                lease
                for lease in self.registry.leases(resource_name(repo_root))
                if lease.holder != self.holder and lease.kind is self.mod.LeaseKind.SECTION
            ]
            if foreign:
                holders = "\n  ".join(describe(lease, now) for lease in foreign)
                return DENY, _index_wide_reason(call, holders, repo_root)

        requests = [
            self.mod.LeaseRequest(
                resource=resource_name(repo_root), scope="", kind=self._kind_of(call)
            )
            for call, repo_root in targets
        ]
        result = self.registry.acquire(
            self.holder, requests, intent=self._intent(), pid=_agent_pid()
        )
        if result.granted:
            return ALLOW, ""
        # A VCS lease lasts one command, so waiting is measured in seconds. A
        # merge lease can last as long as a conflict resolution -- don't stall.
        if all(request.kind is self.mod.LeaseKind.VCS for request in requests) and self._wait_for(
            requests
        ):
            return ALLOW, ""
        holders = "\n  ".join(describe(lease, now) for lease in result.conflicts)
        repos = ", ".join(sorted({request.resource for request in requests}))
        return DENY, (
            f"git state is held in {repos}:\n  {holders}\n"
            f"{worktree_hint(targets[0][1])}\n"
            f"If that holder is gone: task claims:reap, or "
            f"`scripts/repo_lease.py steal <id> --reason '...'`."
        )

    def _kind_of(self, call: GitCall):
        return self.mod.LeaseKind.MERGE if call.lease_class == "merge" else self.mod.LeaseKind.VCS

    # -- helpers

    def _wait_for(self, requests) -> bool:
        """Poll for a short-lived lease to free up. Still all-or-nothing per attempt."""
        if not isinstance(requests, list):
            requests = [requests]
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.5)
            if self.registry.acquire(
                self.holder, requests, intent=self._intent(), pid=_agent_pid()
            ).granted:
                return True
        return False

    def _holds_merge(self, resource: str) -> bool:
        return any(
            lease.holder == self.holder and lease.kind is self.mod.LeaseKind.MERGE
            for lease in self.registry.leases(resource)
        )

    def _intent(self) -> str:
        return f"{self.tool} via session {self.holder[:8]}"

    def _ask_owner_text(self, resource: str, scope: str, others, target: Path) -> str:
        now = time.time()
        holders = "\n  ".join(describe(lease, now) for lease in others)
        return (
            f"ASK OWNER -- cannot decide this one.\n"
            f"{target.name} is shared, so whether your edit collides depends on what you and "
            f"the other agent are each changing:\n  {holders}\n"
            f"Ask the owner, quoting both intents. Their answer is recorded once and never "
            f"asked again:\n"
            f"  task claims:decide -- {resource} '{scope}' '{_conflict_scope(others)}' allow|deny"
        )


def _conflict_scope(leases) -> str:
    """
    The scope used to key an owner verdict, chosen deterministically.

    Taking `leases[0]` would key the decision on registry order, so the command
    printed to the agent and the lookup done next time could disagree -- the
    owner would answer once and be asked again.
    """
    return min(lease.scope for lease in leases)


def _index_wide_reason(call: GitCall, holders: str, repo_root: Path) -> str:
    """
    Say the right thing for the command at hand.

    A commit has a scoped alternative (a pathspec) and a `reset --hard` does not
    -- it discards the other agent's uncommitted work outright. Telling someone
    to "name your own paths" for a reset is advice that cannot be followed, and
    unfollowable advice is how an agent concludes the guardrail is broken.
    """
    subcommand = call.subcommand
    head = (
        f"`git {subcommand}` in {resource_name(repo_root)} affects the whole checkout, and "
        f"another agent is working in it:\n  {holders}\n"
    )
    if subcommand in GIT_INDEX_OPS:
        return head + (
            "Name your own paths instead -- `git commit -- <your files>` ignores whatever "
            "else is staged or dirty. Never `-a`, `add .` or `add -A` in a shared checkout."
        )
    return head + (
        f"There is no scoped form of `git {subcommand}`: it would discard or move work that "
        f"is not yours. Wait for them to finish (`task claims` to watch), or\n"
        f"{worktree_hint(repo_root)}"
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def is_agent_cmdline(cmdline: str) -> bool:
    """
    Is this /proc cmdline the agent CLI itself?

    Must match on argv[0]'s basename, not a substring. A substring test looked
    fine and was actively harmful: when the hook is invoked from a Bash tool
    call, its parent is a shell running a snapshot script under `~/.claude/`,
    whose cmdline contains "claude". That recorded a pid which exited the moment
    the command finished, so every lease was reaped as dead-owner within seconds
    and enforcement silently stopped -- the worst possible failure, because
    nothing looks broken.
    """
    argv0 = cmdline.split("\0")[0] if "\0" in cmdline else cmdline.split(" ")[0]
    name = Path(argv0).name.lower()
    return name in {"claude", "claude.exe"}


def _agent_pid() -> int | None:
    """
    The agent process, for crash detection -- not this hook, which exits at once.

    Unknown parent -> None -> the TTL alone decides. That direction is safe: a
    lease held slightly too long costs one wait, a lease dropped too early costs
    a second writer in the same section.
    """
    try:
        ppid = os.getppid()
        cmdline = Path(f"/proc/{ppid}/cmdline").read_bytes().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    return ppid if is_agent_cmdline(cmdline) else None


# ------------------------------------------------------------------------- CLI


def cli_holder(args) -> str:
    return args.holder or os.environ.get("XW_LEASE_HOLDER") or f"manual-{os.getuid()}"


def cmd_hook(args) -> int:
    # Two switches for one job: an agent's permission classifier can refuse an
    # `XW_LEASE_OFF=1 ...` command outright, which left a false denial with no
    # escape at all. A file the agent can simply Write always works.
    if os.environ.get("XW_LEASE_OFF") == "1" or (LOCKS_DIR / "OFF").exists():
        return 0
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return 0  # not a payload we understand; never block on that
    try:
        return Hook(payload, load_lease_module()).run()
    except Exception as exc:  # noqa: BLE001 -- policy, see module docstring
        _log_error(exc, payload)
        if _is_destructive_payload(payload):
            return emit(
                DENY,
                f"repo-lease hook failed ({type(exc).__name__}: {exc}) and this command is "
                f"destructive, so it is blocked rather than run unprotected. Re-run with "
                f"XW_LEASE_OFF=1, or create the file {LOCKS_DIR / 'OFF'} if that env prefix "
                f"is refused, when you are certain no other agent is in this checkout.",
                payload.get("hook_event_name", "PreToolUse"),
            )
        return 0  # fail open for edits


# Derived, never hand-listed: a second copy of the subcommand taxonomy silently
# drifts, and the failure mode is the fail-closed path quietly falling open for
# whichever subcommand was added to one list and not the other. Index ops are
# excluded on purpose -- the agreed policy is fail-closed for *destructive* git,
# and blocking every commit when the registry is unreadable is wider than that.
_FAIL_CLOSED_SUBCOMMANDS = GIT_MERGE_OPS | GIT_DESTRUCTIVE
_FAIL_CLOSED_RE = re.compile(
    r"\bgit\s+(?:-\S+(?:\s+\S+)?\s+)*(" + "|".join(sorted(_FAIL_CLOSED_SUBCOMMANDS)) + r")\b"
)


def _is_destructive_payload(payload: dict) -> bool:
    """
    Best-effort, and deliberately regex-based rather than a full parse.

    This runs in the exception handler, where the real parser has already failed
    or the registry is unreadable -- so it must not depend on any of that
    machinery working.
    """
    command = ((payload.get("tool_input") or {}).get("command")) or ""
    return bool(_FAIL_CLOSED_RE.search(command))


def _log_error(exc: Exception, payload: dict) -> None:
    try:
        LOCKS_DIR.mkdir(parents=True, exist_ok=True)
        with ERRORS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "error": f"{type(exc).__name__}: {exc}",
                        "tool": payload.get("tool_name"),
                        "session": payload.get("session_id"),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    except OSError:
        pass


def cmd_claims(args) -> int:
    mod, registry = open_lease_system()
    leases = registry.leases()
    if args.json:
        print(json.dumps([lease.to_dict() for lease in leases], indent=2, sort_keys=True))
        return 0
    if not leases:
        print("no leases held")
        return 0
    now = time.time()
    print(f"{'REPO':28} {'KIND':8} {'SCOPE':38} {'AGE':>5}  HOLDER / ID")
    for lease in sorted(leases, key=lambda item: (item.resource, item.scope)):
        age = f"{int(lease.age(now) // 60)}m"
        # Truncate from the LEFT: the tail is what distinguishes two scopes, so
        # ".../providers/market_kz.py" is useful where ".../providers" is not.
        scope = lease.scope or "<whole repo>"
        if len(scope) > 38:
            scope = "…" + scope[-37:]
        print(
            f"{lease.resource[:28]:28} {lease.kind.value:8} {scope:38} {age:>5}  "
            f"{lease.holder[:12]} {lease.id}"
        )
        if lease.intent:
            print(f"{'':28} intent: {lease.intent}")
    return 0


def cmd_claim(args) -> int:
    mod, registry = open_lease_system()
    kind = mod.LeaseKind(args.kind)
    requests = [
        mod.LeaseRequest(resource=repo, scope=args.scope, kind=kind) for repo in args.repos
    ]
    # No pid: this process exits immediately, and a lease pinned to a dead pid is
    # reaped on the next read -- i.e. the claim would silently evaporate. A
    # hand-taken lease lives on the TTL and on `release`.
    result = registry.acquire(cli_holder(args), requests, intent=args.intent, pid=None)
    if result.granted:
        print(f"held {len(result.leases)} lease(s): {', '.join(args.repos)}")
        return 0
    now = time.time()
    print("blocked by:", file=sys.stderr)
    for lease in result.conflicts:
        print(f"  {describe(lease, now)}", file=sys.stderr)
    return 1


def cmd_release(args) -> int:
    mod, registry = open_lease_system()
    kind = mod.LeaseKind(args.kind) if args.kind else None
    count = registry.release(cli_holder(args), args.repo, kind=kind)
    print(f"released {count} lease(s)")
    return 0


def cmd_reap(args) -> int:
    mod, registry = open_lease_system()
    reaped = registry.reap()
    if not reaped:
        print("nothing stale")
        return 0
    for lease in reaped:
        print(f"reaped {lease.resource} {lease.kind.value}:{lease.scope} (was {lease.holder})")
    return 0


def cmd_steal(args) -> int:
    mod, registry = open_lease_system()
    stolen = registry.steal(cli_holder(args), args.lease_id, reason=args.reason)
    if stolen is None:
        print(f"no lease {args.lease_id} (already released?)", file=sys.stderr)
        return 1
    print(f"took {stolen.resource} {stolen.kind.value}:{stolen.scope} from {stolen.stolen_from}")
    return 0


SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def hook_config() -> dict:
    """
    The hook block, registered at USER level on purpose.

    Sessions here are rooted in three different places -- the workspace root,
    inside `repos/<repo>`, and inside a worktree -- and each loads a *different*
    project settings file. A workspace-root registration would therefore not
    exist for the sessions most likely to collide. The script guards on path
    (anything outside this workspace exits 0 immediately), so unrelated projects
    are unaffected.
    """
    command = f"/usr/bin/python3 {Path(__file__).resolve()} hook"
    return {
        "PreToolUse": [
            {
                "matcher": "Edit|Write|NotebookEdit|MultiEdit|Bash",
                # Longer than the default: a same-file conflict waits up to
                # XW_LEASE_WAIT seconds for the other agent to finish.
                "hooks": [{"type": "command", "command": command, "timeout": 90}],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": command, "timeout": 30}],
            }
        ],
        "SessionEnd": [{"hooks": [{"type": "command", "command": command, "timeout": 30}]}],
    }


def cmd_install_hook(args) -> int:
    """Merge the hook block into ~/.claude/settings.json (idempotent, backs up first)."""
    blocks = hook_config()
    if args.print:
        print(json.dumps({"hooks": blocks}, indent=2))
        return 0
    try:
        existing = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        existing = {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {SETTINGS_PATH}: {exc}", file=sys.stderr)
        return 1

    backup = SETTINGS_PATH.with_suffix(f".json.bak-{int(time.time())}")
    if SETTINGS_PATH.exists():
        backup.write_text(SETTINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    hooks = existing.setdefault("hooks", {})
    added = 0
    for event, entries in blocks.items():
        current = hooks.setdefault(event, [])
        for entry in entries:
            serialized = json.dumps(entry, sort_keys=True)
            if any(json.dumps(item, sort_keys=True) == serialized for item in current):
                continue
            # Drop any earlier registration of this same script before re-adding,
            # so re-running install after moving the file cannot leave two.
            current[:] = [
                item
                for item in current
                if "repo_lease.py" not in json.dumps(item)
            ]
            current.append(entry)
            added += 1
    SETTINGS_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"registered {added} hook entr{'y' if added == 1 else 'ies'} in {SETTINGS_PATH}")
    if SETTINGS_PATH.exists() and backup.exists():
        print(f"backup: {backup}")
    print("Start a new session for it to take effect. To disable: XW_LEASE_OFF=1, or")
    print("remove the repo_lease.py entries from that file.")
    return 0


def cmd_decide(args) -> int:
    key = decision_key(args.repo, args.scope_a, args.scope_b)
    record_decision(key, args.verdict, args.note)
    print(f"recorded: {key} -> {args.verdict}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    hook = sub.add_parser("hook", help="handle a Claude Code hook payload on stdin")
    hook.set_defaults(func=cmd_hook)

    claims = sub.add_parser("claims", help="show live leases")
    claims.add_argument("--json", action="store_true")
    claims.set_defaults(func=cmd_claims)

    claim = sub.add_parser("claim", help="take a lease by hand")
    claim.add_argument("repos", nargs="+")
    claim.add_argument("--scope", default="")
    claim.add_argument("--kind", default="section", choices=["section", "vcs", "merge"])
    claim.add_argument("--intent", default="")
    claim.add_argument("--holder")
    claim.set_defaults(func=cmd_claim)

    release = sub.add_parser("release", help="drop your leases")
    release.add_argument("--repo")
    release.add_argument("--kind", choices=["section", "vcs", "merge"])
    release.add_argument("--holder")
    release.set_defaults(func=cmd_release)

    reap = sub.add_parser("reap", help="drop expired or dead-owner leases")
    reap.set_defaults(func=cmd_reap)

    steal = sub.add_parser("steal", help="force-transfer a lease (reason required)")
    steal.add_argument("lease_id")
    steal.add_argument("--reason", required=True)
    steal.add_argument("--holder")
    steal.set_defaults(func=cmd_steal)

    install = sub.add_parser("install-hook", help="register the hook in ~/.claude/settings.json")
    install.add_argument("--print", action="store_true", help="show the JSON instead of writing")
    install.set_defaults(func=cmd_install_hook)

    decide = sub.add_parser("decide", help="record the owner's verdict for a scope pair")
    decide.add_argument("repo")
    decide.add_argument("scope_a")
    decide.add_argument("scope_b")
    decide.add_argument("verdict", choices=["allow", "deny"])
    decide.add_argument("--note", default="")
    decide.set_defaults(func=cmd_decide)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
