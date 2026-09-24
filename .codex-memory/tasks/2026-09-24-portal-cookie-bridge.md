# Parent-page Cookie bridge

## Decision

- The parent Vue page writes `mcp_username` and `mcp_email` after its own login.
- No OIDC, Spring Boot Session lookup, or `X-Token` check is part of this flow.
- The gateway uses an opt-in Cookie exchange. This is custom SSO behavior, not OAuth protocol authorization.
- Existing local and other-provider accounts are not linked by email. Portal administrators cannot use the Cookie exchange.
- The historical ticket-use migration remains to support upgraded databases.

## Changed behavior

- `POST /auth/portal/exchange` accepts `purpose: login` or `purpose: key` and checks the exact parent Origin.
- Login requires an existing active, non-admin MCP account and sets a one-hour HttpOnly gateway session.
- Key authorization requires the same registered account and sets a five-minute, Key-only proof.
- The iframe reports expired workspace or Key credentials to the parent page, which shows a refresh prompt.
- Cached auth context now preserves the user ID for UUID-subject session validation.
- `infra/portal-session-bridge/README.md` contains the Vue and HTTP deployment contract.

## Verification and limit

- Four focused Python route tests and ten JavaScript tests passed. Ruff and ESLint passed on changed source.
- Isolated live HTTP checks passed Cookie login, `/auth/validate`, workspace iframe loading, Key options, scoped Key issuance, and missing-Cookie denial.
- Test gateways stopped and temporary databases were removed.
- The real parent Vue project was not available. Browser-writable identity Cookies do not prove the parent login state.

## Local browser verification

- Added `infra/portal-session-bridge/local-test.html` to test the parent Cookie flow with buttons instead of DevTools Console paste.
- Windows Python serves `.js` as `text/plain`, so the standalone test page uses an inline script.
- Browser verification passed against an isolated gateway on port 4445: the login iframe loaded the workspace, and the Key iframe loaded the account's Team.
- Port 8000 was unavailable on this host. The test page accepts a different gateway address.
- The isolated gateway and static server stopped. The temporary SQLite database and log were removed.

## Registered-account restriction

- Removed Cookie-login account creation. Both exchange purposes reject unknown or disabled email accounts with 403.
- Existing local and portal ordinary accounts can use the Cookie bridge; administrators still use the administrator login.
- MCP identifies users by email. `mcp_username` must be present but is not matched to the display name.
- The exchange response contains only `next`; it does not return a long-lived token to the parent page.
- Four route tests and Ruff passed. Browser checks confirmed unknown-account denial, normal registered-user workspace login, and Key-page Team lookup.
- Test services stopped, and the disposable database and log were removed.

## Reusable parent authorization token

- The exchange now returns `token` and `expires_at` with `next`. The earlier `next`-only response is superseded.
- The parent sends this token in later exchange request bodies. A valid token works without identity Cookies.
- An expired token falls back to identity Cookies. A changed `mcp_email` Cookie selects the new account.
- The token has a separate signing key and audience, is checked against current account status, and defaults to a 60-minute lifetime.
- The Vue example uses `sessionStorage` and clears the token on logout. The two iframe Cookies retain their existing lifetimes.
- Six Python route tests and four JavaScript helper tests passed. Ruff and ESLint passed.
- Live browser checks passed workspace login, token reuse for the Key page, and Team lookup. Test services and SQLite files were removed.

## Twelve-hour token and demo page

- The parent authorization token now defaults to 720 minutes. The iframe login and Key proofs keep their shorter lifetimes.
- `local-test.html` shows the Cookie, token, and iframe steps, token status, expiry, and both page entries.
- Browser verification confirmed first authorization, token reuse, workspace loading, Key page Team lookup, and clearing parent credentials.
- Six Python route tests and Ruff passed. Both temporary services stopped, and test database files were removed.

## Demo connection diagnosis

- A screenshot showed the demo opened through `file://` while no gateway listened on port 8000.
- The demo now instructs users to serve it from `http://localhost:5173` and reports gateway connection failures clearly.
- The account's email-verification checkbox does not cause the browser's `Failed to fetch` error.
- The served HTTP page now shows a specific gateway connection error. The in-app browser blocked direct `file://` verification.

## Two-service local setup

- A later screenshot showed the 5173 static server serving the page while port 8000 had no gateway listener.
- The local guide now starts the gateway and static page in separate PowerShell windows, then points the form at the gateway's actual port.
- The demo explains that port 5173 only serves the page. No running gateway or user database was changed during this diagnosis.

## Windows Python environment

- The base `I:\anaconda\python.exe` lacks `uvicorn`; `I:\anaconda\envs\py312\python.exe` has it.
- The local guide now starts the gateway with the `py312` interpreter and UTF-8 console output.
