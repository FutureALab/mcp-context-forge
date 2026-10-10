# Progress

## 2026-10-09: MCP usage pages

- Added three monitoring pages with real invocation metrics, UTC daily charts, four rankings, connector status, and audit filters.
- Added administrator-only read APIs, paginated audits, and optional bounded payload capture using the existing JSON metadata column.
- Fixed redaction of JSON embedded in escaped upstream text. Ambiguous historical connector matches remain unknown.
- Passed 39 Python tests and 82 JavaScript tests. Final changed JavaScript and navigation rerun passed 73 tests.
- Ruff, ESLint, Vite production build, and diff whitespace checks pass.
- Isolated live SQLite gateway verification passes 22 real tool calls, MCP errors with HTTP 200, pagination, payload redaction, and permission denials.
- Browser confirms charts, populated rankings, error filtering, and expandable audit details.
- Final cleanup on 2026-10-10 confirms validation processes exited and no TCP listener remains on ports 4447 and 9010.
- Full repository gates remain unrun because required tools are absent. PostgreSQL integration remains unrun.

## 2026-10-09: Local portal startup recovery

- Reproduced the 60-second startup timeout and confirmed PostgreSQL `localhost:5432` was unavailable.
- Verified `--demo-db` startup, portal login, workspace HTML, Key options, and public-only Key issuance over HTTP.
- Default startup now fails in about six seconds with a PostgreSQL diagnostic. Ruff, Python compilation, and diff checks passed.
- Stopped both test services and removed only the temporary databases created during verification.

## 2026-09-24: Personal workspace and public MCP Key choices

- Python member workflow suite passed: 23 tests, including HTTP options/issuance and deny paths.
- JavaScript member workflow suite passed: 9 tests. Ruff and ESLint passed on changed files.
- Local gateway served the updated Key page and JavaScript from port 4445.
- The test gateway was stopped; port 4445 has no listener.
- The Python 3.12 environment lacks pytest. Ruff format check reports existing CRLF formatting across the touched Python files.

## 2026-09-24: Parent-page Cookie bridge

- Replaced the ticket exchange with a parent-cookie exchange and simplified the Vue iframe helper.
- Login and Key authorization remain separate. Expired iframe credentials prompt a parent-page refresh.
- Fixed cached session users losing their ID, which caused `/auth/validate` to reject valid UUID-subject sessions.
- Four Python route tests, ten JavaScript tests, Ruff, and ESLint passed.
- Isolated live HTTP checks passed workspace loading, session validation, Key options, scoped Key issuance, and missing-Cookie denial. Test services were stopped and test databases removed.
- The real parent Vue page remains unavailable for deployment validation.

## 2026-09-24: Parent Session ticket bridge

- Added a disabled-by-default parent ticket exchange route, replay table, migration, Key-page UI path, Vue helper, and Spring Boot integration guide.
- Denial tests cover missing feature, bad Origin, invalid/expired/replayed ticket, wrong purpose, unregistered Key user, local account collision, and disabled account.
- Live isolated gateway passed CORS preflight, browser login, session-only Key denial, separate Key proof, scoped Key issuance, and MCP initialization.
- Five Python tests, eight JavaScript tests, Ruff, and migration idempotency passed.
- Stopped the isolated gateway on port 4451 and removed its temporary database and secrets.
- The actual parent Spring Boot code is not in this repository; the guide documents its required Session and CSRF integration points.

## 2026-09-23: Separate OAuth login and Key proof

- Added a Key-only signed proof with a five-minute lifetime and separate signing key.
- Kept the gateway session for normal OAuth login and added an opt-in automatic provider start on the login page.
- Updated the HTTP parent-page example for automatic login and independent Key authorization.
- Isolated live HTTP flow passed portal login, Key OAuth, scoped Key issuance, and MCP initialization.
- Three focused Python unittest cases, eight JavaScript tests, Ruff, compilation, and diff whitespace checks passed.
- Pytest callback tests remain unrun because pytest is unavailable in the Python 3.12 environment.
- Stopped the isolated gateway on port 4450. Existing demo services were not modified.

## 2026-09-23: HTTP intranet iframe rollout

