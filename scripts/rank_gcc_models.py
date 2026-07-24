#!/usr/bin/env python3
"""Rank mawtarx's active GCC listings by (make_norm, model_norm) and print the
head that covers ~80% of volume — the curation target list for markibx's MVP
catalog spine (docs/markibx-mvp-catalog-model.md, decision D-g).

Input: mawtarx's listing snapshot, as either
  - a URL to mawtarx-api `GET /listings/snapshot` (needs a service token), or
  - a JSON file (an array of listing dicts, or {"items"/"listings": [...]}).

Each listing is expected to carry: make_norm, model_norm, country, status,
and optionally year (used only to hint the generation spread per model).

Usage:
  python rank_gcc_models.py --file snapshot.json
  python rank_gcc_models.py --url http://127.0.0.1:8252/api/mawtarx/v1/listings/snapshot \\
                            --token "$MAWTARX_TOKEN"
  python rank_gcc_models.py --file snapshot.json --coverage 0.8
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from urllib.request import Request, urlopen

GCC = {"SA", "AE", "KW", "QA", "BH", "OM"}


def load_listings(args: argparse.Namespace) -> list[dict]:
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            data = json.load(fh)
    elif args.url:
        req = Request(args.url)
        if args.token:
            req.add_header("Authorization", f"Bearer {args.token}")
        with urlopen(req, timeout=60) as resp:  # noqa: S310 (operator-supplied URL)
            data = json.load(resp)
    else:
        sys.exit("give --file or --url")
    if isinstance(data, dict):
        data = data.get("items") or data.get("listings") or data.get("results") or []
    if not isinstance(data, list):
        sys.exit("snapshot is not a list of listings")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file")
    ap.add_argument("--url")
    ap.add_argument("--token")
    ap.add_argument("--coverage", type=float, default=0.80,
                    help="cumulative volume fraction to cover (default 0.80)")
    ap.add_argument("--all", action="store_true", help="print every row, not just the cut")
    args = ap.parse_args()

    listings = load_listings(args)

    counts: Counter[tuple[str, str]] = Counter()
    years: dict[tuple[str, str], set[int]] = defaultdict(set)
    kept = skipped_geo = skipped_status = skipped_blank = 0

    for lst in listings:
        if (lst.get("status") or "active").lower() != "active":
            skipped_status += 1
            continue
        if (lst.get("country") or "SA").upper() not in GCC:
            skipped_geo += 1
            continue
        mk = (lst.get("make_norm") or "").strip().lower()
        md = (lst.get("model_norm") or "").strip().lower()
        if not mk or not md:
            skipped_blank += 1
            continue
        counts[(mk, md)] += 1
        y = lst.get("year")
        if isinstance(y, int) and 1990 < y < 2030:
            years[(mk, md)].add(y)
        kept += 1

    if not kept:
        sys.exit("no active GCC listings with make_norm+model_norm found")

    ranked = counts.most_common()
    total = sum(counts.values())
    cum = 0
    cut_idx = len(ranked)
    print(f"# active GCC listings: {kept}  (skipped: geo={skipped_geo} "
          f"status={skipped_status} blank_norm={skipped_blank})")
    print(f"# distinct make·model: {len(ranked)}  target coverage: {args.coverage:.0%}\n")
    print(f"{'rank':>4}  {'cum%':>6}  {'count':>6}  {'share':>6}  make · model  (years seen)")
    for i, ((mk, md), n) in enumerate(ranked, 1):
        cum += n
        frac = cum / total
        yrs = sorted(years[(mk, md)])
        yspan = f"{yrs[0]}–{yrs[-1]}" if yrs else "?"
        if i <= cut_idx or args.all:
            print(f"{i:>4}  {frac:>6.1%}  {n:>6}  {n/total:>6.1%}  {mk} · {md}  ({yspan})")
        if cum / total >= args.coverage and cut_idx == len(ranked):
            cut_idx = i
            if not args.all:
                print(f"\n# ── {args.coverage:.0%} coverage reached at {i} make·model combos "
                      f"({cum}/{total} listings) ──")
                if i < len(ranked):
                    print(f"# (+{len(ranked) - i} more combos make up the remaining "
                          f"{1 - frac:.1%})")
                break


if __name__ == "__main__":
    main()
