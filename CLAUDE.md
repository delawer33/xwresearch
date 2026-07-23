# CLAUDE.md

## Read before you act

Calibration, not the map. This is the only doc loaded automatically — the table is a hard
trigger, not a suggestion:

| Before you… | Read |
| --- | --- |
| …reason about what exists, what's live, or what talks to what | **`ARCHITECTURE.md`** |
| …write or change **any** code | **`AGENTS.md`** (the loop + conventions) |
| …write **any** utility, helper, or client | **`docs/tool-index.md`** — it probably already exists |
| …claim *why* something is the way it is, or reverse a design | **`DECISIONS.md`** |
| …use a term you can't define (`catalog_key`, `dedup_key`, `make_norm`) | **`docs/glossary.md`** |
| …touch a specific repo | that repo's own **`CLAUDE.md`** — truth for that repo, and its gotchas |

## What this workspace is

`repos/` holds ~40 **independent git repos**. Two worlds: the **karaa** car product (live, in
active development) and the **xw\*** platform libraries it's built on. Map: `ARCHITECTURE.md`.
It's a slice of the company, not all of it — `xwui` licensing, `aqarx`, `opsx`, `maalx` and
friends are real and live outside this checkout.

## Company priority (weigh every task against this)

**Technology (`xw*`) > Products (`markibx`/`mawtarx`) > Projects (`kara`/client repos)** —
strategic weight, not delivery urgency. When they conflict: architecture/design calls go by
priority; weekly delivery goes by urgency (kara carries real deadlines despite being P3). Before
picking up work, ask which layer it's really in — "due this week" and "strategic" are different
axes, and it's easy to spend a month entirely in P3 without noticing.

## How to think here

**The code overstates itself and the docs lag.** Each rule below has a real corpse behind it.

1. **Code and names lie.** Registered connectors don't run. Whole API surfaces are stubs nothing
   calls. `xwstorage-connect`'s `EncryptionAtRest` advertises AES/Fernet and is **XOR**. Find the
   caller; read the implementation.

2. **Verify against synced code, not prose.** A doc's claim is a hypothesis until you check.
   Repos go stale, live repos go missing from `repos/`, deleted files linger on disk — each looks
   exactly like "this doesn't exist." Run **`/pull-repos`** first, and check the running server
   when that's cheaper than reading. **What _runs_ in prod (daemons/cron/workers) is invisible to
   `grep src/`** — a systemd-launched worker imports into nothing. Check `deploy/*.service`,
   `pyproject.toml [project.scripts]`, `docs/vps-current-state.md`; treat "no daemon / nothing
   runs" as a claim to _falsify_, not a fact. (A live scraper daemon was missed exactly this way.)

3. **Local ≠ production.** Your data and the server's differ a lot — never reason about prod from
   your local store.

4. **Reuse before you build.** ~18 platform libraries exist and about half are unwired — the gap
   is discovery, not capability. `docs/tool-index.md` before any utility. If you're about to
   write HMAC, a parser, a graph, or a deep-merge, you're duplicating something.

5. **Say only what you checked.** "Unverified" is a fine answer; a confident wrong one costs the
   next agent an hour and can reach production. Scope the claim: "no route *in the repos I
   synced* uses it" — not "it has zero production routes." One wrong fact in a shared doc
   misleads every agent after you.
