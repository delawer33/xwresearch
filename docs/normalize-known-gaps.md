# markibx normalize.py — known gaps

Cross-repo note on `repos/markibx/src/exonware/markibx/normalize.py` (make/model
normalization, S1) and `normalize_data.py` (its dictionary). See
`repos/markibx/CLAUDE.md` and `repos/mawtarx/CLAUDE.md` for the repos this spans.

## The gap: per-make trim rules don't scale

`canonical_model()` collapses grade/trim suffixes ("Bentayga **Speed**", "C63
**AMG**") into a base model slug via `MODEL_TRIM_RULES` — a hand-written regex
list keyed per make. As of 2026-07-16 that table covers ~10 makes (Mercedes,
BMW, Audi, Lexus, Land Rover, Exeed, Chery, GWM, Toyota, and — after the fix
below — Bentley). Every other make gets **deterministic cleanup only**: casefold
+ strip punctuation, nothing else. A raw model string with a grade word baked
in ("Bentayga S", "Continental Flying Spur First Edition") slugs to its own
unique `model_norm` and never pools with its siblings.

This is silent and structural, not a one-off bug: it recurs for every make
someone hasn't yet written rules for, and it hits luxury/low-volume makes
hardest — exactly the segment with the fewest listings to begin with, so a
5-way split is often enough to starve every pricing tier of its 2-3 comp
minimum. `mawtarx-intelligence-audit.md` (2026-07-06) measured make/model
fragmentation moving ~36% of estimates; this per-make-rule gap is a live
contributor.

## What was fixed (quick, per-make)

2026-07-16: added Bentley-specific rules (`normalize_data.py`
`MODEL_TRIM_RULES["bentley"]`) collapsing Bentayga/Continental GT/Continental
Flying Spur grade suffixes to their base model. Verified against the live
local store (`repos/mawtarx-connect/mawtarx-data/xwdb-saudi-v2`): 45 Bentleys
went from 17 `model_norm` buckets down to 5 (21 `bentayga`, 12
`continentalgt`, 10 `continentalflyingspur`, plus 2 genuinely single-listing
models left as-is). Every previously-`insufficient_data` Bentayga/Continental
now prices at Tier 1-4 (confidence 61-79, 3-6 comps) instead of falling to the
Tier 6/7 floor.

This is the same shape of fix as the existing Chery/Exeed/GWM/Toyota entries —
low risk, but it only fixes the one make it targets. The dictionary will need
the same bespoke treatment for the next fragmented make someone notices (and
won't for the ones nobody's looked at yet).

## The systemic fix (not done — recommended next)

Replace the per-make regex table with a **general grade-token splitter**: a
single ordered list of known trim/grade words (S, Speed, V8, First Edition,
Black Edition, Super Sport, AMG, GT, Plus, Pro, Luxury, …) that `canonical_model()`
strips from the *end* of any slugified model string, for *any* make, writing
the stripped remainder into `trim` when the listing didn't already carry one
explicitly. This would fix Bentley and every future luxury/low-volume make in
one pass instead of a bespoke regex per make per bug report.

Design questions worth resolving before building it (flag for whoever picks
this up, not resolved here):
- **Token list provenance** — mined from the live corpus (rank suffix tokens
  that appear after a recognized base model across many makes) vs.
  hand-curated, per D3's "LLM only offline to bootstrap" precedent.
- **False-positive risk** — a base model that legitimately ENDS in a token on
  the list (e.g., a model literally named "S" or "GT") must not get stripped
  to nothing; needs a per-make allowlist/denylist, not a blind global strip.
- **Trim field backfill** — for makes where `trim` is already populated
  separately from `model`, stripping a token from `model` and duplicating it
  into `trim` needs a collision rule (keep existing `trim`? overwrite? merge?).
- **Interacts with `catalog_link.py`** — a model split that changes
  `model_norm` also changes what a listing catalog-links to in markibx; the
  splitter needs to run through the same D2c re-link path as any other
  normalize.py change (`store.renormalize()` isn't enough on its own, per the
  backfill-mechanics note below).

## Applying a `MODEL_TRIM_RULES` change to already-stored data

`_recompute_norm()` (mawtarx `store.py`) is the D2c enforcement point — it only
runs inside `upsert()`, deliberately NOT at read/hydrate time, so a rule
change is invisible on already-stored rows until they're next re-scraped
(self-heal, by design). To apply a rule change immediately instead of waiting
on the next scrape cycle:

- **Postgres**: `backfill_make_model_norm.py` (batched `UPDATE`, builds the
  index after). Postgres-only — does not apply to the xwjson/xwstorage-db
  store this ecosystem actually runs on in prod (`../../CLAUDE.md`).
- **Any store (xwjson, xwstorage-db, in-memory)**: `IVehicleStore.renormalize()`
  (added 2026-07-16, `store.py` + the `XwJsonVehicleStore`/
  `XwStorageDbVehicleStore` overrides in `store_xwstorage.py`) — recomputes
  every resident listing's `make_norm`/`model_norm`, reindexes the moved
  ones, and persists only the rows that actually changed bucket (NOT every
  row — `XwStorageDbVehicleStore`'s `engine.update()` rewrites the whole
  collection file per call, so persisting all 7,508 rows to fix 20 would
  multiply an O(n) full-collection rewrite by n). CLI: `mawtarx renormalize
  --store <path>`.

**Caution on a live/prod box**: each changed row's persist is a full
collection-file rewrite, and xwjson's atomic writer defaults to keeping a
`.backup.<timestamp>` copy on every write (`backup=True` in
`exonware.xwjson`'s `save_file`/`AtomicFileWriter`) — so N changed rows costs
roughly `2 × N × collection_file_size` in disk churn, not `2 × collection_file_size`
once. Confirm free disk headroom covers that before running `renormalize` against
a large store; a near-full disk mid-run can throw `OSError: [Errno 28] No space
left on device` (hit once during this fix's verification — no data was lost,
the atomic writer never touches the live file until the new one is fully
written, but it's worth budgeting for rather than discovering live).
