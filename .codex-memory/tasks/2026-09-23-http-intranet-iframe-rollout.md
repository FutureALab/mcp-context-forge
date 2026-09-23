# HTTP intranet iframe rollout

- Added `infra/iframe-oauth/INTRANET-ROLLOUT.md` for the current HTTP intranet setup.
- The plan uses a shared OIDC provider with separate parent and gateway clients.
- The parent page checks a gateway session and embeds the workspace or API Key page.
- Same-site HTTP requires matching scheme and site; same-IP different-port deployment shares Cookie names.
- Current code forces Secure cookies in `ENVIRONMENT=production`; HTTP requires staging or development and `SECURE_COOKIES=false`.
- Non-localhost HTTP OAuth callbacks require an exact `ALLOWED_ORIGINS` match and IdP support.
- Without corporate OIDC, local account/password issuance remains available but does not provide parent-to-gateway SSO.
- Verified the example JavaScript parses and every listed gateway setting exists in `config.py`.
- An in-process check confirms exact HTTP callback allowlisting and staging-versus-production Cookie flags.
- Actual intranet hostnames, IdP compatibility, and live end-to-end validation remain deployment inputs.
