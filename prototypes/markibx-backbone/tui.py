#!/usr/bin/env python3
"""
THROWAWAY TUI for the markibx canonical-backbone logic prototype.

Run interactively:   python3 prototypes/markibx-backbone/tui.py
Run the scripted demo (no typing, good for AFK):  python3 prototypes/markibx-backbone/tui.py --demo

This shell is optimised for being driven by hand and is NOT for production. The keepable bit is
backbone.py. See README.md for the question this is answering.
"""
from __future__ import annotations

import sys

from backbone import (
    TRUST_TIERS, TIER_CEILING, FieldClaim, CanonicalRegistry, CanonicalCar,
)

B, D, R, G, Y, RED = "\x1b[1m", "\x1b[2m", "\x1b[0m", "\x1b[32m", "\x1b[33m", "\x1b[31m"


# --------------------------------------------------------------------------- seed
def seed() -> tuple[CanonicalRegistry, dict[str, CanonicalCar], list]:
    reg = CanonicalRegistry(threshold=0.82)
    # makes seeded from a tiny brands.py stand-in (authority-first, D4)
    reg.seed_make("toyota", "Toyota", ["toyota motor"])
    reg.seed_make("nissan", "Nissan", ["datsun"])
    # models seeded from the "authoritative reference" directory
    reg.seed_model("toyota:camry", "toyota", "Camry", ["Aurion"][:0])  # Aurion NOT an alias yet
    reg.seed_model("toyota:corolla", "toyota", "Corolla", [])
    reg.seed_model("nissan:sunny", "nissan", "Sunny", ["Versa"])  # D2 nameplate alias
    cars: dict[str, CanonicalCar] = {}
    queue: list = []
    return reg, cars, queue


STATE = {}


def reset():
    reg, cars, queue = seed()
    STATE.clear()
    STATE.update(reg=reg, cars=cars, queue=queue, log=[])


def car_for(model_id: str) -> CanonicalCar:
    cars = STATE["cars"]
    if model_id not in cars:
        cars[model_id] = CanonicalCar(model_id)
    return cars[model_id]


# --------------------------------------------------------------------------- render
def render() -> str:
    reg: CanonicalRegistry = STATE["reg"]
    cars = STATE["cars"]
    queue = STATE["queue"]
    out = []
    out.append(f"{B}markibx canonical backbone — logic prototype{R}   "
               f"{D}auto-resolve threshold = {R}{B}{reg.threshold:.2f}{R}")
    out.append(D + "─" * 78 + R)

    out.append(f"{B}Canonical makes{R}  ({len(reg.makes)})")
    for m in reg.makes.values():
        al = f"  {D}aka {', '.join(m.aliases)}{R}" if m.aliases else ""
        out.append(f"   {m.id:<10} {m.display}{al}")

    out.append(f"{B}Canonical models{R}  ({len(reg.models)})")
    for m in reg.models.values():
        al = f"  {D}aka {', '.join(m.aliases)}{R}" if m.aliases else ""
        out.append(f"   {m.id:<18} {m.display}{al}")

    out.append("")
    out.append(f"{B}Catalog (provenanced){R}")
    if not cars:
        out.append(f"   {D}(no cars linked yet){R}")
    for cid, car in cars.items():
        out.append(f"   {B}{cid}{R}")
        if not car.claims:
            out.append(f"      {D}(no field claims){R}")
        for fld in car.fields():
            res = car.value_of(fld)
            w = res.winner
            conf = res.confidence
            color = G if conf >= 0.75 else (Y if conf >= 0.4 else RED)
            losers = [c for c in res.claims if c is not w]
            loser_s = ""
            if losers:
                loser_s = "   " + D + "beaten: " + ", ".join(
                    f"{c.value}[{c.tier} {c.effective_confidence:.2f}]" for c in losers) + R
            out.append(f"      {fld:<14} {w.value:<12} "
                       f"{color}conf {conf:.2f}{R} {D}({w.tier} · {w.source}){R}{loser_s}")

    out.append("")
    out.append(f"{B}Moderation queue{R}  {D}(human gate — D5){R}  "
               + (f"{RED}{len(queue)} pending{R}" if queue else f"{G}empty{R}"))
    for i, p in enumerate(queue):
        guess = f" {D}→ nearest {p.best_guess_id} ({p.best_score:.2f}){R}" if p.best_guess_id else ""
        out.append(f"   [{i}] {Y}{p.kind}{R}  raw={p.raw!r}{guess}")

    if STATE["log"]:
        out.append("")
        out.append(f"{B}Last action{R}")
        for line in STATE["log"][-3:]:
            out.append("   " + line)

    out.append(D + "─" * 78 + R)
    out.append(
        f"{B}o{R}{D} observe make/model  {R}"
        f"{B}c{R}{D} claim field  {R}"
        f"{B}a{R}{D} approve queue#  {R}"
        f"{B}r{R}{D} reject queue#  {R}"
        f"{B}t{R}{D} threshold  {R}"
        f"{B}x{R}{D} reset  {R}"
        f"{B}q{R}{D} quit{R}")
    return "\n".join(out)


