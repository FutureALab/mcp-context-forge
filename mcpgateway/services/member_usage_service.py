"""Summarize recorded member requests with explicit collection coverage.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
from collections import defaultdict
from datetime import timedelta
import math
import re

# Third-Party
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.config import settings
from mcpgateway.db import EmailApiToken, EmailTeam, EmailTeamMember, EmailUser, Server, TokenUsageLog, utc_now


def summarize(rows: list) -> dict:
    """Calculate request outcomes, latency percentiles, and reported token totals."""
    latencies = sorted(r.response_time_ms for r in rows if r.response_time_ms is not None)
    failed = sum(1 for r in rows if (r.status_code or 0) >= 400 or (r.mcp_details or {}).get("outcome") == "error")
    known = sum(1 for r in rows if (r.status_code or 0) > 0)
    inputs = [(r.mcp_details or {}).get("input_tokens") for r in rows]
    outputs = [(r.mcp_details or {}).get("output_tokens") for r in rows]
    return {
        "calls": len(rows),
        "tool_calls": sum((r.mcp_details or {}).get("method") == "tools/call" for r in rows),
        "errors": failed,
        "blocked": sum(bool(r.blocked) for r in rows),
        "success_rate": round((known - failed) / len(rows) * 100, 2) if rows else None,
        "avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "p95_ms": latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else None,
        "input_tokens": sum(v for v in inputs if v is not None) if any(v is not None for v in inputs) else None,
        "output_tokens": sum(v for v in outputs if v is not None) if any(v is not None for v in outputs) else None,
        "usage_reported_calls": sum(a is not None or b is not None for a, b in zip(inputs, outputs)),
        "last_used": max((r.timestamp for r in rows), default=None),
    }


def member_usage_summary(db: Session, days: int, server_id: str | None, email: str | None, token_id: str | None, method: str | None) -> dict:
    """Group recent request records by member, token, MCP method, and UTC day."""
    period_end = utc_now()
    period_start = period_end - timedelta(days=days)
    query = select(TokenUsageLog).where(TokenUsageLog.timestamp >= period_start, TokenUsageLog.timestamp <= period_end)
    tokens = db.execute(select(EmailApiToken)).scalars().all()
    token_map = {t.jti: t for t in tokens}
    if email:
        query = query.where(TokenUsageLog.user_email == email)
    if token_id:
        query = query.where(TokenUsageLog.token_jti.in_([t.jti for t in tokens if t.id == token_id]))
    if server_id:
        scoped = [t.jti for t in tokens if t.server_id == server_id]
        recorded_server = TokenUsageLog.mcp_details["server_id"].as_string()
        legacy_match = (
            TokenUsageLog.token_jti.in_(scoped)
            | TokenUsageLog.endpoint.contains(f"/servers/{server_id}/", autoescape=True)
            | TokenUsageLog.endpoint.contains(f"/virtual-servers/{server_id}/", autoescape=True)
        )
        query = query.where((recorded_server == server_id) | (recorded_server.is_(None) & legacy_match))
    if method:
        query = query.where((TokenUsageLog.mcp_details["method"].as_string() == method) | (TokenUsageLog.mcp_details["resource"].as_string() == method))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    logs = db.execute(query.order_by(TokenUsageLog.timestamp.desc()).limit(50000)).scalars().all()
    members, methods, by_token, trend = (defaultdict(list) for _ in range(4))
    tool_members, tool_trend = defaultdict(list), defaultdict(list)
    server_names = dict(db.execute(select(Server.id, Server.name)).all())
    recent = []
    for row in logs:
        token = token_map.get(row.token_jti)
        detail = row.mcp_details or {}
        match = re.search(r"/(?:servers|virtual-servers)/([^/]+)/", row.endpoint or "")
        actual_server = detail.get("server_id") or (match.group(1) if match else (token.server_id if token else None))
        members[row.user_email].append(row)
        if detail.get("method") == "tools/call":
            tool_members[row.user_email].append(row)
            bucket = row.timestamp.strftime("%Y-%m-%dT%H:00:00") if days == 1 else row.timestamp.date().isoformat()
            tool_trend[bucket].append(row)
        methods[(detail.get("method", "未采集 MCP 方法"), detail.get("resource", ""))].append(row)
        by_token[row.token_jti].append(row)
        trend[row.timestamp.date().isoformat()].append(row)
        if len(recent) < 100:
            recent.append(
                {
                    "timestamp": row.timestamp,
                    "email": row.user_email,
                    "token_name": token.name if token else "已删除的 Token",
                    "server": server_names.get(actual_server, actual_server),
                    "method": detail.get("method"),
                    "resource": detail.get("resource"),
                    "http_status": row.status_code,
                    "outcome": detail.get("outcome"),
                    "latency_ms": row.response_time_ms,
                    "blocked": row.blocked,
                }
            )
    bucket_time = period_start.replace(minute=0, second=0, microsecond=0) if days == 1 else period_start.replace(hour=0, minute=0, second=0, microsecond=0)
    while bucket_time <= period_end:
        bucket = bucket_time.strftime("%Y-%m-%dT%H:00:00") if days == 1 else bucket_time.date().isoformat()
        tool_trend.setdefault(bucket, [])
        bucket_time += timedelta(hours=1) if days == 1 else timedelta(days=1)

    token_rows = []
    for token in tokens:
        if (server_id and token.server_id != server_id) or (email and token.user_email != email) or (token_id and token.id != token_id):
            continue
        if method and token.jti not in by_token:
            continue
        expires = token.expires_at
        expired = expires is not None and expires.replace(tzinfo=None) <= utc_now().replace(tzinfo=None)
        token_rows.append(
            {
                "id": token.id,
                "name": token.name,
                "email": token.user_email,
                "server": server_names.get(token.server_id, token.server_id),
                "expires_at": token.expires_at,
                "status": "已撤销" if not token.is_active else "已过期" if expired else "有效",
                **summarize(by_token[token.jti]),
            }
        )
    roster_query = (
        select(EmailUser.email, EmailUser.full_name)
        .join(EmailTeamMember, EmailTeamMember.user_email == EmailUser.email)
        .join(EmailTeam, EmailTeam.id == EmailTeamMember.team_id)
        .join(Server, Server.team_id == EmailTeam.id)
        .where(EmailUser.is_active.is_(True), EmailTeam.is_active.is_(True), EmailTeamMember.is_active.is_(True))
        .distinct()
    )
    if server_id:
        roster_query = roster_query.where(Server.id == server_id)
    else:
        roster_query = select(EmailUser.email, EmailUser.full_name).where(EmailUser.is_active.is_(True))
    if email:
        roster_query = roster_query.where(EmailUser.email == email)
    names = dict(db.execute(roster_query).all())
    if not token_id and not method:
        for address in names:
            members.setdefault(address, [])
    member_rows = []
    for address, rows in members.items():
        owned = [t for t in token_rows if t["email"] == address]
        member_rows.append({"email": address, "name": names.get(address), "token_count": len(owned), "active_tokens": sum(t["status"] == "有效" for t in owned), **summarize(rows)})
    return {
        "tool_summary": summarize([r for rows in tool_members.values() for r in rows]),
        "tool_members": [{"email": address, "name": names.get(address), **summarize(tool_members[address])} for address in members],
        "tool_trend": [{"date": k, **summarize(v)} for k, v in sorted(tool_trend.items())],
        "member_states": {
            "active": sum(bool(tool_members[address]) for address in members),
            "errors": sum(any((r.mcp_details or {}).get("outcome") == "error" or (r.status_code or 0) >= 400 for r in tool_members[address]) for address in members),
            "idle": sum(not tool_members[address] for address in members),
        },
        "summary": summarize(logs),
        "members": member_rows,
        "methods": [{"method": k[0], "resource": k[1], **summarize(v)} for k, v in methods.items()],
        "tokens": token_rows,
        "trend": [{"date": k, **summarize(v)} for k, v in sorted(trend.items())],
        "recent": recent,
        "coverage": {
            "matching_requests": total,
            "included_requests": len(logs),
            "truncated": total > len(logs),
            "logging_enabled": settings.token_usage_logging_enabled,
            "timezone": "UTC",
            "latency": "HTTP 请求完成耗时；不是模型推理耗时",
            "model_usage": "只统计上游明确提供的用量；缺失不计为零",
        },
    }
