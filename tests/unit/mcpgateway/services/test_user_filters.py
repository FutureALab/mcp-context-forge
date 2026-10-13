"""Verify combined user filters and pagination with persisted memberships.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
from datetime import timedelta
import unittest

# Third-Party
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.db import Base, EmailTeam, EmailTeamMember, EmailUser, Role, UserRole, utc_now
from mcpgateway.services.email_auth_service import EmailAuthService


class TestUserFilters(unittest.IsolatedAsyncioTestCase):
    """Use real queries to check filters before pagination."""

    def setUp(self):
        """Create users with distinct roles and memberships."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all(
            [
                EmailUser(email="alice@example.com", full_name="Alice", is_admin=False),
                EmailUser(email="allen@example.com", full_name="Allen", is_admin=False),
                EmailUser(email="bob@example.com", full_name="Bob", is_admin=True),
                EmailUser(email="a%literal@example.com", full_name="Literal", is_admin=False),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                EmailTeam(id="team-a", name="Team A", slug="team-a", created_by="bob@example.com"),
                EmailTeam(id="team-b", name="Team B", slug="team-b", created_by="bob@example.com"),
                Role(id="developer-role", name="developer-fixture", scope="team", created_by="bob@example.com", permissions=["tools.read"]),
                Role(id="global-role", name="global-fixture", scope="global", created_by="bob@example.com", permissions=["tools.read"]),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                EmailTeamMember(team_id="team-a", user_email="alice@example.com"),
                EmailTeamMember(team_id="team-b", user_email="alice@example.com"),
                EmailTeamMember(team_id="team-a", user_email="allen@example.com"),
                EmailTeamMember(team_id="team-a", user_email="bob@example.com"),
                UserRole(user_email="alice@example.com", role_id="developer-role", scope="team", scope_id="team-a", granted_by="bob@example.com"),
                UserRole(user_email="alice@example.com", role_id="developer-role", scope="team", scope_id="team-b", granted_by="bob@example.com"),
                UserRole(user_email="allen@example.com", role_id="developer-role", scope="team", scope_id="team-b", granted_by="bob@example.com"),
                UserRole(user_email="bob@example.com", role_id="global-role", scope="global", granted_by="bob@example.com"),
            ]
        )
        self.db.commit()
        self.service = EmailAuthService(self.db)

    def tearDown(self):
        """Release the isolated database."""
        self.db.close()
        self.engine.dispose()

    async def test_combined_filters_and_pagination(self):
        """Combine search, role, and team filters before counting rows."""
        result = await self.service.list_users(search="AL", role_id="developer-role", team_id="team-a", page=1, per_page=1)
        self.assertEqual([user.email for user in result.data], ["alice@example.com"])
        assert result.pagination is not None
        assert result.links is not None
        self.assertEqual(result.pagination.total_items, 1)
        self.assertIn("role_id=developer-role", result.links.self)
        result = await self.service.list_users(role_id="developer-role", page=1, per_page=1)
        assert result.pagination is not None
        self.assertEqual(result.pagination.total_items, 2)
        self.assertEqual(result.pagination.total_pages, 2)
        second = await self.service.list_users(role_id="developer-role", page=2, per_page=1)
        self.assertNotEqual(result.data[0].email, second.data[0].email)
        self.assertEqual([user.email for user in (await self.service.list_users(role_id="global-role", team_id="team-a")).data], ["bob@example.com"])

    async def test_administrator_flag_and_literal_search(self):
        """Filter administrator flags and escape wildcard characters in searches."""
        admins = await self.service.list_users(role_id="__admin__")
        self.assertEqual([user.email for user in admins.data], ["bob@example.com"])
        members = await self.service.list_users(role_id="__member__", team_id="team-a")
        self.assertEqual({user.email for user in members.data}, {"alice@example.com", "allen@example.com"})
        literal = await self.service.list_users(search="a%")
        self.assertEqual([user.email for user in literal.data], ["a%literal@example.com"])
        self.assertEqual([user.email for user in (await self.service.list_users(search="Literal")).data], ["a%literal@example.com"])
        self.assertEqual((await self.service.list_users(role_id="unknown", team_id="team-a")).data, [])

    async def test_inactive_and_expired_assignments(self):
        """Exclude inactive memberships, roles, and expired role assignments."""
        assignment = self.db.query(UserRole).filter_by(user_email="alice@example.com", scope_id="team-a").one()
        assignment.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        self.assertEqual((await self.service.list_users(role_id="developer-role", team_id="team-a")).data, [])
        assignment.expires_at = None
        assignment.is_active = False
        self.db.commit()
        self.assertEqual((await self.service.list_users(role_id="developer-role", team_id="team-a")).data, [])
        assignment.is_active = True
        membership = self.db.query(EmailTeamMember).filter_by(user_email="alice@example.com", team_id="team-a").one()
        membership.is_active = False
        self.db.commit()
        self.assertEqual((await self.service.list_users(role_id="developer-role", team_id="team-a")).data, [])
        membership.is_active = True
        self.db.query(Role).filter_by(id="developer-role").one().is_active = False
        self.db.commit()
        self.assertEqual((await self.service.list_users(role_id="developer-role")).data, [])
