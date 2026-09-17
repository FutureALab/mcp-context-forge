"""Check membership boundaries, token scoping, and MCP usage extraction.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import importlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# Third-Party
from fastapi import HTTPException
import jwt
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import Base, EmailTeam, EmailTeamMember, EmailUser, Role, Server, TokenUsageLog, UserRole
from mcpgateway.services.mcp_usage_capture import MCPUsageCapture
from mcpgateway.services.member_usage_service import member_usage_summary, summarize
from mcpgateway.services.server_member_service import issue_member_key, member_server


class TestMemberKeys(unittest.IsolatedAsyncioTestCase):
    """Use real persistence and JWT issuance for membership regression cases."""

    def setUp(self):
        """Create two isolated teams and one server."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([EmailUser(email="member@example.com"), EmailUser(email="other@example.com")])
        self.db.flush()
        self.db.add_all([EmailTeam(id="team-a", name="A", slug="team-a", created_by="member@example.com"), EmailTeam(id="team-b", name="B", slug="team-b", created_by="other@example.com")])
        self.db.flush()
        self.db.add(EmailTeamMember(team_id="team-a", user_email="member@example.com"))
        self.db.add(Server(id="server-a", name="A", team_id="team-a", visibility="team", owner_email="member@example.com"))
        self.db.add(Role(id="role-a", name="member-test", scope="team", created_by="member@example.com", permissions=["servers.use", "tools.read", "tools.execute"]))
        self.db.flush()
        self.db.add(UserRole(user_email="member@example.com", role_id="role-a", scope="team", scope_id="team-a", granted_by="member@example.com"))
        self.db.commit()

    def tearDown(self):
        """Release the isolated database."""
        self.db.close()
        self.engine.dispose()

    async def test_distinct_scoped_keys(self):
        """Issue unique JWTs that cannot grant management permissions."""
        with patch("mcpgateway.services.server_member_service.get_audit_trail_service"):
            first = await issue_member_key(self.db, "MEMBER@example.com", "team-a", "server-a", 7, "self-service")
            second = await issue_member_key(self.db, "member@example.com", "team-a", "server-a", 7, "self-service")
        self.assertNotEqual(first["api_key"], second["api_key"])
        claims = jwt.decode(first["api_key"], options={"verify_signature": False})
        self.assertEqual(claims["teams"], ["team-a"])
        self.assertEqual(claims["scopes"]["server_id"], "server-a")
        self.assertNotIn("tokens.create", claims["scopes"]["permissions"])

    def test_membership_denials(self):
        """Reject unknown accounts, wrong teams, and nonmembers."""
        for email, team, server in [
            ("missing@example.com", "team-a", "server-a"),
            ("member@example.com", "team-b", "server-a"),
            ("other@example.com", "team-a", "server-a"),
            ("member@example.com", "team-a", "missing"),
        ]:
            with self.subTest(email=email, team=team, server=server), self.assertRaises(HTTPException):
                member_server(self.db, email, team, server)

    def test_disabled_entities_and_private_visibility(self):
        """Reject disabled identities, memberships, teams, servers, and private resources."""
        objects = [
            (self.db.query(EmailUser).filter_by(email="member@example.com").one(), "is_active"),
            (self.db.query(EmailTeamMember).one(), "is_active"),
            (self.db.get(EmailTeam, "team-a"), "is_active"),
            (self.db.get(Server, "server-a"), "enabled"),
        ]
        for obj, attribute in objects:
            setattr(obj, attribute, False)
            self.db.commit()
            with self.assertRaises(HTTPException):
                member_server(self.db, "member@example.com", "team-a", "server-a")
            setattr(obj, attribute, True)
            self.db.commit()
        server = self.db.get(Server, "server-a")
        server.visibility, server.owner_email = "private", "other@example.com"
        self.db.commit()
        with self.assertRaises(HTTPException):
            member_server(self.db, "member@example.com", "team-a", "server-a")

    async def test_missing_mcp_permission(self):
        """Reject issuance when membership grants no MCP transport permission."""
        self.db.get(Role, "role-a").permissions = ["tools.read"]
        self.db.commit()
        with self.assertRaises(HTTPException):
            await issue_member_key(self.db, "member@example.com", "team-a", "server-a", 7, "self-service")

    def test_roster_and_method_filter(self):
        """Include unused members and filter records by their actual server."""
        data = member_usage_summary(self.db, 7, "server-a", None, None, None)
        self.assertEqual(data["members"][0]["calls"], 0)
        self.db.add_all(
            [
                TokenUsageLog(
                    token_jti="deleted-token",
                    user_email="member@example.com",
                    endpoint="/mcp/",
                    status_code=200,
                    response_time_ms=0,
                    mcp_details={"method": "tools/list", "server_id": "server-a", "outcome": "success"},
                ),
                TokenUsageLog(token_jti="deleted-token", user_email="member@example.com", endpoint="/mcp/", status_code=403, mcp_details={"method": "tools/list", "server_id": "server-b"}),
            ]
        )
        self.db.commit()
        data = member_usage_summary(self.db, 7, "server-a", None, None, "tools/list")
        self.assertEqual(data["summary"]["calls"], 1)
        self.assertEqual(data["summary"]["errors"], 0)
        self.assertEqual(data["recent"][0]["server"], "A")


