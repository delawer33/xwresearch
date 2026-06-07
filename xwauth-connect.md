# xwauth-connect — Developer Report

**Package:** `exonware-xwauth-connect` v0.0.1.11 | **License:** Apache 2.0 | **Python:** 3.12+

---

## A. What the Repo Does

`xwauth-connect` is the **external identity provider connector** for the eXonware auth stack. It provides:

- OAuth 2.0 / OIDC client-side support for 250+ external providers (Google, Apple, Microsoft Entra, GitHub, Discord, LDAP, SAML, and many more)
- Token generation and validation (JWT/opaque), session management, CSRF protection
- Federation core — bridges external IdP tokens to the local identity system
- HTTP handlers (FastAPI-compatible) for SSO callbacks and provider discovery
- Lazy-loading provider registry — providers are indexed at import but not loaded until first use

**Invariant:** This package **never imports** `exonware.xwauth.identity`. Both share the `exonware.xwauth` namespace via pkgutil. xwauth-connect discovers xwauth-identity at runtime via `discover_identity_package()`.

---

## B. Backend Architecture

- **Pattern:** I-prefix Protocols + A-prefix Abstract classes + provider registry
- **Async-first:** 560+ `async def`
- **Framework:** FastAPI-compatible HTTP handlers via `exonware.xwapi.http`
- **Provider pattern:** `ABaseProvider` base class with 3 URL fields + field-mapping override per provider; 150+ concrete one-file implementations
- **Lazy loading:** `exonware-xwlazy` indexes providers by name without importing them; first `get_connection_class()` call triggers import
- **Key dependencies:** PyJWT, cryptography, authlib, oauthlib, webauthn, exonware-xwsystem == 0.9.0.43, exonware-xwaction, exonware-xwschema

---

## C. Main Folders and Files

```
src/exonware/xwauth/connect/
├── __init__.py            — Discovery helpers: discover_identity_package(), identity_is_available()
├── facade.py / base.py    — ABaseAuth, ABaseProvider (shared abstract classes)
├── contracts.py           — I-prefix Protocol interfaces
├── defs.py                — Enums (GrantType, TokenType, ProviderType 250+, ...)
├── errors.py              — Exception hierarchy
├── api_paths.py           — HTTP route prefix constants
├── ops_hooks.py           — Operational lifecycle hooks
├── providers/             — 185+ provider implementation files
│   ├── base.py            — ABaseProvider (auth URL, token exchange, userinfo, PKCE, CSRF)
│   ├── registry.py        — ProviderRegistry: register, lookup, list
│   ├── callback_providers.py — Dynamic discovery of callback-capable providers
│   ├── google.py          — GoogleProvider (86 lines)
│   ├── github.py          — GitHubProvider (91 lines)
│   ├── microsoft.py       — MicrosoftProvider
│   ├── apple.py           — AppleProvider (JWT-based token exchange)
│   ├── discord.py, slack.py, linkedin.py, twitter.py, ...  (individual providers)
│   ├── keycloak.py, auth0.py, okta.py  — Enterprise OIDC wrappers
│   ├── tier1_global_essential_providers.py  — Aliases: Microsoft365, X (Twitter)
│   ├── enterprise_tier2_oidc.py             — Enterprise IAM stubs
│   ├── apac_india_sea_cis_stubs.py          — APAC/CIS stub providers
│   ├── china_wecom_unionpay_stubs.py        — China enterprise stubs
│   ├── latam_fintech_retail_stubs.py        — LATAM stubs
│   ├── mea_emea_fintech_stubs.py            — MEA/EMEA stubs
│   ├── eidas_europe_providers.py            — EU eIDAS providers
│   └── tier6_non_oauth_stubs.py             — Non-OAuth placeholder stubs
├── handlers/
│   ├── _common.py         — OpenAPI tags, auth instance getters
│   └── mixins/sso_providers.py — SSO callback handlers (hard-coded email keys + extra attrs)
├── oauth_http/
│   ├── errors.py          — RFC 6749 error-to-HTTP mapping
│   └── __init__.py        — OAuth metadata discovery helpers
└── scripts/
    ├── protocol_governance_check.py
    └── split_legacy_mixins.py
```

**Docs:** 65+ files in `docs/` — GUIDE_* (usage, migration from Keycloak/Auth0/Supabase, SAML, SCIM), REF_* (architecture, operations, compliance, interop).

---

## D. Data Models and Entities

**Enums** (`defs.py`):

| Enum | Values |
|------|--------|
| `GrantType` | authorization_code, client_credentials, resource_owner_password, refresh_token, device_code, token_exchange |
| `TokenType` | JWT, OPAQUE, BEARER, MAC |
| `ResponseType` | code, token, id_token, + hybrid combinations |
| `ClientType` | PUBLIC, CONFIDENTIAL |
| `SessionStatus` | ACTIVE, EXPIRED, REVOKED, TERMINATED |
| `UserStatus` | ACTIVE, PENDING, SUSPENDED, DISABLED, DELETED |
| `MFAMethod` | TOTP, SMS, EMAIL, WEBAUTHN, BACKUP_CODE |
| `ProviderType` | 250+ entries (auto-merged from all provider files) |

