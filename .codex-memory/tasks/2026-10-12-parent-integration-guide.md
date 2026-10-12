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
