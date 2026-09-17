# Current Task

## 2026-09-17: Expired session and Excel layout follow-up

- Screenshot confirms an expired login token blocked the MCP list; the loading placeholder survived the failed request.
- Requests now use the existing Admin token helper. Expired sessions show a top-of-dialog login link and disable mutations.
- Failed list requests replace the loading placeholder; network failures offer retry with a bounded read timeout.
- Excel uses a compact file card beside Key management, showing filename, size, and validation before import.
- Browser confirmed that fresh login loads and selects the MCP list. Existing expired sessions must sign in again.
- DOM regression, live gateway integration, ESLint, and production build pass. Test services are stopped.

## 2026-09-17: Password and embedded management revision

- The new password requirement supersedes email-only self-service below.
- Both options and issuance authenticate through EmailAuthService, including lockout and disabled-account policies.
- Team selection includes public MCP servers under canonical visibility rules. Issued tokens keep the recipient's selected Team scope.
- Monitoring now contains the member-usage tab, with charts, member/method/token tables, and local timestamps formatted YYYY-MM-dd HH:mm:ss.
- Per-server actions open an embedded Excel and bulk-key dialog. The catalog header also supports all-server batch issuance.
- Real tools/call tests confirm concrete tool names and protocol outcomes. Historical missing method metadata cannot be reconstructed.
- Restart the existing gateway and reload the browser after pulling changes. New Vite assets were built locally.
- Verification results are in [[progress]].

## 2026-09-17: Initial implementation (requirements superseded above)

- Implemented team-backed member imports, bulk server-scoped keys, member analytics, and the login-styled self-service key page.
- Initial requirement allowed email-only issuance; the later password requirement supersedes it.
- Membership follows the existing Team model. Imports accept registered, active accounts.
- Self-service remains feature-flagged by default; enabled locally through the ignored `.env` file.
- New MCP metadata only applies to newly recorded calls. Missing model usage stays unknown.
- Full verification and environment limits are recorded in [[progress]].
- Remaining operational action: restart the existing gateway to apply configuration, migration, routes, and templates.
- Browser final issuance click needs explicit test-account approval if further UI validation is requested.
