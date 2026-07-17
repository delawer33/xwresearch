# CLAUDE.md

## Read before you act

This file is calibration, not the map. It is the only doc loaded automatically — everything
below is a hard trigger, not a suggestion:

| Before you…                                                            | Read                                                                              |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| …reason about what exists, what's live, or what talks to what          | **`ARCHITECTURE.md`**                                                             |
| …write or change **any** code                                          | **`AGENTS.md`** (the loop + conventions)                                          |
| …write **any** utility, helper, or client                              | **`docs/tool-index.md`** — it probably already exists                             |
| …claim _why_ something is the way it is, or reverse a design           | **`DECISIONS.md`**                                                                |
| …use a term you can't define (`catalog_key`, `dedup_key`, `make_norm`) | **`docs/glossary.md`**                                                            |
| …touch a specific repo                                                 | that repo's own **`CLAUDE.md`** — truth for that repo, and it carries the gotchas |

## What this workspace is

`repos/` holds ~30 **independent git repos**. Two worlds: the **karaa** car product (live, in
active development) and the **xw\*** platform libraries it's built on. Map: `ARCHITECTURE.md`.

## How to think here

**The defining property of this ecosystem: the code overstates itself and the docs lag.**
Every rule below is a scar, not a slogan — each one has a real corpse behind it.

1. **Code existing is not proof it's live.** Registered connectors don't run. Whole API
   surfaces are stubs nothing calls. Much of markibx/mawtarx is scaffold. Before you call
   anything load-bearing, find the caller.

2. **A doc's claim is a hypothesis until you check the code.** Verify with imports and
   `git log -S`, not with README prose.

3. **A name is not a guarantee.** `xwstorage-connect`'s `EncryptionAtRest` advertises
   AES/Fernet in its enum and is **XOR**. `xwstorage`'s repo folder, pip name, and import path
   are three different strings. Read the implementation.

4. **Local ≠ production.** Your laptop's data and the server's differ a lot — never reason
   about prod from your local store.

5. **Reuse before you build.** 18 platform libraries already exist and 10 of them are unused —
   the gap is discovery, not capability. `docs/tool-index.md` before any utility. If you're
   about to write HMAC, a parser, a graph, or a deep-merge, you're about to duplicate
   something.

6. **Never launder a guess into an answer or a doc.** Say "unverified," or go check. One
   wrong fact in a shared doc misleads every future agent — that's how the pre-split root docs
   rotted, and cleaning it up cost more than writing it right would have.

7. **Report what's true, including when it's unflattering.** "Benchmarked but unadopted" beats
   "it's fast now." "Tests fail, here's the output" beats silence. The value you add is being
   right, not being reassuring.

## When in doubt

Ask. A blocked question costs a message; a confident wrong answer costs the next agent an
hour and may reach production. If a fact hinges on code you're unsure is real or current,
**verify it or say so** — do not guess.
