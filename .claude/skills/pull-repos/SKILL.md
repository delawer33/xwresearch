---
name: pull-repos
description: >
  Sync the ecosystem's independent repos under repos/ from their remotes and report exactly
  what landed. Use whenever the user says "pull", "pull the repos", "pull changes", "pull the
  latest", "sync the repos", "update the repos", "fetch", or names repos/families to pull
  (e.g. "pull kara/mawtarx/markibx") — and before ANY analysis of what code does, exists, or
  is adopted.
---

# Pull repos

Every subdir of `repos/` is its **own independent git repo** (`repos/` is gitignored by
xwresearch). There is no single `git pull` for this workspace. Skipping one repo, or reading a
stale one, produces confident wrong answers — that is not hypothetical, see "Why this exists".

## Rule 0 — "pull" means fetch+merge, always

"Pull the commits for X" is **ambiguous**: it can mean *show me the log* or *get the latest*.
**Always do the fetch+merge first, then show the log.** Never answer a "pull" request with
`git log` alone against an unsynced checkout. If the user only wanted the log, they lose
nothing; if they wanted the sync and you skipped it, everything downstream is wrong.

## 1. Expand the target set — never trust the prefix

A named family means **every repo in it**, and the prefixes are inconsistent:

| User says | Actually covers |
|---|---|
| `kara` / `karaa` | `kara`, `kara-api`, `kara-connect`, `kara-web`, **`karaa-connect-api`** (note the double-a — `ls repos/kara*` **misses** it) |
| `mawtarx` | `mawtarx`, `mawtarx-api`, `mawtarx-connect`, `mawtarx-connect-api`, `mawtarx-web` |
| `markibx` | `markibx`, `markibx-api`, `markibx-connect`, `markibx-connect-api`, `markibx-web` |
| "everything" / unscoped | every dir in `repos/` with a `.git` (~40, including `xw*`) |

Glob both spellings: `ls -d repos/kara* repos/karaa*`. When unsure whether a repo belongs, include
it — a needless fetch costs nothing.

## 2. Fetch + report status for EVERY repo before merging

**The shell here is zsh — it does NOT word-split `$var` like bash.** `for r in $targets` runs
once with the whole list as one string. Pipe into `while read` instead (works in both shells):

```bash
cd <xwresearch-root>/repos
ls -d kara* karaa* mawtarx* markibx* 2>/dev/null | grep -vE "data|_bup" | sort -u |
while IFS= read -r r; do
  [ -d "$r/.git" ] || { printf "  ?? %-22s NOT CLONED\n" "$r"; continue; }
  git -C "$r" fetch --quiet origin 2>/dev/null
  b=$(git -C "$r" rev-list --count HEAD..origin/main 2>/dev/null)
  a=$(git -C "$r" rev-list --count origin/main..HEAD 2>/dev/null)
  d=$(git -C "$r" status --porcelain | wc -l)
  note=""
  [ "$b" != "0" ] && [ "$a" != "0" ] && note="  <- DIVERGED, do not merge"
  [ "$b" != "0" ] && [ "$a" = "0" ]  && note="  <- will fast-forward"
  printf "  %-22s behind=%-4s ahead=%-4s dirty=%-3s%s\n" "$r" "$b" "$a" "$d" "$note"
done
```

(An explicit `arr=(a b c)` array also works in both. Never `for r in $unquoted_var`.)

Print this table. **Every repo gets a line, including the up-to-date ones** — a silent repo is
indistinguishable from a skipped one.

## 3. Merge, and classify what you can't merge

- **behind>0, ahead=0** → `git -C "$r" merge --ff-only origin/main`. Dirty files survive a
  fast-forward; leave them.
- **ahead>0 and behind>0 (diverged)** → **do not merge, do not rebase.** Report it and stop on
  that repo. Someone has unpushed local commits (`git log origin/main..HEAD`); resolving that is
  the user's call, not yours.
- **dirty** → fast-forward is still safe. If it fails (local edits to files the merge touches),
  report it — don't stash or discard someone's work without asking.
- **NOT CLONED** → the repo may exist and be live. Check:
  `git ls-remote https://github.com/Exonware/<name>.git` — if it resolves, offer to clone it.

## 4. Report what actually landed

For each repo that moved: `git -C "$r" log --oneline <old>..<new>`. Summarize the *substance*,
not the count — "kara-api migrated all routes to XWActionRouter" beats "14 commits".

Then say plainly: **any analysis from before this sync is void.** If the session already made
claims about what exists / is used / is adopted, re-derive them.

## 5. Missing-repo sweep (when pulling "everything" or before a completeness claim)

The workspace does **not** guarantee it mirrors production. Cross-check the repo list against
`ARCHITECTURE.md`'s table and `docs/vps-current-state.md`'s services. An absent repo looks
exactly like a nonexistent feature.

## Why this exists

On 2026-07-17 the user asked to "pull all the commits for mawtarx/markibx/kara". The agent read
"pull" as "show me the log", ran `git log` on unsynced checkouts, and never fetched. The whole
session then rested on it and published a false claim — "`@XWAction` has zero production routes"
— while kara-api (14 commits behind) had already migrated its entire route layer to it, and
`karaa-connect-api` (never cloned, invisible to `ls repos/kara*`) had been serving XWAction in
production for weeks. Three traps, one root cause: **nobody fetched.**
