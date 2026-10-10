# Task: Intranet deployment delivery

Tags: #task

Date: 2026-10-10
Scope: global
Status: completed

## Goal

- Commit the latest image-packaging changes with detailed parent integration and Kylin deployment documentation.

## Work Summary

- Compile Chinese catalogs during Containerfile builds and check the catalog in release smoke steps.
- Package the deployment guides and parent helper separately from Docker image archives.
- Document the existing Cookie bridge without implementing OAuth or changing login behavior.
- Preserve the local example credential edits and tool directories outside the delivery commit.

## Decisions And Learnings

- Initial Cookie exchange trusts browser identity fields and does not validate the parent backend session.
- Parent authorization defaults to 12 hours. Workspace sessions and Key proofs retain shorter lifetimes.
- Parent logout does not revoke issued parent tokens, gateway sessions, or MCP API Keys.
- Kylin deployments require architecture matching. Current bundles cover amd64 and arm64 only.
- Existing MO mounts override translations shipped by an upgraded image.

## Verification

- 54 i18n tests passed using isolated memory-database settings and existing temporary pytest dependencies.
- Six portal ASGI integration tests and four JavaScript helper tests passed.
- Gettext compilation and the Chinese Language assertion passed. Ruff passed for the compiler module.
- Documentation examples, local links, workflow YAML/Bash/Python, Compose, and Nginx configuration checks passed.
- The workflow documentation packaging step produced the expected four-file archive.

## Remaining Environment Checks

- Build the complete gateway image and execute its release smoke checks in CI.
- Run the documented acceptance flow on the actual Kylin host and parent application.
- Run MkDocs and repository-wide gates where their required tooling is installed.
