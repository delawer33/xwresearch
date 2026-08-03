# Done today — 2026-08-03

## markibx structural-soundness pass — all slices #39–#46 implemented, closed, deployed

Ran the whole #38 plan-of-record in one day via parallel opus subagents (I reviewed,
committed, closed). Commits: markibx 709b20b + 30ff4f9, markibx-connect 80872a3 + f44aacc +
a71c092 + ac48992, mawtarx ac55608.

- **#39 audit script** (`markibx-connect scripts/audit_demand_coverage.py`): fresh-scp-pull
  acceptance test, classifier verified two independent ways (92.15% row agreement + 40/40
  hand sample). Live-store truth is worse than the local audit said: **66.4% resolve, not
  77.4%** — 1,921 yearless opensooq rows + dubizzle (absent locally) depress it; upstream
  mawtarx-connect gap, not membership. Demand worklist: 244 nameplates = 80% of volume.
- **#40 soundness gate**: 3 rules (year overlap / nameplate-year bleed >30y / shell
  shadowing) wired into `validate_seed`, known offenders grandfathered in a committed
  allowlist meant to shrink — and it did: **29 → 13** by end of day.
- **#41 root cause of the gen1 collapse**: the widening reached Wikidata through ONE
  predicate (`P31 car-model ∧ P176 manufacturer`); gen entities without P176 (Elantra HD)
  and "model series"-typed hubs (Accent, Patrol) were invisible — Camry split by labeling
  luck. New 5-mechanism extractor; dry run over all 244: **23 splittable / 175 residue**.
  Accent/Sonata/Fortuner/Versa have NO generation entities upstream at all → LLM-umbrella
  work, measured not assumed.
- **#42/#43 fill + aliases**: +54 makes / +1,392 models / +1,452 shells via the widening
  ingest (45 verified QID pins), 19 Arabic make aliases + ~50 model rules. Make-miss
  **5.3% → 0.14%**. Model-miss target missed (12.8% vs ~6%): root cause is the identity
  query rejecting `Q59773381` series-typed nameplates (audi arrived as a4b5…b9 fragments,
  no `audi:a4`) — filed #47.
- **#44 splits (ADR 0013)**: 13 catch-alls retired, 55 source-anchored gens minted across
  23 nameplates; shell-pinned facts dropped, not migrated. Demand-head LOCAL-GEN-1
  resolves **563 → 0**; corpus resolve dipped 66.4→61.9 — the honest degradation the ADR
  defends. The 134→~500 real-OEM-code target is unreachable from Wikidata (labels are
  prose); structural goal holds, code-count metric doesn't.
- **#46 year hygiene**: +58 dated gens, 21 proven-bad ranges withdrawn (label-equality is
  the wrong Wikidata guard — all six Mustang gens are labelled "Ford Mustang"; series-edge
  is the discriminator). Found+fixed a parse bug: WDQS dates lack the leading `+`, so
  P580/P582 parsed 0/38 — same bug latent in wikidata_generations.py (chip filed).
- **#45 deploy + relink**: markibx 30ff4f9 shipped to both VPS venvs, 3 services restarted
  and verified live (Camry 2019→XV70, Audi resolves). Dev store: renormalize re-bucketed
  638 rows; catalog-link --relink + top-up → **18,189 / 87.2% linked** (12,721 exact-year,
  4,098 honest model-level). Runbook: `mawtarx docs/runbook-catalog-relink.md`.

Ops lessons paid for in wall-clock: full `--relink` takes 2m05 on 20k rows and **overruns
the 2-min watchdog window** — the service's post-restart flush ate ~900 links; always chase
with a no-`--relink` top-up pass (40s, fits). And `pip --force-reinstall` does NOT remove
files hand-copied into a venv outside pip's RECORD — both VPS venvs still serve the 13
retired gen files (5,270 gens vs 5,257), so ~404 listings still resolve to retired shells.

## Left open

- **#49**: clean-reinstall exonware-markibx in both VPS venvs (one human command — remote
  file deletion is classifier-blocked for me); then run `/tmp/relink_dangling.py` (staged on
  the box) in a watchdog window to relink the ~404 shell rows.
- **#47**: series-typed nameplate fix in the widening identity query — the biggest remaining
  curatable model-miss block (audi 134 rows). #48: `baw` make mixes BAW and FAW Bestune.
- markibx-connect ~400 `__unknown__` + 698 `Other` parse-failure rows: upstream ticket still
  not filed (declared out of scope in the PRD as "filed separately").
- Next umbrella: the LLM depth engine — GCC money facts first, then the 175-nameplate
  `needs-generation-split` residue + 17 `needs_year_range`.
