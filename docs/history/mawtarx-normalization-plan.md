# Mawtarx Make/Model Normalization (S1) — Design & Decisions

Working doc for the S1 fix from `mawtarx-intelligence-audit.md` (the highest-ROI
finding: un-normalized make/model spelling fragments comparable pools and silently
shifts ~36% of premium-brand estimates >5%). Captures decisions as we grill them.

## Problem recap
Pricing (`same_mm`), dedup (`compute_listing_dedup_key`), and `comparables_for`'s SQL
all match make/model on raw strings via `casefold()` only. Scraped data is not
normalized → `Mercedes Benz` / `Mercedes-Benz` / `Mercedes` are 3 non-matching pools;
`VW` vs `Volkswagen`; emoji makes (`🚀Volksvagen`) match nothing. 1,139 distinct makes
for a ~60-make market.

## Decisions (all grilled & agreed)
- **D1 (where/when):** Plan **A** — persist canonical columns (`make_norm`,
  `model_norm`) at ingest; keep raw `make`/`model` for display/audit. Index moves to
  `(make_norm, model_norm)`.
  - **CORRECTION (2026-07-06):** the original D1 listed only 3 matchers (pricing
    `same_mm`, `comparables_for`, `dedup_key`). There are **~9 read sites** that match/
    group make+model on raw strings — all must switch, or the fragmentation bug just
    relocates into another engine. The phase line is **read/grouping (Phase 1) vs
    identity/merge (Phase 2)**, NOT "pricing vs rest". Full inventory:
    - `pricing.py:84` `same_mm` — pricing pools → **Phase 1**
    - `store_pg.py:359` `comparables_for` SQL — pricing/fraud pool → **Phase 1**
    - `store_pg.py:436` `peer_prices` — **fraud** `_check_suspicious_price` → **Phase 1**
      (else a fair car gets flagged SUSPICIOUS_PRICE; deal_score+fraud shown together)
    - `fraud.py:206` `o.make.casefold()==` — fraud source/dup check → **Phase 1**
    - `market.py:89` `supply_for` — liquidity/supply count → **Phase 1**
    - `store_pg.py:398` `top_makes` GROUP BY make — admin KPI **and the D7
      "1,139→60" metric is computed here** → **Phase 1** (else D7 is unmeasurable)
    - `store.py:176/181/226/230` — in-memory store mirrors (test + no-DSN fallback in
      `state.py`) → **Phase 1** for parity
    - `types.py:852` `VehicleSearchFilter.matches` — user-facing search filter →
      **Phase 1**, but as *query-side* normalization (normalize the user's input
      through the same function), not a column swap
    - `dedup.py compute_listing_dedup_key` — identity/merge → **Phase 2 only**
      (the one destructive site; triggers row collapse)
    - `catalog_link.py` `link_listings_to_catalog` — has its OWN ad-hoc `_norm()` +
      model alias/trim-rule tables, independent of both pricing and the future
      shared normalizer → **Phase 1**, merged per **D4b** (not a plain column swap;
      the alias data moves into the shared source, `_norm()` retired)
- **D2 (owner):** **markibx owns the alias map** (`VehicleMake.aliases: list[str]`
  confirmed in `model.py:108`). **Correction (2026-07-06):** only the *schema*
  exists — there is no resolver (`catalog.py` only has `resolve_car(store, key)`,
  a key lookup, not alias matching) and no populated dictionary (`catalog_seed.py`
  has ~4 makes, no aliases set). Both the pure function and the ~60-make dictionary
  are net-new work; D2 only fixes *where* they'll live.
- **D2b (Phase 0 — dictionary before backfill):** Backfilling with deterministic-only
  cleanup before the dictionary exists is wasted work (`mercedes benz` /
  `mercedes-benz` / `mercedes` stay 3 distinct slugs), so a **Phase 0** gates Phase 1:
  1. Build `markibx.normalize.canonical_make` (pure fn + empty data file).
  2. **Data-mine** the dictionary from the real 141k rows' distinct-make distribution
     (rank by row count, curate the top set covering ~95% of rows; long tail falls to
     deterministic-clean + fuzzy-review) — not hand-authored from an assumed list.
     This maximizes `% make_resolved` per curation hour and surfaces real garbage
     (`🚀Volksvagen`) instead of guessing.
  3. **Human-review** the mined dictionary (D7 guard applies here too).
  4. Dictionary lives as a **version-controlled data file in markibx** (reviewable in
     PRs, diffable, no DB dependency for the pure fn), loaded into the store at seed
     time — same pattern as `catalog_seed.py`.
  The dictionary curation, not the code, is the long pole gating Phase 1 and D7's
  metrics.