**Protocol contracts** (`contracts.py`):

```python
IProvider:    provider_name, provider_type, get_authorization_url(), exchange_code_for_token(), get_user_info()
ITokenManager: generate_access_token(), generate_refresh_token(), validate_token(), revoke_token()
ISessionManager: create_session(), get_session(), revoke_session()
IAuthenticator: authenticate(credentials) -> str | None
IAuthorizer:  check_permission(user_id, resource, action) -> bool, get_user_roles()
IRateLimiter: check_rate_limit(), increment_counter()
IAuditLogger: log_event(event_type, details)
```

---

## E. APIs, Endpoints, and Services

**HTTP path prefixes** (`api_paths.py`): `/v1/oauth2`, `/v1/oidc`, `/v1/oauth1`, `/v1/auth`, `/v1/users`, `/v1/admin`, `/v1/organizations`, `/v1/webhooks`, `/scim/v2`, `/v1/system`, `/health`, `/metrics`.

**Handler mixins** (`handlers/mixins/sso_providers.py`):
- Explicit SSO callbacks for: `google`, `microsoft`, `apple`, `github`, `discord`, `slack`, `saml`
- Generic callback route for all other 240+ providers (discovered dynamically via `discover_oauth2_callback_provider_names()`)
- Per-provider email field extraction: `google → "email"`, `microsoft → "email" or "userPrincipalName"`, `github → "email"`, etc.
- Per-provider extra attributes: `google → picture`, `github → login, avatar_url`, `slack → real_name, team_id, team_name`

**Provider Registry** (`providers/registry.py`):
- `ProviderRegistry.register(name, class)` — add provider
- `ProviderRegistry.get(name)` — retrieve (triggers lazy load)
- `discover_oauth2_callback_provider_names()` — list all callback-capable providers

**`ABaseProvider`** (`providers/base.py`) — core flow for all providers:
- `get_authorization_url(client_id, redirect_uri, state, scopes, nonce, code_verifier)` — builds auth URL + PKCE
- `exchange_code_for_token(code, redirect_uri)` — HTTP POST to token_url
- `get_user_info(access_token)` — HTTP GET to userinfo_url
- `_get_authorization_params()` — override hook for provider-specific params

---

## F. Auth, Security, Config, and Env Variables

**Security features in providers:**
- PKCE (S256) generated in `ABaseProvider.get_authorization_url()` if `code_verifier` provided
- CSRF state parameter passed through and validated by caller
- Token encryption via `exonware.xwsystem.security`
- Per-provider OIDC issuer and JWKS URI (e.g., Google: `https://accounts.google.com`)

**Configuration (`XWAuthConfig`):** same 60+ fields as xwauth (see [xwauth.md](xwauth.md) section F).

**Env variables:**
- `XWSTACK_SKIP_XWLAZY_INIT` — skip xwlazy initialization at import
- `XWAUTH_CONNECT_DISABLE_IDENTITY_DISCOVERY=1` — disable xwauth-identity runtime discovery

**Optional extras** (`pyproject.toml`):
- `[lazy]` — exonware-xwlazy (smart dependency install)
- `[xw]` — full XW stack (xwdata, xwentity, xwjson, xwmodels, xwnode, xwquery, xwstorage-connect)
- `[full]` — httpx, redis, lxml, signxml (SAML)
- `[dev]` — pytest, pytest-asyncio, pytest-cov

---

## G. Database, Storage, Queues, and Background Jobs

- **No direct database dependency.** Storage contracts (`IStorageProvider`) delegate to the calling application.
- Session and token persistence handled by `exonware-xwstorage-connect` when the `[xw]` extra is installed.
- Audit logging and rate limiting can be backed by any storage.
- No built-in queues. Background webhook delivery is caller responsibility.

---

## H. How to Run Locally

```bash
pip install "exonware-xwauth-connect[dev]"

# Run tests
pytest tests/                    # all
pytest tests/0.core/             # core OAuth2/OIDC/SAML/PKCE, installation, import parity
pytest tests/1.unit/             # per-subsystem unit tests
pytest tests/2.integration/      # multi-provider flows, error recovery
pytest tests/3.advance/          # deep security tests

# Test lazy loading
python -c "from exonware.xwauth.connect import discover_identity_package; print(discover_identity_package())"
```

**Minimal usage:**
```python
from exonware.xwauth.connect.providers.google import GoogleProvider

provider = GoogleProvider(
    client_id="your-client-id",
    client_secret="your-client-secret",
    redirect_uri="https://example.com/callback/google",
)

auth_url = await provider.get_authorization_url(
    client_id="your-client-id",
    redirect_uri="https://example.com/callback/google",
    state="random-state",
    scopes=["openid", "email", "profile"],
)
# redirect user to auth_url...

token_data = await provider.exchange_code_for_token(code=code, redirect_uri=redirect_uri)
user_info = await provider.get_user_info(token_data["access_token"])
```

---

## I. Tests Available and Tests Missing

**Available (102 test files across 4 levels):**

