# Platform administrator portal login

Tags: #task #decision

Date: 2026-10-13
Status: Implemented and verified.

## Decision and behavior

- The user explicitly requests platform administrator login through the existing parent Cookie bridge.
- Both portal exchange purposes accept registered, active users, including platform administrators.
- Reusable parent authorization also accepts active administrator accounts.
- The gateway database remains authoritative for account status, administrator identity, and role permissions.
- The existing Cookie identity trust model also applies to administrator accounts.
- Preserve origin, feature, session validation, CSRF, membership, and resource permission checks.
- Keep API Key issuance restricted to the existing eligible Team choices.
- Update both parent integration guides to remove the separate administrator login requirement.

## Verification

- Pass seven portal route tests and 34 member workflow tests.
- Browser checks confirm administrator workspace access and automatic Key-page account detection.
- Switching to an ordinary account removes administrator permissions and preserves its Key-page access.
- Live gateway checks pass administrator login, authorization reuse, Key issuance, Team denial, and ordinary-account switching.
- The ordinary shared-session live regression also passes its authentication and permission denial cases.
- Pass Ruff, Bandit, Pylint, docstring coverage, mypy, ty, and pyrefly checks.
- Pylint scores 10.00. Docstring coverage is 100 percent.
- Native Alembic checks confirm one head and no branches.
- Native pre-commit checks pass except the documented unavailable or unrelated normalization hooks.
- Bash-dependent migration and file-header hooks remain unavailable. Native commands verify migration structure.
- Skip whole-file formatting and smart-quote normalization to preserve existing source and documentation formatting.
- Type checks target the changed live regression module.
- Rate-limit counters are shared by client IP across routes. Use separate test clients for the two exchange purposes.
- Existing unit-test context-manager formatting differs from the installed Ruff formatter.
- Preserve unrelated formatting and user changes.
- Full repository Makefile and production-container gates remain unavailable in this Windows environment.

## Scope

- Use fresh isolated databases and temporary gateway and parent services for verification.
- Stop all task-owned test services and confirm their ports have no listeners.
- Remove the isolated databases, token fixtures, and temporary browser tab after verification.
- Leave the configured preview and its database unchanged.
- Preserve unrelated environment, current-task memory, and tool-directory changes.
