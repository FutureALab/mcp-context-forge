# Progress

## 2026-09-16

- Fixed Windows JavaScript MIME mapping for the Admin UI.
- Reproduced incorrect response types against the existing gateway on port 4444.
- Verified both regression cases pass against the fixed gateway on port 4445.
- Verified authenticated A2A listing renders in the browser with PostgreSQL.
- Stopped the temporary test gateway. The existing gateway requires a user restart.

## 2026-09-16: MCP registration follow-up

- Reproduced JavaScript reverting to `text/plain` after constructing a resource service.
- Guarded MIME initialization to preserve previously registered types.
- Passed two regression tests and Ruff checks for changed Python files.
- Added a local MCP through the browser against an isolated SQLite test database.
- Verified discovery of one tool and one resource, page reload, and A2A navigation.
- Passed live JavaScript response checks after registration.
- Temporary gateway and MCP services stopped after testing. Existing user data remains unchanged.

## 2026-09-16 Team token page fix
- Fixed three translation-name collisions in the dashboard and token list templates.
- Added tests/live_gateway/test_team_token_page.py; four live request cases passed on port 4445. Ruff passed.
- Verified the existing ordinary-user browser session renders the selected team and token list. Stopped the temporary service.
