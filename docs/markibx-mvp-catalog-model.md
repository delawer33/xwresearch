# markibx MVP catalog model — curated canonical spine

**Status:** **built and merged to `main`** 2026-07-27 (markibx `b9d8729`, markibx-api `57a823a`;
markibx-web merged locally only — no push access). Steps 1, 3, 5, 6, 7 of the build order below
are done; **2a** is done as a machine-derived identity batch (222 models / 45 makes, 80.08%
SA-listing coverage) with its curated-alias half still open; **2b is deliberately continuous**
(D-010). Not deployed to the VPS. Terms: [`glossary.md`](glossary.md). Current code truth:
`repos/markibx/CLAUDE.md` and `repos/markibx/src/exonware/markibx/data/spine_seed/README.md` —
that README holds the seed's live caveats (SA-only ranking, year window, mechanical aliases,
the `baw`=FAW upstream normalizer bug).

## Goal & consumers

Ask markibx for a car → get back a filled spec sheet with per-field provenance and confidence.
MVP scope: a **curated top-N canonical spine** for **one market (GCC)**, built so the general
auto-resolver (the "Option 1" backbone) plugs into the *same seam* later with no rewrite.

- **Consumer A (north star):** the human-readable spec sheet (markibx-web / kara-web).
- **Consumer B:** mawtarx pricing's MSRP-depreciation method — a narrow subset of A.

## The three roots it fixes (all verified in current code)

1. **Identity fragmentation** — no canonical registry above the rows; "Camry" vs "Camry Classical"
   become separate rows, lookups miss. → a canonical `make → model → generation` registry.
2. **Shallow specs** — ~5% field fill; most rows are identity-only shells. → curate the spine deep.
3. **Zero trust** — `quality.py` returns `confidence 0, sparse=true` because filled fields carry
   no provenance tag. → every fact carries `{value, source, confidence}`.

## Model

Store is xwjson (documents/flat files), so the aggregate is **one document per generation**, plus
a small make/model registry for browse + the resolve seam.

- **`makes/<id>.json`**, **`models/<id>.json`** — canonical registry. Stable ids, per-market name
  aliases, generation list. The `aliases` arrays are the **future resolver's write target**; in
  the MVP they are curated by hand. This is what keeps the spine Option-1-ready.
- **`generations/<id>.json`** — the spec-sheet aggregate:
  - `code`, `year_start`, `year_end` — the generation identity (global).
  - `fields.global` — market-invariant facts only.
  - `fields.<MARKET>` (e.g. `fields.GCC`) — a sibling layer; overrides `global` for that market's
    view only.
  - `trims.<MARKET>[]` — per-trim deltas + `launch_price {amount, currency, market}` in **native
    currency**.
  - Every fact is `{value, source, confidence, as_of?}`. Unknown = **absent**, never `confidence:0`.

**Resolution** for a query in market M: `fields.global ⊕ fields.M ⊕ trim` (M and trim win on
conflict). `quality` is computed at resolve time — `completeness = filled/total`,
`confidence = mean(field confidences)`.

Example: [see the JSON in the grill thread / to be inlined once trims + sources settle.]

## Decisions locked (2026-07-24 grill)

- **D-a — curated spine now, resolver later, one seam.** All identity lookups route through a
  `resolve()` seam that today does exact/normalized match against the hand-curated registry and
  returns an honest "not in catalog" on a miss. Option 1 later plugs fuzzy match + a merge queue
  into the *same* seam. No half-built resolver ships in the MVP.
- **D-b — `generation` is the canonical unit** (year-range + code). Curate once per generation.
- **D-c — market is a scope dimension, not identity.** `global` floor + per-market sibling layers;
  markets never override each other; `global` filled only when a fact is *verified* invariant.
- **D-d — launch price stored native per `(generation, trim, market)`; the resolved-car output
  keeps emitting `original_launch_price_sar` as a derived compat value** *(authoritative record:
  `DECISIONS.md` D-009)* (= the SAR-market amount;
  for GCC, native currency *is* SAR, so the number is unchanged). This keeps mawtarx pricing
  (`pricing_methods/msrp_depreciation.py`, which reads that field by name) working with **zero
  mawtarx changes**. A non-SAR market later is when pricing learns currency — a clean future step,
  not debt taken on now.
- **D-e — three source lanes, confidence from the existing `TRUST_TIERS` ceilings** (reuse, don't
  invent — `markibx-api/entity_schemas.py`: `official-registry 1.0 > oem 0.95 > community 0.7 >
  user 0.5`):
  - **Primary depth — manual OEM / brochure / dealer-pricelist curation** of the top-N GCC
    generations → `oem` (~0.95; dealer pricelist ~0.75). This is the MVP's engine, not a
    fallback: it's the only way GCC trims + native launch price become *trustable*. Bounded to N.
  - **Prefill — NHTSA vPIC (wired, keyless) + optional Wikidata**, `fields.global` **invariant
    fields only** (body type, doors, VIN decode). NHTSA/Wikidata are US-/global-market and do
    **not** know GCC trims/engines/price → never let them fill a market layer. `official-registry`
    ~0.85 for invariant; Wikidata `community` 0.7.
  - **Listing write-back from mawtarx — OUT OF SCOPE, possibly permanently.** Not planned. The
    `source`/`confidence` fields already model a `user`/`community`-tier claim, so *if* it's ever
    wanted it's purely additive (no structural change) — but assume it never ships. It needs the
    unwired mawtarx→markibx path + corroboration logic and is noisy; the curated spine is meant to
    stand without it.

