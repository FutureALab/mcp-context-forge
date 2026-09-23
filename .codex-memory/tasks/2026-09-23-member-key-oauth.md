# Member key OAuth and registration minimum

## Decision

- The Key page starts in OAuth mode. Its detect button reuses a valid SSO browser session or starts provider authorization.
- The callback identifies the Key flow from the persisted OAuth state and disables automatic account creation for that flow.
- Key options and issuance derive the account from the validated session. Password mode keeps the existing password and lockout checks.
- The default minimum for regular user registration is 10 characters. Privileged accounts keep their separate minimum.

## Verification

- Four focused JavaScript tests passed, including OAuth issuance without password fields and the unregistered-user notice.
- Four focused Python unittest cases passed for password, OAuth, cookie authentication, and account-creation boundaries.
- Direct callback checks confirmed the registered-user return and the unregistered-user redirect without account creation.
- Ruff passed for changed runtime Python files. ESLint passed for changed JavaScript files.
- Python 3.12 has no pytest package, so the new pytest callback regression cases could not run locally.
- No external identity provider was available for a live OAuth redirect test.

## Follow-up

- Run the new callback tests with pytest and verify the configured provider accepts the callback URI query parameter.
