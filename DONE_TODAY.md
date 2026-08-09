# Done today — 2026-08-09

## Formal doc system adopted — placement gate now fires at plan time

- Cloned the company's formal doc system (`Exonware/docs`) into `repos/docs` and made it
  discoverable: two CLAUDE.md trigger rows + a `/pull-repos` entry keep it synced and findable.
- Wired its 7-question placement/boundary gate into the project-level `/grill-me`,
  `/grill-with-docs`, and `/design` skills: any new dependency/package/module now gets a
  Pass/Findings/Block verdict while planning, not at implementation time.
- GUIDE_16 LLM rules (pin model, schema-validate output, verify before store writes) added as
  one-line rare-case pointers only, per owner feedback; commented on xwai#2 that schema-validated
  output is now a formal gate blocking the planned markibx LLM depth engine.
- Swept all ~50 repos: only `xwdata` fast-forwarded (stock orjson dropped); 6 repos left behind
  (kara-web 84, xwui 147, xwmemory 8, mawtarx-api 4, xwnode 3, kara-connect 2) because other
  sessions' uncommitted edits collide — theirs to land. Deliberately NOT adopted: the
  adopt-persona session ritual, xwmemory MCP wiring (Linux native bundle unproven), and the 5
  persona-vs-practice conflicts (PR-only, deploys, rm, paths) — owner parked them, current
  practice stands.

## MCP end to end — auth seam landed in xwapi, mawtarx surface built but not merged

- **xwapi#2 closed**: `main 54b5b56f..50a919f0` — `engine="mcp"` had returned a working server with an **empty tool catalog** (xwaction's registry has no `"mcp"` entry, so registration was silently skipped); 1735 passed / 23 skipped on the merged main checkout.
- Shipped the **authorization seam the issue never mentioned**: MCP had none at all, and since product auth is FastAPI `Depends(...)` at the route layer with nothing on the XWAction, publishing any product catalog over MCP was a total auth bypass — the empty catalog was the only thing keeping it unreachable, so fixing registration alone would have opened it (D-025).
- Review caught a second bypass: `register_action` ignored its `app` argument while the engine is a process-wide singleton, so with two apps alive the guard read the **other** app's `mcp_public` flag and tools landed in the public catalog — now per-app state in a `WeakKeyDictionary`.
- **mawtarx-api#5 built, green, NOT merged**: `feat/mxa-5-mcp-readonly` `04bd328` pushed, [PR #11](https://github.com/Exonware/mawtarx-api/pull/11) open; 5 read-only tools off the same `@XWAction` handlers, service-token auth only (D-024), off by default.
- Proved pre-existing so nobody re-debugs them: mawtarx-api's 4 failures of 331 (`test_homepage`, `test_providers_test_route`, `test_search_filters_batch`, `test_vin_report`) fail identically at `7332c27`; deliberately did **not** patch xwaction for the Pydantic-body gap below.

## Left open

- **mawtarx-api#5 stays open** — merge classifier-blocked (5 refusals, 3 command shapes); needs a human click on PR #11. Worktree `mxa-5` kept until then.
- **Unfiled xwaction defect**: the native executor never builds declared Pydantic bodies, so `estimate(req: EstimateRequest)` dies — **the live WS-RPC surface has this today**, not just MCP.
- `XWAPI.create_app(engine="mcp")` can't carry per-tool scopes (facade passes only `{"path","method"}`) — products must use the direct registry path.
- Part 3 (xwaction#3 — enforce `rate_limit=`/`security=` or fail loudly, D-019) not started.
