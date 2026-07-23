# Prototype — markibx canonical backbone (logic)

> **Throwaway.** Answers one design question by hand. The keepable bit is `backbone.py`
> (pure, liftable into the real `markibx`); `tui.py` is a disposable shell. Not production.

Run interactively:  `python3 tui.py`
Run the scripted, self-checking demo (no typing):  `python3 tui.py --demo`

## The question

The D3–D6 loop of `docs/markibx-canonical-backbone-design.md` looks clean on paper:
raw strings **resolve** into canonical IDs (auto if confident, else a human-gated **proposal**),
and field values enter as **tiered claims** that `resolve_field` ranks so a low-trust source can
only gap-fill. Two things only *feel* wrong once you push cases through by hand:

1. **Where does the resolve threshold actually sit** between "auto-collapse `Camry Classical`
   into `Camry`" (good — that's the fragmentation we exist to kill) and "false-merge `Aurion`
   into `Camry`" (catastrophic — a real distinct car erased)?
2. **Does the tier/ceiling math** genuinely stop a `user` claim from clobbering an
   `official-registry` value, while still producing a real non-zero confidence (today's prod is a
   blind 0.0)?

## What driving it revealed

**Finding (the reason this prototype earned its keep):** whole-string similarity
(`SequenceMatcher` ratio) *mis-scores the dominant real-world fragmentation pattern* — the
descriptor suffix. `Camry Classical` vs `Camry` scores only **0.50**, because the extra word
dominates the string. On the first pass that dropped it into a **`new_model`** proposal — i.e.
the resolver's instinct was to *create a fourth Camry variant*, the exact opposite of its job.
Meanwhile `Aurion` (a genuinely distinct car) correctly sat at 0.36. A single scalar ratio
**cannot separate "same nameplate + extra word" from "different car."**

**Decision it forced (now encoded in `backbone.py`):** model matching is **token/containment-
aware**, and a *superstring* match gets its own outcome — a **gated `merge` proposal**, distinct
from both auto-link and `new_model`:

- **auto-link** — near-exact / alias / typo (high ratio, same nameplate): no human.
- **merge proposal (human-gated)** — candidate nameplate ⊆ raw tokens (`Camry` ⊂ `Camry
  Classical`), *or* a strong-but-uncertain fuzzy hit. Probably the same car — but aliasing is an
  **identity change** (D2/D5), so a curator confirms. A superstring **never auto-links**, because
  silently folding `Aurion`-shaped strings would be how false-merges happen.
- **new_model proposal** — nothing close: a real unknown model.

Result, verified by the demo's self-checks: `Camry Classical` → **merge**, `Aurion` →
**new_model**, `Rivian` make → gated (never auto-created). The one scalar threshold was a trap;
containment is a separate axis from similarity and has to be modelled as one.

**On the claim engine (question 2): confirmed sound as designed.** `user`-tier `Diesel` could not
displace `official-registry` `Petrol` (served 0.95, real and non-zero); a `user` value *did*
gap-fill an empty `transmission` field and then correctly lost to a later `community` claim; all
competing claims stay preserved. The tier ceiling carries the "gap-fill only" guarantee with no
extra gate needed — exactly what D6 claimed. No change required there.

## What to lift into real markibx

`backbone.py`'s `_best_model` containment axis + the three-outcome `resolve_model` belong in the
real **CanonicalResolver** (PRD module #1). The `resolve_field` / `ingest_claim` shapes matched
the existing `conflict.resolve_field` + `VehicleSourceRef` design and needed no change — that part
of the design is validated, not revised.
