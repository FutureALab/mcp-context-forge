# Task: Independent parent integration guide

Tags: #task

Date: 2026-10-12
Scope: global
Status: completed

## Outcome

- Add a Chinese integration guide for an independent intranet parent application.
- Document separate Nginx and gateway hosts, identity Cookies, iframe handling, and authentication interfaces.
- Provide a native JavaScript example with visible errors and account-switch cleanup.
- Link the guide from deployment navigation and the existing bridge README.

## Interface Constraints

- Initial exchange trusts browser identity Cookies without validating the parent backend session.
- Parent authorization tokens, workspace sessions, and MCP API Keys have separate uses.
- The Key page requires its own proof and CSRF Cookie, not the workspace session alone.
- Parent logout does not revoke issued gateway credentials.
- Ignoring stale responses cannot guarantee suppression of their Set-Cookie headers.

## Verification

- Passed local-link, navigation, YAML, environment-name, and source-route checks.
- Passed JavaScript syntax and JSON example checks.
- Simulated login, Key exchange, token reuse, error display, message validation, and stale-result cleanup.
- Completed independent reader review and addressed its three findings.
- No services started for this documentation task.

## Remaining Deployment Checks

- MkDocs is absent from the available Python environment; full documentation build remains unverified.
- Validate the documented flow against the actual intranet parent application and deployed gateway.
- Preserve unrelated environment, current-task memory, and tool-directory changes.

## Frontend Scope Correction

- The user requests a short frontend-only guide. Replace deployment and backend sections with the exchange contract.
- Document login triggers, response fields, minimal iframe code, error display, and account-switch cleanup.
- The earlier work summary and validation describe the initial draft, not the final document.
- The final examples pass syntax, JSON, simulated login/Key, error-display, and iframe-message checks.

## Shared Session Revision

- Replace the earlier separate-proof requirement with the shared `jwt_token` session behavior.
- Login and Key exchange establish the same session. An authenticated parent opens `/admin/api-key` directly.
- Shorten the guide to the parent interface, response fields, login trigger, Cookie ownership, and error handling.
- The gateway manages `mcpgateway_csrf_token`. The parent does not set `member_key_proof`.
- Preserve the identity-Cookie trust boundary and gateway logout requirement.
- Verify JSON and JavaScript syntax, login/Key examples, encoded Cookies, failure messages, and iframe message validation.
- These example checks use browser mocks. The actual intranet deployment check remains outstanding.
