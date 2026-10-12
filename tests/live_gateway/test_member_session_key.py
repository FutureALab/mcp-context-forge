"""Verify shared login and Key sessions against an isolated running gateway.

Set MEMBER_SESSION_TEST_FIXTURE to an isolated JSON token fixture and GATEWAY_URL.
Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import json
import os
from pathlib import Path
import unittest

# Third-Party
import httpx


class TestMemberSessionKey(unittest.TestCase):
    """Exercise portal login, session validation, and scoped Key issuance."""

    def test_shared_session_and_denial_paths(self):
        """Use one login for Key issuance and reject invalid or restricted sessions."""
        fixture_path = os.getenv("MEMBER_SESSION_TEST_FIXTURE")
        if not fixture_path:
            self.skipTest("Set MEMBER_SESSION_TEST_FIXTURE for an isolated gateway")
        tokens = json.loads(Path(fixture_path).read_text(encoding="utf-8"))["tokens"]
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4450")
        parent_origin = os.getenv("MEMBER_SESSION_PARENT_ORIGIN", "http://127.0.0.1:4451")
        email = os.getenv("MEMBER_SESSION_EMAIL", "session-member@example.com")
        team = os.getenv("MEMBER_SESSION_TEAM", "session-team")
        server = os.getenv("MEMBER_SESSION_SERVER", "session-server")
        body = {"team_id": team, "server_id": server, "days": 7}
        with httpx.Client(base_url=origin, timeout=30, trust_env=False) as client:
            client.headers["X-Forwarded-For"] = "192.0.2.36"
            client.cookies.update({"mcp_username": "Session Member", "mcp_email": email})
            exchange = client.post("/auth/portal/exchange", json={"purpose": "login"}, headers={"Origin": parent_origin})
            self.assertEqual(exchange.status_code, 200, "Portal login must succeed")
            self.assertIn("jwt_token", client.cookies)
            self.assertNotIn("member_key_proof", client.cookies)
            page = client.get("/admin/api-key")
            self.assertEqual(page.status_code, 200)
            self.assertIn('data-session-cookie="true"', page.text)
            client.headers.update({"Origin": origin, "X-CSRF-Token": client.cookies["mcpgateway_csrf_token"]})
            options = client.post("/admin/api-key/sso/options", json={})
            self.assertEqual(options.status_code, 200, options.text)
            self.assertEqual(options.json()["email"], email)
            self.assertIn(server, [item["id"] for item in options.json()["servers"]])
            issued = client.post("/admin/api-key/sso/issue", json=body)
            self.assertEqual(issued.status_code, 200, "Session Key issuance must succeed")
            self.assertTrue(issued.json()["api_key"])
            self.assertEqual(client.post("/admin/api-key/sso/issue", json=body, headers={"X-CSRF-Token": "wrong"}).status_code, 403)
            client.cookies.delete("jwt_token")
            self.assertEqual(client.post("/admin/api-key/sso/options", json={}).status_code, 401)
            for name, status in (("expired", 401), ("revoked", 401), ("disabled", 401), ("api", 403)):
                with self.subTest(token=name):
                    client.cookies.set("jwt_token", tokens[name])
                    self.assertEqual(client.post("/admin/api-key/sso/options", json={}).status_code, status)
            client.cookies.set("jwt_token", "invalid-session")
            self.assertEqual(client.post("/admin/api-key/sso/options", json={}).status_code, 401)
            client.cookies.set("jwt_token", tokens["narrowed"])
            scoped = client.post("/admin/api-key/sso/options", json={})
            self.assertEqual(scoped.status_code, 200, scoped.text)
            self.assertNotIn(team, [item["id"] for item in scoped.json()["teams"]])
            self.assertEqual(client.post("/admin/api-key/sso/issue", json=body).status_code, 403)
            client.cookies.set("jwt_token", tokens["viewer"])
            self.assertEqual(client.post("/admin/api-key/sso/issue", json=body).status_code, 403)


if __name__ == "__main__":
    unittest.main()
