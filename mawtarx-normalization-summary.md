# Make/Model Normalization — What Was Done

*Status: done, tested, committed on branch `s1-make-model-normalization` (markibx + mawtarx). Not merged yet.*

## The problem, in one line

The system treated `Mercedes`, `Mercedes-Benz`, and `Mercedes Benz` as three
different car brands. So when pricing a Mercedes, it only compared it against
cars with the *exact same spelling* — a smaller, wrong group — and gave a
confident but wrong price. The audit found this shifted about a third of
premium-car prices. The same problem quietly hurt fraud detection, the market
"how many similar cars are for sale" number, and search.

## What we did about it

We built one small tool that cleans up any make/model spelling into a single
standard form — `Mercedes-Benz`, `Mercedes benz`, `MERCEDES`, even `🚀Mercedes`
all become the same thing. It knows ~60 real brands, fixes accents and small
typos, and handles Arabic/Cyrillic names too.

Every car now stores this cleaned-up version alongside its original text. The
database fills it in automatically on every save, so it can never get out of
sync, and old records fix themselves the next time they're scraped. We then
pointed everything that compares cars — pricing, fraud, market stats, search,
and the catalog link — at the clean version instead of the raw text. Finally we
cleaned up all 141,000 existing cars in one pass.

## Did it work?

Yes, measured on the real 141k-car database:

- **96% of cars now sit under a clean, known brand** (was a mess of 1,000+ spellings).
- The Mercedes example went from **7 separate groups down to 1**.
- A typical Mercedes now gets compared against **~59 similar cars instead of ~23**.
- Only **58 cars** (0.04%) are left unidentifiable — and those are genuinely junk
  (someone put an emoji like ✅ or 🚗 as the brand name).

In plain terms: pricing now has enough real comparisons to be confident, and a
fairly-priced car is no longer flagged as suspicious just because its rivals were
spelled differently.

## What the review pass caught

After the first version we went back and looked hard for mistakes. We found and
fixed:

- **A genuine bug:** the two ways the app searches (one for the live database,
  one used in tests) cleaned up search terms slightly differently, so the same
  search could find a car in one place and miss it in the other. Now they share
  one piece of code and always agree.
- **Non-English brands were being wiped:** brands written in Arabic or Russian
  were turning into blank, which lumped them all together. Fixed — they now keep
  their own identity.
- **The catalog link** now recognises "Mercedes" and "Mercedes-Benz" as the same
  car, which it didn't before.

Everything is covered by **129 automated tests, all passing**, plus an
end-to-end run through the real pricing/fraud/market code.

## What we deliberately left for later

- **Merging duplicate listings** — this is the risky part (it deletes rows), so
  it's a separate, carefully-gated step. Not touched here.
- **Scraper quality** — the last few percent of messy data isn't a code problem.
  It's two things: (1) a handful of real brands we haven't added to the list yet
  (Dacia, Cupra, Daewoo…), and (2) two Czech/Slovak scrapers dumping the ad title
  into the brand field. Both are quick follow-ups — grow the brand list, and
  either fix or drop those two scrapers (they're not even Saudi-market anyway).

---
*More detail: `mawtarx-normalization-report.md` (technical) · `mawtarx-normalization-plan.md` (design decisions).*