class TestMCPCapture(unittest.TestCase):
    """Verify protocol errors, reported usage, and capture bounds."""

    def test_sse_tool_error_with_usage(self):
        """Read a chunked SSE result without storing tool arguments."""
        capture = MCPUsageCapture()
        capture.append(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"secret": "not-stored"}}}).encode())
        response = b'data: {"jsonrpc":"2.0","id":1,"result":{"isError":true,"_meta":{"usage":{"input_tokens":12,"output_tokens":4}}}}\n\n'
        capture.append(response[:40], response=True)
        capture.append(response[40:], response=True)
        details = capture.details()
        self.assertEqual(details["outcome"], "error")
        self.assertEqual(details["input_tokens"], 12)
        self.assertNotIn("not-stored", str(details))

    def test_missing_usage_and_bound(self):
        """Keep missing model usage distinct from zero and bound memory."""
        capture = MCPUsageCapture()
        capture.append(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
        capture.append(b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}', response=True)
        self.assertNotIn("input_tokens", capture.details())
        capture.append(b"x" * 300000, response=True)
        self.assertEqual(len(capture.response), 262144)
        self.assertTrue(capture.truncated)

    def test_metrics_count_protocol_errors_and_zero_latency(self):
        """Count HTTP-200 MCP errors and preserve zero-millisecond latency."""
        rows = [
            SimpleNamespace(response_time_ms=0, status_code=200, mcp_details={"outcome": "error"}, blocked=False, timestamp=1),
            SimpleNamespace(response_time_ms=100, status_code=200, mcp_details={"input_tokens": 0, "output_tokens": 3}, blocked=False, timestamp=2),
        ]
        data = summarize(rows)
        self.assertEqual(data["avg_ms"], 50)
        self.assertEqual(data["p95_ms"], 100)
        self.assertEqual(data["success_rate"], 50)
        self.assertEqual(data["input_tokens"], 0)
        self.assertEqual(data["usage_reported_calls"], 1)
        self.assertIsNone(summarize(rows[:1])["input_tokens"])


class TestManagementBoundaries(unittest.TestCase):
    """Check feature flags and management-plane isolation."""

    def test_disabled_self_service(self):
        """Reject public issuance when either feature flag is disabled."""
        # First-Party
        from mcpgateway.routers.server_members import require_self_service

        for enabled, email_auth in ((False, True), (True, False)):
            with patch("mcpgateway.routers.server_members.settings") as settings:
                settings.self_service_api_keys_enabled = enabled
                settings.email_auth_enabled = email_auth
                with self.assertRaises(HTTPException) as error:
                    require_self_service()
                self.assertEqual(error.exception.status_code, 404)

    def test_management_denials(self):
        """Reject anonymous users, API tokens, members, and narrowed admins."""
        # First-Party
        from mcpgateway.routers.server_members import require_platform_session

        for user in (
            {},
            {"auth_method": "anonymous"},
            {"auth_method": "api_token", "is_admin": True},
            {"auth_method": "session", "is_admin": False},
            {"auth_method": "session", "is_admin": True, "token_teams": ["other-team"]},
        ):
            with self.subTest(user=user), self.assertRaises(HTTPException):
                require_platform_session(user)

    def test_metadata_migration(self):
        """Upgrade existing data twice and downgrade without changing request fields."""
        # Third-Party
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        migration = importlib.import_module("mcpgateway.alembic.versions.c31d7e4a092b_add_member_mcp_usage_details")
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE token_usage_logs (id INTEGER PRIMARY KEY, user_email VARCHAR(255))"))
            connection.execute(text("INSERT INTO token_usage_logs VALUES (1, 'member@example.com')"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
                self.assertIn("mcp_details", {c["name"] for c in inspect(connection).get_columns("token_usage_logs")})
                migration.downgrade()
                migration.downgrade()
            self.assertEqual(connection.scalar(text("SELECT user_email FROM token_usage_logs WHERE id=1")), "member@example.com")
        engine.dispose()


class TestUsageMiddleware(unittest.IsolatedAsyncioTestCase):
    """Verify that collection preserves ASGI messages and scoped server identity."""

    async def test_stream_passthrough(self):
        """Capture a protocol error without changing response bytes."""
        # First-Party
        from mcpgateway.middleware.token_usage_middleware import TokenUsageMiddleware

        payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"example"}}'
        output = b'data: {"jsonrpc":"2.0","id":1,"result":{"isError":true}}\n\n'
        received = []

        async def app(scope, receive, send):
            self.assertEqual((await receive())["body"], payload)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": output[:20], "more_body": True})
            await send({"type": "http.response.body", "body": output[20:], "more_body": False})

        async def receive():
            return {"type": "http.request", "body": payload}

        async def send(message):
            received.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp/",
            "modified_path": "/servers/server-a/mcp",
            "headers": [],
            "state": {"auth_method": "api_token", "jti": "test-jti", "user_email": "member@example.com"},
        }
        with patch("mcpgateway.middleware.token_usage_middleware.fresh_db_session"), patch("mcpgateway.middleware.token_usage_middleware.TokenCatalogService") as service:
            service.return_value.log_token_usage = AsyncMock()
            await TokenUsageMiddleware(app)(scope, receive, send)
            details = service.return_value.log_token_usage.call_args.kwargs["mcp_details"]
        self.assertEqual(details["server_id"], "server-a")
        self.assertEqual(details["outcome"], "error")
        self.assertEqual(b"".join(m.get("body", b"") for m in received), output)


if __name__ == "__main__":
    unittest.main()
