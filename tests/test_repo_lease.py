#!/usr/bin/env python
"""Tests for scripts/repo_lease.py -- the workspace half of the lease system.

The library half (xwsystem's LeaseRegistry) has its own suite. What is tested
here is the *mapping*: file path -> repo -> section, and shell line -> git lease
class. Both are heuristics over this workspace's real layout, so they are
exercised against the real repos on disk rather than fixtures -- a fixture would
have happily accepted the rule that made all 663 connectors in
mawtarx-connect/providers/ one section.

End-to-end hook runs go through a throwaway registry (XW_LEASE_DIR) and never
touch the live one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]
SCRIPT = WORKSPACE / "scripts" / "repo_lease.py"
CONNECT = WORKSPACE / "repos" / "mawtarx-connect"


def load_module(locks_dir: Path):
    """Fresh import with the registry redirected; module-level constants read env."""
    os.environ["XW_LEASE_DIR"] = str(locks_dir)
    spec = importlib.util.spec_from_file_location(f"repo_lease_{locks_dir.name}", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mod(tmp_path):
    return load_module(tmp_path / "locks")


def hook(mod, payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "XW_LEASE_DIR": str(mod.LOCKS_DIR), "XW_LEASE_WAIT": "1"}
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), "hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=120,
    )


def edit_payload(session: str, path: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "cwd": str(WORKSPACE),
        "tool_name": "Edit",
        "tool_input": {"file_path": str(path)},
    }


def bash_payload(session: str, command: str, cwd: Path = WORKSPACE) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "cwd": str(cwd),
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


class TestRepoGeometry:
    """Main checkout vs worktree, decided without spawning git."""

    def test_main_checkout_is_not_a_worktree(self, mod):
        repo_root, is_worktree = mod.find_repo(CONNECT / "src")
        assert repo_root == CONNECT
        assert is_worktree is False

    def test_worktree_is_detected_by_dot_git_being_a_file(self, mod):
        worktrees = list((WORKSPACE / "repos" / "mawtarx").glob(".claude/worktrees/*/.git"))
        if not worktrees:
            pytest.skip("no worktree checked out right now")
        repo_root, is_worktree = mod.find_repo(worktrees[0].parent / "src")
        assert is_worktree is True

    def test_path_outside_any_repo_has_no_repo(self, mod, tmp_path):
        assert mod.find_repo(tmp_path / "nowhere") is None

    def test_resource_name_is_workspace_relative(self, mod):
        assert mod.resource_name(CONNECT) == "repos/mawtarx-connect"


class TestSectionMapping:
    """The rule that decides who blocks whom."""

    def test_flat_wide_directory_gives_each_file_its_own_section(self, mod):
        providers = CONNECT / "src" / "exonware" / "mawtarx_connect" / "providers"
        if not providers.is_dir():
            pytest.skip("providers/ not present in this checkout")
        first = mod.scope_for(CONNECT, providers / "market_kz.py")
        second = mod.scope_for(CONNECT, providers / "carwiz_il.py")
        assert first != second, "663 sibling connectors must not be one section"
        assert not mod.load_lease_module().scopes_overlap(first, second)

    def test_normal_module_directory_is_one_section(self, mod):
        pkg = CONNECT / "src" / "exonware" / "mawtarx_connect"
        scope = mod.scope_for(CONNECT, pkg / "runner.py")
        assert scope == f"src/exonware/mawtarx_connect/{mod.DIR_SENTINEL}"

    def test_module_scope_does_not_swallow_its_subdirectories(self, mod):
        """Editing runner.py must not claim all 663 files under providers/."""
        pkg = CONNECT / "src" / "exonware" / "mawtarx_connect"
        overlap = mod.load_lease_module().scopes_overlap
        assert not overlap(
            mod.scope_for(CONNECT, pkg / "runner.py"),
            mod.scope_for(CONNECT, pkg / "providers" / "market_kz.py"),
        )

    def test_an_explicit_claim_still_covers_the_whole_subtree(self, mod):
        """A refactor claims `src/pkg` with no sentinel and does cover everything."""
        pkg = CONNECT / "src" / "exonware" / "mawtarx_connect"
        overlap = mod.load_lease_module().scopes_overlap
        assert overlap(
            "src/exonware/mawtarx_connect",
            mod.scope_for(CONNECT, pkg / "providers" / "market_kz.py"),
        )
        assert overlap(
            "src/exonware/mawtarx_connect", mod.scope_for(CONNECT, pkg / "runner.py")
        )

    def test_repo_root_file_is_its_own_section_not_the_whole_repo(self, mod):
        scope = mod.scope_for(CONNECT, CONNECT / "CLAUDE.md")
        assert scope == "CLAUDE.md", "an empty scope would lock the entire repo"


class TestAgentPidDetection:
    """
    Recording the wrong pid is the quietest way to break this whole system: the
    lease is reaped as dead-owner within seconds and nothing looks wrong.
    """

    def test_real_agent_cmdline_is_accepted(self, mod):
        cmdline = (
            "/home/delawer/.config/Claude/claude-code/2.1.219/claude\0--output-format\0"
            "stream-json\0--model\0claude-opus-5\0"
        )
        assert mod.is_agent_cmdline(cmdline) is True

    @pytest.mark.parametrize(
        "cmdline",
        [
            # A shell running a snapshot script under ~/.claude/ -- the substring
            # test accepted this and dropped every lease seconds later.
            "/bin/zsh\0-c\0source /home/delawer/.claude/shell-snapshots/snapshot-zsh-1.sh",
            "/bin/bash\0/home/delawer/.claude/shell-snapshots/snapshot.sh",
            "/usr/lib/claude-desktop/claude-desktop\0",
            "python3\0/some/claude/script.py",
        ],
    )
    def test_processes_that_merely_mention_claude_are_rejected(self, mod, cmdline):
        assert mod.is_agent_cmdline(cmdline) is False


class TestGitParsing:
    def test_finds_subcommand_and_classifies(self, mod):
        calls = mod.git_invocations("git merge feat/x", WORKSPACE)
        assert [call.subcommand for call in calls] == ["merge"]
        assert calls[0].lease_class == "merge"

    def test_dash_c_retargets_the_repo(self, mod):
        calls = mod.git_invocations("git -C repos/mawtarx commit -m x", WORKSPACE)
        assert calls[0].directory == WORKSPACE / "repos/mawtarx"

    def test_read_only_commands_are_unpoliced(self, mod):
        for command in ("git status", "git log --oneline -3", "git diff HEAD"):
            assert mod.git_invocations(command, WORKSPACE)[0].lease_class is None

    def test_chained_commands_are_all_seen(self, mod):
        calls = mod.git_invocations("git add . && git commit -m x", WORKSPACE)
        assert [call.subcommand for call in calls] == ["add", "commit"]

    def test_non_git_command_yields_nothing(self, mod):
        assert mod.git_invocations("ls -la && task test", WORKSPACE) == []

    @pytest.mark.parametrize(
        "command, index_wide",
        [
            ("git commit -m 'x'", True),  # bare: commits the shared index
            ("git commit -a -m 'x'", True),
            ("git commit -m 'x' -- src/a.py", False),
            ("git add .", True),
            ("git add -A", True),
            ("git add src/a.py", False),
            ("git reset --hard origin/main", True),
            ("git stash", True),
            # -C's value must not be read as the subcommand, nor -m's as a path.
            ("git -C repos/mawtarx commit -m wip", True),
            ("git -C repos/mawtarx commit -m wip -- src/a.py", False),
        ],
    )
    def test_index_wide_classification(self, mod, command, index_wide):
        argv = mod._split(command)[0]
        assert mod.is_index_wide(argv) is index_wide


class TestHookEndToEnd:
    """Two sessions, one checkout, through the real script."""

    def test_edit_in_a_free_section_is_allowed(self, mod):
        result = hook(mod, edit_payload("agent-a", CONNECT / "src/exonware/mawtarx_connect/runner.py"))
        assert result.returncode == 0, result.stderr

    def test_second_agent_in_a_different_section_also_allowed(self, mod):
        base = CONNECT / "src/exonware/mawtarx_connect"
        assert hook(mod, edit_payload("agent-a", base / "vin_report/fetch.py")).returncode == 0
        second = hook(mod, edit_payload("agent-b", base / "connectors/sources/x.py"))
        assert second.returncode == 0, second.stderr

    def test_overlapping_section_is_denied_with_the_worktree_command(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        blocked = hook(mod, edit_payload("agent-b", target.parent / "adapters.py"))
        assert blocked.returncode == 2
        assert "worktree add" in blocked.stderr
        assert "agent-a" in blocked.stderr

    def test_edits_in_a_worktree_are_never_leased(self, mod):
        worktrees = list((WORKSPACE / "repos" / "mawtarx").glob(".claude/worktrees/*/.git"))
        if not worktrees:
            pytest.skip("no worktree checked out right now")
        tree = worktrees[0].parent
        assert hook(mod, edit_payload("agent-a", tree / "src/anything.py")).returncode == 0
        assert hook(mod, edit_payload("agent-b", tree / "src/anything.py")).returncode == 0
        assert mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases() == ()

    def test_index_wide_commit_blocked_while_another_agent_edits(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        blocked = hook(mod, bash_payload("agent-b", "git -C repos/mawtarx-connect commit -m wip"))
        assert blocked.returncode == 2
        assert "affects the whole checkout" in blocked.stderr
        assert "commit -- <your files>" in blocked.stderr, "must offer the scoped alternative"

    def test_destructive_command_is_not_told_to_use_a_pathspec(self, mod):
        """`git reset --hard` has no scoped form; advising one is unfollowable."""
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        blocked = hook(
            mod, bash_payload("agent-b", "git -C repos/mawtarx-connect reset --hard origin/main")
        )
        assert blocked.returncode == 2
        assert "no scoped form" in blocked.stderr
        assert "commit -- <your files>" not in blocked.stderr

    def test_pathspec_commit_allowed_while_another_agent_edits(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        allowed = hook(
            mod,
            bash_payload("agent-b", "git -C repos/mawtarx-connect commit -m wip -- README.md"),
        )
        assert allowed.returncode == 0, allowed.stderr

    def test_own_index_wide_commit_is_not_blocked_by_own_section(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        mine = hook(mod, bash_payload("agent-a", "git -C repos/mawtarx-connect commit -m wip"))
        assert mine.returncode == 0, mine.stderr

    def test_merge_lease_excludes_another_agents_edit(self, mod):
        assert hook(mod, bash_payload("agent-a", "git -C repos/mawtarx-connect merge feat/x")).returncode == 0
        blocked = hook(mod, edit_payload("agent-b", CONNECT / "docs/anything.md"))
        assert blocked.returncode == 2

    def test_shared_file_escalates_to_the_owner(self, mod):
        assert hook(mod, edit_payload("agent-a", CONNECT / "src/exonware/mawtarx_connect/runner.py")).returncode == 0
        asked = hook(mod, edit_payload("agent-b", CONNECT / "src/exonware/mawtarx_connect/__init__.py"))
        assert asked.returncode == 2
        assert "ASK OWNER" in asked.stderr

    def test_recorded_owner_decision_stops_the_asking(self, mod):
        base = CONNECT / "src/exonware/mawtarx_connect"
        assert hook(mod, edit_payload("agent-a", base / "runner.py")).returncode == 0
        scope = mod.scope_for(CONNECT, base / "runner.py")
        key = mod.decision_key("repos/mawtarx-connect", scope, scope)
        mod.record_decision(key, "allow", note="unrelated in practice")
        allowed = hook(mod, edit_payload("agent-b", base / "__init__.py"))
        assert allowed.returncode == 0, allowed.stderr

    def test_owner_approved_shared_file_still_takes_a_lease(self, mod):
        """
        An allowed edit with no lease is an agent invisible to `task claims` and
        unprotected by the index-wide git check.
        """
        base = CONNECT / "src/exonware/mawtarx_connect"
        assert hook(mod, edit_payload("agent-a", base / "runner.py")).returncode == 0
        key = mod.decision_key(
            "repos/mawtarx-connect",
            f"src/exonware/mawtarx_connect/{mod.DIR_SENTINEL}",
            f"src/exonware/mawtarx_connect/{mod.DIR_SENTINEL}",
        )
        mod.record_decision(key, "allow", note="unrelated in practice")
        assert hook(mod, edit_payload("agent-b", base / "__init__.py")).returncode == 0
        leases = mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()
        mine = [lease for lease in leases if lease.holder == "agent-b"]
        assert len(mine) == 1, "the owner-approved edit must be visible in the registry"
        assert mine[0].scope == "src/exonware/mawtarx_connect/__init__.py"

    def test_ask_owner_command_key_matches_what_the_lookup_reads(self, mod):
        """
        The printed `claims:decide` command must produce the key the next lookup
        uses, or the owner answers once and gets asked again.
        """
        base = CONNECT / "src/exonware/mawtarx_connect"
        hook(mod, edit_payload("agent-a", base / "runner.py"))
        asked = hook(mod, edit_payload("agent-b", base / "__init__.py"))
        assert asked.returncode == 2 and "ASK OWNER" in asked.stderr
        printed = [line for line in asked.stderr.splitlines() if "claims:decide" in line][0]
        parts = shlex.split(printed.replace("task claims:decide -- ", "").strip())
        repo, scope_a, scope_b = parts[0], parts[1], parts[2]
        mod.record_decision(mod.decision_key(repo, scope_a, scope_b), "allow")
        assert hook(mod, edit_payload("agent-b", base / "__init__.py")).returncode == 0

    def test_ask_reports_deny_in_json_so_it_matches_the_exit_code(self, mod):
        base = CONNECT / "src/exonware/mawtarx_connect"
        hook(mod, edit_payload("agent-a", base / "runner.py"))
        asked = hook(mod, edit_payload("agent-b", base / "__init__.py"))
        payload = json.loads(asked.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "ASK OWNER" in payload["hookSpecificOutput"]["permissionDecisionReason"]

    def test_session_end_releases_everything(self, mod):
        assert hook(mod, edit_payload("agent-a", CONNECT / "src/exonware/mawtarx_connect/runner.py")).returncode == 0
        hook(mod, {"hook_event_name": "SessionEnd", "session_id": "agent-a", "cwd": str(WORKSPACE)})
        assert mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases() == ()

    def test_post_tool_use_drops_the_git_lease_but_keeps_the_section(self, mod):
        base = CONNECT / "src/exonware/mawtarx_connect"
        hook(mod, edit_payload("agent-a", base / "runner.py"))
        hook(mod, bash_payload("agent-a", "git -C repos/mawtarx-connect commit -m x -- runner.py"))
        hook(
            mod,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "agent-a",
                "cwd": str(WORKSPACE),
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m x"},
            },
        )
        kinds = {lease.kind.value for lease in mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()}
        assert kinds == {"section"}

    def test_stop_is_a_heartbeat_not_a_release(self, mod):
        """Stop fires every turn; releasing there would make leases last one reply."""
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        hook(mod, {"hook_event_name": "Stop", "session_id": "agent-a", "cwd": str(WORKSPACE)})
        assert len(mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()) == 1
        blocked = hook(mod, edit_payload("agent-b", target))
        assert blocked.returncode == 2

    def test_session_rooted_inside_a_repo_with_a_relative_path(self, mod):
        """
        The colliding sessions are often rooted at `repos/<repo>`, where Edit
        carries a repo-relative path. Failing to resolve it against cwd would make
        the hook silently no-op for exactly those agents.
        """
        inside = CONNECT
        first = hook(
            mod,
            {
                "hook_event_name": "PreToolUse",
                "session_id": "agent-a",
                "cwd": str(inside),
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/exonware/mawtarx_connect/runner.py"},
            },
        )
        assert first.returncode == 0
        second = hook(
            mod,
            {
                "hook_event_name": "PreToolUse",
                "session_id": "agent-b",
                "cwd": str(inside),
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/exonware/mawtarx_connect/adapters.py"},
            },
        )
        assert second.returncode == 2, "a relative path must resolve to the same section"
        assert "repos/mawtarx-connect" in second.stderr

    def test_workspace_root_docs_do_not_block_each_other(self, mod):
        """
        Every session edits DONE_TODAY.md. If root files shared one scope, the
        workspace repo would serialise all agents on its own bookkeeping.
        """
        assert hook(mod, edit_payload("agent-a", WORKSPACE / "DONE_TODAY.md")).returncode == 0
        assert hook(mod, edit_payload("agent-b", WORKSPACE / "AGENTS.md")).returncode == 0
        scopes = {
            lease.scope for lease in mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()
        }
        assert scopes == {"DONE_TODAY.md", "AGENTS.md"}

    def test_two_agents_on_the_same_root_doc_do_conflict(self, mod):
        assert hook(mod, edit_payload("agent-a", WORKSPACE / "DONE_TODAY.md")).returncode == 0
        assert hook(mod, edit_payload("agent-b", WORKSPACE / "DONE_TODAY.md")).returncode == 2

    def test_a_section_conflict_denies_immediately_without_waiting(self, mod):
        """
        A section lease lives until its session ends, so polling for it would
        just spend the whole timeout and deny anyway. Long XW_LEASE_WAIT here: if
        the wait ever comes back, this test takes 30s instead of failing quietly.
        """
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        assert hook(mod, edit_payload("agent-a", target)).returncode == 0
        started = time.monotonic()
        blocked = hook(mod, edit_payload("agent-b", target), env={"XW_LEASE_WAIT": "30"})
        assert blocked.returncode == 2
        assert time.monotonic() - started < 5, "must not poll a lease that outlives the turn"

    def test_paths_outside_the_workspace_are_ignored(self, mod, tmp_path):
        outside = tmp_path / "elsewhere.py"
        outside.write_text("x", encoding="utf-8")
        assert hook(mod, edit_payload("agent-a", outside)).returncode == 0


class TestMultiRepoAtomicity:
    """
    A shell line touching several repos must take all leases or none. Holding
    two of three blocks other agents while being useless to this one.
    """

    def test_multi_repo_merge_is_all_or_nothing(self, mod):
        """agent-a holds mawtarx; agent-b's 3-repo merge must acquire nothing."""
        assert hook(mod, bash_payload("agent-a", "git -C repos/mawtarx merge feat/x")).returncode == 0
        blocked = hook(
            mod,
            bash_payload(
                "agent-b",
                "git -C repos/mawtarx-api merge feat/x && git -C repos/mawtarx merge feat/x",
            ),
        )
        assert blocked.returncode == 2
        held = {
            (lease.holder, lease.resource)
            for lease in mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()
        }
        assert held == {("agent-a", "repos/mawtarx")}, (
            "mawtarx-api must not be left held by the failed acquire"
        )

    def test_disjoint_repo_sets_both_proceed(self, mod):
        first = hook(mod, bash_payload("agent-a", "git -C repos/mawtarx merge feat/x"))
        second = hook(mod, bash_payload("agent-b", "git -C repos/markibx merge feat/y"))
        assert (first.returncode, second.returncode) == (0, 0)

    def test_git_outside_the_workspace_is_ignored(self, mod, tmp_path):
        """The bash path needs the same workspace guard the edit path has."""
        outside = tmp_path / "other-project"
        (outside / ".git").mkdir(parents=True)
        result = hook(mod, bash_payload("agent-a", f"git -C {outside} reset --hard"))
        assert result.returncode == 0
        assert mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases() == ()