def log(s: str):
    STATE["log"].append(s)


# --------------------------------------------------------------------------- actions
def do_observe(make_raw: str, model_raw: str):
    reg: CanonicalRegistry = STATE["reg"]
    mk = reg.resolve_make(make_raw)
    if not mk.auto_linked:
        STATE["queue"].append(mk.proposal)
        log(f"make {make_raw!r} → {RED}proposal {mk.proposal.kind}{R} (score {mk.score:.2f})")
        return
    md = reg.resolve_model(mk.canonical_id, model_raw)
    if md.auto_linked:
        car_for(md.canonical_id)
        log(f"{make_raw}/{model_raw} → {G}auto-linked{R} {md.canonical_id} "
            f"(make {mk.score:.2f}, model {md.score:.2f})")
    else:
        STATE["queue"].append(md.proposal)
        log(f"{make_raw}/{model_raw} → {Y}proposal {md.proposal.kind}{R} "
            f"(model score {md.score:.2f}) — human decides")


def do_claim(model_id: str, fld: str, value: str, tier: str, conf: float):
    if tier not in TRUST_TIERS:
        log(f"{RED}unknown tier {tier!r}{R} (one of {', '.join(TRUST_TIERS)})")
        return
    car = car_for(model_id)
    res = car.ingest_claim(FieldClaim(fld, value, tier, tier, conf))
    won = res.winner.value == value and res.winner.tier == tier
    verdict = f"{G}now winning{R}" if won else f"{RED}stored but LOST{R} to {res.winner.value}"
    log(f"claim {fld}={value} @{tier}({conf:.2f}) on {model_id} → {verdict} "
        f"(served conf {res.confidence:.2f})")


def do_approve(idx: int):
    q = STATE["queue"]
    if not (0 <= idx < len(q)):
        log(f"{RED}no queue item {idx}{R}"); return
    p = q.pop(idx)
    cid = STATE["reg"].approve(p)
    if p.kind != "new_make":
        car_for(cid)
    log(f"{G}approved{R} {p.kind} {p.raw!r} → {cid}")


def do_reject(idx: int):
    q = STATE["queue"]
    if not (0 <= idx < len(q)):
        log(f"{RED}no queue item {idx}{R}"); return
    p = q.pop(idx)
    log(f"{D}rejected{R} {p.kind} {p.raw!r}")


# --------------------------------------------------------------------------- loop
def clear():
    sys.stdout.write("\x1b[2J\x1b[H")


def interactive():
    reset()
    while True:
        clear()
        print(render())
        try:
            cmd = input(f"\n{B}> {R}").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if not cmd:
            continue
        k, *rest = cmd.split(None, 1)
        arg = rest[0] if rest else ""
        try:
            if k == "q":
                return
            elif k == "x":
                reset()
            elif k == "t":
                STATE["reg"].threshold = float(arg)
            elif k == "o":
                mk, md = [s.strip() for s in arg.split("/", 1)]
                do_observe(mk, md)
            elif k == "c":
                model_id, fld, value, tier, conf = [s.strip() for s in arg.split(",")]
                do_claim(model_id, fld, value, tier, float(conf))
            elif k == "a":
                do_approve(int(arg))
            elif k == "r":
                do_reject(int(arg))
            else:
                log(f"{RED}unknown command {k!r}{R}")
        except Exception as e:  # prototype: keep the loop alive, surface the error
            log(f"{RED}bad input: {e}{R}")


