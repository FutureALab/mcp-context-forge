"""Exchange parent-page identity cookies for gateway browser credentials."""

# Standard
import secrets
from typing import Literal
from urllib.parse import unquote

# Third-Party
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.admin import rate_limit
from mcpgateway.config import settings
from mcpgateway.db import EmailUser, get_db
from mcpgateway.services.email_auth_service import EmailAuthService, EmailValidationError
from mcpgateway.services.server_member_service import registered_user
from mcpgateway.utils.create_jwt_token import create_jwt_token
from mcpgateway.utils.member_key_proof import create_member_key_proof, MEMBER_KEY_PROOF_COOKIE, MEMBER_KEY_PROOF_TTL_SECONDS
from mcpgateway.utils.paths import resolve_root_path
from mcpgateway.utils.security_cookies import CookieTooLargeError, set_auth_cookie

router = APIRouter(prefix="/auth/portal", tags=["Parent Application Authentication"])
_PROVIDER = "portal"


class PortalExchangeRequest(BaseModel):
    """Select the credential required by the embedded page."""

    purpose: Literal["login", "key"]


def _cookie_identity(request: Request) -> tuple[str, str]:
    """Read the parent page's account cookies from the browser request."""
    if not settings.portal_sso_enabled:
        raise HTTPException(404, "父平台登录未启用")
    parent_origin = settings.portal_sso_parent_origin.rstrip("/")
    if not parent_origin:
        raise HTTPException(503, "未配置父平台来源")
    if request.headers.get("origin") != parent_origin:
        raise HTTPException(403, "父平台来源不匹配")
    email = unquote(request.cookies.get("mcp_email", "")).strip().lower()
    username = unquote(request.cookies.get("mcp_username", "")).strip()
    if not email or not username or len(email) > 254 or len(username) > 255:
        raise HTTPException(401, "登录已过期，请刷新页面")
    return email, username


@router.post("/exchange")
@rate_limit(requests_per_minute=20)
async def exchange_portal_cookies(request: Request, body: PortalExchangeRequest, db: Session = Depends(get_db)) -> JSONResponse:
    """Issue a login session or Key-only proof for a parent-cookie account."""
    email, username = _cookie_identity(request)
    if body.purpose == "key" and not settings.self_service_api_keys_enabled:
        raise HTTPException(404, "自助领取未启用")
    auth_service = EmailAuthService(db)
    try:
        auth_service.validate_email(email)
    except EmailValidationError as exc:
        raise HTTPException(401, "父平台账号邮箱无效") from exc
    user = db.execute(select(EmailUser).where(func.lower(EmailUser.email) == email)).scalar_one_or_none()
    if body.purpose == "key":
        user = registered_user(db, email)
    elif user is None:
        user = await auth_service.create_user(email=email, password=secrets.token_urlsafe(32), full_name=username, is_admin=False, auth_provider=_PROVIDER)
    if not user or not user.is_active or str(user.auth_provider or "").lower() != _PROVIDER or user.is_admin:
        raise HTTPException(403, "账号未绑定父平台、已停用或需管理员登录")

    root_path = resolve_root_path(request)
    destination = f"{root_path}/admin" if body.purpose == "login" else f"{root_path}/admin/api-key"
    response = JSONResponse({"next": destination}, headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Origin, Cookie"})
    if body.purpose == "login":
        token = await create_jwt_token(
            {
                "sub": str(user.id),
                "auth_provider": _PROVIDER,
                "token_use": "session",
                "scopes": {"server_id": None, "permissions": [], "ip_restrictions": [], "time_restrictions": {}},
            },
            expires_in_minutes=60,
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
