# Complete offline Release bundle

Date: 2026-10-13
Scope: global
Status: pushed; live build verification pending

## Goal

- Create a downloadable Release after each successful Docker Release Bundle run.
- Include images and engineering files for offline Docker deployment.

## Findings

- Run 38353545474 succeeds but skips Release upload, Compose attachment, and Release verification.
- Its workflow artifact expires on 2026-10-27. The original image archive omits PostgreSQL.
- The original Compose requires PostgreSQL. Manual builds without release_tag produce only temporary artifacts.

## Changes

- Resolve the requested source to an immutable commit before architecture builds.
- Generate build-<sha>-<run-id>-<attempt> tags when release_tag is empty.
- Add PostgreSQL to the gateway and Phoenix image archive.
- Add complete architecture archives containing images, committed source, Compose, templates, guides, checksums, and image metadata.
- Exclude real .env files and local memory/tool directories from committed source archives.
- Generate deployment secrets once. Reject an existing .env to preserve encryption secrets during upgrades.
- Test extracted archives with docker compose up --pull never, gateway health, login HTML, and a frontend stylesheet in CI.
- Aggregate all requested architectures before publication. Check tag/source consistency and uploaded asset sizes.
- Publish newly created draft Releases only after upload verification. Keep existing standalone image and documentation assets.
- New build Releases are prereleases and do not replace the latest stable Release.

## Verification

- 13 focused pytest tests pass with isolated Git fixtures and simulated GitHub CLI calls.
- Tests cover both architectures, source filtering, missing PostgreSQL, wrong architecture, metadata resolution, and secret preservation.
- Publication tests cover success, source mismatch, upload failure, and incomplete remote assets.
- Ruff, formatting, Bandit, Interrogate, Pylint, ty, mypy, and pyrefly pass for the two new Python files.
- Mypy ignores missing third-party stubs because PyYAML stubs are absent locally.
- Workflow YAML, 13 Bash steps, init-env.sh, and generated Compose configuration pass checks.
- No local services or containers start during these checks.

## Publication

- The user authorizes the push on 2026-10-13.
- Commit 43e7ff3e416386372c8fc5bdf25794d3da4bd911 reaches origin/feature_20260917_dev.
- GitHub reports the matching branch commit after the push.
- The user plans to run the packaging workflow. No workflow run starts during this push.

## Remaining Checks

- Build and start the gateway/Phoenix/PostgreSQL bundle in GitHub Actions. Local gateway and Phoenix images are absent.
- Run repository-wide make gates where make is installed. No PR readiness claim is made.
- Validate the package on the target Kylin host.
- Preserve unrelated .env.example, .codex-memory/current-task.md, .codegraph, and .cursor changes.

## 2026-10-13 follow-up: external database and publication fix

- This follow-up supersedes the original bundled PostgreSQL decision.
- The user requests removal of the PostgreSQL image. Keep Phoenix for gateway tracing.
- Package only gateway and Phoenix images, metadata, and Compose services.
- Require GATEWAY_DATABASE_URL for an existing PostgreSQL instance. Remove generated database credentials and database volumes.
- Keep PostgreSQL only as a temporary CI test container outside the exported archive. Clean up its container and network.
- Run 38361188387 passes image builds and extracted-package startup. Release publication fails with HTTP 422.
- Draft Release creation does not create its Git tag. The following commit lookup therefore fails.
- Create missing tags at the source SHA before creating drafts. Verify the tag before uploading assets.
- Publish existing drafts after successful upload verification. Preserve existing published Release status.
- Reproduce the old publication failure with a missing-tag fixture. Pass 17 focused regression tests after the fix.
- Pass Python quality checks, workflow YAML parsing, 12 Bash syntax checks, and actual extracted Compose validation.
- Actual Compose validation requires an external database URL and configures only gateway and Phoenix images.
- No local services or containers start. Local gateway and Phoenix images remain absent.
- The revised live startup and GitHub publication require a new workflow run from the updated branch.
- Full repository make gates and target Kylin verification remain pending. make is absent locally.
