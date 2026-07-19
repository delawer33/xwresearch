# Test strategy — the scraping → price-history pipeline

**Why this exists:** the pipeline's output is a function of *time*. A car has no history until it
has been swept twice, so a logic bug costs days of calendar time to discover and another sweep
cycle to confirm fixed. This document decides, before implementation, what must always be true,
what can go wrong, and how each of those is proven without waiting.

Companion: `docs/price-history-implementation-plan.md` (the what), `docs/xwstorage-db-guide.md`
(storage behaviour). Scope: **Saudi sources only** — syarah, opensooq, saudisale, sayarat, samaco,
haraj, motory.

---

## 0. Four design decisions that make the rest testable

Retrofitting these is expensive; they are prerequisites, not preferences.

1. **The clock is a parameter.** No `utcnow()` inside pipeline logic — overdue checks, series
   timestamps and retention all take an injected `now`. This is what collapses "three weeks of
   operation" into a millisecond test.
2. **HTTP is recorded and replayed.** One captured fixture corpus per Saudi source; every
   second-sweep scenario is a mutation of it.
3. **The sweep outcome is a pure function** of (store state, incoming batch) → (versions, price
   points, reconcile decision). No I/O. Everything in §2 is asserted against it directly.
4. **Dry-run is a first-class mode**, not a debug flag: execute a real sweep, write nothing, report
   exactly what would have changed — above all, how many listings would be marked sold.

The ingest boundary helps here for free: the server is testable with synthetic batches and no
scraper, the scraper is testable by asserting its POSTs with no database.

## 1. The sweep profile rule (learned from `collect.saudi.yaml`)

The seven Saudi connectors take **five different bounding parameter shapes** — page ranges
(syarah, opensooq), `max_details` (saudisale default **60**, sayarat 200), brands × `max_pages`
(samaco), a tag with `page_start: 0` (haraj, off-by-one against everyone else), and nothing at all
(motory). Feed-based sources ignore page params entirely; chunking them re-crawls the same feed.

> **Each source declares named sweep profiles (`full`, `incremental`) carrying its own parameter
> shape. Reconcile is permitted only after a sweep that used the declared `full` profile and ran to
> completion — never off connector defaults.**

Running saudisale on defaults collects 60 listings; reconciling against those 60 would mark
thousands sold. This is the same failure as the `count`/`max_records` bug, reached by a second
route, which is why it is a structural rule rather than a code fix.

## 2. Invariants

Every one of these is machine-checkable after any sweep. They are the assertion set for §4.

### Safety — a violation destroys data

- **S1** A listing still live on its source is never marked SOLD.
- **S2** Reconcile runs only after a *completed* sweep that used the source's declared `full`
  profile, and only against the union of seen-ids from that entire sweep.
- **S3** A sweep that errored, was truncated, or whose raw count collapsed against its baseline
  never reconciles.
- **S4** A degraded parse never overwrites good stored data with empty or null fields.
- **S5** Exactly one process writes the store, always.

### Correctness — a violation means a wrong chart

- **C1** Every point in a price series corresponds to an actually observed version. No generated
  or interpolated value ever enters a series.
- **C2** A point is appended **iff** the advertised price changed. An unchanged re-observation
  bumps `seen_count` and appends nothing.
- **C3** All points within one series share one currency (D-002).
- **C4** Series timestamps are strictly non-decreasing, never in the future, and never carry two
  different values at the same timestamp.
- **C5** `basis == "observed"` **iff** the series holds ≥2 observed points; otherwise
  `"indicative"`. The API never labels synthetic data as observed.

### Idempotency — the pipeline is at-least-once

- **R1** Replaying an identical batch changes nothing but `seen_count`.
- **R2** A sweep interrupted and re-run reaches the same end state as one that ran cleanly.
- **R3** The ingest endpoint is idempotent per `(sweep_id, batch_id)`.

### Boundedness — a violation kills the box slowly

