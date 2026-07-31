# 010 — Catalog readiness bar for Saudi (depth, missing makes, sub-brand burial, baw bug)

- Type: `wayfinder:grilling` + `task` (decision, then bounded fixes)
- Status: open (frontier — unblocked; 002 resolved)
- Blocked by: — (was 002, now resolved: parity says depth must reach Motory/YallaMotor spec-level, not just breadth)
- Assignee: —

## Question

The spine has GCC nameplates but **depth ~0%** (114/3,754 gens have specs, 1 has trims; LLM depth
engine ADR 0010 built-not-run) and Saudi-relevant fitness gaps: missing **Audi**, Lexus/Infiniti/
Genesis **buried** under parent makes (breaks make-level browse/facets Saudi buyers rely on),
`baw`=FAW data bug. Decide the catalog-readiness bar for Saudi launch: how much spec/trim depth
does the chosen surface (001) and parity benchmark (002) actually require, and do we run the LLM
depth engine over the SA-relevant model set now? The three fitness fixes (add Audi, un-bury the
luxury sub-brands, fix baw) are small and largely independent — decide fix-now vs defer.

Resolve to: a depth bar + a run/defer call on the LLM depth engine for SA models + a fix-now list
for the fitness gaps.
