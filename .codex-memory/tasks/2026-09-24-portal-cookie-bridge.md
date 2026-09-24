# Parent-page Cookie bridge

## Decision

- The parent Vue page writes `mcp_username` and `mcp_email` after its own login.
- No OIDC, Spring Boot Session lookup, or `X-Token` check is part of this flow.
- The gateway uses an opt-in Cookie exchange. This is custom SSO behavior, not OAuth protocol authorization.
- Existing local and other-provider accounts are not linked by email. Portal administrators cannot use the Cookie exchange.
- The historical ticket-use migration remains to support upgraded databases.

## Changed behavior

- `POST /auth/portal/exchange` accepts `purpose: login` or `purpose: key` and checks the exact parent Origin.
- Login creates an ordinary portal user when necessary and sets a one-hour HttpOnly gateway session.
- Key authorization requires an existing active portal user and sets a five-minute, Key-only proof.
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
