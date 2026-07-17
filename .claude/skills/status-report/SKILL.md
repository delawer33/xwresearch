---
name: status-report
description: >
  Write a brief, human-readable summary of recent work across the ecosystem's ~30
  repos, grouped by theme (not by repo, not by commit). Use when the user asks for
  "today's report", "status report", "what shipped today", "summarize today's
  commits/work", or invokes /status-report. Pulls from real git history across
  `repos/*` — never from this conversation's uncommitted work unless the user says
  to include it.
---

# Status report

A short, plain-English summary of what actually landed in git, for someone who
wasn't in the room — a teammate, the client, future-you. Optimize for **brief and
readable**, not complete. This is not a changelog and not a standup transcript.

## Step 1 — gather the real commits, not conversation memory

Scope defaults to **today** across every repo under `repos/`. If the user names a
person, date, or range, use that instead — don't assume "today" or "me" silently.

```bash
cd repos
for d in */; do
  repo="${d%/}"
  [ -d "$repo/.git" ] || continue
  commits=$(cd "$repo" && git log --since="<start>" --until="<end>" --oneline)
  [ -n "$commits" ] && { echo "=== $repo ==="; echo "$commits"; }
done
```

Filter by author only if the user asks for "my" commits specifically **and** you can
resolve their git identity (`git config user.email`) — otherwise report everyone's,
since a solo-looking repo often has a Cursor/Claude co-author on every commit here.

For each commit found, pull enough to summarize accurately — don't guess from the
subject line alone:

```bash
git show --stat --format="%B" <sha> | head -15
```

**Never include this conversation's own uncommitted edits or VPS deploys in the
report unless the user explicitly says to.** A report about "today's commits" means
committed git history — work still sitting in a working tree or shipped straight to
a server without a commit doesn't count until the user says otherwise.

## Step 2 — group by theme, not by repo or chronology

Read every commit message + diff stat, then cluster them into 3-6 themes that would
make sense to someone skimming (e.g. "read-path performance", "media engine
consolidation", "admin moderation tools") — a theme can span several repos in one
bullet; don't give each repo its own section. Drop pure noise (typo fixes, doc
formatting) unless nothing else happened that day.

## Step 3 — write it in this exact shape

```
Today's work — <2-4 word theme> (<date>)

<One sentence: the throughline connecting the day's work.>

Shipped & live (<comma-separated repos involved>):
- <theme bullet: what changed + why it matters, one line, no jargon dump>
- <theme bullet>
- <theme bullet — 3-6 total, not one per commit>

In progress:
- <what's being built next, in plain English, if the user has given you that
  context — see Step 4. Omit this section entirely if there's nothing in flight.>
```

Rules that keep it brief and honest:
- **One line per theme, not per commit.** Multiple commits implementing one feature
  become one bullet.
- **Say what changed and why it matters**, not the mechanism. "Cut ~1.7s off a 2.8s
  search response" beats "removed a synchronous socket call."
- **No commit hashes, no file paths, no code** in the report itself — this is for a
  human skimming, not a diff review.
- **Name real numbers when a commit message has them** (a measured ms/percent
  improvement, a row count) — don't invent one if the commit doesn't say.
- Co-author trailers (`Cursor`, `Claude ...`) are provenance, not content — never
  surface them in the report.

## Step 4 — in-progress work

Only comes from what the **user tells you directly** in the request (a plan, a
description of what's being built next) — never infer or guess at unlanded work
from partial diffs or branch names. If the user describes upcoming work in
conversational detail, compress it to ONE bullet: what it does, the key mechanism
if it's non-obvious (e.g. a fallback ladder, a stopping condition), and why it
exists — cut everything else. If they give you nothing, omit the section.

## Worked example

Input: today's commits across `xwapi`, `xwaction`, `xwbase`, `mawtarx`, `mawtarx-api`,
`markibx`, `markibx-api`, `kara-api` (WS-RPC surface, a media engine consolidation +
DNS perf fix, catalog wiring, autocomplete vocab sync, admin moderation routes) plus
a user-supplied description of an upcoming `/search/similar` endpoint.

```
Today's work — karaa/mawtarx catalog, media, and platform-surface publishing (2026-07-15)

Theme: publishing shared xwapi/xwbase/xwaction surface that products depend on, plus
catalog wiring, a media engine consolidation, and admin moderation tools.

Shipped & live (xwapi, xwaction, xwbase, mawtarx, mawtarx-api, markibx, markibx-api, kara-api):
- Published xwapi's WS-RPC surface (transport-agnostic dispatcher, WS client, HTTP
  re-exports) — fixes import crashes that were breaking deploys on products expecting
  these symbols.
- New xwbase media engine: inline data-URI photo bounding/thumbnailing, plus a DNS
  perf fix at thumbnail-signing time (cut ~1.7s off a 2.8s search response by dropping
  a redundant per-card DNS lookup). mawtarx-api and kara-api now wire through the
  shared engine instead of their own copies.
- Catalog: mawtarx gained a market_catalog module, markibx's store gained catalog
  helpers, both -api services mounted the new routes.
- Autocomplete: mawtarx-api now exposes its full vocab; kara-api pulls + backs it up
  so /autocomplete still works if mawtarx is offline.
- Admin moderation (kara-api): soft/hard delete + restore + mark-sold for listings,
  JWT-gated ad reporting with a resolve flow.

In progress:
- GET /search/similar: a fallback-ladder endpoint (make+model -> drop trim/year ->
  same make+body-type -> same body-type+price band, stopping at 3 matches) so the
  Estimate flow can show similar cars for a typed make/model/year rather than a
  listing id - returns a match_level for the UI, and retires the dead
  year_min/year_max frontend<->backend mismatch by giving year logic one owner.
```

## Output

Print the report directly in the response — plain text, no artifact, no file
written, unless the user asks you to save or publish it somewhere.