- **B1** `len(listing.versions) ≤ cap` after any write.
- **B2** Series length is bounded by the retention policy.
- **B3** The ingest queue is bounded and sheds load rather than growing without limit.

## 3. Edge cases

Grouped by origin. Each needs a named test in §4; the starred ones are the ones I expect to bite.

**Source behaviour**
1. Zero results returned (bot-block, outage) → must not reconcile, must alarm.
2. Rate-limited or aborted mid-sweep → sweep incomplete → must not reconcile.
3. ★ **Markup changed: normal listing count, but fields now parse empty.** Passes a count-based
   guard while silently corrupting data. Count checks are not sufficient — S4 needs a
   field-completeness guard (e.g. % of records with a price) alongside the count guard.
4. Bot-block returns HTTP 200 with a challenge page that parses to zero listings.
5. Duplicate `source_id`s within one response.
6. Infinite/looping pagination (`MAX_PAGE_CAP = 300` exists as a backstop).

**Price**
7. Price is 0, null, or "call for price" → must never enter a series.
8. ★ Implausible price (a typo: 5,000,000 SAR for a Corolla) enters history and destroys the
   chart's y-axis permanently. Decide: reject at ingest, or store and filter at render.
9. Price changes more than once between sweeps — only the observed value is recorded. Acceptable,
   but must be stated: this is a sampled history, not a complete one.
10. Seller oscillates the price to farm the "price dropped" badge in `dealscore.py:172`.

**Identity**
11. ★ **Same car listed on haraj *and* syarah.** Dedup merges them into one listing carrying two
    per-source version chains. **Which chain does the chart show?** Undecided — needs a call:
    primary source, longest chain, or merged. Affects C3 if the sources disagree on price.
12. ★ **`dedup_key` instability.** Arabic normalization is an input to the key; improving the
    normalizer shifts keys, splitting or merging listings and orphaning their history. Any change
    to normalization is a history-migration event, not a cosmetic fix.