- **D-f — committed seed files are the system of record; no daemon.** The curated spine lives as
  data-as-code (extends the existing `catalog_seed.py` / `catalog_specs_seed.py` pattern), lands
  via PR, and rebuilds the store on deploy — so local and prod converge from one file, not from a
  fragile prod-only xwjson copy. Connector **prefill** runs **on-demand** (existing admin
  `POST /catalog/connectors/pull`, a timer at most) — markibx deliberately does **not** copy
  mawtarx-connect's always-on scraper daemon. The admin `POST /catalog/car` upsert + web console
  stay for quick fixes, but are **non-durable**: anything entered there is lost on rebuild unless
  back-ported to the seed.

- **D-g — N is defined by listing-volume coverage, not a fixed count.** Curate the
  `make·model·generation` combos covering **~80% of mawtarx's active GCC listings**
  (`country ∈ {SA,AE,KW,QA,BH,OM}`, `status=active`), ranked by `(make_norm, model_norm)` count,
  then mapped to their generation(s) in the ~2010–2025 sale window. Self-limiting; makes consumer
  B useful immediately. Rough magnitude: ~50–80 make·model combos → a few hundred generation docs.
  The list is **data-derived** (`scripts/rank_gcc_models.py` against a snapshot), not guessed.
- **D-h — contributions/moderation deferred.** The community-submission queue exists in
  markibx-api but is out of MVP scope; the curated seed (D-f) is the only write path that counts.

## MVP build order (what to do now)

1. **Model layer (core markibx):** **built** (#21–#25). Canonical registry (`makes`/`models`/
   `generations`) above the rows; `generation` is a node; market lifted to `global`/`<MARKET>`
   scope keys; inline per-field `{value, source, confidence}`; the `resolve(key, market)` seam
   (exact/normalized match, honest "not in catalog" on miss); `original_launch_price_sar` kept as
   a **derived output field** (D-d).
2. **Derive N + seed identity (2a):** **built** (#33). `scripts/rank_gcc_models.py` ranks combos
   by active-listing volume; `scripts/seed_gcc_identity.py` writes the identity rows. Run against
   the **local real snapshot** `repos/mawtarx-connect/mawtarx-data/xwdb-saudi-v2` (8,315 scraped
   listings) — a prod pull was never needed, contrary to the original issue. 7,355 rankable rows →
   945 combos → **222 selected at 80.08%**. ⚠️ Every row is 100% `country=SA`, so the ranking is
   **Saudi-volume, not pan-GCC** — recorded in each row's `provenance.sa_only` and the seed README.
   The **curated-alias** half of the acceptance criteria (Arabic / variant spellings) is still open.
3. **Prefill:** NHTSA vPIC (+ optional Wikidata) into `fields.global` invariant fields only (D-e).
   Auto-fills the identity rows from step 2 — no human. **Built** (#26).
4. **Curate (2b):** OEM/brochure/dealer facts for each target generation → GCC layers, trims,
   native launch price → committed **seed files** (D-f). Confidence from `TRUST_TIERS`. **Depth
   pass, not a gate** — runs continuously *after* the console is live (D-010).
5. **Scoring:** **built.** Per-field confidence tags feed `quality.py`, so completeness +
   confidence are real (Camry XV70 resolves at 75% / 96%). An identity-only 2a row honestly
   reports 0% / 0% rather than a fabricated score.
6. **markibx-api:** **built** (#25/#31). `GET /catalog/resolve` + four `/catalog/browse/*` routes;
   miss → typed `model_not_in_catalog`; broken seed → 503 "spine unavailable" (D-012).
7. **Verify consumer B:** **verified.** `mawtarx/pricing_methods/methods/msrp_depreciation.py`
   (and `catalog_msrp.py`) still read `original_launch_price_sar`; the resolved output emits it
   (Camry LE 2.5 → 122,900 SAR, native == compat since GCC is SAR). Zero mawtarx changes.

## Deferred / out of scope (not debt — additive later)

- **Option-1 general resolver** (fuzzy auto-link + merge queue) — plugs into the `resolve()` seam.
- **Listing write-back** from mawtarx — possibly permanent non-goal (D-e).
- **Markets beyond GCC** — additive via new scope keys (D-c); no migration.
- **Contributions/moderation** (D-h).

## Deltas from today's `CatalogVehicle` (the actual work)

- `generation` string field → first-class node (registry above rows).
- `specs["market"]` blob + child-key hack → `global` / `<MARKET>` scope keys.
- `original_launch_price_sar` field → native `launch_price` (+ compat field on *output* only).
- confidence blob in `specs` → inline per-field `{value, source, confidence}` tags.

## Open — remaining grill branches

- ~~**N:** how many models~~ — **settled by measurement:** 222 combos at the 80% cut. Note D-g's
  "~50–80 make·model combos" magnitude estimate was **wrong by ~4×** (57 combos is 50% coverage,
  not 80%); the real tail is much fatter. The number is a flag, not a constant — re-run
  `rank_gcc_models.py --coverage` against a newer snapshot rather than trusting these figures.
- **Curated aliases** (Arabic / variant spellings per model) — the open HITL half of #33.
- **A pan-GCC snapshot.** Everything seeded so far is ranked on Saudi volume alone.
- **Upstream normalizer fragmentation** blocks clean identity: Arabic-script duplicates
  (`تويوتا/كورولا` ranks separately from `toyota/corolla`), mixed-script mangling (`patrolربع`),
  brand-prefix splits (`mg:5` vs `mg:mg5`), `baw`=FAW, and residual `zz*` test makes. None reached
  the seed (all below the cut) but this is exactly root cause #1, measured in live data. Fix
  belongs in `mawtarx-connect`, and changing `make_norm` output will shift the seed ids on re-run.
- **Contributions/moderation** for curated edits — still deferred past the MVP (D-h).
