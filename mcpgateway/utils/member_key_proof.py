"""Issue short-lived OAuth proofs for the API Key page."""

# Standard
import hashlib
import hmac
import secrets
import time

# Third-Party
from fastapi import HTTPException
import jwt

# First-Party
from mcpgateway.config import settings

MEMBER_KEY_PROOF_COOKIE = "member_key_proof"
MEMBER_KEY_PROOF_TTL_SECONDS = 300
_MEMBER_KEY_AUDIENCE = "member-key"


def _signing_key() -> bytes:
    """Derive a key that cannot validate ordinary gateway JWTs."""
    return hmac.new(settings.jwt_secret_key.get_secret_value().encode(), b"member-key-oauth-proof", hashlib.sha256).digest()


def create_member_key_proof(email: str, provider: str) -> str:
    """Sign a proof limited to the API Key page and five minutes."""
    now = int(time.time())
    return jwt.encode(
        {"sub": email, "provider": provider, "aud": _MEMBER_KEY_AUDIENCE, "iat": now, "exp": now + MEMBER_KEY_PROOF_TTL_SECONDS, "jti": secrets.token_urlsafe(16)},
        _signing_key(),
        algorithm="HS256",
    )


def read_member_key_proof(token: str | None) -> tuple[str, str]:
    """Validate a proof without accepting a gateway session token."""
    if not token:
        raise HTTPException(401, "请先完成 OAuth 授权")
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=["HS256"],
            audience=_MEMBER_KEY_AUDIENCE,
            options={"require": ["sub", "provider", "aud", "iat", "exp", "jti"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "OAuth 授权已失效，请重新授权") from exc
    email = payload.get("sub")
    provider = payload.get("provider")
    if not isinstance(email, str) or not email or not isinstance(provider, str) or not provider:
        raise HTTPException(401, "OAuth 授权无效")
    return email, provider
