# Shared login session for API Key self-service

Date: 2026-10-12
Status: Implemented and functionally verified.

## Request and decision

- Use the existing browser login session for API Key self-service.
- Both portal exchange purposes set the same HttpOnly `jwt_token` session type.
- A logged-in parent opens `/admin/api-key` directly without another exchange.
- Keep legacy OAuth proofs compatible when no login session Cookie exists.

## Behavior

- The page automatically queries memberships when a login session Cookie exists.
- The backend uses `get_session_user()` for signature, expiry, revocation, and account validation.
- Only session tokens qualify; API tokens and Authorization headers cannot issue self-service Keys.
- An invalid login session does not fall back to a legacy proof.
- The canonical resource scope limits Team choices and issuance.
- Existing CSRF, membership, server visibility, permissions, and feature checks remain active.
- Parent integration documents describe the shared session.

## Verification

- Python regression tests: 40 passed, including 29 subtests.
- Frontend regression tests: 15 passed.
- Live gateway HTTP regression passes login, issuance, and denial cases.
- Browser verification passes one login exchange, direct iframe navigation, automatic resource queries, and Key renewal.
- Ruff, Bandit, docstring coverage, ESLint, and new-test type checks pass.
- Pylint reports two pre-existing `_check_server_access` protected-access warnings.
- Pylint scores 10.00 when those pre-existing warnings are excluded.
- Bash-based Alembic hooks cannot run because WSL lacks `/bin/bash`.
- Native Alembic checks confirm one head and no branches.
- Native pre-commit lint, content, syntax, and whitespace checks pass.
- Preserve pre-existing smart quotes and formatting outside the changed behavior; omit those normalization hooks.
- The file-header hook remains blocked by WSL; its native check reports pre-existing header and Windows path differences.
- Review secret-scanner false positives and update only this task's baseline entries.
- Windows lacks `make`; full repository Makefile checks and the production container gate remain unverified.

## Scope

- Preserve unrelated `.env.example` and `.codex-memory/current-task.md` edits.
- Use a temporary virtual environment and an isolated live database.
- Task-owned gateway, parent server, and browser are stopped; both HTTP ports reject connections.