- Added a deployable HTTP plan and parent-page example beside the iframe demo.
- Verified JavaScript syntax, gateway setting names, README link, Markdown whitespace, HTTP callback allowlisting, and Cookie flags.
- No live intranet IdP or parent platform was available for end-to-end deployment verification.

## 2026-09-23: Complete iframe login and API Key claim

- Added authenticated portal buttons for the MCP workspace and API Key page.
- Demo startup enables self-service keys and seeds an idempotent public virtual MCP.
- Live HTTP verification passes OAuth, iframe SSO, Key issuance, MCP initialization, denial paths, and logout.
- Six Node test groups, one Vitest UI test, Ruff, Python compilation, ESLint, and Compose validation pass.
- The isolated demo remains running for user inspection. Existing business services remain unchanged.

## 2026-09-23: Member key OAuth

- Completed the signed `mk:` state flow with the provider's unchanged callback URI.
- In-process HTTP checks passed for start, unregistered and registered callbacks, and provider denial.
- Five focused JavaScript tests, ESLint, runtime Ruff, and Python compilation passed. Pytest remains unavailable locally.
- Replaced the callback query marker with a signed OAuth `state` marker after the user requested the standard callback flow.
- Added registered-user-only OAuth callback handling for the Key page and session-backed options and issuance.
- Preserved password authentication as a separate choice. Registration schemas and default user policy now require 10 characters.
- Focused Python API, cookie authentication, JavaScript, ESLint, and Ruff checks passed.
- The local Python 3.12 environment lacks pytest. A real external OAuth provider was not used for this check.

## 2026-09-23: iframe OAuth demo

- Added an isolated parent portal, OIDC fixture, and two-port Nginx configuration.
- Passed six Node test groups and real gateway SSO, permission, framing, CORS, list, and logout checks.
- Browser confirms parent login automatically opens the actual MCP Admin UI inside the iframe.
- Stopped the demo containers and gateway. Ports 18080, 18081, and 4446 are closed.
- Ruff, ESLint, compilation, Nginx syntax, and Compose checks pass. Full repository tools remain unavailable.
- Details: [[tasks/2026-09-23-iframe-oauth-demo]].

## 2026-09-17 Server key inventory verification

- Added database-backed server key listing, detail retrieval, and complete Excel export.
- Tests include cross-owner/team history, pagination, general-token exclusion, missing originals, status changes, and formula-safe export cells.
- Deny tests cover nonadmin sessions, API tokens, narrowed admins, and mismatched server/key pairs.
- Live export returns every matching row even when the list page limit is one. Original key material and expiry remain unchanged.
- DOM checks cover detail display and clearing, including a delayed response after the dialog closes.
- The supplied PNG and deployed asset have matching SHA-256 hashes. No image pixels were changed.
- Passed 25 Python tests plus 27 subtests, 99 JavaScript tests, Ruff, ESLint, Vite build, and live integration.
- Browser confirms the supplied branding and five member key records with detailed permissions.
- Stopped gateway PID 43940 and test MCP PID 14232. Ports 4445 and 9009 have no listeners.
- Full repository gates remain unrun. Restart the deployed gateway and refresh browser assets after applying this commit.

## 2026-09-17 Key retrieval and team navigation verification

- Added encrypted token persistence with the existing encryption service and an idempotent nullable-column migration.
- Retrieval validates management authentication, owner/admin access, team scope, and the stored token hash.
- Tests cover reopening storage, renewal preserving the original key, historical null values, and rejected unauthorized access.
- Live checks compare retrieved material with the issued key, verify real MCP calls, and confirm lists omit secret fields.
- Browser checks confirm the reveal dialog, clearing secrets on close, and team navigation after registering an MCP server.
- Final checks pass: 23 Python tests plus 15 subtests; 274 JavaScript tests; Ruff; product ESLint; Vite production build.
- Existing formFieldHandlers.test.js has unrelated unused-variable lint findings at lines near 184, 450, and 525.
- Migration heads report only d72f8a1c903e. Upgrade/downgrade tests preserve historical token hashes.
- Test gateway PID 23908 and upstream MCP PID 41160 are stopped. Full repository gates remain unrun.

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
