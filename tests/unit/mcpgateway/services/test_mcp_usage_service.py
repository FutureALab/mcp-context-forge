"""Verify MCP invocation aggregates, audit filters, and payload redaction.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

# Third-Party
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import Base, Gateway, Server, TokenUsageLog, Tool, utc_now
from mcpgateway.services.mcp_usage_capture import MCPUsageCapture
from mcpgateway.services.mcp_usage_service import invocation_audit, usage_overview


class TestMCPUsage(unittest.TestCase):
    """Check complete aggregation and stable, searchable audit pages."""

    def setUp(self):
        """Create tool calls and discovery requests in an isolated database."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(Gateway(id="connector-a", name="Connector A", slug="connector-a", url="http://localhost", capabilities={}))
        self.db.add(Server(id="server-a", name="Server A"))
        self.db.flush()
        now = utc_now()
        for index in range(25):
            self.db.add(
                TokenUsageLog(
                    token_jti="deleted",
                    user_email="member@example.com",
                    timestamp=now,
                    status_code=200,
                    response_time_ms=0,
                    mcp_details={"method": "tools/call", "resource": "query_%", "server_id": "server-a", "gateway_id": "connector-a", "outcome": "success"},
                )
            )
        for code, outcome in [(200, "error"), (504, None), (403, None), (200, None)]:
            self.db.add(
                TokenUsageLog(
                    token_jti="deleted",
                    user_email="other@example.com",
                    timestamp=now,
                    status_code=code,
                    response_time_ms=100,
                    mcp_details={"method": "tools/call", "resource": "other", "outcome": outcome},
                )
            )
        for days, method in [(0, "tools/list"), (100, "tools/call")]:
            self.db.add(
                TokenUsageLog(token_jti="deleted", user_email="member@example.com", timestamp=now - timedelta(days=days), status_code=200, mcp_details={"method": method, "outcome": "success"})
            )
        self.db.commit()

    def tearDown(self):
        """Close the isolated database."""
        self.db.close()
        self.engine.dispose()

    def test_aggregate_protocol_errors_and_empty_days(self):
        """Exclude discovery and old requests while counting MCP errors."""
        result = usage_overview(self.db, 7)
        self.assertEqual(result["summary"]["calls"], 29)
        self.assertEqual(result["summary"]["successes"], 25)
        self.assertEqual(result["summary"]["errors"], 3)
        self.assertEqual(result["summary"]["users"], 2)
        self.assertEqual(len(result["trend"]), 7)
        self.assertEqual(sum(row["calls"] for row in result["trend"]), 29)
        self.assertEqual(result["rankings"]["gateway"][0], {"name": "Connector A", "calls": 25})

    def test_pagination_and_literal_search(self):
        """Keep tied timestamps stable and escape wildcard search characters."""
        first = invocation_audit(self.db, 30, "", "connector-a", "server-a", "success", 0, 20)
        second = invocation_audit(self.db, 30, "", "connector-a", "server-a", "success", 20, 20)
        self.assertEqual(first["total"], 25)
        self.assertEqual(len(second["records"]), 5)
        self.assertFalse({row["id"] for row in first["records"]} & {row["id"] for row in second["records"]})
        self.assertIsNone(first["records"][0]["input"])
        self.assertEqual(invocation_audit(self.db, 7, "_%", "", "", "all", 0, 100)["total"], 25)
        self.assertEqual(invocation_audit(self.db, 7, "", "", "", "timeout", 0, 100)["total"], 1)
        self.assertEqual(invocation_audit(self.db, 7, "", "", "", "error", 0, 100)["total"], 2)
        self.assertEqual(invocation_audit(self.db, 7, "", "", "", "unknown", 0, 100)["total"], 1)

    def test_optional_redacted_payloads(self):
        """Keep capture disabled by default and redact enabled payloads."""
        capture = MCPUsageCapture()
        capture.append(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {"password": "private-value", "department": "engineering"}}}).encode())
        capture.append(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"api_key": "private-value", "count": 5}}}).encode(), response=True)
        self.assertNotIn("input", capture.details())
        payload = capture.details(include_payloads=True)
        self.assertNotIn("private-value", str(payload))
        self.assertEqual(json.loads(payload["input"])["department"], "engineering")
        self.assertEqual(json.loads(payload["output"])["structuredContent"]["count"], 5)

    def test_ambiguous_historical_connector_remains_unknown(self):
        """Avoid assigning historical calls to an arbitrary matching connector."""
        self.db.add(Gateway(id="connector-b", name="Connector B", slug="connector-b", url="http://localhost", capabilities={}))
        self.db.flush()
        for connector in ("connector-a", "connector-b"):
            self.db.add(Tool(name="shared-name", original_name="shared-name", gateway_id=connector, input_schema={}))
        self.db.add(TokenUsageLog(token_jti="deleted", user_email="member@example.com", status_code=200, mcp_details={"method": "tools/call", "resource": "shared-name", "outcome": "success"}))
        self.db.commit()
        record = invocation_audit(self.db, 7, "shared-name", "", "", "all", 0, 20)["records"][0]
        self.assertIsNone(record["gateway_id"])
        self.assertIsNone(record["gateway"])

    def test_payload_size_is_bounded(self):
        """Bound oversized audit payloads after redaction."""
        capture = MCPUsageCapture()
        capture.append(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"arguments": {"text": "x" * 30000, "password": "private-value"}}}).encode())
        detail = capture.details(include_payloads=True)
        self.assertLessEqual(len(detail["input"]), 16384)
        self.assertNotIn("private-value", detail["input"])

    def test_json_encoded_text_is_redacted(self):
        """Redact secrets inside JSON and escaped JSON tool text."""
        for text in ('{"password":"private-value","count":5}', '{\\n  \\"password\\": \\"private-value\\", \\"count\\": 5\\n}'):
            capture = MCPUsageCapture()
            capture.append(b'{"jsonrpc":"2.0","id":1,"method":"tools/call"}')
            capture.append(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}]}}).encode(), response=True)
            detail = capture.details(include_payloads=True)
            self.assertNotIn("private-value", detail["output"])
            self.assertIn("count", detail["output"])

    def test_collection_flags_are_explicit(self):
        """Report disabled logging and payload collection without fabricating history."""
        with patch("mcpgateway.services.mcp_usage_service.settings.token_usage_logging_enabled", False), patch("mcpgateway.services.mcp_usage_service.settings.mcp_audit_payloads_enabled", False):
            result = usage_overview(self.db, 7)
        self.assertFalse(result["coverage"]["logging_enabled"])
        self.assertFalse(result["coverage"]["payloads_enabled"])

    def test_platform_session_denials(self):
        """Reject unauthenticated, API-token, ordinary, and narrowed sessions."""
        from mcpgateway.routers.server_members import require_platform_session

        allowed = {"auth_method": "jwt", "is_admin": True, "token_teams": None, "email": "admin@example.com"}
        self.assertEqual(require_platform_session(allowed), "admin@example.com")
        for changes in ({"auth_method": None}, {"auth_method": "anonymous"}, {"auth_method": "api_token"}, {"is_admin": False}, {"token_teams": ["wrong-team"]}, {"token_teams": []}):
            with self.subTest(changes=changes), self.assertRaises(HTTPException):
                require_platform_session({**allowed, **changes})


if __name__ == "__main__":
    unittest.main()
