"""Read server-scoped token records without issuing or renewing keys."""

import hashlib
from datetime import timezone

from sqlalchemy import select

from mcpgateway.config import settings
from mcpgateway.db import EmailApiToken, EmailTeam, EmailUser, TokenRevocation, utc_now
from mcpgateway.services.encryption_service import get_encryption_service


def inventory_query(server_id: str):
    """Include every owner and lifecycle state for one virtual server."""
    return (
        select(EmailApiToken, EmailUser, EmailTeam, TokenRevocation)
        .outerjoin(EmailUser, EmailUser.email == EmailApiToken.user_email)
        .outerjoin(EmailTeam, EmailTeam.id == EmailApiToken.team_id)
        .outerjoin(TokenRevocation, TokenRevocation.jti == EmailApiToken.jti)
        .where(EmailApiToken.server_id == server_id)
        .order_by(EmailApiToken.created_at.desc(), EmailApiToken.id)
    )


def inventory_record(row) -> dict:
    """Serialize metadata without exposing encrypted or plaintext token material."""
    token, user, team, revocation = row
    expires = token.expires_at
    expired = bool(expires and expires.replace(tzinfo=expires.tzinfo or timezone.utc) <= utc_now())
    return {
        "token_id": token.id,
        "name": token.name,
        "email": token.user_email,
        "team_id": token.team_id,
        "team_name": team.name if team else None,
        "status": "已吊销" if revocation else "已停用" if not token.is_active else "已到期" if expired else "有效",
        "account_status": "正常" if user and user.is_active else "已停用或不存在",
        "created_at": token.created_at.isoformat(),
        "expires_at": expires.isoformat() if expires else None,
        "last_used": token.last_used.isoformat() if token.last_used else None,
        "description": token.description,
        "permissions": token.resource_scopes or [],
        "ip_restrictions": token.ip_restrictions or [],
        "time_restrictions": token.time_restrictions or {},
        "usage_limits": token.usage_limits or {},
        "key_available": bool(token.encrypted_token),
        "revoked_at": revocation.revoked_at.isoformat() if revocation else None,
        "revocation_reason": revocation.reason if revocation else None,
    }


async def inventory_secret(token: EmailApiToken) -> dict:
    """Read stored material and report missing or invalid historical values per record."""
    if not token.encrypted_token:
        return {"api_key": None, "key_message": "仅保存哈希，无法恢复原文"}
    try:
        raw = await get_encryption_service(settings.auth_encryption_secret).decrypt_secret_strict_async(token.encrypted_token)
        if hashlib.sha256(raw.encode()).hexdigest() != token.token_hash:
            return {"api_key": None, "key_message": "完整性校验失败"}
        return {"api_key": raw, "key_message": "可查看"}
    except ValueError:
        return {"api_key": None, "key_message": "解密失败，请检查服务器加密配置"}
