"""Exchange parent-page identity cookies for gateway browser credentials."""

# Standard
import hashlib
import hmac
import secrets
import time
from typing import Literal
from urllib.parse import unquote

# Third-Party
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.admin import rate_limit
from mcpgateway.config import settings
from mcpgateway.db import EmailUser, get_db
from mcpgateway.services.email_auth_service import EmailAuthService, EmailValidationError
from mcpgateway.services.server_member_service import registered_user
from mcpgateway.utils.create_jwt_token import create_jwt_token
from mcpgateway.utils.paths import resolve_root_path
from mcpgateway.utils.security_cookies import CookieTooLargeError, set_auth_cookie

router = APIRouter(prefix="/auth/portal", tags=["Parent Application Authentication"])
_PROVIDER = "portal"
_AUDIENCE = "contextforge-portal-authorization"
_TOKEN_USE = "portal_authorization"  # nosec B105 - JWT claim type, not a password.


class PortalExchangeRequest(BaseModel):
    """Select the embedded page and optionally reuse parent authorization."""

    purpose: Literal["login", "key"]
    token: str | None = Field(default=None, max_length=4096)


def _require_parent_origin(request: Request) -> None:
    """Check the feature flag and exact parent browser Origin."""
    if not settings.portal_sso_enabled:
        raise HTTPException(404, "父平台登录未启用")
    parent_origin = settings.portal_sso_parent_origin.rstrip("/")
    if not parent_origin:
        raise HTTPException(503, "未配置父平台来源")
    if request.headers.get("origin") != parent_origin:
        raise HTTPException(403, "父平台来源不匹配")


def _cookie_identity(request: Request) -> str:
    """Read the parent page's account cookies from the browser request."""
    email = unquote(request.cookies.get("mcp_email", "")).strip().lower()
    username = unquote(request.cookies.get("mcp_username", "")).strip()
    if not email or not username or len(email) > 254 or len(username) > 255:
        raise HTTPException(401, "登录已过期，请刷新页面")
    return email


def _portal_signing_key() -> bytes:
    """Separate parent authorization tokens from gateway session JWTs."""
    secret = settings.jwt_secret_key.get_secret_value().encode()
    return hmac.new(secret, b"portal-authorization-token", hashlib.sha256).digest()


def _read_portal_token(token: str, db: Session) -> tuple[EmailUser, int] | None:
    """Resolve a signed parent token to a still-active registered account."""
    try:
        payload = jwt.decode(
            token,
            _portal_signing_key(),
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=settings.jwt_issuer,
            options={"require": ["iss", "aud", "sub", "iat", "exp", "token_use"]},
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("token_use") != _TOKEN_USE or not isinstance(payload.get("sub"), str):
        return None
    user = db.get(EmailUser, payload["sub"])
    if user is None or not user.is_active or user.is_admin:
        raise HTTPException(403, "MCP 账号不存在、已停用或需管理员登录")
    return user, payload["exp"]


def _create_portal_token(user: EmailUser) -> tuple[str, int]:
    """Issue a reusable parent token with a bounded expiration."""
    now = int(time.time())
    expires_at = now + settings.portal_sso_token_ttl_minutes * 60
    token = jwt.encode(
        {"iss": settings.jwt_issuer, "aud": _AUDIENCE, "sub": str(user.id), "iat": now, "exp": expires_at, "token_use": _TOKEN_USE, "jti": secrets.token_urlsafe(16)},
        _portal_signing_key(),
        algorithm="HS256",
    )
    return token, expires_at


@router.post("/exchange")
@rate_limit(requests_per_minute=20)
async def exchange_portal_cookies(request: Request, body: PortalExchangeRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Authorize the parent and issue an embedded-page browser credential."""
    _require_parent_origin(request)
    if body.purpose == "key" and not settings.self_service_api_keys_enabled:
        raise HTTPException(404, "自助领取未启用")
    authorization = _read_portal_token(body.token, db) if body.token else None
    cookie_email = unquote(request.cookies.get("mcp_email", "")).strip().lower()
    if authorization is not None and cookie_email and cookie_email != authorization[0].email.lower():
        authorization = None
    if authorization is None:
        email = _cookie_identity(request)
        auth_service = EmailAuthService(db)
        try:
            auth_service.validate_email(email)
        except EmailValidationError as exc:
            raise HTTPException(401, "父平台账号邮箱无效") from exc
        user = registered_user(db, email)
        if user.is_admin:
            raise HTTPException(403, "请使用管理员登录入口")
        portal_token, expires_at = _create_portal_token(user)
    else:
        user, expires_at = authorization
        portal_token = body.token

    root_path = resolve_root_path(request)
    destination = f"{root_path}/admin" if body.purpose == "login" else f"{root_path}/admin/api-key"
    response = JSONResponse({"next": destination, "token": portal_token, "expires_at": expires_at}, headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Origin, Cookie"})
    token = await create_jwt_token(
        {
            "sub": str(user.id),
            "auth_provider": _PROVIDER,
            "token_use": "session",  # nosec B105 - JWT claim type, not a password.
            "scopes": {"server_id": None, "permissions": [], "ip_restrictions": [], "time_restrictions": {}},
        },
        expires_in_minutes=60,
    )
    try:
        set_auth_cookie(response, token, remember_me=False)
    except CookieTooLargeError as exc:
        raise HTTPException(400, "网关登录会话过大") from exc
    return response
