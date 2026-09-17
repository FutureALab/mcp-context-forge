"""Manage team-backed virtual server membership and scoped key issuance.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import uuid

# Third-Party
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import EmailTeam, EmailTeamMember, EmailUser, Server
from mcpgateway.services.audit_trail_service import get_audit_trail_service
from mcpgateway.services.permission_service import PermissionService
from mcpgateway.services.token_catalog_service import TokenCatalogService, TokenScope

MCP_PERMISSIONS = ("servers.use", "tools.read", "tools.execute", "resources.read", "prompts.read", "prompts.execute")


def registered_user(db: Session, email: str) -> EmailUser:
    """Return an enabled registered user, or reject the account."""
    user = db.execute(select(EmailUser).where(func.lower(EmailUser.email) == email.strip().lower(), EmailUser.is_active.is_(True))).scalar_one_or_none()
    if user is None:
        raise HTTPException(403, "账号不存在、已停用或不具备所选资源的访问权限")
    return user


def member_server(db: Session, email: str, team_id: str, server_id: str) -> tuple[EmailUser, Server]:
    """Validate the user, active team membership, and server visibility."""
    user = registered_user(db, email)
    membership = db.execute(
        select(EmailTeamMember)
        .join(EmailTeam)
        .where(
            EmailTeamMember.user_email == user.email,
            EmailTeamMember.team_id == team_id,
            EmailTeamMember.is_active.is_(True),
            EmailTeam.is_active.is_(True),
        )
    ).scalar_one_or_none()
    server = db.get(Server, server_id)
    if membership is None or server is None or not server.enabled or server.team_id != team_id:
        raise HTTPException(403, "账号不存在、已停用或不具备所选资源的访问权限")
    if server.visibility == "private" and server.owner_email != user.email:
        raise HTTPException(403, "账号不存在、已停用或不具备所选资源的访问权限")
    return user, server


async def issue_member_key(db: Session, email: str, team_id: str, server_id: str, days: int, actor: str) -> dict:
    """Issue a distinct key with only the recipient's MCP permissions."""
    user, server = member_server(db, email, team_id, server_id)
    permissions = await PermissionService(db).get_user_permissions(user.email, team_id=team_id, token_teams=[team_id])
    allowed = [p for p in MCP_PERMISSIONS if p in permissions or "*" in permissions or p.split(".")[0] + ".*" in permissions]
    if "servers.use" not in allowed:
        raise HTTPException(403, "该账号没有 MCP 使用权限")
    record, raw = await TokenCatalogService(db).create_token(
        user_email=user.email,
        name=f"mcp-{server.id[:8]}-{uuid.uuid4().hex[:12]}",
        description="Server member API key",
        scope=TokenScope(server_id=server.id, permissions=allowed),
        expires_in_days=days,
        team_id=team_id,
        caller_permissions=list(permissions),
        caller_token_teams=[team_id],
        caller_token_teams_provided=True,
        caller_email=user.email,
    )
    result = {"email": user.email, "team_id": team_id, "server_id": server.id, "server_name": server.name, "token_id": record.id, "api_key": raw, "expires_at": record.expires_at.isoformat()}
    get_audit_trail_service().log_action(
        action="create",
        resource_type="token",
        resource_id=record.id,
        user_id=actor,
        user_email=actor if actor != "self-service" else None,
        team_id=team_id,
        context={"source": actor, "recipient": user.email, "server_id": server.id},
    )
    return result