13. Listing relisted under a new `source_id` → new identity, history restarts. Expected.
14. Two genuinely different cars collide on `dedup_key` (D-006's known risk) → merged history is
    fiction.

**Lifecycle**
15. Listing disappears, then returns (repost) → must revive; `store.py:146` already handles the
    status-sync half of this.
16. Listing edited (title/photos) with price unchanged → a version *is* created (the hash covers
    title) but **no** price point. Direct C2 test.

**Timing**
17. Two sweeps within the same second → identical timestamps (C4).
18. Clock skew between the scraper process and the API. Prefer server-assigned timestamps.
19. API restarts mid-sweep → in-flight batches lost, sweep never completes → no reconcile. Correct
    by design; assert it.

**Scale**
20. Backfill emits one enormous batch → memory spike (B3).
21. A market-wide price move appends points for many listings at once.
22. First sweep after a long gap — everything looks changed at once.

**Saudi-specific**
23. ★ **Ramadan / Hajj seasonality** produces legitimate large swings in listing volume. The
    reconcile drop threshold cannot be chosen a priori — see §5.
24. haraj's `page_start: 0` versus everyone else's `1`.
25. Non-uniform bound parameters across all seven sources (§1).

## 4. Test layers

| Layer | What it covers | Speed | Blocks CI |
|---|---|---|---|
| 1. Unit | Pure functions: version diffing, series projection, reconcile decision, overdue, retention | ms | yes |
| 2. **Sweep simulator** | N sweeps over mutated fixtures with an injected clock; all §2 invariants asserted after each | seconds | yes |
| 3. Property-based | Random sweep sequences (price up/down/flat, appear/disappear/return, source fails); invariants must hold for all | seconds | yes |
| 4. Integration | Real xwstorage-db + real ingest endpoint; also measures write cost | ~minute | yes |
| 5. Live connector contract | Hit the real Saudi sites; assert field completeness against thresholds | minutes | **no** — scheduled, alerts |
| 6. Shadow mode | Full pipeline in prod, writes disabled, logs what it would do | continuous | n/a |
| 7. Staged rollout | One source, reconcile off, metrics + kill switch | days | n/a |

**Layer 2 is the centrepiece.** Record each Saudi source once, then define a mutation set — price
+10%, price −10%, listing removed, listing added, all removed (block), fields stripped (markup
change), duplicate ids, price → 0, price → absurd. The simulator runs sweep 1 as a baseline, then
sweeps 2..N applying chosen mutations while advancing the injected clock, asserting every invariant
after each sweep. Scenario tests read directly: *"price drops on sweep 3"* asserts the series holds
exactly two points with the expected values and that `basis` flips to `observed`.

That is the test which replaces waiting three weeks.

**Layer 3 catches what we failed to imagine.** The enumeration in §3 is guaranteed incomplete;
generated sweep sequences checked against §2 are what find the rest.

**Layer 5 must not block CI.** Real sites fail for reasons unrelated to our code. It runs on a
schedule and alerts; a red build for a site outage trains people to ignore red builds.

## 5. What cannot be tested, and what we do instead

Three things genuinely resist pre-testing. Each gets a mitigation rather than a test.

**Real site drift.** Sites change markup without warning. Mitigated by layer 5 plus S4's
field-completeness guard: if the fraction of records carrying a price drops below a threshold, halt
the sweep and alarm rather than ingesting rubbish.

**The reconcile threshold.** `reconcile_drop_threshold_pct` defaults to 30, and there is no way to
know whether 30 is right for Saudi sources without observing normal variance — Ramadan and Hajj
alone could move volumes more than that. **So: run full sweeps with reconcile OFF for 2–3 weeks,
recording per sweep what reconcile *would* have marked.** That produces the baseline that makes the
threshold an evidence-based number. Turning reconcile on before that is guessing with production
data.

**Long-run RAM growth.** Projectable from measurement (~7 KB/listing resident, ~14× disk→RAM
observed in prod) but not provable quickly. Mitigated by the version cap landing *before* sweeps
start, plus an RSS alarm.

## 6. Definition of done, per phase

- **Phase 0** — 1,000 records ingested into a 15k store in seconds; mawtarx-api p99 unchanged
  during ingest. Measured, not assumed.
- **Phase 1** — the regression test in `plan.md` item 6 is red before the fix, green after.
- **Phase 2–3** — layers 1–4 green; the simulator covers every starred edge case in §3.
- **Phase 4** — B1/B2 hold under a simulated 100-sweep run.
- **Phase 5** — C5 verified in both directions: a 1-point listing serves `indicative`, a 2-point
  listing serves `observed`, and no listing ever serves synthetic data labelled observed.
- **Phase 6** — shadow mode has run one full cycle over all Saudi sources with a would-mark-sold
  count that a human has looked at and agreed with.

## 7. Decisions

**Merged-listing history (edge 11) — decided 2026-07-19: track the merged listing's own resolved
price.** The series follows the single price the card displays, as it changes over time; the chart
therefore always explains the number the user is looking at and can never sawtooth between two
sources quoting different prices. Per-source chains are still kept in `listing.versions` for
`dealscore` and provenance — they are simply not what the chart draws.

Two consequences worth stating: a point is appended when the *resolved* price changes, which may be
caused by a merge rather than a seller's edit (acceptable — it is a real change to the advertised
price we showed); and C3 gets easier, because currency comes from the merged listing rather than
needing reconciliation across sources.

**Implausible prices (edge 8) — reject only the impossible, handle outliers at render.** Values
that are not prices (≤ 0, null, "call for price") never enter a series. A real-but-extreme value is
stored, because discarding observations makes the history a lie and the judgement is not reversible
once dropped. The chart protects itself with a robust y-axis instead.

**Sweep cadence — daily.** Asking prices do not move hourly, a daily point is the right resolution
for a 12-month chart, and it is the gentlest cadence on the sources that still produces a usable
series within weeks.

**Still open: field-completeness thresholds** per source for the S4 guard — needs one real sweep to
calibrate, so it is set during Phase 6 shadow mode rather than guessed now.
