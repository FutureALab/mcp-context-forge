# Progress

## 2026-09-17 Public MCP follow-up verification

- Reproduced personal-team import rejection and owner-only bulk membership in an isolated database.
- Added explicit shared-team selection for public MCP management, preserving visibility and ownership boundaries.
- Live checks cover Excel member import, selected-team bulk issuance, real workbook export, and original-key MCP calls.
- Repeated 180/365/30-day requests stop at original creation plus 365 days without replacing the key.
- Deny-path tests cover personal/inactive teams, wrong-team nonpublic MCP management, and nonadmin exports.
- Export cells remain strings, including formula-looking input. Responses disable caching and do not persist raw keys.
- Final validation: 19 Python tests and 9 subtests; 97 JavaScript tests; Ruff, ESLint, Vite build; live gateway integration.
- Browser checks confirm the white statistics surface, MCP Gateway logo, and enabled batch action after shared-team selection.
- Test gateway PID 45592 and upstream MCP PID 38420 are stopped; ports 4445 and 9009 have no listeners.
- Full repository gates remain unrun because the Windows environment lacks make and required analysis tools.

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


## 2026-09-17: Password, monitoring tab, and server member dialog

- Added required passwords to self-service options and issuance. Existing authentication enforces failures and lockout.
- Fixed public MCP discovery across Team ownership while preserving membership, visibility, and RBAC restrictions.
- Moved analytics into Monitoring and member imports/bulk keys into the Virtual MCP Servers page.
- Added Chart.js trends and method ranking. Tables display concrete tool names and local YYYY-MM-dd HH:mm:ss timestamps.
- Passed 14 Python regressions, 88 JavaScript tests, Ruff, ESLint, and the Vite production build.
- Live isolated integration passed password checks, key issuance, real upstream tools/call, Excel import, distinct member keys, and method-filtered analytics.
- Browser verified the Monitoring tab, real chart/table rendering, per-server dialog, password entry, and Team/public-server discovery.
- Historical records without MCP metadata remain explicitly unknown. New tools/call records include method, concrete tool, outcome, and time.
- Full repository gates remain unavailable as noted above; targeted integration completed successfully.
- Stopped both isolated validation services and verified ports 4445 and 9009 are closed. Existing business services remain unchanged.


## 2026-09-17: Recover member-list failures and refine Excel UI

- Fixed persistent loading placeholder after an expired-token response. Login recovery now appears at the top of the dialog.
- Added list retry, read timeout, and compatibility with the existing Admin authentication helper.
- Replaced native file-row layout with a file selection card, validation feedback, and responsive two-column actions.
- Expanded DOM regression to cover expired sessions, failed reads, retry recovery, invalid files, and server-specific FormData submission.
- Live gateway integration passed, including authenticated list retrieval, actual Excel import, issuance, and MCP calls.
- Browser confirmed list selection and final layout after login. ESLint and Vite build passed.
- Stopped isolated services and verified ports 4445 and 9009 are closed.

## 2026-09-17: Import, expiry, and monitoring refinement

- Added Chinese user-import guidance, Excel template download, and shared-team assignment.
- Added 180/365-day choices and stable-key renewal across member, bulk, and token API issuance.
- Exposed renewal status in API responses and retained exact existing key material.
- Added six monitoring charts, compact legends, horizontal rankings, and zero-filled tool trends.
- Passed 61 Python regressions, 97 JavaScript regressions, Ruff, ESLint, and the Vite production build.
- Live gateway tests passed template import, duplicate handling, team assignment, both token APIs, and real MCP tool calls.
- A registry-renewed key passed live MCP authentication after its signed JWT expiration.
- Browser verified populated charts and Chinese import controls. Full repository gates remain unrun.
- Stopped isolated gateway and upstream MCP test processes after validation.
