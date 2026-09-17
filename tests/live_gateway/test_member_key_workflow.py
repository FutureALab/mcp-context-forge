"""Exercise member key issuance and analytics against a live isolated gateway.

Set MEMBER_TEST_ADMIN_TOKEN, MEMBER_TEST_EMAIL, MEMBER_TEST_TEAM, and MEMBER_TEST_SERVER.
Set MEMBER_TEST_IMPORT_EMAIL to test an existing account outside the selected team.
Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import io
import os
import time
import unittest

# Third-Party
import httpx
import openpyxl


class TestMemberKeyWorkflow(unittest.TestCase):
    """Validate public membership checks, MCP use, imports, and aggregation."""

    def test_full_workflow(self):
        """Run the public and administrative flows with real HTTP requests."""
        token = os.getenv("MEMBER_TEST_ADMIN_TOKEN")
        if not token:
            self.skipTest("Set MEMBER_TEST_ADMIN_TOKEN for an isolated gateway")
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4445")
        email, team, server = (os.environ[k] for k in ("MEMBER_TEST_EMAIL", "MEMBER_TEST_TEAM", "MEMBER_TEST_SERVER"))
        with httpx.Client(base_url=origin, trust_env=False, timeout=30) as public, httpx.Client(base_url=origin, trust_env=False, timeout=30) as admin:
            page = public.get("/admin/api-key")
            self.assertEqual(page.status_code, 200)
            self.assertIn('id="member-key-form"', page.text)
            self.assertIn("no-store", page.headers["cache-control"])
            self.assertEqual(public.post("/admin/api-key/issue", json={"email": email, "team_id": team, "server_id": server}).status_code, 403)
            public.headers["X-CSRF-Token"] = public.cookies["mcpgateway_csrf_token"]
            public.headers["Origin"] = origin
            options = public.post("/admin/api-key/options", json={"email": email})
            self.assertEqual(options.status_code, 200, options.text)
            self.assertIn(server, [s["id"] for s in options.json()["servers"]])
            bad = public.post("/admin/api-key/issue", json={"email": email, "team_id": "wrong-team", "server_id": server})
            self.assertEqual(bad.status_code, 403, bad.text)
            issued = public.post("/admin/api-key/issue", json={"email": email, "team_id": team, "server_id": server, "days": 7})
            self.assertEqual(issued.status_code, 200, issued.text if issued.status_code != 200 else "")
            key = issued.json()["api_key"]
            self.assertIn("no-store", issued.headers["cache-control"])
            self.assertNotIn("jwt_token", public.cookies)
            mcp_headers = {"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"}
            response = public.post(
                f"/servers/{server}/mcp",
                headers=mcp_headers,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "member-test", "version": "1"}}},
            )
            self.assertEqual(response.status_code, 200, response.text)
            if "mcp-session-id" in response.headers:
                mcp_headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
            public.post(f"/servers/{server}/mcp", headers=mcp_headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            response = public.post(f"/servers/{server}/mcp", headers=mcp_headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("tools", response.text)
            admin.headers["Authorization"] = f"Bearer {token}"
            panel = admin.get("/admin/member-usage")
            self.assertEqual(panel.status_code, 200, panel.text[:200])
            self.assertIn('id="member-panel"', panel.text)
            imported = os.getenv("MEMBER_TEST_IMPORT_EMAIL")
            if imported:
                workbook = openpyxl.Workbook()
                workbook.active.append(["邮箱"])
                for account in (email, imported, "missing-import@example.com"):
                    workbook.active.append([account])
                content = io.BytesIO()
                workbook.save(content)
                workbook.close()
                response = admin.post(f"/admin/member-usage/import/{server}", files={"file": ("members.xlsx", content.getvalue())})
                self.assertEqual(response.status_code, 200, response.text)
                outcomes = {r["email"]: r["status"] for r in response.json()["results"]}
                self.assertEqual(outcomes[email], "skipped")
                self.assertIn(outcomes[imported], ("added", "skipped"))
                self.assertEqual(outcomes["missing-import@example.com"], "failed")
            response = admin.post("/admin/member-usage/keys", json={"server_id": server, "days": 7})
            self.assertEqual(response.status_code, 200, response.text if response.status_code != 200 else "")
            keys = [r["api_key"] for r in response.json()["results"] if r["status"] == "created"]
            self.assertGreaterEqual(len(keys), 1)
            self.assertEqual(len(keys), len(set(keys)))
            for _ in range(10):
                response = admin.get("/admin/member-usage/data", params={"server_id": server, "email": email})
                self.assertEqual(response.status_code, 200, response.text[:200])
                data = response.json()
                if any(m["method"] == "tools/list" for m in data["methods"]):
                    break
                time.sleep(0.2)
            self.assertTrue(any(m["method"] == "tools/list" for m in data["methods"]), data["methods"])
            self.assertGreaterEqual(data["summary"]["calls"], 2)
            self.assertIsNone(data["summary"]["input_tokens"])
            self.assertNotIn(key, response.text)
            denied = public.get("/admin/member-usage/data", headers={"Authorization": f"Bearer {key}"})
            self.assertIn(denied.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