- **D2c (enforcement — corrected from "three write sites"):** `store_pg.upsert` is
  the **single enforcement point**. It **unconditionally recomputes**
  `make_norm`/`model_norm` from raw `make`/`model` on every write — not `if not set`
  (unlike `dedup_key`, no caller has a legitimate reason to supply `make_norm`).
  Rationale: `upsert` is the one chokepoint every scrape, backfill row, and manual
  edit passes through, so enforcing there makes drift structurally impossible;
  unconditional recompute means rows **self-heal** on every re-scrape as the
  dictionary improves, with no incremental re-backfill needed for live inventory.
  mawtarx-connect adapters are **dropped as a persistence site** (may call the pure
  fn for display, never persist `make_norm`) — the store owns it alone. Cost:
  `canonical_make` runs on every write (hot path, 141k+ scrapes), so it must stay
  cheap — dict lookup is O(1) casefold+hit; the edit-distance fuzzy pass (D3 layer 3)
  runs **only on dictionary-miss**, in-process, dictionary loaded once at store init.
- **D3 (mechanism):** Layered — (1) deterministic rules (casefold, strip
  emoji/punctuation, collapse whitespace) → (2) curated make-alias **dictionary**
  (makes are a closed ~60-set, hand-curatable) → (3) fuzzy fallback (edit-distance
  vs canonical make list). LLM only *offline* to bootstrap the dictionary, never at
  runtime.
  - **CORRECTION (2026-07-06) — auto-apply, not gated review:** originally specced
    as "logged, reviewed not auto-trusted" with a human-confirmation queue before a
    fuzzy guess could affect `make_norm`. Rejected as unnecessary process: because
    D2c makes `upsert` recompute unconditionally on every write, a bad auto-applied
    guess **self-heals** the moment the dictionary gets an exception/override — no
    migration, no per-row fix needed. Given the make list is a closed ~60-set (true
    ambiguous collisions, e.g. a `Siat` typo sitting equidistant between real makes
    `Fiat`/`Seat`, are rare not common), gating adds overhead disproportionate to the
    risk. Final mechanism: **edit-distance 1 auto-applies** into `make_norm`
    immediately (tightened from the original ≤1–2 range for precision); edit-distance
    2 does **not** auto-apply — those rows fall back to deterministic-clean-only
    (same bucket as no-match, D6). Every fuzzy application (distance-1 auto-applied,
    and distance-2 near-misses) is still **logged** (raw string, guessed slug,
    score) for periodic (not blocking) audit — bad guesses are fixed by adding a
    dictionary alias (confirms it) or an explicit never-match exception (blocks it),
    either way propagating forward automatically via the same self-heal.
