"""Exercise usage pages against a live gateway and upstream MCP tools.

Set MCP_USAGE_ADMIN_TOKEN, MCP_USAGE_MEMBER_TOKEN, and MCP_USAGE_SERVER.
Set MCP_USAGE_SUCCESS_TOOL and MCP_USAGE_ERROR_TOOL to discovered upstream names.
Use an isolated database with MCP_AUDIT_PAYLOADS_ENABLED=true.
Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import os
import time
import unittest
from uuid import uuid4

# Third-Party
import httpx


class TestMCPUsageLive(unittest.TestCase):
    """Verify real tool traffic, filtering, payloads, and management isolation."""

    def test_usage_pages_and_calls(self):
        """Invoke real tools and inspect their aggregated and paginated audits."""
        admin_token = os.getenv("MCP_USAGE_ADMIN_TOKEN")
        if not admin_token:
            self.skipTest("Set MCP_USAGE_ADMIN_TOKEN for an isolated gateway")
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4447")
        with httpx.Client(base_url=origin, timeout=30, trust_env=False) as admin, httpx.Client(base_url=origin, timeout=30, trust_env=False) as client:
            admin.headers["Authorization"] = f"Bearer {admin_token}"
            page = admin.get("/admin/")
            self.assertEqual(page.status_code, 200)
            for view in ("mcp-dashboard", "mcp-analytics", "mcp-audit"):
                self.assertIn(f'id="{view}-panel"', page.text)
                self.assertIn(f'id="tab-{view}"', page.text)
            admin.headers["X-CSRF-Token"] = admin.cookies["mcpgateway_csrf_token"]
            admin.headers["Origin"] = origin
            server = os.environ["MCP_USAGE_SERVER"]
            issued = admin.post("/tokens", json={"name": f"usage-integration-{uuid4().hex}", "scope": {"server_id": server}, "expires_in_days": 1})
            self.assertEqual(issued.status_code, 201)
            key = issued.json()["access_token"]
            if not key:
                revealed = admin.post(f"/tokens/{issued.json()['token']['id']}/reveal")
                self.assertEqual(revealed.status_code, 200)
                key = revealed.json()["access_token"]
            client.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json, text/event-stream"})
            path = f"/servers/{server}/mcp"
            initialize = client.post(
                path,
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "usage-integration", "version": "1"}}},
            )
            self.assertEqual(initialize.status_code, 200)
            if initialize.headers.get("mcp-session-id"):
                client.headers["Mcp-Session-Id"] = initialize.headers["mcp-session-id"]
            client.post(path, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            client.post(path, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            before = admin.get("/admin/mcp-usage/overview").json()["summary"]["calls"]
            for index in range(22):
                tool = os.environ["MCP_USAGE_ERROR_TOOL" if index == 21 else "MCP_USAGE_SUCCESS_TOOL"]
                result = client.post(
                    path, json={"jsonrpc": "2.0", "id": index + 3, "method": "tools/call", "params": {"name": tool, "arguments": {"department": "engineering", "password": "redaction-fixture"}}}
                )
                self.assertEqual(result.status_code, 200)
            for _ in range(20):
                result = admin.get("/admin/mcp-usage/overview?days=7")
                if result.json()["summary"]["calls"] >= before + 22:
                    break
                time.sleep(0.1)
            data = result.json()
            self.assertEqual(data["summary"]["calls"], before + 22)
            self.assertGreaterEqual(data["summary"]["errors"], 1)
            self.assertEqual(len(data["trend"]), 7)
            self.assertIn("no-store", result.headers["cache-control"])
            audit = admin.get("/admin/mcp-usage/audit?status=error").json()
            self.assertTrue(audit["records"])
            failed = audit["records"][0]
            self.assertEqual(failed["http_status"], 200)
            self.assertIn("engineering", failed["input"])
            self.assertNotIn("redaction-fixture", failed["input"])
            self.assertEqual(failed["server_id"], server)
            self.assertTrue(failed["gateway_id"])
            self.assertIn("isError", failed["output"])
            successful = admin.get("/admin/mcp-usage/audit?status=success").json()["records"][0]
            self.assertNotIn("redaction-fixture", successful["output"])
            self.assertEqual(admin.get("/admin/mcp-usage/audit", params={"search": "not-a-tool"}).json()["total"], 0)
            self.assertGreaterEqual(admin.get("/admin/mcp-usage/audit", params={"gateway_id": failed["gateway_id"], "server_id": server}).json()["total"], 22)
            first = admin.get("/admin/mcp-usage/audit?limit=20").json()
            second = admin.get("/admin/mcp-usage/audit?limit=20&offset=20").json()
            self.assertEqual(len(first["records"]), 20)
            self.assertFalse({row["id"] for row in first["records"]} & {row["id"] for row in second["records"]})
            for endpoint in ("overview", "audit"):
                route = f"/admin/mcp-usage/{endpoint}"
                self.assertIn(httpx.get(origin + route, trust_env=False).status_code, (401, 403))
                self.assertIn(client.get(route).status_code, (401, 403))
                denied = admin.get(route, headers={"Authorization": f"Bearer {os.environ['MCP_USAGE_MEMBER_TOKEN']}"})
                self.assertIn(denied.status_code, (401, 403))
                if os.getenv("MCP_USAGE_NOPERMISSION_TOKEN"):
                    denied = admin.get(route, headers={"Authorization": f"Bearer {os.environ['MCP_USAGE_NOPERMISSION_TOKEN']}"})
                    self.assertIn(denied.status_code, (401, 403))
            self.assertEqual(admin.get("/admin/mcp-usage/audit?status=invalid").status_code, 422)
            self.assertEqual(admin.get("/admin/mcp-usage/audit?limit=101").status_code, 422)


if __name__ == "__main__":
    unittest.main()