| Path | Focus |
|------|-------|
| `tests/0.core/` | OAuth2, OIDC, PKCE, PAR, SAML, device code, DCR, RFC compliance, import validation, lazy mode |
| `tests/1.unit/` | Authorization, config, federation, security, tokens, sessions, SCIM, organizations, JOSE, ops, interop lab |
| `tests/2.integration/` | Multi-provider flows, complete auth flow, error recovery, new features |
| `tests/3.advance/` | Deep security testing |
| `tests/fixtures/interop_lab/` | Pre-recorded provider responses for offline testing |

**Tests missing / gaps:**
- Most of the 250+ individual provider files have no dedicated tests; behavior is tested only through `ABaseProvider`
- Stub providers (`apac_india_sea_cis_stubs.py`, `tier6_non_oauth_stubs.py`, etc.) have no test confirming they raise `XWProviderError` correctly
- Lazy loading only tested via `tests/1.unit/utils/test_lazy_mode_example.py` — no test that a full provider import chain works after lazy trigger
- Handler mixin `sso_providers.py` email-key and extra-attrs mappings not covered by dedicated tests

---

## J. Risks, Unclear Parts, and Questions

**J1 — 150+ shallow provider files (~18,000 lines, 50–80% boilerplate)**
Every provider in `providers/` is ~70 lines where ~55 are copy-paste of `ABaseProvider`. The unique content per provider is: 3 URL strings + 1 field-mapping dict. YouTube provider has 0 unique lines (pure alias to Google). Verified: `google.py` = 86 lines / ~66 boilerplate, `github.py` = 91 lines / ~70 boilerplate. At 150+ files this is ~10,000 lines of maintainable but identical structural code.

**J2 — Stub provider classes as code, not data**
`apac_india_sea_cis_stubs.py`, `china_wecom_unionpay_stubs.py`, `latam_fintech_retail_stubs.py`, `mea_emea_fintech_stubs.py`, `tier6_non_oauth_stubs.py` each define an identical `_StubBase` (35 lines) that raises `XWProviderError("nonstandard_oauth_flow")` on every call. Sub-classes add only a `_hint: str`. This pattern is duplicated 5 times and results in 50+ stub classes that could be replaced by a `ProviderStub(name, hint)` factory.

**J3 — Handler mixin hard-codes provider metadata**
`handlers/mixins/sso_providers.py` hard-codes email field keys and extra attributes per provider in dicts at module level. Adding a provider that has a non-standard email field requires editing the handler — not the provider class. This is tight coupling between presentation and provider logic.

**J4 — Contracts duplicated with xwauth and xwauth-identity**
`IProvider`, `ITokenManager`, `ISessionManager`, `IAuthenticator`, `IAuthorizer` in `contracts.py` are byte-identical to those in `xwauth/contracts.py` and `xwauth-identity/contracts.py`. Nominal type inequality across packages. (See [xwauth.md J2](xwauth.md))

**J5 — Runtime discovery function duplicated verbatim**
`discover_identity_package()` in this package and `discover_connect_package()` in xwauth-identity are 35-line byte-for-byte copies. See [xwauth.md J2](xwauth.md).

**J6 — `cargo-cult exchange_code_for_token` in some providers**
`github.py` lines 54–72: overrides `exchange_code_for_token()`, constructs a data dict, then calls `super().exchange_code_for_token()` which ignores the dict. The override has no effect. Similar patterns may exist in other providers.

---

## K. Suggested First Improvements

**K1 — Replace per-provider classes with a data-driven registry (highest impact)**
Define a `ProviderDefinition` dataclass: `name, provider_type, authorization_url, token_url, userinfo_url, extra_params, field_map`. Ship a `PROVIDERS: list[ProviderDefinition]` and a `build_provider(defn)` factory that returns an `ABaseProvider` subclass. This reduces 150+ files (~18,000 lines) to a single registry file (~3,000 lines) with zero behavior change.

**K2 — Replace stub base classes with a single `ProviderStub` factory**
```python
def ProviderStub(provider_name: str, provider_type: ProviderType, hint: str) -> type[ABaseProvider]:
    ...
```
Replace the 5 stub base classes and 50+ stub sub-classes with `registry.register(ProviderStub("mixi", ProviderType.MIXI, "Historical mixi..."))`. Eliminates ~2,000 lines.

**K3 — Move email-key and extra-attrs metadata into provider definitions**
Add `email_keys: tuple[str, ...]` and `extra_attrs: tuple[str, ...]` to `ABaseProvider` (or `ProviderDefinition`). Remove the hard-coded dicts from `sso_providers.py`. Handlers read from the provider object. Adding a new provider no longer requires touching the handler.

**K4 — Unify contracts (same as xwauth K2)**
Extract `IProvider`, `ITokenManager`, etc. to a shared location. See [xwauth.md K2](xwauth.md).

**K5 — Move discovery helpers to xwsystem**
`discover_connect_package()` / `discover_identity_package()` are identical generic patterns. Move to `exonware.xwsystem.utils.discover_optional_package(module_name, disable_env_var)`. Both packages call the shared function.