class TestMergeLeaseLifecycle:
    """
    Nothing but this releases a merge lease, and `Stop` refreshes it every turn --
    so a missing release means one `git merge` owns the repo for the whole session.
    """

    def test_merge_lease_is_dropped_once_git_reports_no_merge_in_flight(self, mod):
        assert hook(mod, bash_payload("agent-a", "git -C repos/mawtarx merge feat/x")).returncode == 0
        assert len(mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases()) == 1
        hook(
            mod,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "agent-a",
                "cwd": str(WORKSPACE),
                "tool_name": "Bash",
                "tool_input": {"command": "git -C repos/mawtarx merge feat/x"},
            },
        )
        # repos/mawtarx has no MERGE_HEAD, so the transition is over.
        assert mod.load_lease_module().LeaseRegistry(mod.LOCKS_DIR).leases() == ()

    def test_released_merge_no_longer_blocks_another_agent(self, mod):
        hook(mod, bash_payload("agent-a", "git -C repos/mawtarx merge feat/x"))
        hook(
            mod,
            {
                "hook_event_name": "PostToolUse",
                "session_id": "agent-a",
                "cwd": str(WORKSPACE),
                "tool_name": "Bash",
                "tool_input": {"command": "git -C repos/mawtarx merge feat/x"},
            },
        )
        allowed = hook(mod, edit_payload("agent-b", WORKSPACE / "repos/mawtarx/README.md"))
        assert allowed.returncode == 0, allowed.stderr


