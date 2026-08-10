# Done today — 2026-08-10

## markibx/mawtarx audit — measured the catalog link's false precision, filed 3 tiered issues

- Measured against the real 8,315-row corpus that the `catalog_car_id` ladder reports `exact` for 5,078 of 5,721 matches (88.8%) that land on catch-all `gen1`/QID shells, 50.8% of them spanning ≥10 years (`hyundai:accent:gen1` = 2006–2026, `toyota:landcruiser:j70` = 42y), so a 2006 and a 2024 Accent share one spec sheet and one MSRP baseline — the linker itself is sound at 91.8% on resolvable rows.
- Reframed spec depth from a 1,623-generation problem to a ~120-generation one: all 5,721 exact matches land on 260 generations, 103 cover 80% of demand, and 122 of the 260 carry no spec (43.6% of real listings could show a spec sheet).
- Filed [delawer33/xwresearch#36](https://github.com/delawer33/xwresearch/issues/36) (verification holes, open auth gates, unguarded writes, misleading docs), [#37](https://github.com/delawer33/xwresearch/issues/37) (false precision, overstated product knowledge), [#38](https://github.com/delawer33/xwresearch/issues/38) (zero-dep doctrine conflict, forked platform types, inverted xwapi ownership) — problems only, no remedies.
- Proved pre-existing breakage so the next agent doesn't re-debug it: 16 failed / 2,843 passed / 20 skipped across both families, with markibx `main` committed-red at 8 failures on a clean tree, and `Taskfile.yml:89-91` scoring zero-collected-tests as a pass (which is why `markibx-connect-api`'s 1,037 LOC including `auth.py` reports clean); also established authoritative connector counts by importing the registry — 245 registered / 137 ACTIVE / 14 prod-swept, against 671/86/~7 in the docs.
- Deliberately changed no code and closed no issues; corrected three of my own audits' claims that failed verification (spine browse is not broken — only `year_source` is None; the two connect repos do not duplicate each other; there are exactly 14 declared-synthetic sources).

**Left open**

- All of #36/#37/#38 — recommended Tier 1 sequencing is: prune worktrees, then the Taskfile exit-code fix alone (nothing else is verifiable until it lands), then auth + store-integrity + docs in parallel, then the stale tests last.
- Whether `MAWTARX_JWT_SECRET`/`MARKIBX_JWT_SECRET`/`MAWTARX_ADMIN_TOKEN` are actually set on the dev box is unverified — `/etc/*.env` is root-owned; both APIs default to a hardcoded literal with no boot guard, and only karaa's deploy generates one.
- 7 fully-merged worktrees under `repos/*/.claude/worktrees/` (~40MB, none gitignored) still make every grep return 3 contradictory copies — this corrupted two of my own audit agents' counts; `worktrees/mawtarx-coverage` holds 1 genuinely unmerged commit.
- Another session is implementing #36's atomic-write item right now (new `markibx/src/exonware/markibx/atomic_io.py` + the six write sites); it touches `spine_seed_writer.py`, which is also where #37's `origin`-drop fix lands — conflict to coordinate.
- `markibx-web` still holds 9 unpushed commits of finished spine-console work behind a 403 push wall.