# --------------------------------------------------------------------------- demo
def demo():
    """Drive a fixed, decision-rich scenario through the SAME pure module, printing each frame.
    No typing — for AFK verification. The interesting lines are annotated."""
    reset()
    steps = [
        ("clean hit — 'toyota'/'camry' resolves straight through",
         lambda: do_observe("toyota", "camry")),
        ("typo/variant — 'Toyota'/'Camry Classical': does it auto-merge or propose?",
         lambda: do_observe("Toyota", "Camry Classical")),
        ("the trap — 'Toyota'/'Aurion': a REAL distinct car. Must NOT false-merge to Camry",
         lambda: do_observe("Toyota", "Aurion")),
        ("nameplate alias — 'Nissan'/'Versa' should hit the seeded Sunny alias",
         lambda: do_observe("Nissan", "Versa")),
        ("unknown make — 'Rivian'/'R1T': never auto-create a make (#11)",
         lambda: do_observe("Rivian", "R1T")),
        ("official value lands: fuel_type=Petrol @official-registry",
         lambda: do_claim("toyota:camry", "fuel_type", "Petrol", "official-registry", 0.95)),
        ("user tries to OVERRIDE it: fuel_type=Diesel @user — must lose (gap-fill only)",
         lambda: do_claim("toyota:camry", "fuel_type", "Diesel", "user", 0.99)),
        ("user gap-fills an EMPTY field: transmission=CVT @user — allowed, low conf",
         lambda: do_claim("toyota:camry", "transmission", "CVT", "user", 0.99)),
        ("community disagrees on transmission=Automatic — beats user, still capped",
         lambda: do_claim("toyota:camry", "transmission", "Automatic", "community", 0.95)),
    ]
    for title, act in steps:
        act()
        clear()
        print(render())
        print(f"\n{B}demo step:{R} {title}")
        print(f"{D}(pure-module frame above; interactive mode lets you drive your own){R}")
        input(f"{D}[enter for next step, ctrl-c to stop]{R}") if sys.stdin.isatty() else None
    # AFK final assertions so the demo self-verifies even piped
    reg = STATE["reg"]
    camry = STATE["cars"]["toyota:camry"]
    fuel = camry.value_of("fuel_type")
    trans = camry.value_of("transmission")
    def qkind(raw):
        return next((p.kind for p in STATE["queue"] if p.raw == raw), None)
    aurion_pending = any(p.raw == "Aurion" for p in STATE["queue"])
    print(f"\n{B}self-check{R}")
    checks = [
        ("'Camry Classical' routes to a MERGE proposal (collapses fragmentation)",
         qkind("Camry Classical") == "merge"),
        ("'Aurion' stays a NEW_MODEL proposal (distinct car, no false merge)",
         qkind("Aurion") == "new_model"),
        ("Aurion did NOT false-merge (is a pending proposal)", aurion_pending),
        ("fuel_type winner is the official Petrol, not user Diesel", fuel.winner.value == "Petrol"),
        ("fuel_type confidence is real & non-zero", fuel.confidence >= 0.9),
        ("empty-field transmission accepted a user claim then lost to community",
         trans.winner.tier == "community"),
        ("both transmission claims preserved", len(trans.claims) == 2),
    ]
    ok = True
    for label, cond in checks:
        ok = ok and cond
        print(f"   {(G+'PASS'+R) if cond else (RED+'FAIL'+R)}  {label}")
    print(f"\n{(G+'all checks passed'+R) if ok else (RED+'CHECK FAILED'+R)}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.exit(demo())
    interactive()