class TestFailurePolicy:
    """Asymmetric by design: an unprotected edit is cheap, an unprotected merge is not."""

    def test_broken_registry_fails_open_for_edits(self, mod):
        mod.LOCKS_DIR.mkdir(parents=True, exist_ok=True)
        (mod.LOCKS_DIR / "leases.json").write_text("{not json", encoding="utf-8")
        result = hook(mod, edit_payload("agent-a", CONNECT / "src/exonware/mawtarx_connect/runner.py"))
        assert result.returncode == 0
        assert (mod.LOCKS_DIR / "errors.log").exists(), "failing open must still be recorded"

    def test_broken_registry_fails_closed_for_destructive_git(self, mod):
        mod.LOCKS_DIR.mkdir(parents=True, exist_ok=True)
        (mod.LOCKS_DIR / "leases.json").write_text("{not json", encoding="utf-8")
        result = hook(mod, bash_payload("agent-a", "git -C repos/mawtarx-connect merge feat/x"))
        assert result.returncode == 2
        assert "XW_LEASE_OFF=1" in result.stderr

    def test_fail_closed_covers_destructive_git_only(self, mod):
        """
        Agreed policy is fail-closed for *destructive* git. A bare commit is an
        index op, so a broken registry must not block every commit in the box.
        """
        assert mod._is_destructive_payload(
            {"tool_input": {"command": "git -C repos/mawtarx reset --hard"}}
        ) is True
        assert mod._is_destructive_payload({"tool_input": {"command": "git merge feat/x"}}) is True
        assert mod._is_destructive_payload({"tool_input": {"command": "git commit -m x"}}) is False
        assert mod._is_destructive_payload({"tool_input": {"command": "git status"}}) is False

    def test_fail_closed_list_is_derived_not_hand_written(self, mod):
        """A second copy of the taxonomy drifts, and the fail-closed path falls open."""
        assert mod._FAIL_CLOSED_SUBCOMMANDS == mod.GIT_MERGE_OPS | mod.GIT_DESTRUCTIVE

    def test_off_switch_bypasses_everything(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        hook(mod, edit_payload("agent-a", target))
        result = hook(mod, edit_payload("agent-b", target), env={"XW_LEASE_OFF": "1"})
        assert result.returncode == 0

    def test_shadow_mode_logs_but_never_blocks(self, mod):
        target = CONNECT / "src/exonware/mawtarx_connect/runner.py"
        hook(mod, edit_payload("agent-a", target))
        result = hook(mod, edit_payload("agent-b", target), env={"XW_LEASE_SHADOW": "1"})
        assert result.returncode == 0
        logged = (mod.LOCKS_DIR / "decisions.log").read_text(encoding="utf-8")
        assert '"shadow": true' in logged and '"decision": "deny"' in logged

    def test_malformed_payload_never_blocks(self, mod):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "hook"],
            input="not json at all",
            capture_output=True,
            text=True,
            env={**os.environ, "XW_LEASE_DIR": str(mod.LOCKS_DIR)},
            timeout=60,
        )
        assert result.returncode == 0


