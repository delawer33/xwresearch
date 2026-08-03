# CLAUDE.md

## STOP — writing code? read first

"implement" / "write code" / "add this" / "fix this" / "quick change" → before your first
`Edit`/`Write`: **`AGENTS.md`, `ARCHITECTURE.md`, target repo's `CLAUDE.md`.** Urgency is not
an exemption. Then open with one line: what you read, what it changed. No line = you skipped it.

## Read before you act

Calibration, not the map. This is the only doc loaded automatically — the table is a hard
trigger, not a suggestion:

| Before you…                                                            | Read                                                                   |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| …plan, grill, or design **any feature** (before designing behaviour)   | ask the layer question **xw > product > project** and **record the answer** — does this belong in an `xw*` package first? (cascade: **`AGENTS.md` §2**) |
| …reason about what exists, what's live, or what talks to what          | **`ARCHITECTURE.md`**                                                  |
| …write or change **any** code                                          | **`AGENTS.md`** (the loop + conventions)                               |
| …write **any** utility, helper, or client                              | **`docs/tool-index.md`** — it probably already exists                  |
| …claim _why_ something is the way it is, or reverse a design           | **`DECISIONS.md`**                                                     |
| …use a term you can't define (`catalog_car_id`, `dedup_key`, `make_norm`) | **`docs/glossary.md`**                                              |
| …touch a specific repo                                                 | that repo's own **`CLAUDE.md`** — truth for that repo, and its gotchas |
| …claim code works, or that something is broken                         | run it: **`task doctor`** then **`task test`** (root `Taskfile.yml`)   |

## Verify by running, not by reading

Every product repo now has a `Taskfile.yml`. From the root: **`task test`** runs all twelve
Python suites and prints one pass/fail table; **`task doctor`** checks the shared
`repos/.venv` still resolves every `exonware` package. Inside a repo, `task test` and
`task test -- tests/test_foo.py`.

**A collection error is an environment fault, not a test failure** — and the two look
identical in a bare pytest tail. When libraries move their source (xwapi, xwstorage, xwbase
et al. moved `src/` → `ports/python/src/` on 2026-07-23) the editable installs keep pointing
at the old directories, which still exist and import as empty namespace packages. Symptom:
`ImportError: cannot import name X from exonware.Y (unknown location)` everywhere at once.
`task doctor` names the stale packages; **`task venv` repairs them.** Run doctor after every
`/pull-repos`.

`task ci:local -- <repo>` reproduces the whole CI job in ~60s. Before writing any env, venv, or
CI helper, read **`docs/tool-index.md`'s "Workspace tooling"** — it also records why a plain
`pip install -e .` can never work here.

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
   when that's cheaper than reading.

3. **Local ≠ production.** Your data and the server's differ a lot — never reason about prod from
   your local store.

4. **Reuse before you build.** ~18 platform libraries exist and about half are unwired — the gap
   is discovery, not capability. `docs/tool-index.md` before any utility. If you're about to
   write HMAC, a parser, a graph, or a deep-merge, you're duplicating something.

5. **Say only what you checked.** "Unverified" is a fine answer; a confident wrong one costs the
   next agent an hour and can reach production. Scope the claim: "no route _in the repos I
   synced_ uses it" — not "it has zero production routes." One wrong fact in a shared doc
   misleads every agent after you.

## Talking to me and reporting

-When reporting information to me, be extremely concise and sacrifice grammar for the sake of concision.