- **D4 (scope of v1):** **Makes** get full layered normalization; **models** get
  **deterministic cleanup only** (casefold, strip punctuation/spaces/emoji) so
  `RAV 4`→`rav4`, PLUS the existing alias/trim-rule table below (D4b) — not "later."
  - **CORRECTION (2026-07-06) — a model alias table already exists.**
    `catalog_link.py` has its own `_ALIASES: dict[(make_norm, model_norm), str]` and
    per-make `_TRIM_RULES` (regex), e.g. `("toyota","prado")→"landcruiserprado"`,
    Mercedes `C200/A180/G63`→`cclass/aclass/gclass`, `("kia","mohave")→"borrego"`.
    Built for catalog matching (finding one specific spec entry), not pricing
    pooling, but it already solves exactly the semantic model-split problem D4
    deferred as "a later data-driven pass." **Decision: reuse it, don't defer.**
  - **D4b (merge target):** Move `_ALIASES`/`_TRIM_RULES` out of `catalog_link.py`
    and into the markibx normalize data file (D2b), as the shared model-alias
    source for both `canonical_model()` (pricing's `model_norm`) and
    `catalog_link.py` (which switches to calling it instead of its local `_norm()`
    + inline tables). `catalog_link.py`'s own ad-hoc `_norm()` is retired in favor
    of the shared normalizer so there's one implementation, not two independently
    drifting ones. `_JUNK_MODELS` (`"other"`, `"unknown"`, `"na"`, `"n/a"`, blank)
    folds into D6's unknown-sentinel handling.
- **D5 (phasing):** Ship in two phases.
  - **Phase 1 (safe, delivers the 36% win):** add `make_norm`/`model_norm`, backfill
    141k rows, move the index to the norm columns, and switch **all read-path
    matchers** to them (per the D1 correction: pricing `same_mm`, `comparables_for`,
    fraud `peer_prices` + `fraud.py:206`, `market.supply_for`, `top_makes`
    aggregation, the in-memory `store.py` mirrors, and search-filter query
    normalization). **Do NOT touch `dedup_key`.** No row deletion, no merge risk. All
    read sites must move together for cross-engine coherence (fraud vs pricing must
    agree on the peer set). Also fold in the blank-trim one-liner (require both trims
    non-blank).
  - **Phase 2 (risky, separate, gated):** switch `dedup_key` + mawtarx-connect scrapes
    to the norm fields **atomically** with a collapse migration (group by new key,
    survivor = earliest `first_seen`, union sources/versions/photos, delete losers,
    repoint refs). Reason it must be atomic: mismatched keys between new scrapes and
    old rows would create duplicate-key rows. The store only merges at upsert time on
    `dedup_key`; there is no auto-collapse of already-stored rows.
    - **Conflict rule (decided 2026-07-06):** for scalar fields that disagree between
      merging duplicates (price, mileage, year, etc.), **the survivor's own values
      win** — no separate freshness tiebreak. Simpler (one rule, not two), consistent
      with "survivor" already being the merge's authority, and losers' scalars aren't
      lost — they remain visible in the unioned `versions` history.
  - **Backfill mechanics (decided 2026-07-06):** batch the 141k-row `UPDATE` (e.g.
    ~5k rows/tx) to avoid long-held locks; build the `(make_norm, model_norm)` index
    **after** the backfill completes, not before — skips index-maintenance overhead
    during the bulk write, and a temporarily-missing index is fine for a one-time
    offline job.
- **D6 (unmatchable/garbage):** Never null, never drop.
  - Unresolved **makes** → `make_norm` = deterministically-cleaned raw value
    (`🚀Volksvagen`→`volksvagen`); carry a `make_resolved` bool/score for coverage
    metrics. Per D3's correction, "unresolved" = dictionary-miss AND (no
    edit-distance-1 fuzzy hit) — distance-1 hits auto-apply and count as resolved;
    distance-2 near-misses are logged but land here (unresolved) same as no-match.
  - **Models** = `Other`/blank/junk → an explicit **unknown sentinel** that
    `comparables_for` treats like blank (returns `[]`). Fixes a live mini-bug where
    `model="Other"` rows currently pool as if identical. Junk set includes
    `catalog_link.py`'s existing `_JUNK_MODELS` (`""`, `"other"`, `"others"`,
    `"unknown"`, `"na"`, `"n/a"`) per D4b.
    - **Sentinel value (decided 2026-07-06):** `model_norm = "__unknown__"`.
      Deterministic cleanup only strips non-word chars/emoji/whitespace from real
      scraped text, so a literal double-underscore-wrapped token can't arise from
      real data — safe, greppable, self-documenting in query results.
- **D7 (metrics + false-merge guard):**
  - Success: before/after estimate-shift across all fragmented brands; median pool
    size ↑; tier distribution (exact/similar ↑, depreciation/manual ↓ from 13.6%);
    low-trust conf<40 ↓ from 15.8%; self-anchor ↓ from 6.8%; distinct makes
    1,139 → ~60; `% make_resolved`; **distinct `model_norm` count per `make_norm`**
    post-Phase-1 (free byproduct of the `top_makes`-style aggregation) — validates
    or refutes D4's bet that model fragmentation is mostly whitespace-level, not
    semantic; a make with implausibly many distinct model slugs (e.g. 40+ for
    Toyota) is the trigger for D4's deferred data-driven model pass.
  - Guard (gates Phase 2): the **Phase 0 dictionary** (D2b) is human-reviewed before
    Phase 1 backfill (unchanged). **Runtime fuzzy matches are NOT gated** (D3
    correction) — distance-1 auto-applies and is logged for periodic audit, not
    blocking. What *does* gate Phase 2: the alias-log audit trail is reviewed
    on-or-before the Phase-2 cutover (catch accumulated bad auto-applies first);
    Phase-2 re-dedup runs **dry-run diff first**; hard assertion **never merge rows
    with different known VINs** + flag merges with divergent price/year. Phase 2
    blocked until the accumulated alias log is reviewed AND dry-run shows zero
    VIN-conflict merges.
