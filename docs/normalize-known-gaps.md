# markibx normalize.py — known gaps

Cross-repo note on `repos/markibx/src/exonware/markibx/normalize.py` (make/model
normalization, S1) and `normalize_data.py` (its dictionary). See
`repos/markibx/CLAUDE.md` and `repos/mawtarx/CLAUDE.md` for the repos this spans.

Two independent gaps live here: model-side **fragmentation** (one real model → many slugs) and
make-side **collision** (two real makes → one slug). Fragmentation starves pricing comps;
collision merges unrelated cars under a confident-looking `resolved=True`.

## Gap 1: per-make trim rules don't scale

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

## Gap 2: fuzzy make-matching silently aliases an UNKNOWN make onto a known one

Measured 2026-07-27 against the same store. `canonical_make("FAW")` returns
`MakeResult(slug="baw", resolved=True, score=0.9)` — FAW is **absent** from
`MAKE_CANONICAL_SLUGS`/`MAKE_ALIASES`, BAW is present, and Levenshtein("faw","baw") == 1, so
`FUZZY_AUTO_APPLY_DISTANCE = 1` auto-applies it. Result in live data: 60 rows under
`make_norm="baw"`, of which **55 are FAW Bestune** and only 5 genuine BAW. Two different Chinese
manufacturers merged, and `resolved=True` means nothing downstream flags it.

**Why this is a class of bug, not one entry to add:** distance-1 auto-apply is scale-free but
make slugs are not. For a 3-character make one edit is a third of the string, and 18 canonical
slugs are ≤ 4 chars (`baw bmw byd gac gmc gwm jac kia mg ram rox seat audi fiat ford jeep mini
opel`). **Any short make missing from the dictionary can be captured by a near neighbour at
`score` 0.9** — and the score is *derived from edit distance* (`1.0 - d/10`), so it reads as high
confidence precisely when it's least trustworthy. The fix is not "add FAW": it's to make the
auto-apply threshold **length-aware** (require a relative distance, not an absolute one) or refuse
auto-apply below some slug length, and add FAW as a canonical make. Everything needed to see this
is already logged — `make_normalize.fuzzy_candidate … auto_applied=True` fires on every hit, so
the log has been recording this the whole time.

Two related things the same measurement showed, both *not* mis-resolutions — these fall through
to `resolved=False` and pass through as-is, which is the honest behaviour:

- **Arabic-script names don't transliterate.** `canonical_make("تويوتا")` → slug `تويوتا`,
  unresolved. So `تويوتا/كورولا` ranks as a separate make·model from `toyota/corolla`. Latin-side
  variants split the same way (`mg:5` vs `mg:mg5`, `bmw:5series` vs `bmw:520i`), and mixed-script
  input mangles (`patrolربع`, `hs5deluxeتوwd`).
- **Test/junk makes pass through** (`zzperf`, `zzsold`, `zzr2`, `zzs4`, `zztest`) — 310+ rows in
  the store. Consumers must exclude `zz*` themselves; nothing upstream does.

⚠️ **Where the fix goes:** `repos/markibx`'s `normalize.py` + `normalize_data.py` (this doc's
subject), NOT `mawtarx-connect`. The connectors don't normalize; mawtarx's
`store.py::_recompute_norm()` calls markibx on `upsert()` (see below). Easy to get wrong — a
scraped-data bug intuitively feels like a scraper bug.

**Blast radius if you change `canonical_make`:** markibx's own catalog **spine seed** ids are
derived from `make_norm` (`repos/markibx/.../data/spine_seed/`, 45 makes / 222 models, ranked from
this very store). Re-resolving FAW off `baw` changes seed ids and what incoming listings link to,
so it must go through the D2c re-link path *and* a seed re-run together — see that seed's
`README.md`, which documents the `baw`=FAW case for exactly this reason.

## Applying a `MODEL_TRIM_RULES` change to already-stored data

`_recompute_norm()` (mawtarx `store.py`) is the D2c enforcement point — it only
runs inside `upsert()`, deliberately NOT at read/hydrate time, so a rule
change is invisible on already-stored rows until they're next re-scraped
(self-heal, by design). To apply a rule change immediately instead of waiting
on the next scrape cycle:

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
