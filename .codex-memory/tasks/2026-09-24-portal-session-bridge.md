# Parent Session ticket bridge without OIDC

## Decision

- The user does not want to deploy OIDC. The existing parent uses Vue, Node, Spring Boot, and a browser Session Cookie.
- Spring Boot must derive identity from its server-side Session and sign a short-lived, purpose-bound ticket.
- The gateway exchanges each ticket once. Its database records the ticket ID across workers.
- Login creates a gateway session. Key authorization issues only the existing short-lived Key proof.
- An existing account with another provider is not linked by matching email.

## Changed behavior

- `POST /auth/portal/exchange` is disabled until `PORTAL_SSO_ENABLED=true` and the secret, issuer, and exact parent Origin are configured.
- A login ticket may create a non-admin account; a Key ticket requires an existing active portal account.
- The Key page can ask its parent iframe to renew authorization when its proof expires.
- `infra/portal-session-bridge/README.md` documents Spring Boot signing, Vue calls, HTTP deployment, and acceptance checks.

## Verification and limits

- Five focused Python tests and eight JavaScript tests passed.
- An isolated live gateway passed CORS, login, Key-only proof, scoped issuance, and MCP initialization.
- Ruff and migration upgrade/downgrade idempotency passed.
- The isolated gateway and test files were removed. Existing user services were left running.
- The real Spring Boot source is unavailable. Replace its Session attribute, CSRF header, domain, and secret placeholders before deployment.
