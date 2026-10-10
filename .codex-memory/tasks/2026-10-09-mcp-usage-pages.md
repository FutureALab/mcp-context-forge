# Task: MCP Usage Pages

Tags: #task
Date: 2026-10-09
Scope: global
Status: completed

## Goal

- Add dashboard, analytics, and invocation audits following the supplied screenshots.

## Behavior

- Monitoring links open `#mcp-dashboard`, `#mcp-analytics`, and `#mcp-audit` in the existing administration interface.
- Dashboard shows connector status, tool inventory, 24-hour calls/errors, daily trends, and shortcuts.
- Analytics offers 7/30/90-day metrics and top-ten tools, connectors, virtual servers, and users.
- Audit supports status, literal search, connector/server filters, stable pagination, and expandable input/output details.
- Scope covers API Key-authenticated MCP `tools/call`. Initialization, discovery, and browser-session testing are excluded explicitly.
- Read APIs require `tokens.read` and unrestricted platform sessions; responses disable caching.
- Payload capture defaults off through `MCP_AUDIT_PAYLOADS_ENABLED`. Captured directions each have a 16384-character serialization limit.
- Capture normalizes embedded JSON before existing trace redaction. Missing historical content remains unknown.
- Existing JSON metadata stores the new details. No schema migration is required.

## Verification

- Python unittest: 39 tests pass, including existing member workflows and new aggregation, redaction, pagination, and deny cases.
- Vitest: 82 tests pass; final affected page/navigation rerun passes 73 tests.
- Ruff, ESLint, Vite production build, and diff whitespace checks pass.
- Live isolated gateway: 22 real calls, HTTP-200 protocol error, input/output redaction, filtering, pagination, anonymous/API-token/member/permission denials pass.
- Browser confirms all three pages, real metrics, rankings, filtering, and detail expansion.
- Full repository gates and PostgreSQL integration remain unrun. Required make/static-analysis/pytest tools are unavailable locally.

## Deployment

- Restart the gateway and refresh frontend assets. Keep `TOKEN_USAGE_LOGGING_ENABLED=true` for usage collection.
- Enable `MCP_AUDIT_PAYLOADS_ENABLED=true` when input/output retention is required. Historical missing payloads cannot be recovered.
- Cleanup on 2026-10-10 confirms temporary validation processes exited. Ports 4447 and 9010 have no TCP listener.
