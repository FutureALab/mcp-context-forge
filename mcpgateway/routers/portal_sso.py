"""Exchange parent application session tickets for gateway browser cookies."""

# Standard
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID

# Third-Party
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import jwt
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.admin import rate_limit
from mcpgateway.config import settings
from mcpgateway.db import EmailUser, get_db, PortalTicketUse, utc_now
from mcpgateway.services.email_auth_service import EmailAuthService, EmailValidationError
from mcpgateway.services.server_member_service import registered_user
from mcpgateway.utils.create_jwt_token import create_jwt_token
from mcpgateway.utils.member_key_proof import create_member_key_proof, MEMBER_KEY_PROOF_COOKIE, MEMBER_KEY_PROOF_TTL_SECONDS
from mcpgateway.utils.security_cookies import CookieTooLargeError, set_auth_cookie

router = APIRouter(prefix="/auth/portal", tags=["Parent Application Authentication"])
_AUDIENCE = "contextforge-portal"
_PROVIDER = "portal"
_TICKET_TTL_SECONDS = 60


class PortalExchangeRequest(BaseModel):
    """Carry a short-lived ticket issued after parent session validation."""

    ticket: str = Field(min_length=20, max_length=4096)


def _verify_ticket(request: Request, ticket: str) -> dict:
    """Validate a purpose-bound parent ticket and the exact browser Origin."""
    if not settings.portal_sso_enabled:
        raise HTTPException(404, "父平台登录未启用")
    secret = settings.portal_sso_shared_secret.get_secret_value()
    parent_origin = settings.portal_sso_parent_origin.rstrip("/")
    if len(secret) < 32 or not parent_origin or not settings.portal_sso_issuer:
        raise HTTPException(503, "父平台登录配置不完整")
    if request.headers.get("origin") != parent_origin:
        raise HTTPException(403, "父平台来源不匹配")
    try:
        claims = jwt.decode(
            ticket,
            secret,
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=settings.portal_sso_issuer,
            options={"require": ["iss", "aud", "sub", "email", "purpose", "iat", "exp", "jti"]},
        )
        issued_at, expires_at = claims["iat"], claims["exp"]
        if type(issued_at) is not int or type(expires_at) is not int or expires_at - issued_at > _TICKET_TTL_SECONDS or issued_at > time.time() + 5:
            raise ValueError("invalid ticket lifetime")
        if claims["purpose"] not in ("login", "key") or not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("invalid ticket purpose or subject")
        if not isinstance(claims["email"], str) or not claims["email"].strip():
            raise ValueError("invalid ticket email")
        if not isinstance(claims["jti"], str):
            raise ValueError("invalid ticket ID")
        claims["jti"] = str(UUID(claims["jti"]))
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "父平台票据无效或已过期") from exc
    return claims


def _consume_ticket(db: Session, claims: dict) -> None:
    """Commit a unique ticket ID before issuing any browser credential."""
    db.execute(delete(PortalTicketUse).where(PortalTicketUse.expires_at < utc_now()))
    db.add(PortalTicketUse(jti=claims["jti"], expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc)))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(401, "父平台票据已使用") from exc


@router.post("/exchange")
@rate_limit(requests_per_minute=20)
async def exchange_portal_ticket(request: Request, body: PortalExchangeRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Exchange one parent ticket for a login session or a Key-only proof."""
    claims = _verify_ticket(request, body.ticket)
    if claims["purpose"] == "key" and not settings.self_service_api_keys_enabled:
        raise HTTPException(404, "自助领取未启用")
    email = claims["email"].strip().lower()
    auth_service = EmailAuthService(db)
    try:
        auth_service.validate_email(email)
    except EmailValidationError as exc:
        raise HTTPException(401, "父平台票据邮箱无效") from exc
    user = db.execute(select(EmailUser).where(func.lower(EmailUser.email) == email)).scalar_one_or_none()
    if claims["purpose"] == "key":
        user = registered_user(db, email)
    elif user is None:
        user = await auth_service.create_user(email=email, password=secrets.token_urlsafe(32), full_name=email, is_admin=False, auth_provider=_PROVIDER)
    if not user or not user.is_active or str(user.auth_provider or "").lower() != _PROVIDER:
        raise HTTPException(403, "账号未绑定父平台或已停用")

    _consume_ticket(db, claims)
    root_path = request.scope.get("root_path", "")
    destination = f"{root_path}/admin" if claims["purpose"] == "login" else f"{root_path}/admin/api-key"
    response = JSONResponse({"next": destination}, headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Origin"})
    if claims["purpose"] == "login":
        token = await create_jwt_token(
            {
                "sub": str(user.id),
                "auth_provider": _PROVIDER,
                "iat": int(time.time()),
                "token_use": "session",
                "scopes": {"server_id": None, "permissions": ["*"] if user.is_admin else [], "ip_restrictions": [], "time_restrictions": {}},
            }
        )
        try:
            set_auth_cookie(response, token, remember_me=False)
        except CookieTooLargeError as exc:
            raise HTTPException(400, "网关登录会话过大") from exc
    else:
        response.set_cookie(
            key=MEMBER_KEY_PROOF_COOKIE,
            value=create_member_key_proof(user.email, _PROVIDER),
            max_age=MEMBER_KEY_PROOF_TTL_SECONDS,
            httponly=True,
            secure=(settings.environment == "production") or settings.secure_cookies,
            samesite=settings.cookie_samesite,
            path=f"{root_path}/admin/api-key",
        )
    return response
