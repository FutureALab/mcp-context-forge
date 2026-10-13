# One browser authentication flow for login and API Key self-service

Date: 2026-10-13
Status: Implemented and verified.

- Password login on the Key page calls the existing `/admin/login` handler.
- The handler accepts only `/admin/api-key` as an additional return destination.
- OAuth Key login now creates the standard `jwt_token` browser session.
- Key endpoints require that session and no longer authenticate password bodies or `member_key_proof`.
- Existing endpoint names remain aliases; account identity comes from the verified session.
- Canonical session validation, resource scope, CSRF, and RBAC remain active.
- This supersedes legacy proof compatibility in [[2026-10-12-unified-key-session]].

Verification:

- Member workflow tests pass: 34 tests.
- Portal tests pass: seven tests.
- SSO router tests pass: 57 tests.
- Existing admin login handler tests pass: two tests.
- Frontend tests pass: 12 tests.
- Three live gateway flows pass, including ordinary, administrator, and password login sessions.
- Browser password login loads resources, renews a Key, and reopens the page without another password.
- Ruff, ESLint, and docstring coverage pass.
- Bandit reports two existing password-label false positives in unrelated admin code.
- Pylint reports existing SSO argument/import/style warnings; the changed routes add none.
- Full Makefile and production container checks remain unavailable on this Windows setup.

The temporary gateway requires cleanup after the next user filtering verification.
The user requests user search, role filters, and team filters next.

Follow-up: [[2026-10-13-user-filters]] records the completed filters and temporary service cleanup.
