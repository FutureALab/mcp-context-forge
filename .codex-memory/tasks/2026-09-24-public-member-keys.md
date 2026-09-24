# Personal workspace and public MCP Keys

- Date: 2026-09-24
- The Key page includes active personal teams and a public MCP choice.
- A registered non-admin user can request a public-only server-scoped Key without Team membership.
- The issuer uses the existing Layer 1 visibility check and the caller's global or personal RBAC permissions.
- Team and private MCP Keys retain active Team membership checks. Administrators cannot request public-only Keys through self-service.
- Verified with 23 Python member workflow tests, 9 JavaScript tests, Ruff, ESLint, and local HTTP asset checks.
- The local parent page must refresh its embedded Key page after deploying these changes.
