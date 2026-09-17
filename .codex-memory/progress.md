# Progress

## 2026-09-17 Member workflows and self-service keys

- Added an opt-in, unauthenticated key page at `/admin/api-key`, sharing the login template.
- The user explicitly requires no identity verification. The backend checks registration, enabled status, active team membership, server ownership scope, and MCP permissions.
- Local `.env` enables `SELF_SERVICE_API_KEYS_ENABLED`; the default stays disabled. Existing processes require restart.
- Added `/admin/member-usage` for existing-account Excel imports, per-member server-scoped keys, and usage analytics.
- Imports reuse team membership. Unknown accounts are reported, not created. Importing grants the team's existing access.
- Added bounded MCP JSON/SSE metadata capture and migration `c31d7e4a092b`, following verified head `5e211ec89cad`.
- Metrics include request counts, protocol errors, latency, members, methods, keys, UTC trends, and explicitly reported model usage.
- Passed 12 unittest regressions, Ruff, ESLint, JavaScript syntax, migration idempotency, and migration downgrade checks.
- A live isolated gateway passed issuance, MCP initialize/tools-list, Excel import, distinct bulk keys, and analytics checks.
- Final read checks passed for method filters, statistics, Excel template, and absence of raw keys in analytics.
- Browser checks passed for login, the new admin entry, public team/server selection, and real analytics rendering.
- Automatic approval review rejected the browser's final key-generation click because it creates credentials. The API workflow passed before that rejection.
- Full repository gates remain unrun: this environment lacks make, pytest, ty, mypy, pyrefly, bandit, pylint, and interrogate.
- Stopped the isolated gateway and verified port 4445 is closed. Existing business services and data remain unchanged.

## 2026-09-16

- Fixed Windows JavaScript MIME mapping for the Admin UI.
- Reproduced incorrect response types against the existing gateway on port 4444.
- Verified both regression cases pass against the fixed gateway on port 4445.
- Verified authenticated A2A listing renders in the browser with PostgreSQL.
- Stopped the temporary test gateway. The existing gateway requires a user restart.

## 2026-09-16: MCP registration follow-up

- Reproduced JavaScript reverting to `text/plain` after constructing a resource service.
- Guarded MIME initialization to preserve previously registered types.
- Passed two regression tests and Ruff checks for changed Python files.
- Added a local MCP through the browser against an isolated SQLite test database.
- Verified discovery of one tool and one resource, page reload, and A2A navigation.
- Passed live JavaScript response checks after registration.
- Temporary gateway and MCP services stopped after testing. Existing user data remains unchanged.

## 2026-09-16 Team token page fix
- Fixed three translation-name collisions in the dashboard and token list templates.
- Added tests/live_gateway/test_team_token_page.py; four live request cases passed on port 4445. Ruff passed.
- Verified the existing ordinary-user browser session renders the selected team and token list. Stopped the temporary service.

## 2026-09-16 Token usage oversight
- Reproduced usage button HTTP 404: team token cards can include another user's token, but usage endpoint required ownership.
- Usage endpoint now permits unrestricted platform admins; aggregation uses the token owner's email.
- Ordinary and narrowed-admin callers retain ownership checks. Anonymous and API-token callers remain denied.
- Two unittest cases with eight access scenarios passed; Ruff passed. Live browser displayed four requests for the member token.
- Stopped temporary gateway on port 4445. Existing gateway requires restart.
