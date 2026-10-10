"""Check repeated self-service Key retrieval against an isolated live gateway.

Set MCP_USAGE_MEMBER_EMAIL, MCP_USAGE_MEMBER_PASSWORD, and MCP_USAGE_SERVER.
Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import os
import unittest

# Third-Party
import httpx


class TestMemberKeyRecoveryLive(unittest.TestCase):
    """Verify unchanged key material, expiry limits, and recovery denials."""

    def test_repeat_retrieval(self):
        """Retrieve the same key after renewal and the cumulative lifetime cap."""
        password = os.getenv("MCP_USAGE_MEMBER_PASSWORD")
        if not password:
            self.skipTest("Set isolated self-service fixture credentials")
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4447")
        body = {
            "email": os.environ["MCP_USAGE_MEMBER_EMAIL"],
            "password": password,
            "server_id": os.environ["MCP_USAGE_SERVER"],
            "team_id": None,
            "days": 7,
        }
        with httpx.Client(base_url=origin, trust_env=False, timeout=30) as client:
            page = client.get("/admin/api-key")
            self.assertEqual(page.status_code, 200)
            client.headers.update({"Origin": origin, "X-CSRF-Token": client.cookies["mcpgateway_csrf_token"]})
            self.assertEqual(client.post("/admin/api-key/options", json=body).status_code, 200)
            response = client.post("/admin/api-key/issue", json=body)
            self.assertEqual(response.status_code, 200)
            first = response.json()
            self.assertTrue(first["api_key"])
            legacy_key = os.getenv("MCP_USAGE_LEGACY_KEY")
            if legacy_key:
                self.assertNotEqual(first["api_key"], legacy_key)
                self.assertFalse(first["renewed"])
                for key in (legacy_key, first["api_key"]):
                    initialized = client.post(
                        f"/servers/{body['server_id']}/mcp/",
                        headers={"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"},
                        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "key-recovery-test", "version": "1"}}},
                    )
                    self.assertEqual(initialized.status_code, 200)
                    self.assertIn("protocolVersion", initialized.text)
            for days in (7, 365, 365):
                response = client.post("/admin/api-key/issue", json={**body, "days": days})
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers["cache-control"])
                self.assertEqual(response.headers["pragma"], "no-cache")
                repeated = response.json()
                self.assertEqual(repeated["api_key"], first["api_key"])
                self.assertEqual(repeated["token_id"], first["token_id"])
                self.assertTrue(repeated["renewed"])
                self.assertEqual(repeated["limit_reached"], days == 365)
            self.assertEqual(client.post("/admin/api-key/issue", json={**body, "password": "invalid"}).status_code, 403)
            self.assertEqual(client.post("/admin/api-key/issue", json={**body, "team_id": "unrelated-team"}).status_code, 403)
            self.assertEqual(client.post("/admin/api-key/issue", json=body, headers={"X-CSRF-Token": "invalid"}).status_code, 403)
            self.assertEqual(client.post("/admin/api-key/sso/issue", json={"server_id": body["server_id"], "days": 7}).status_code, 401)
