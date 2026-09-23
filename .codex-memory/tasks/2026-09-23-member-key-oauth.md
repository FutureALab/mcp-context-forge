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

- The callback query marker was superseded. The Key flow now uses a signed `mk:` state prefix and the existing callback URI.
- The reserved prefix cannot occur in a regular URL-safe state nonce. Provider errors return to the Key page.
- Five JavaScript tests, ESLint, runtime Python Ruff, compilation, direct callback checks, and an in-process HTTP flow passed.
- The HTTP flow covered authorization start, browser cookie, unregistered rejection, registered return, and provider denial.
- Pytest is unavailable in the working Python 3.12 environment. The new pytest cases remain unrun locally.

## Separate login and Key authorization follow-up

- The Key callback now verifies an existing active account bound to the provider and creates only a five-minute proof Cookie.
- Key options and issuance accept that proof, then enforce CSRF, current account state, Team membership, and MCP permissions.
- The ordinary OAuth callback continues to create the gateway login session. `/admin/login?auto_sso=corp-oidc` starts the configured provider automatically.
- Gateway session Cookies cannot substitute for a Key proof. The proof uses a separate signing key and cannot serve as a gateway JWT.
- The HTTP intranet guide now shows both flows and the parent-page automatic login link.
- An isolated live gateway passed portal OAuth login, separate Key OAuth, scoped Key issuance, and MCP initialization.
- Three focused Python unittest cases, eight JavaScript tests, Ruff, compilation, and diff whitespace checks passed.
- Pytest callback tests remain unrun because the Python 3.12 environment has no pytest package.
- The isolated gateway on port 4450 was stopped; preexisting demo services were left running.
