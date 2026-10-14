# Single deployment package and Release numbering

Date: 2026-10-14
Scope: global
Status: implemented and verified locally; new live workflow run pending

## Requirements and decisions

- The user requests one complete deployment package and regular Release numbers.
- The user chooses v<application-version>-r.<workflow-run-number>, such as v1.0.10-r.8.
- Read the application version from the checked-out pyproject.toml. New runs increment the workflow number; retries retain it.
- Keep application code versions unchanged. Record the Release tag and application version separately in VERSION.json.
- Publish only one complete archive and its checksum per selected architecture.
- Keep image archives in runner temporary storage. Include images, source, Compose, templates, and guides inside the complete package.
- Stop publishing standalone image archives, document archives, and Compose files. Preserve previously published Release assets.
- GitHub source ZIP and tar links remain platform-generated. They are not deployment assets.
- Keep existing-tag rebuilds and source/tag matching checks.

## Verification

- Pass 22 focused release tests, including sequential numbering, retry numbering, exact output files, and remote asset checks.
- Publication checks reject extra files, missing checksums, and corrupted archives. Both architectures remain supported.
- Pass Ruff, formatting, Bandit, Interrogate, Pylint, ty, mypy, and pyrefly checks.
- Use the existing Python environment explicitly for ty and pyrefly. Do not change system environment configuration.
- Pass packaging CLI integration with isolated image fixtures. Validate the extracted Compose against actual Docker Compose.
- Pass workflow YAML parsing, 10 workflow Bash steps, and 12 documented Bash blocks.
- No services or containers start. Live image build/startup and remote publication require the next Actions run.
- Repository-wide make gates remain unrun because make is absent. No PR-readiness claim is made.
- Preserve unrelated .env.example, .codex-memory/current-task.md, .codegraph, and .cursor edits.
