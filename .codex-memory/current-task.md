# Current Task

## 2026-09-23: Separate OAuth login and Key authorization

- Workspace login can start the configured provider automatically with `/admin/login?auto_sso=corp-oidc`.
- Its callback creates the gateway session. The Key page starts a separate OAuth flow and receives a five-minute, Key-only proof.
- A gateway login cookie cannot authorize Key issuance; the Key proof cannot authenticate as a gateway JWT.
- Existing active OAuth users can claim Keys with current Team and MCP permission checks. The Key flow does not create accounts.
- Live isolated HTTP integration passed portal login, separate Key authorization, issuance, and MCP initialization.
- See [[tasks/2026-09-23-member-key-oauth]] for checks and remaining deployment inputs.

## 2026-09-23: HTTP intranet iframe rollout

- Documented HTTP deployment and exact parent-page changes in `infra/iframe-oauth/INTRANET-ROLLOUT.md`.
- The plan accounts for cookie, origin, iframe, OIDC, and Team permission requirements.
- Deployment-specific domains and identity-service endpoints still need operator values.
- See [[tasks/2026-09-23-http-intranet-iframe-rollout]].

## 2026-09-23: Complete iframe login and API Key claim

- The isolated portal shows MCP workspace and API Key buttons after the iframe session is ready.
- Demo startup enables self-service keys and seeds one public virtual MCP for the demo user.
- Live verification covers SSO, session-backed Key options, issuance, MCP initialization, and denial paths.
- The demo runs on ports 18080, 18081, and 4446 for user inspection.
- See [[tasks/2026-09-23-iframe-oauth-demo]] for setup and verification details.

## 2026-09-23: Member key OAuth and registration minimum

- OAuth Key authorization now uses a signed `state` marker. The provider callback URI stays unchanged.
- The final `mk:` marker has no overlap with regular OAuth nonces. Provider denials return to the Key page.
- The API Key page defaults to OAuth detection and retains a password mode switch.
- Superseded: the Key flow no longer uses the gateway browser session; it uses its own short-lived OAuth proof.
- New regular user passwords require at least 10 characters by default.
- The sidebar documentation and GitHub icons are removed.
- Targeted API and JavaScript tests passed. See [[tasks/2026-09-23-member-key-oauth]] for verification limits.

## 2026-09-23: iframe OAuth demo

- Implemented the isolated demo in `infra/iframe-oauth` using existing Nginx and Node images.
- Browser and live gateway checks confirm automatic iframe SSO and logout with a non-admin account.
- Test services are stopped. Restart the demo with its `start.ps1` script.
- Existing core authentication, deployment edits, root `.env`, and business database remain unchanged.
- See [[tasks/2026-09-23-iframe-oauth-demo]] for commands, constraints, and verification details.

## 2026-09-17: Supplied brand image and server key inventory

- Brand images now use the user-supplied PNG unchanged on login, password-change, sidebar, collapsed-sidebar, and favicon surfaces.
- Virtual MCP member management includes a paginated key inventory across all owners and teams for the selected server.
- Inventory includes active, expired, disabled, and revoked records. Unscoped general tokens are excluded explicitly.
- Metadata lists omit secret material. Detail and full Excel export decrypt persisted keys only on explicit requests.
- Historical hash-only records remain listed with an unavailable-original notice. No inventory action issues or renews keys.
- Inventory endpoints require tokens.read and unrestricted platform sessions. Detail also matches the requested server and token.
- Detail and export write audits without secret material. Export uses text cells and no-cache responses.
- Browser checks confirm five member records, details, secret clearing, and the supplied image.
- Passed 25 Python tests, 27 subtests, 99 JavaScript tests, Ruff, ESLint, build, and live gateway integration.
- Test services on ports 4445 and 9009 are stopped. Full repository gates remain unrun.

## 2026-09-17: Key retrieval and team switching

- New API tokens retain encrypted material alongside their verification hash. This supersedes the previous hash-only storage policy.
- Migration `d72f8a1c903e` follows verified head `c31d7e4a092b`; historical rows retain null encrypted material.
- Historical hash-only keys cannot be recovered. Retrieval reports this without replacing or renewing them.
- POST `/tokens/{id}/reveal` requires management authentication, tokens.read, and ownership or unrestricted platform administration.
- Narrowed sessions retain team restrictions. Successful reveals write an audit event without key material and disable response caching.
- Token lists expose a Chinese reveal/copy dialog. Closing it clears the displayed key.
- Team switching uses a bundled navigation module and Alpine 3 state access. Selector requests time out after 15 seconds.
- Browser checks confirm switching to a shared team and back after MCP registration, plus key retrieval and modal cleanup.
- Passed 23 Python tests, 15 subtests, 274 JavaScript tests, production build, Ruff, and live gateway integration.
- Product JavaScript lint passes. The existing formFieldHandlers test file retains three unrelated unused-variable lint findings.
- Test services on ports 4445 and 9009 are stopped. Full repository gates remain unrun.
- Restart the deployed gateway to apply the migration and refresh frontend assets.

