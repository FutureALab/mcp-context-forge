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

    def test_password_login_uses_the_same_key_session(self):
        """Use system login for both Key endpoints and reject independent credentials."""
        fixture_path = os.getenv("MEMBER_SESSION_TEST_FIXTURE")
        if not fixture_path:
            self.skipTest("Set MEMBER_SESSION_TEST_FIXTURE for an isolated gateway")
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4450")
        email = os.getenv("MEMBER_SESSION_EMAIL", "session-member@example.com")
        body = {"team_id": "session-team", "server_id": "session-server", "days": 7}
        with httpx.Client(base_url=origin, timeout=30, trust_env=False, headers={"Accept": "text/html, application/json", "X-Forwarded-For": "192.0.2.146"}) as client:
            client.get("/admin/api-key")
            client.headers.update({"Origin": origin, "X-CSRF-Token": client.cookies["mcpgateway_csrf_token"]})
            self.assertEqual(client.post("/admin/api-key/issue", json={**body, "email": email, "password": fixture["password"]}).status_code, 401)
            login = client.post("/admin/login", data={"email": email, "password": fixture["password"], "next": "/admin/api-key"})
            self.assertEqual(login.status_code, 303)
            self.assertEqual(login.headers["location"], "/admin/api-key")
            self.assertIn("jwt_token", client.cookies)
            self.assertNotIn("member_key_proof", client.cookies)
            page = client.get(login.headers["location"])
            self.assertIn('data-session-cookie="true"', page.text)
            client.headers["X-CSRF-Token"] = client.cookies["mcpgateway_csrf_token"]
            for prefix in ("", "sso/"):
                options = client.post(f"/admin/api-key/{prefix}options", json={"email": "session-disabled@example.com"})
                self.assertEqual(options.status_code, 200, options.text)
                self.assertEqual(options.json()["email"], email)
                issued = client.post(f"/admin/api-key/{prefix}issue", json=body)
                self.assertEqual(issued.status_code, 200, "Shared password-session issuance must succeed")
                self.assertEqual(issued.json()["email"], email)
            client.headers["X-Forwarded-For"] = "192.0.2.147"
            unsafe = client.post("/admin/login", data={"email": email, "password": fixture["password"], "next": "https://other.test"})
            self.assertEqual(unsafe.headers["location"], "/admin")
            client.cookies.delete("jwt_token")
            client.get("/admin/api-key")
            client.headers["X-CSRF-Token"] = client.cookies["mcpgateway_csrf_token"]
            failed = client.post("/admin/login", data={"email": email, "password": "incorrect", "next": "/admin/api-key"})  # pragma: allowlist secret
            self.assertIn("error=invalid_credentials", failed.headers["location"])
            self.assertNotIn("jwt_token", client.cookies)

    def test_administrator_portal_login_and_key_session(self):
        """Allow administrator portal sessions while preserving resource checks."""
        if not os.getenv("MEMBER_SESSION_TEST_FIXTURE"):
            self.skipTest("Set MEMBER_SESSION_TEST_FIXTURE for an isolated gateway")
        origin = os.getenv("GATEWAY_URL", "http://127.0.0.1:4450")
        parent_origin = os.getenv("MEMBER_SESSION_PARENT_ORIGIN", "http://127.0.0.1:4451")
        email = os.getenv("MEMBER_SESSION_ADMIN_EMAIL", "session-admin@example.com")
        team = os.getenv("MEMBER_SESSION_TEAM", "session-team")
        server = os.getenv("MEMBER_SESSION_SERVER", "session-server")
        with httpx.Client(base_url=origin, timeout=30, trust_env=False, headers={"Accept": "text/html, application/json"}) as client:
            client.cookies.update({"mcp_username": "Session Admin", "mcp_email": email})
            for purpose in ("login", "key"):
                with self.subTest(purpose=purpose):
                    client.headers["X-Forwarded-For"] = "192.0.2.137" if purpose == "login" else "192.0.2.138"
                    exchange = client.post("/auth/portal/exchange", json={"purpose": purpose}, headers={"Origin": parent_origin})
                    self.assertEqual(exchange.status_code, 200, "Administrator exchange must succeed")
                    self.assertIn("jwt_token", client.cookies)
                    self.assertEqual(client.get(exchange.json()["next"], follow_redirects=True).status_code, 200)
                    self.assertEqual(client.get("/admin/users/partial").status_code, 200)
                    page = client.get("/admin/api-key")
                    self.assertEqual(page.status_code, 200)
                    self.assertIn('data-session-cookie="true"', page.text)
                    headers = {"Origin": origin, "X-CSRF-Token": client.cookies["mcpgateway_csrf_token"]}
                    options = client.post("/admin/api-key/sso/options", json={}, headers=headers)
                    self.assertEqual(options.status_code, 200, options.text)
                    self.assertEqual(options.json()["email"], email)
                    issued = client.post("/admin/api-key/sso/issue", json={"team_id": team, "server_id": server, "days": 7}, headers=headers)
                    self.assertEqual(issued.status_code, 200, "Administrator session Key issuance must succeed")
                    self.assertTrue(issued.json()["api_key"])
                    self.assertEqual(client.post("/admin/api-key/sso/issue", json={"team_id": None, "server_id": server, "days": 7}, headers=headers).status_code, 403)
                    self.assertEqual(client.post("/admin/api-key/sso/issue", json={"team_id": "session-team-b", "server_id": "session-server-b", "days": 7}, headers=headers).status_code, 403)
                    reused = client.post("/auth/portal/exchange", json={"purpose": purpose, "token": exchange.json()["token"]}, headers={"Origin": parent_origin})
                    self.assertEqual(reused.status_code, 200, "Administrator authorization reuse must succeed")
                    self.assertEqual(reused.json()["token"], exchange.json()["token"])
                    self.assertEqual(client.post("/auth/portal/exchange", json={"purpose": purpose}, headers={"Origin": "http://other.test"}).status_code, 403)

            client.cookies.update({"mcp_username": "Session Member", "mcp_email": os.getenv("MEMBER_SESSION_EMAIL", "session-member@example.com")})
            switched = client.post("/auth/portal/exchange", json={"purpose": "login", "token": exchange.json()["token"]}, headers={"Origin": parent_origin})
            self.assertEqual(switched.status_code, 200)
            self.assertIn(client.get("/admin/users/partial").status_code, (302, 403))

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
