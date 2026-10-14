# Offline Release deployment guide

Date: 2026-10-14
Scope: global
Status: verified documentation

## Request and delivery

- Explain required and optional assets for Release build-1168227-38372867939-1.
- Expand infra/release-bundle/README.md with PostgreSQL preparation, secrets, HTTP login, two Compose examples, acceptance, troubleshooting, and upgrades.
- Keep the existing README packaging path. Future bundles include the guide without packaging code changes.
- Existing published archives retain their original README. The expanded guide is available from the repository.
- Read the published Compose asset to verify the exact image tags and env_file behavior.

## Decisions

- First deployments download the complete archive and its checksum. Standalone images, documents, Compose, and GitHub source archives are optional.
- Require an existing PostgreSQL connection. Preserve generated secrets and existing database encryption keys.
- Explain SECURE_COOKIES=false for direct HTTP access and explicit image tags in the released Compose.
- Provide gateway with Phoenix and gateway-only configurations. Disable trace export and remove Phoenix dependencies in the latter.
- Specify the original project name and selected Compose file before upgrade commands.

## Verification

- A fresh reader answers all five deployment questions after two wording fixes.
- Actual Docker Compose validates both examples with generated secrets and an encoded database password.
- Check secret preservation, external database mapping, HTTP cookies, port changes, and disabled Phoenix tracing.
- Both configurations reject an empty database URL. All 12 Bash command blocks pass syntax checks.
- Both architecture packaging regressions pass. No services or containers start.
- Target-host database connectivity and business MCP acceptance remain deployment steps for the operator.
- Preserve unrelated .env.example, .codex-memory/current-task.md, .codegraph, and .cursor edits.
