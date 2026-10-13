"""Verify user search and filters through the running administration API.

Set MEMBER_SESSION_TEST_FIXTURE, GATEWAY_URL, and MEMBER_SESSION_PARENT_ORIGIN.
Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import html
import json
import os
import re
import unittest

# Third-Party
import httpx


class TestUserFilters(unittest.TestCase):
    """Check combined filters, pagination, reset, and authorization."""

    def test_filters_and_authorization(self):
        """Exercise user filters without bypassing the user-management permission."""
        if not os.getenv("MEMBER_SESSION_TEST_FIXTURE"):
            self.skipTest("Set MEMBER_SESSION_TEST_FIXTURE for an isolated gateway")
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4450")
        parent_origin = os.getenv("MEMBER_SESSION_PARENT_ORIGIN", "http://127.0.0.1:4451")
        with httpx.Client(base_url=origin, timeout=30, trust_env=False, headers={"Accept": "text/html", "X-Forwarded-For": "192.0.2.154"}) as client:
            self.assertIn(client.get("/admin/users/partial", params={"search": "session"}).status_code, (302, 401, 403))
            client.cookies.update({"mcp_username": "Session Admin", "mcp_email": "session-admin@example.com"})
            self.assertEqual(client.post("/auth/portal/exchange", json={"purpose": "login"}, headers={"Origin": parent_origin}).status_code, 200)
            filters = {"search": "Session Member", "role_id": "session-role", "filter_team_id": "session-team"}
            combined = client.get("/admin/users/partial", params=filters)
            self.assertEqual(combined.status_code, 200)
            self.assertEqual(re.findall(r"📧\s*([^<]+)", combined.text), ["session-member@example.com"])
            self.assertIn('id="users-filter-form"', combined.text)
            encoded = re.search(r'data-extra-params="([^"]+)"', combined.text)
            assert encoded is not None
            self.assertEqual(json.loads(html.unescape(encoded.group(1))), filters)
            admins = client.get("/admin/users/partial", params={"role_id": "__admin__"})
            self.assertIn("session-admin@example.com", re.findall(r"📧\s*([^<]+)", admins.text))
            self.assertNotIn("session-member@example.com", re.findall(r"📧\s*([^<]+)", admins.text))
            params = {"search": "Session", "filter_team_id": "session-team", "per_page": 1}
            first = client.get("/admin/users/partial", params={**params, "page": 1})
            second = client.get("/admin/users/partial", params={**params, "page": 2})
            self.assertIn('data-total-items="3"', first.text)
            self.assertNotEqual(re.findall(r"📧\s*([^<]+)", first.text), re.findall(r"📧\s*([^<]+)", second.text))
            empty = client.get("/admin/users/partial", params={"search": "not-existing-user"})
            self.assertEqual(re.findall(r"📧\s*([^<]+)", empty.text), [])
            reset = client.get("/admin/users/partial", params={**filters, "clear_filters": 1})
            self.assertGreater(len(re.findall(r"📧\s*([^<]+)", reset.text)), 1)
            self.assertIn('value="" placeholder="输入邮箱或姓名开头"', reset.text)
            client.cookies.update({"mcp_email": "session-member@example.com"})
            self.assertEqual(client.post("/auth/portal/exchange", json={"purpose": "login"}, headers={"Origin": parent_origin}).status_code, 200)
            self.assertIn(client.get("/admin/users/partial", params=filters).status_code, (302, 403))


if __name__ == "__main__":
    unittest.main()
