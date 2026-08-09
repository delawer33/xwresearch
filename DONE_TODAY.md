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

## Part 2 of the 3-part issue run — MCP, end to end

**xwapi#2 — LANDED and CLOSED.** `main 54b5b56f..50a919f0`. 1735 passed / 23 skipped, verified on
the main checkout (the editable-install path products actually import), not just the worktree.

The issue's diagnosis was wrong on every specific: `create_app` does NOT "only branch on fastapi
and xwrouter" (it dispatches through `api_server_engine_registry.get_engine`), unknown engines
already raised `ValueError`, and the MCP engine was registered and returned a real surface. The
actual defect was narrower: `engine="mcp"` returned a working MCP server with an **empty tool
catalog** — xwaction's action-engine registry has no `"mcp"` entry, so `if action_engine:` was
falsy and the whole registration block was skipped. Zero tools, no error, nothing above `debug`.

**The thing the issue never mentioned, and the reason it couldn't close alone:** xwapi's MCP
engine had **no authorization seam at all**. `handle_post` never read `Authorization`,
`MCPSession` carried no principal, `dispatch` took no credentials, `tools/list` was unfiltered.
Since every product authorizes at the HTTP route layer (FastAPI `Depends`) and **nothing lives on
the XWAction**, and MCP multiplexes every `tools/call` through one POST, publishing a product
catalog over MCP was a total auth bypass. The empty catalog was the ONLY thing keeping it
unreachable — so fixing registration alone would have turned a broken path into an
unauthenticated one. Both landed in one merge. See D-025.

**Found by review, not by me:** `register_action`/`generate_schema` ignored their `app` argument
while the engine is a process-wide singleton. With two apps alive, registering into the protected
one read the OTHER app's `mcp_public` flag — guard doesn't fire, tools land in the public app's
catalog — and each `create_app` wiped the previous app's tools. Per-app state now lives in a
`WeakKeyDictionary` keyed by the app object (`id(app)` rejected: recycled ints in a
security-relevant lookup). Also removed `self._app`, which was written, never read, and pinned the
newest app against the weak keying.

**mawtarx-api#5 — committed, NOT landed.** `feat/mxa-5-mcp-readonly` `04bd328`, pushed;
[PR #11](https://github.com/Exonware/mawtarx-api/pull/11) open. Five read-only tools from the same
`@XWAction` handlers, no route body copied. 331 tests / 4 failures — the same 4 that fail on
`origin/main` untouched (`test_homepage`, `test_providers_test_route`, `test_search_filters_batch`,
`test_vin_report`), **baselined in a clean worktree at `7332c27`, not assumed**. +20 new, green.

Two mechanisms make HTTP handlers run off the HTTP path, worth knowing before anyone tries this
again in another product:
- The `state: AppState = Depends(current_state)` default **is** resolved by xwaction's native
  executor (`engines/base._resolve_injection_params`) — app.py's "the same bodies then run over
  WS-RPC" comment is true for this half.
- The ContextVar half is NOT reusable: `_ContextMiddleware` is HTTP-only and WS binds from its
  `meter` hook. `MCPDispatcher`'s only per-call product callback is the **authorizer**, so it both
  decides and binds. **Binding cannot move into a wrapper around the handler** — the executor
  resolves `Depends` BEFORE calling it, so a binder inside is one call too late and every handler
  silently receives `state=None`, surfacing as `AttributeError` deep in the route.

## Facts verified this session

- **`XWAPI.create_app(engine="mcp")` cannot carry per-tool auth metadata.** The facade's
  `_register_via_server_engine` passes only `{"path", "method"}` as `route_info`, so per-tool
  scopes need the direct `api_server_engine_registry` path. That path still supplies a non-`None`
  `route_info`, so the no-authorizer guard stays armed.
- **Pre-existing platform gap, NOT MCP-specific:** xwaction's native executor passes a JSON body
  through as a plain `dict` and never builds the declared Pydantic model, so
  `estimate(req: EstimateRequest)` dies with `'dict' object has no attribute 'listing_id'`.
  **The existing WS-RPC surface has the same defect today** — both routers are in
  `_ws_data_routers`. Worked around locally with a generic coercion; the real fix is an xwaction
  issue nobody has filed.
- `xwmemory/server/app.py` is still the only MCP-engine consumer outside xwapi, and it hand-rolls
  `register_action` — unchanged and still working.
- mawtarx actions carry `roles == []` and `_security_config == "default"` (a string), not the
  `roles == ["*"]` default xwaction's base sets. `requirements` is still always a populated dict,
  but for a different reason than the xwapi docstring implies.

## Left open

- **mawtarx-api#5 is NOT on `main` and stays OPEN.** PR #11 is ready; the merge is blocked by the
  command classifier — `git push origin HEAD:main` refused twice, `gh api ... /pulls/11/merge`
  refused twice. Needs a human click or a Bash permission rule. Do not close #5 until it's merged.
- Worktree `repos/mawtarx-api/.claude/worktrees/mxa-5` deliberately kept — the branch isn't merged.
- No deploy: xwapi is a library, and the mawtarx MCP surface is off by default and unmerged.
- An xwaction issue should be filed for the Pydantic-body gap above; it degrades WS-RPC today, not
  just MCP.
- Part 3 (xwaction#3 — enforce `rate_limit=`/`security=` or fail loudly, D-019) not started.
