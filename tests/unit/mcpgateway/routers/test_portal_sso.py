"""Exercise parent Session ticket exchange and its denial boundaries."""

# Standard
import secrets
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

# Third-Party
from fastapi import FastAPI
import httpx
import jwt
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import Base, EmailUser, get_db, PortalTicketUse
from mcpgateway.routers.portal_sso import router


class TestPortalTicketExchange(unittest.IsolatedAsyncioTestCase):
    """Use a real database and ASGI routes for parent ticket exchange."""

    def setUp(self):
        """Create an isolated account and ticket-use table."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(EmailUser(email="member@example.com", auth_provider="portal", is_active=True, is_admin=False))
        self.db.add(EmailUser(email="local@example.com", auth_provider="local", is_active=True, is_admin=True))
        self.db.commit()
        self.secret = secrets.token_urlsafe(32)
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        """Close the isolated database."""
        self.db.close()
        self.engine.dispose()

    def ticket(self, purpose="login", email="member@example.com", **overrides):
        """Sign one fixture ticket using the parent contract."""
        now = int(time.time())
        claims = {"iss": "parent-portal", "aud": "contextforge-portal", "sub": "parent-user-1", "email": email, "purpose": purpose, "iat": now, "exp": now + 60, "jti": str(uuid4())}
        claims.update(overrides)
        return jwt.encode(claims, self.secret, algorithm="HS256")

    async def exchange(self, ticket, origin="http://portal.test"):
        """Call the browser exchange route with an Origin header."""
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, client=("127.0.0.12", 12345)), base_url="http://gateway.test") as client:
            return await client.post("/auth/portal/exchange", json={"ticket": ticket}, headers={"Origin": origin})

    async def test_login_and_key_receive_different_cookies(self):
        """Keep gateway sessions separate from Key-only proofs."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch("mcpgateway.routers.portal_sso.settings.portal_sso_shared_secret", SecretStr(self.secret)), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            login = await self.exchange(self.ticket("login"))
            self.assertEqual(login.status_code, 200, login.text)
            self.assertIn("jwt_token=", login.headers["set-cookie"])
            self.assertNotIn("member_key_proof=", login.headers["set-cookie"])
            key = await self.exchange(self.ticket("key"))
            self.assertEqual(key.status_code, 200, key.text)
            self.assertIn("member_key_proof=", key.headers["set-cookie"])
            self.assertNotIn("jwt_token=", key.headers["set-cookie"])
            self.assertEqual(key.json()["next"], "/admin/api-key")
            self.assertEqual(self.db.query(PortalTicketUse).count(), 2)

    async def test_ticket_denial_paths(self):
        """Reject replay, false identity, disabled feature, and cross-site exchange."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch("mcpgateway.routers.portal_sso.settings.portal_sso_shared_secret", SecretStr(self.secret)), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            ticket = self.ticket("key")
            self.assertEqual((await self.exchange(ticket, origin="http://attacker.test")).status_code, 403)
            self.assertEqual((await self.exchange(self.ticket("key", email="unknown@example.com"))).status_code, 403)
            self.assertEqual((await self.exchange(self.ticket("login", email="local@example.com"))).status_code, 403)
            self.assertEqual((await self.exchange(self.ticket("admin"))).status_code, 401)
            self.assertEqual((await self.exchange(self.ticket("key", exp=int(time.time()) - 1))).status_code, 401)
            self.assertEqual((await self.exchange(self.ticket("key", exp=int(time.time()) + 90))).status_code, 401)
            self.assertEqual((await self.exchange(jwt.encode({"email": "member@example.com"}, secrets.token_urlsafe(32), algorithm="HS256"))).status_code, 401)
            self.assertEqual((await self.exchange(self.ticket("key", jti=7))).status_code, 401)
            self.assertEqual((await self.exchange(self.ticket("key", email="invalid-email"))).status_code, 401)
            self.assertEqual((await self.exchange(ticket)).status_code, 200)
            self.assertEqual((await self.exchange(ticket)).status_code, 401)
            user = self.db.query(EmailUser).filter_by(email="member@example.com").one()
            user.is_active = False
            self.db.commit()
            self.assertEqual((await self.exchange(self.ticket("key"))).status_code, 403)
            with patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", False):
                self.assertEqual((await self.exchange(self.ticket("key"))).status_code, 404)
            with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", False):
                self.assertEqual((await self.exchange(self.ticket("key"))).status_code, 404)

    async def test_only_login_provisions_an_unprivileged_user(self):
        """Create an ordinary account at login, then allow its Key authorization."""
        with patch("mcpgateway.routers.portal_sso.settings.portal_sso_enabled", True), patch("mcpgateway.routers.portal_sso.settings.self_service_api_keys_enabled", True), patch("mcpgateway.routers.portal_sso.settings.portal_sso_shared_secret", SecretStr(self.secret)), patch(
            "mcpgateway.routers.portal_sso.settings.portal_sso_parent_origin", "http://portal.test"
        ):
            email = "newmember@example.com"
            self.assertEqual((await self.exchange(self.ticket("key", email=email))).status_code, 403)
            login = await self.exchange(self.ticket("login", email=email))
            self.assertEqual(login.status_code, 200, login.text)
            user = self.db.query(EmailUser).filter_by(email=email).one()
            self.assertEqual(user.auth_provider, "portal")
            self.assertFalse(user.is_admin)
            self.assertEqual((await self.exchange(self.ticket("key", email=email))).status_code, 200)
