"""Query MCP tool usage and paginated invocation audits.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
from datetime import timedelta

# Third-Party
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.config import settings
from mcpgateway.db import EmailApiToken, Gateway, Server, TokenUsageLog, Tool, utc_now


def invocation_query(days: int, search: str = "", gateway_id: str = "", server_id: str = "", status: str = "all") -> Select:
    """Select tool calls with recorded identities and protocol-aware outcomes."""
    detail = TokenUsageLog.mcp_details
    tool_gateway = (
        select(case((func.count(func.distinct(func.coalesce(Tool.gateway_id, ""))) == 1, func.min(Tool.gateway_id)), else_=None)).where(Tool.name == detail["resource"].as_string()).scalar_subquery()
    )
    connector = func.coalesce(detail["gateway_id"].as_string(), tool_gateway)
    server = func.coalesce(detail["server_id"].as_string(), EmailApiToken.server_id)
    outcome = case(
        (TokenUsageLog.status_code.in_([408, 504]), "timeout"),
        (or_(TokenUsageLog.blocked.is_(True), TokenUsageLog.status_code >= 400, detail["outcome"].as_string() == "error"), "error"),
        ((detail["outcome"].as_string() == "success") & (TokenUsageLog.status_code < 400), "success"),
        else_="unknown",
    )
    end = utc_now()
    start = end - timedelta(days=1) if days == 1 else end.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    query = (
        select(
            TokenUsageLog.id,
            TokenUsageLog.timestamp,
            TokenUsageLog.user_email.label("email"),
            TokenUsageLog.status_code.label("http_status"),
            TokenUsageLog.response_time_ms.label("latency_ms"),
            detail["resource"].as_string().label("tool"),
            connector.label("gateway_id"),
            Gateway.name.label("gateway"),
            server.label("server_id"),
            Server.name.label("server"),
            EmailApiToken.name.label("token_name"),
            outcome.label("outcome"),
        )
        .outerjoin(EmailApiToken, EmailApiToken.jti == TokenUsageLog.token_jti)
        .outerjoin(Gateway, Gateway.id == connector)
        .outerjoin(Server, Server.id == server)
        .where(detail["method"].as_string() == "tools/call", TokenUsageLog.timestamp >= start, TokenUsageLog.timestamp <= end)
    )
    if search:
        query = query.where(
            or_(detail["resource"].as_string().contains(search, autoescape=True), Gateway.name.contains(search, autoescape=True), TokenUsageLog.user_email.contains(search, autoescape=True))
        )
    if gateway_id:
        query = query.where(connector == gateway_id)
    if server_id:
        query = query.where(server == server_id)
    if status != "all":
        query = query.where(outcome == status)
    return query


def usage_overview(db: Session, days: int) -> dict:
    """Aggregate all matching tool calls without loading invocation payloads."""
    calls = invocation_query(days).subquery()
    count = func.count()
    success = func.sum(case((calls.c.outcome == "success", 1), else_=0))
    errors = func.sum(case((calls.c.outcome.in_(["error", "timeout"]), 1), else_=0))
    summary = dict(
        db.execute(
            select(count.label("calls"), success.label("successes"), errors.label("errors"), func.avg(calls.c.latency_ms).label("avg_ms"), func.count(func.distinct(calls.c.email)).label("users"))
        )
        .mappings()
        .one()
    )
    summary["successes"] = summary["successes"] or 0
    summary["errors"] = summary["errors"] or 0
    summary["success_rate"] = round(summary["successes"] / summary["calls"] * 100, 2) if summary["calls"] else None
    daily = func.date(calls.c.timestamp)
    buckets = {str(row["date"]): dict(row) for row in db.execute(select(daily.label("date"), count.label("calls"), success.label("successes"), errors.label("errors")).group_by(daily)).mappings()}
    today = utc_now().date()
    trend = []
    for index in range(days):
        day = (today - timedelta(days=days - index - 1)).isoformat()
        trend.append({"date": day, **buckets.get(day, {"calls": 0, "successes": 0, "errors": 0})})
    rankings = {}
    for category in ("tool", "gateway", "server", "email"):
        label = func.coalesce(calls.c[category], "未采集" if category == "tool" else "未关联")
        rankings[category] = [dict(row) for row in db.execute(select(label.label("name"), count.label("calls")).group_by(label).order_by(count.desc(), label).limit(10)).mappings()]
    connectors = [dict(row) for row in db.execute(select(Gateway.id, Gateway.name, Gateway.enabled, Gateway.reachable, Gateway.last_seen).order_by(Gateway.name)).mappings()]
    return {
        "summary": summary,
        "trend": trend,
        "rankings": rankings,
        "connectors": connectors,
        "tool_count": db.scalar(select(func.count()).select_from(Tool).where(Tool.enabled.is_(True))),
        "servers": [dict(row) for row in db.execute(select(Server.id, Server.name).order_by(Server.name)).mappings()],
        "coverage": {
            "logging_enabled": settings.token_usage_logging_enabled,
            "payloads_enabled": settings.mcp_audit_payloads_enabled,
            "scope": "API Key 认证的 tools/call；不含初始化、工具发现及浏览器测试调用",
            "timezone": "UTC",
        },
    }


def invocation_audit(db: Session, days: int, search: str, gateway_id: str, server_id: str, status: str, offset: int, limit: int) -> dict:
    """Return a stable page of tool calls and redacted captured payloads."""
    query = invocation_query(days, search, gateway_id, server_id, status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    records = [dict(row) for row in db.execute(query.order_by(TokenUsageLog.timestamp.desc(), TokenUsageLog.id.desc()).offset(offset).limit(limit)).mappings()]
    ids = [row["id"] for row in records]
    payloads = dict(db.execute(select(TokenUsageLog.id, TokenUsageLog.mcp_details).where(TokenUsageLog.id.in_(ids))).all()) if ids else {}
    for row in records:
        detail = payloads.get(row["id"]) or {}
        row["input"] = detail.get("input")
        row["output"] = detail.get("output")
        row["capture_truncated"] = detail.get("capture_truncated", False)
    return {"records": records, "total": total, "offset": offset, "limit": limit}
