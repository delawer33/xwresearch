# Make/Model Normalization (S1) — Summary

**Status:** Done, tested, committed. Ready to review.
**Branches:** `s1-make-model-normalization` in both `markibx` and `mawtarx`.
**Scope:** mawtarx + markibx only. Does **not** touch dedup/merge (later phase).

## The problem

Car makes/models were matched as raw text, so `Mercedes Benz`, `Mercedes-Benz`,
and `Mercedes` were **three different brands**. Pricing compared each car only
against its own spelling group — smaller, wrong pools — giving confident-but-wrong
estimates (the audit measured ~36% of premium estimates moving >5%). The same
bug hit fraud checks, market liquidity, and search.

## What we did

1. **One normalizer** (`markibx.canonical_make` / `canonical_model`): dictionary
   of ~60 brands + accent folding (`Škoda`→`skoda`) + emoji/punctuation strip +
   1-letter-typo auto-fix. Keeps non-Latin scripts (Cyrillic/Arabic) as their own
   slug instead of blanking them.
2. **Two stored columns** (`make_norm`, `model_norm`) on every listing.
3. **One enforcement point:** the store recomputes them on every write, so data
   can't drift and old rows self-heal on their next scrape.
4. **Switched every matcher** — pricing, fraud, market, search, catalog linking —
   to the clean key.
5. **Backfilled all 141k rows** and added the index.

## Results (measured on the real 141k database)

| | Before | After |
|---|---|---|
| Listings on a clean, known brand | — | **96.3%** |
| Mercedes spellings | 7 pools | 1 pool |
| Comparable pool size (Mercedes sample) | ~23 | ~59 |
| Unidentifiable rows | — | 58 (0.04%, pure emoji/symbol names) |

Pricing now reaches its highest-confidence tier on cars that used to fall to weak
fallbacks; fraud no longer flags a fair car for having differently-spelled peers.

## Critical review + refactor (this pass)

Reviewed the first cut and fixed what was wrong:

- **Real bug found & fixed:** the SQL search and in-memory search normalized a
  *model-only* query differently, so the same filter could match in one and not
  the other. Both now share one helper (`search_norm_keys`) — they can't diverge.
- **Non-Latin makes** were collapsing to blank (Cyrillic/Arabic). Fixed the
  slugifier to keep any script; re-ran backfill (blank makes 124 → 58, all now
  genuine emoji-only junk).
- **Consistency:** catalog linking now keys on the canonical make slug like
  pricing does, so a listing spelled "Mercedes" links to the "Mercedes-Benz"
  catalog entry (smoke-test link rate 88% → 100%).
- **De-duplicated** the enforcement helper so both stores share one copy.

## Testing

**129 tests pass, zero regressions** (40 new, written before the code / TDD).
Ran the real pricing/fraud/market/catalog engines end-to-end as a smoke test.

## What's next (not done here, on purpose)

- **Dedup/merge switch** — the risky part (collapses duplicate rows). Separate
  phase, gated on a dry-run safety check.
- **Scraper data quality** — the leftover ~3.7% unresolved is mostly (a) real
  brands the ~60-list doesn't have yet (Dacia, Cupra, Daewoo…) and (b) a couple of
  connectors (`bazos.cz/sk`) dumping title text into the make field. Both are data/
  connector work, not code: grow the dictionary, add a title-recovery fallback for
  the 2-3 bad connectors, and question whether non-Saudi sources belong at all.

## Where to look

- Code: `markibx/normalize.py`, `markibx/normalize_data.py` (the dictionary),
  `mawtarx/store*.py`, `pricing.py`, `fraud.py`, `market.py`, `catalog_link.py`.
- Migration + backfill: `mawtarx/migrations/007_make_model_norm.sql`,
  `mawtarx/backfill_make_model_norm.py` (run once on deploy — idempotent, also
  builds the index).
- Full technical write-up: `mawtarx-normalization-report.md`.
- Design decisions: `mawtarx-normalization-plan.md`.