class TestCli:
    def run_cli(self, mod, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env={**os.environ, "XW_LEASE_DIR": str(mod.LOCKS_DIR), "XW_LEASE_HOLDER": "cli-test"},
            timeout=60,
        )

    def test_claims_reports_nothing_when_idle(self, mod):
        assert "no leases held" in self.run_cli(mod, "claims").stdout

    def test_claim_then_claims_shows_it(self, mod):
        claimed = self.run_cli(mod, "claim", "repos/mawtarx", "--scope", "src", "--intent", "widen")
        assert claimed.returncode == 0, claimed.stderr
        listed = self.run_cli(mod, "claims").stdout
        assert "repos/mawtarx" in listed and "widen" in listed

    def test_claim_multi_repo_is_all_or_nothing(self, mod):
        assert self.run_cli(mod, "claim", "repos/mawtarx", "--kind", "merge").returncode == 0
        blocked = subprocess.run(
            [sys.executable, str(SCRIPT), "claim", "repos/mawtarx-api", "repos/mawtarx",
             "--kind", "merge", "--holder", "other"],
            capture_output=True, text=True,
            env={**os.environ, "XW_LEASE_DIR": str(mod.LOCKS_DIR)}, timeout=60,
        )
        assert blocked.returncode == 1
        held = self.run_cli(mod, "claims").stdout
        assert "mawtarx-api" not in held, "a failed multi-repo claim must hold nothing"

    def test_release_drops_them(self, mod):
        self.run_cli(mod, "claim", "repos/mawtarx", "--scope", "src")
        assert "released 1" in self.run_cli(mod, "release").stdout

    def test_steal_requires_a_reason_and_reports_the_victim(self, mod):
        self.run_cli(mod, "claim", "repos/mawtarx", "--scope", "src")
        lease_id = json.loads(self.run_cli(mod, "claims", "--json").stdout)[0]["id"]
        stolen = subprocess.run(
            [sys.executable, str(SCRIPT), "steal", lease_id, "--reason", "holder crashed"],
            capture_output=True, text=True,
            env={**os.environ, "XW_LEASE_DIR": str(mod.LOCKS_DIR), "XW_LEASE_HOLDER": "rescuer"},
            timeout=60,
        )
        assert stolen.returncode == 0
        assert "cli-test" in stolen.stdout

    def test_install_hook_print_is_valid_and_covers_all_three_events(self, mod):
        printed = json.loads(self.run_cli(mod, "install-hook", "--print").stdout)
        assert set(printed["hooks"]) == {"PreToolUse", "PostToolUse", "SessionEnd"}
        assert "Stop" not in printed["hooks"], "Stop fires every turn; it must not release"

    def test_install_hook_merges_and_is_idempotent(self, mod, tmp_path):
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        settings = home / ".claude" / "settings.json"
        settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        env = {**os.environ, "HOME": str(home), "XW_LEASE_DIR": str(mod.LOCKS_DIR)}

        def install():
            return subprocess.run(
                [sys.executable, str(SCRIPT), "install-hook"],
                capture_output=True, text=True, env=env, timeout=60,
            )

        assert install().returncode == 0
        first = json.loads(settings.read_text(encoding="utf-8"))
        assert first["theme"] == "dark", "existing settings must survive the merge"
        assert len(first["hooks"]["PreToolUse"]) == 1

        assert install().returncode == 0
        second = json.loads(settings.read_text(encoding="utf-8"))
        assert len(second["hooks"]["PreToolUse"]) == 1, "re-running must not double-register"

    def test_decide_records_a_verdict(self, mod):
        out = self.run_cli(mod, "decide", "repos/mawtarx", "src/a", "src/b", "allow")
        assert out.returncode == 0
        assert mod.recorded_decision(mod.decision_key("repos/mawtarx", "src/a", "src/b")) == "allow"
