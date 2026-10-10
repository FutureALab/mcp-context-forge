# Task: Monitoring Design and Key Recovery

Tags: #task
Date: 2026-10-10
Scope: global
Status: completed

## Behavior

- Dashboard, analytics, and audit use separate cards, indigo accents, consistent spacing, segmented navigation, and status badges.
- Chart styling and ranked lists use the existing product palette and icon library.
- Self-service renewal returns the encrypted original Key and client configuration after password or Key-only SSO authorization.
- Recovery verifies the token owner, selected team, and virtual server before decrypting existing material.
- Responses disable caching. Recovery preserves Key material and the cumulative 365-day lifetime cap.
- Historical hash-only Keys show an explicit recovery limitation. Users contact an administrator when these Keys are lost.
- Existing management and bulk issuance contracts remain unchanged. No database migration is required.

## Verification

- Passed 41 Python tests and 82 JavaScript tests, including recovery, lifetime caps, unavailable material, and access denials.
- Ruff, ESLint, Vite production build, and diff whitespace checks pass.
- Isolated live gateway passes 22 real MCP calls, aggregation, pagination, redaction, and monitoring permission denials.
- Live recovery passes repeated retrieval, unchanged Key material, lifetime caps, cache headers, password, team, CSRF, and SSO denials.
- Browser checks confirm all three pages, audit filtering and expansion, and repeated Key/configuration display.
- Desktop and dark-theme layouts were inspected. Narrow-screen validation remains limited by the existing open sidebar.
- Full repository gates remain unrun because make and several required tools are unavailable.

## Runtime

- Stopped isolated validation processes and confirmed ports 4447 and 9010 have no listener.
- Started the configured preview gateway on localhost:4445. Its health endpoint returns 200.
- Kept the existing local parent-page server on port 5173. No deployment configuration changes are part of this task.

## Follow-up: Historical Hash-only Keys and White Background

- The user screenshot confirms the deployed Key has no encrypted material. Existing recovery cannot reconstruct its original value.
- Self-service now skips matching hash-only Keys during reuse and creates one encrypted, recoverable Key.
- Existing Key hashes, expiration, and active status remain unchanged. Later requests reuse the new recoverable Key.
- Management and bulk issuance retain their previous reuse behavior.
- This supersedes the administrator-contact behavior above for historical hash-only self-service Keys.
- The three monitoring pages use a white main background. Other administration pages retain their existing background.
- Passed 41 Python tests, 82 JavaScript tests, Ruff, ESLint, build, and whitespace checks.
- Live tests start with a hash-only Key and confirm both old and new Keys initialize MCP sessions.
- Browser confirms Key/configuration display, repeated retrieval, and white backgrounds on all three pages.
- Stopped the isolated test gateway on 4447. Restarted the configured preview on 4445 and confirmed health status 200.
