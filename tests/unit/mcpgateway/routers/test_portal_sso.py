"""Exercise the parent-cookie exchange and its denial boundaries."""

# Standard
import unittest
from unittest.mock import patch

# Third-Party
from fastapi import FastAPI
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import Base, EmailUser, get_db
from mcpgateway.routers.portal_sso import router
from mcpgateway.utils.member_key_proof import read_member_key_proof


class TestPortalCookieExchange(unittest.IsolatedAsyncioTestCase):
    """Use real ASGI routes and an isolated account database."""

    def setUp(self):
        """Create accounts for allowed and denied portal exchanges."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(EmailUser(email="member@example.com", auth_provider="portal", is_active=True, is_admin=False))
        self.db.add(EmailUser(email="local-member@example.com", auth_provider="local", is_active=True, is_admin=False))
        self.db.add(EmailUser(email="local@example.com", auth_provider="local", is_active=True, is_admin=True))
        self.db.add(EmailUser(email="admin@example.com", auth_provider="portal", is_active=True, is_admin=True))
        self.db.add(EmailUser(email="disabled@example.com", auth_provider="portal", is_active=False, is_admin=False))
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        """Close the isolated database."""
        self.db.close()
        self.engine.dispose()

    async def exchange(self, purpose="login", email="member@example.com", username="Member", origin="http://portal.test"):
        """Call the browser exchange route with parent-page cookies."""
        cookies = {}
        if email is not None:
            cookies["mcp_email"] = email
        if username is not None:
            cookies["mcp_username"] = username
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("127.0.0.12", 12345)), base_url="http://gateway.test", cookies=cookies) as client:
            return await client.post("/auth/portal/exchange", json={"purpose": purpose}, headers={"Origin": origin})

    async def test_login_and_key_receive_different_cookies(self):
        """Keep gateway sessions separate from Key-only proofs."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            login = await self.exchange("login")
            self.assertEqual(login.status_code, 200, login.text)
            self.assertIn("jwt_token=", login.headers["set-cookie"])
            self.assertNotIn("member_key_proof=", login.headers["set-cookie"])
            key = await self.exchange("key")
            self.assertEqual(key.status_code, 200, key.text)
            self.assertIn("member_key_proof=", key.headers["set-cookie"])
            self.assertNotIn("jwt_token=", key.headers["set-cookie"])
            self.assertEqual(key.json()["next"], "/admin/api-key")

    async def test_denial_paths(self):
        """Reject missing cookies, disabled users, administrators, and wrong Origin."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            self.assertEqual((await self.exchange(origin="http://other.test")).status_code, 403)
            self.assertEqual((await self.exchange(email=None)).status_code, 401)
            self.assertEqual((await self.exchange(username=None)).status_code, 401)
            self.assertEqual((await self.exchange(email="invalid-email")).status_code, 401)
            self.assertEqual((await self.exchange(email="local@example.com")).status_code, 403)
            self.assertEqual((await self.exchange(email="admin@example.com")).status_code, 403)
            self.assertEqual((await self.exchange(email="disabled@example.com")).status_code, 403)
            self.assertEqual((await self.exchange(email="unknown@example.com")).status_code, 403)
            self.assertEqual((await self.exchange("key", email="unknown@example.com")).status_code, 403)
            self.assertEqual((await self.exchange("invalid")).status_code, 422)
            with patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", False):
                self.assertEqual((await self.exchange("key")).status_code, 404)
            with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", False):
                self.assertEqual((await self.exchange()).status_code, 404)

    async def test_only_registered_users_can_exchange_cookies(self):
        """Reject unknown accounts without creating them, and accept a registered local user."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            email = "newmember@example.com"
            self.assertEqual((await self.exchange("key", email=email)).status_code, 403)
            login = await self.exchange("login", email=email, username="New Member")
            self.assertEqual(login.status_code, 403, login.text)
            self.assertIsNone(self.db.query(EmailUser).filter_by(email=email).one_or_none())
            local_login = await self.exchange("login", email="local-member@example.com")
            self.assertEqual(local_login.status_code, 200, local_login.text)
            local_key = await self.exchange("key", email="local-member@example.com")
            self.assertEqual(local_key.status_code, 200, local_key.text)
            self.assertEqual(read_member_key_proof(local_key.cookies.get("member_key_proof")), ("local-member@example.com", "local"))

    async def test_proxy_prefix_scopes_both_cookies(self):
        """Return iframe URLs and cookies beneath the configured proxy prefix."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ), patch("mcpgateway.routers.portal_sso.settings.app_root_path", "/mcp"):
            login = await self.exchange("login")
            self.assertEqual(login.json()["next"], "/mcp/admin")
            self.assertIn("Path=/mcp", login.headers["set-cookie"])
            key = await self.exchange("key")
            self.assertEqual(key.json()["next"], "/mcp/admin/api-key")
            self.assertIn("Path=/mcp/admin/api-key", key.headers["set-cookie"])