## 2026-09-17: Shared-team management, lifetime cap, and branding

- Personal ownership does not restrict public MCP visibility. Authentication and RBAC still apply.
- Public MCP management now accepts an explicit shared team without changing resource ownership or visibility.
- Personal teams cannot receive members. The UI explains the restriction and requires a shared-team choice.
- Bulk issuance uses selected shared-team members. Downloads contain a real Excel workbook with formula-safe text cells.
- Renewal now caps expiry at original creation plus 365 days. Existing longer keys remain unchanged and cannot extend.
- This lifetime cap supersedes the uncapped extension behavior described below.
- Monitoring uses a continuous white surface and compact metrics. UI branding now displays MCP Gateway.
- Passed 19 Python tests, 9 subtests, 97 JavaScript tests, Ruff, ESLint, production build, and live gateway integration.
- Browser checks confirm branding, populated statistics, and shared-team selection for personal public MCP servers.
- Stopped both isolated test services on ports 4445 and 9009. The user's running service was not changed.
- Full repository gates remain unrun. Restart the deployed gateway and refresh the browser to apply changes.

## 2026-09-17: Chinese imports, monitoring, and renewable API keys

- Completed the four requested changes, including existing uncommitted implementation work.
- User imports provide Chinese guidance, a workbook template, and shared-team assignment with administrator scope checks.
- All issuance interfaces offer 180 and 365 days. Matching active server keys extend their existing expiry.
- Renewal requires the same owner, team, server, permissions, and restrictions. Expired or disabled keys get replacements.
- Creation responses expose `renewed`; renewal returns an empty raw key. Existing key material stays unchanged.
- Signed-expiry fallback validates signature, issuer, audience, exact registry hash, active status, server scope, and revocation.
- Monitoring provides six charts and includes unused active accounts. Tool trends fill empty UTC buckets with zero.
- Passed 61 Python tests, 97 JavaScript tests, lint, production build, and live gateway integration.
- Verified real tool calls and continued MCP access after signed JWT expiry on a registry-renewed key.
- Browser verification covers Chinese import controls, shared-team choices, and populated monitoring charts.
- Full repository gates remain unrun; this Windows environment lacks `make` and several required analysis tools.
- Existing `.env.example`, `.codegraph`, and `.cursor` changes remain outside this feature commit.


## 2026-09-17: Expired session and Excel layout follow-up

- Screenshot confirms an expired login token blocked the MCP list; the loading placeholder survived the failed request.
- Requests now use the existing Admin token helper. Expired sessions show a top-of-dialog login link and disable mutations.
- Failed list requests replace the loading placeholder; network failures offer retry with a bounded read timeout.
- Excel uses a compact file card beside Key management, showing filename, size, and validation before import.
- Browser confirmed that fresh login loads and selects the MCP list. Existing expired sessions must sign in again.
- DOM regression, live gateway integration, ESLint, and production build pass. Test services are stopped.

## 2026-09-17: Password and embedded management revision

- The new password requirement supersedes email-only self-service below.
- Both options and issuance authenticate through EmailAuthService, including lockout and disabled-account policies.
- Team selection includes public MCP servers under canonical visibility rules. Issued tokens keep the recipient's selected Team scope.
- Monitoring now contains the member-usage tab, with charts, member/method/token tables, and local timestamps formatted YYYY-MM-dd HH:mm:ss.
- Per-server actions open an embedded Excel and bulk-key dialog. The catalog header also supports all-server batch issuance.
- Real tools/call tests confirm concrete tool names and protocol outcomes. Historical missing method metadata cannot be reconstructed.
- Restart the existing gateway and reload the browser after pulling changes. New Vite assets were built locally.
- Verification results are in [[progress]].

## 2026-09-17: Initial implementation (requirements superseded above)

- Implemented team-backed member imports, bulk server-scoped keys, member analytics, and the login-styled self-service key page.
- Initial requirement allowed email-only issuance; the later password requirement supersedes it.
- Membership follows the existing Team model. Imports accept registered, active accounts.
- Self-service remains feature-flagged by default; enabled locally through the ignored `.env` file.
- New MCP metadata only applies to newly recorded calls. Missing model usage stays unknown.
- Full verification and environment limits are recorded in [[progress]].
- Remaining operational action: restart the existing gateway to apply configuration, migration, routes, and templates.
- Browser final issuance click needs explicit test-account approval if further UI validation is requested.