- **D8 (format + location):** `make_norm`/`model_norm` store a **lowercase canonical
  slug** (match key only, e.g. `mercedes-benz`); raw preserved for display, pretty
  display resolved from markibx catalog when needed. One pure function
  `markibx.normalize.canonical_make(raw) -> (slug, resolved, score)` + data-file alias
  dictionary (see D2b for where it lives and how it's built). **Superseded by D2c:**
  invoked at a single enforcement site (`store_pg.upsert`, unconditional), not three
  write sites — mawtarx-connect never persists `make_norm`, and the backfill job
  calls the same function as a one-time pass for rows not soon re-scraped.

---

## APPENDIX — FUTURE GRILLING AGENDA: S2/S7 (wrong-market + scrape breadth)

NOT YET GRILLED. Captured 2026-07-06 so the next session can run this like the S1
grill above. S2 (only 2.4% Saudi inventory) and S7 (43 of ~625 connectors active) are
the same root problem seen from two ends: the product is Saudi-facing but the pipeline
mostly scrapes elsewhere. Each item below has a *recommended starting position* to
argue for/against — decisions are still open.

**Grounding done:** mawtarx-connect has `CONNECTOR_REGISTRY` + `SOURCE_META` (the full
registry) and a `daemon` that only runs "configured source ids" on an overdue schedule
(`daemon_schedule.is_overdue`, `_load_configured_source_ids`). So "active" ≠
"registered" — the 43-vs-625 gap is at least partly *which sources are configured/
scheduled*, not necessarily broken code. First grill question must resolve which.

**G1 (foundational — target market):** Is the product Saudi-first or pan-GCC/MENA? If
Saudi-first (Mojaz = Saudi history, SAR display strongly imply it), 2.4% inventory is a
crisis and S2 is P0. If multi-market, the "wrong market" framing dissolves and the mix
is acceptable. *Everything downstream depends on this.* **Rec:** confirm Saudi-first;
treat GCC as secondary markets, non-GCC (PL/CZ/SK/UA) as either out-of-scope noise or a
separate product line. Verify against the Karaa product spec, not assumption.

**G2 (diagnosis of the 582 silent connectors):** Classify a sample of the inactive
registry into: (a) registered-but-not-scheduled (config flip), (b) implemented-but-
broken (anti-bot / layout drift / blocked), (c) stub/never-implemented, (d) dead site.
This decides whether breadth is a config change or real engineering. **Rec:** pull the
registry, diff against the 43 active source ids, run `debug_runner` on a sample of
inactive ones, tabulate failure modes before committing effort.

**G3 (depth vs breadth):** For the target-market gap, deepen the few Saudi sources
(opensooq.sa, syarah, saudisale, sayarat, samaco) vs light up more connectors broadly.
**Rec:** Saudi *depth* first — more breadth in non-target countries doesn't help the
product; the goal is enough Saudi pool to reach pricing Tiers 1-3.

**G4 (coverage SLA):** Define "acceptable" inventory quantitatively. Pricing needs ≥3
same make+model+year+city comps for the trustworthy tiers, so back out a per-market
minimum active-listing target (esp. Saudi) from the tier requirements + the make/model
distribution. **Rec:** set a Saudi active-listing floor and a per-popular-model depth
target; make it the success metric for S2/S7 like D7 is for S1.

**G5 (dead-source monitoring):** The audit found 43/625 *manually* — there's no signal
when a scraper silently dies. **Rec:** per-source health metric (last successful
yield, row count trend) + alert on drop-to-zero; cheap, prevents silent decay.

**G6 (anti-bot / access):** If G2 shows many sources blocked, decide policy — proxies/
headless vs official feeds/partnerships for key Saudi sources, incl. ToS/legal.
**Rec:** for a handful of high-value Saudi sources, pursue official/feed access over an
arms race; scrape the long tail.

**G7 (per-source data quality → ties to S3/S4):** Which sources emit placeholder prices
/ zero-mileage / junk makes; gate or clean at the adapter. **Rec:** fold a per-source
quality scorecard into G2's diagnosis so scraping and pricing fixes share one pass.

---

## Scope note
**kara is out of scope** (decided 2026-07-06): kara consumes listings/pricing only
through mawtarx's API and never independently matches raw make/model strings, so
this work is fully contained in mawtarx + markibx.

## Status
Design complete, fully grilled (2026-07-06) — includes D1 (9→10 read/write sites,
+catalog_link.py), D2b/D2c (Phase 0 dictionary + single enforcement point), D3
(auto-apply fuzzy, not gated), D4/D4b (model alias reuse from catalog_link.py), D5
(Phase 2 conflict rule + backfill mechanics), D6 (unknown sentinel value). Ready to
implement. Build order:
1. **Phase 0:** `markibx.normalize` module — `canonical_make`/`canonical_model` pure
   functions; data-mine the make dictionary from the real 141k-row distribution;
   merge `catalog_link.py`'s `_ALIASES`/`_TRIM_RULES` in as the model-alias source
   (D4b); human-review the mined dictionary.
2. **Phase 1:** add `make_norm`/`model_norm` columns; batched backfill; build the
   `(make_norm, model_norm)` index after backfill; switch all ~10 read/write sites
   (D1) to the norm columns, including `catalog_link.py`'s own matcher (D4b) and the
   blank-trim one-liner; do NOT touch `dedup_key`.
3. Measure against D7 baselines (including the new per-make model-count check).
4. Gate Phase 2 on: alias-log review + dry-run diff showing zero VIN-conflict merges.

---

## DEFERRED — Trim logic (documented 2026-07-06, NOT implementing now)

Findings kept here so they aren't lost; decision was **do not implement now**.

**What's wrong with trim today:**
- Trim is used in **exactly one place** — the Tier-1 exact-match gate
  `(c.trim or "").casefold() == (listing.trim or "").casefold()`. Tiers 2–7 ignore
  it. Only ~1% of listings reach Tier 1, so for **~99% of cars the estimate pools all
  trims together** and takes the median → loaded trims under-valued, base trims
  over-valued (trim is a 20–40% price driver on many models). Invisible, systematic.
- **`blank == blank` is treated as a confirmed match** — with 47% of trims blank, a
  no-trim car matches other no-trim cars and can reach `exact_match` at confidence 88,
  i.e. *most* confident about trim when it knows *nothing*. Inverted trust (a real bug).
- When trim *is* present it's too noisy to gate on: 3,023 distinct strings mixing real
  trims (`LE`,`SE`,`XLE`) with non-trims (`Standard`,`Full`,`Mid`,`Core`) and regional
  transliterations (`GL/GLX/GLE/GLI` on a Camry). Exact-string match rarely fires →
  Tier 1 stuck at 1%. The gate is simultaneously **too strict** (exact string) and
  **too loose** (blank↔blank).

**Recommended enhancement (when we do it):**
- **Cheap, worth doing when S1 ships (still deferred per decision):** require BOTH
  trims non-blank before treating them as an exact-match — a one-line fix that only
  demotes falsely-confident blank-trim estimates from Tier 1 (conf 88) to Tier 2
  (conf 76). Pure correctness, no data dependency.
- **Phase 2 (real work, bounded ROI):** canonicalize trim → a coarse **trim level**
  (economy/standard/premium) via markibx's trim vocabulary; in pricing, prefer
  same-level comps and apply a graded **trim-level adjustment factor** (mirroring
  `_adj_year`/`_adj_mileage`) instead of a hard string gate. Bounded because 47% of
  trims are blank — helps at most ~half the inventory, mostly premium — so scope it to
  high-trim-variance segments (luxury/large SUV), not a blanket feature.
- **Never:** keep exact raw-string trim gating — worst option (brittle *and*
  over-trusting).
</content>
