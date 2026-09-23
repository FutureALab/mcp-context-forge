# SPDX-License-Identifier: Apache-2.0
"""Prepare isolated credentials or run the native gateway for the iframe demo."""

import json
import os
from pathlib import Path
import secrets
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = HERE / ".runtime"


def prepare() -> dict:
    """Create persistent local demo configuration with randomly generated secrets."""
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / "config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    config = {
        "portalOrigin": "http://localhost:18080",
        "gatewayOrigin": "http://localhost:18081",
        "password": "Demo!" + secrets.token_urlsafe(18),
        "portalSecret": secrets.token_urlsafe(32),
        "gatewaySecret": secrets.token_urlsafe(32),
        "jwtSecret": secrets.token_urlsafe(48),
        "encryptionSecret": secrets.token_urlsafe(48),
        "adminPassword": "Admin!" + secrets.token_urlsafe(24),
    }
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    (RUNTIME / "account.txt").write_text(f"Local demo only\nURL: {config['portalOrigin']}\nEmail: demo@aiops.example\nPassword: {config['password']}\n", encoding="utf-8")
    return config


def gateway() -> None:
    """Run the repository gateway against a dedicated SQLite database and issuer."""
    config = prepare()
    issuer = config["portalOrigin"] + "/oidc"
    os.environ["NO_PROXY"] = ",".join(filter(None, [os.environ.get("NO_PROXY", ""), "localhost", "127.0.0.1", "::1"]))
    os.environ.update(
        {
            "ENVIRONMENT": "development",
            "DATABASE_URL": "sqlite:///" + (RUNTIME / "gateway.db").as_posix(),
            "JWT_SECRET_KEY": config["jwtSecret"],
            "AUTH_ENCRYPTION_SECRET": config["encryptionSecret"],
            "PLATFORM_ADMIN_EMAIL": "admin@aiops.example",
            "PLATFORM_ADMIN_PASSWORD": config["adminPassword"],
            "BASIC_AUTH_PASSWORD": config["adminPassword"],
            "DEFAULT_USER_PASSWORD": config["adminPassword"],
            "DEFAULT_USER_ROLE": "platform_viewer",
            "PASSWORD_CHANGE_ENFORCEMENT_ENABLED": "false",
            "AUTH_REQUIRED": "true",
            "EMAIL_AUTH_ENABLED": "true",
            "TRUST_PROXY_AUTH": "false",
            "MCPGATEWAY_UI_ENABLED": "true",
            "MCPGATEWAY_ADMIN_API_ENABLED": "true",
            "MCPGATEWAY_UI_EMBEDDED": "true",
            "SECURE_COOKIES": "false",
            "COOKIE_SAMESITE": "lax",
            "X_FRAME_OPTIONS": "none",
            "APP_DOMAIN": config["gatewayOrigin"],
            "APP_ROOT_PATH": "",
            "CORS_ENABLED": "true",
            "CORS_ALLOW_CREDENTIALS": "true",
            "ALLOWED_ORIGINS": json.dumps([config["portalOrigin"], config["gatewayOrigin"]]),
            "SSO_ENABLED": "true",
            "SSO_GENERIC_ENABLED": "true",
            "SSO_GENERIC_PROVIDER_ID": "intranet-demo",
            "SSO_GENERIC_DISPLAY_NAME": "Intranet demo",
            "SSO_GENERIC_CLIENT_ID": "contextforge-demo",
            "SSO_GENERIC_CLIENT_SECRET": config["gatewaySecret"],
            "SSO_GENERIC_AUTHORIZATION_URL": issuer + "/authorize",
            "SSO_GENERIC_TOKEN_URL": issuer + "/token",
            "SSO_GENERIC_USERINFO_URL": issuer + "/userinfo",
            "SSO_GENERIC_ISSUER": issuer,
            "SSO_GENERIC_JWKS_URI": issuer + "/jwks",
            "SSO_GENERIC_DEFAULT_ROLE": "platform_viewer",
            "SSO_TRUSTED_DOMAINS": '["aiops.example"]',
            "SSO_AUTO_CREATE_USERS": "true",
            "SSO_REQUIRE_ADMIN_APPROVAL": "false",
            "SSRF_ALLOW_LOCALHOST": "true",
            "SSRF_ALLOW_PRIVATE_NETWORKS": "true",
            "PLUGINS_ENABLED": "false",
            "CACHE_TYPE": "memory",
            "FEDERATION_ENABLED": "false",
            "MCPGATEWAY_A2A_ENABLED": "false",
            "OBSERVABILITY_ENABLED": "false",
            "LLMCHAT_ENABLED": "false",
            "LOG_LEVEL": "WARNING",
            "LOG_TO_FILE": "false",
            "I18N_ENABLED": "true",
            "I18N_DEFAULT_LOCALE": "zh_CN",
        }
    )
    # Isolate .env discovery and generated files from the user's gateway environment.
    os.chdir(RUNTIME)
    sys.path.insert(0, str(ROOT))
    import uvicorn  # pylint: disable=import-outside-toplevel

    uvicorn.run("mcpgateway.main:app", host="0.0.0.0", port=4446, log_level="warning", access_log=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif sys.argv[1:] == ["gateway"]:
        gateway()
    else:
        raise SystemExit("Usage: run_gateway.py prepare|gateway")
