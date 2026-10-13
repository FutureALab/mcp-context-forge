# User search, role filters, and team filters

Date: 2026-10-13
Status: Implemented and verified.

- The users page searches email or full-name prefixes without case sensitivity.
- Role filters include the account administrator flag and active assigned RBAC roles.
- Team filters require active membership in an active team.
- Combined role and team filters require a global role or a role assigned to the selected team.
- Expired or inactive role assignments do not match.
- Filters apply before pagination and counting. Duplicate assignments do not duplicate users.
- Pagination, page-size changes, and refresh keep the selected filters.
- A new search starts on page one. Reset clears all filters.
- The existing user-management permission remains required.

Verification:

- Three persisted-query tests pass, including inactive assignments and literal wildcard searches.
- Seven existing users partial tests pass.
- The live gateway filter test passes, including unauthenticated and insufficient-permission requests.
- Browser combination search, reset, page-size changes, and second-page results pass.
- Ruff, HTMLHint, Pylint, Bandit, docstring coverage, mypy, ty, and pyrefly pass for the applicable files.
- The three live shared-session authentication flows pass again with these changes.
- Full Makefile and production container checks remain unavailable on this Windows setup.

The temporary gateway and parent server stop after verification.
Ports 4462 and 4463 have no listeners. Existing services on 4445 and 5173 remain running.
The shared browser authentication change is committed as `ab048f5c`.
See [[2026-10-13-browser-session]] for that change and its verification.
