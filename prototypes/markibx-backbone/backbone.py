"""
markibx canonical-backbone — PORTABLE LOGIC MODULE (prototype, throwaway TUI shell lives in tui.py)

This is the bit that answers the design question. Pure: no I/O, no printing, no terminal code.
The TUI imports it and calls in; nothing flows back out. If this ever references input()/print(),
it has stopped being liftable into the real markibx code.

It mirrors the shapes the PRD (D3-D6) commits to, deliberately simplified:
  - CanonicalRegistry : makes + models with aliases; resolve_make / resolve_model.
                        Resolution into the set is AUTO (confidence-gated); creation of a
                        canonical entity is a Proposal (human-gated). Makes NEVER auto-create.
  - resolve_field     : competing FieldClaims -> winner by trust tier, then effective confidence.
                        Lower tier index = more authority. Effective confidence is capped by the
                        tier ceiling, which is what makes "user can only gap-fill" fall out for free.
  - ingest_claim      : the catalog write path; every value enters as a tiered claim and the stored
                        value/confidence is whatever resolve_field currently elects.

The numbers (ceilings, threshold) are guesses on purpose — feeling them out is the whole point.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

# ---------------------------------------------------------------------------
# Trust tiers  (D6).  Order == authority.  Index 0 is most authoritative.
# ---------------------------------------------------------------------------
TRUST_TIERS = ("official-registry", "oem", "canon-game", "community", "user")
TIER_INDEX = {t: i for i, t in enumerate(TRUST_TIERS)}

# Per-tier confidence ceiling. A claim's *effective* confidence is min(raw, ceiling).
# This is the single knob that enforces "a low-trust source can only gap-fill, never override".
TIER_CEILING = {
    "official-registry": 1.00,
    "oem": 0.90,
    "canon-game": 0.75,
    "community": 0.60,
    "user": 0.40,
}


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


# ---------------------------------------------------------------------------
# Claims + conflict resolution  (D6)
# ---------------------------------------------------------------------------
@dataclass
class FieldClaim:
    field: str
    value: str
    source: str          # human-readable source name, e.g. "NHTSA vPIC"
    tier: str            # one of TRUST_TIERS
    raw_confidence: float  # what the source asserts, before the tier ceiling
    ts: float = field(default_factory=time.time)

    @property
    def effective_confidence(self) -> float:
        return min(self.raw_confidence, TIER_CEILING[self.tier])


@dataclass
class Resolution:
    winner: Optional[FieldClaim]
    confidence: float            # effective confidence of the winner (0.0 if no claims)
    claims: list[FieldClaim]     # ALL claims, preserved, best-first


def resolve_field(fld: str, claims: list[FieldClaim]) -> Resolution:
    """Deterministic: lowest tier index wins; ties break on effective confidence; then newest.
    All claims preserved. Empty -> confidence 0.0 (the honest 'we don't know' — today's prod
    stores this as a blind 0.0 for *every* field; here it means literally no claim)."""
    relevant = [c for c in claims if c.field == fld]
    if not relevant:
        return Resolution(None, 0.0, [])
    ranked = sorted(
        relevant,
        key=lambda c: (TIER_INDEX[c.tier], -c.effective_confidence, -c.ts),
    )
    winner = ranked[0]
    return Resolution(winner, winner.effective_confidence, ranked)


# ---------------------------------------------------------------------------
# Canonical registry + resolver  (D1, D3, D4, D5)
# ---------------------------------------------------------------------------
@dataclass
class CanonicalModel:
    id: str
    make_id: str
    display: str
    aliases: list[str]          # nameplate / regional aliases (D2)


@dataclass
class CanonicalMake:
    id: str
    display: str
    aliases: list[str]


@dataclass
class Proposal:
    """Emitted when resolution is not confident enough to auto-link. This is what lands in the
    moderation queue (D5). kind: 'new_make' | 'new_model' | 'merge'."""
    kind: str
    raw: str
    make_id: Optional[str]           # for models
    best_guess_id: Optional[str]     # nearest canonical entity, if any
    best_score: float


@dataclass
class ResolveResult:
    """Either an auto-link (canonical_id set) or a proposal for a human. Never both."""
    canonical_id: Optional[str]
    score: float
    proposal: Optional[Proposal]

    @property
    def auto_linked(self) -> bool:
        return self.canonical_id is not None


class CanonicalRegistry:
    def __init__(self, threshold: float = 0.82):
        self.makes: dict[str, CanonicalMake] = {}
        self.models: dict[str, CanonicalModel] = {}
        # threshold is a *setting* (D4/D5): started conservative, tuned by false-merge rate.
        self.threshold = threshold

    # ---- seeding (authority-first; D4) ----
    def seed_make(self, id: str, display: str, aliases: Optional[list[str]] = None) -> None:
        self.makes[id] = CanonicalMake(id, display, aliases or [])

    def seed_model(self, id: str, make_id: str, display: str,
                   aliases: Optional[list[str]] = None) -> None:
        self.models[id] = CanonicalModel(id, make_id, display, aliases or [])

    # ---- matching helpers ----
    def _best_make(self, raw: str) -> tuple[Optional[str], float]:
        best_id, best = None, 0.0
        for m in self.makes.values():
            for cand in (m.display, *m.aliases):
                r = _ratio(raw, cand)
                if r > best:
                    best_id, best = m.id, r
        return best_id, best

    def _best_model(self, make_id: str, raw: str) -> tuple[Optional[str], float, bool]:
        """Returns (id, ratio, contained). `contained` = the candidate nameplate's tokens are a
        subset of raw's (e.g. 'Camry' ⊆ 'Camry Classical') — the descriptor-suffix fragmentation
        pattern. Whole-string ratio alone scores that ~0.50 and misses it, so we track it apart."""
        raw_tokens = set(_norm(raw).split())
        best_id, best, best_contained = None, 0.0, False
        for m in self.models.values():
            if m.make_id != make_id:
                continue
            for cand in (m.display, *m.aliases):
                r = _ratio(raw, cand)
                cand_tokens = set(_norm(cand).split())
                contained = bool(cand_tokens) and cand_tokens < raw_tokens  # strict superstring
                # prefer a containment hit even if its raw ratio is lower
                score_key = (contained, r)
                if score_key > (best_contained, best):
                    best_id, best, best_contained = m.id, r, contained
        return best_id, best, best_contained

    # ---- resolution (D3/D4) ----
    def resolve_make(self, raw: str) -> ResolveResult:
        """Makes: resolve auto, but NEVER auto-create (#11). No confident match -> proposal."""
        best_id, score = self._best_make(raw)
        if best_id is not None and score >= self.threshold:
            return ResolveResult(best_id, score, None)
        return ResolveResult(
            None, score,
            Proposal("new_make", raw, None, best_id, score),
        )

    def resolve_model(self, make_id: str, raw: str) -> ResolveResult:
        """Models. Three outcomes:
          - auto-link : a near-exact/alias/typo match (high ratio, same nameplate) — no human.
          - merge proposal (gated) : a superstring descriptor ('Camry Classical' ⊇ 'Camry') OR a
            strong-but-not-certain fuzzy hit — probably this car, but aliasing is an *identity*
            change (D2/D5), so a human confirms. This is the case whole-string ratio used to miss.
          - new_model proposal : nothing close — a genuinely new/unknown model.
        """
        best_id, score, contained = self._best_model(make_id, raw)
        if best_id is None:
            return ResolveResult(None, 0.0, Proposal("new_model", raw, make_id, None, 0.0))
        # exact hit (ratio ~1.0) auto-links; a superstring never auto-links (it changes identity)
        if score >= self.threshold and not contained:
            return ResolveResult(best_id, score, None)
        if contained or score >= (self.threshold - 0.20):
            return ResolveResult(None, score, Proposal("merge", raw, make_id, best_id, score))
        return ResolveResult(None, score, Proposal("new_model", raw, make_id, None, score))

    # ---- human gate outcomes (D5) ----
    def approve(self, p: Proposal) -> str:
        """Apply an approved proposal. Returns the canonical id that now covers `raw`."""
        if p.kind == "new_make":
            new_id = _norm(p.raw).replace(" ", "-")
            self.seed_make(new_id, p.raw)
            return new_id
        if p.kind == "merge" and p.best_guess_id:
            self.models[p.best_guess_id].aliases.append(p.raw)  # collapse fragmentation
            return p.best_guess_id
        # new_model
        new_id = f"{p.make_id}:{_norm(p.raw).replace(' ', '-')}"
        self.seed_model(new_id, p.make_id or "?", p.raw)
        return new_id


# ---------------------------------------------------------------------------
# Provenanced catalog  (D6) — the write path everything funnels through
# ---------------------------------------------------------------------------
@dataclass
class CanonicalCar:
    id: str                       # model_id (+year in the real thing; year elided here)
    claims: list[FieldClaim] = field(default_factory=list)

    def ingest_claim(self, claim: FieldClaim) -> Resolution:
        """Every value enters here. We never mutate a field in place; we append a claim and
        re-resolve. The stored/served value is whatever resolve_field currently elects."""
        self.claims.append(claim)
        return resolve_field(claim.field, self.claims)

    def value_of(self, fld: str) -> Resolution:
        return resolve_field(fld, self.claims)

    def fields(self) -> list[str]:
        seen: list[str] = []
        for c in self.claims:
            if c.field not in seen:
                seen.append(c.field)
        return seen
