"""Keep the database user ID through auth-context caching."""

# Standard
from contextlib import contextmanager
import unittest
from unittest.mock import patch

# Third-Party
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# First-Party
from mcpgateway.auth import _get_auth_context_batched_sync, _user_from_cached_dict
from mcpgateway.db import Base, EmailUser


class TestCachedUserId(unittest.TestCase):
    """Preserve UUID session subjects when users cross the cache boundary."""

    def test_batched_context_round_trips_user_id(self):
        """Return the same ID from the database lookup and cached user object."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        user_id = "5b4f8240-72cb-4451-a077-85a81b3be85b"
        with Session(engine) as db:
            db.add(EmailUser(id=user_id, email="member@example.com", auth_provider="portal"))
            db.commit()

        @contextmanager
        def db_session():
            """Provide the isolated database to the batched lookup."""
            with Session(engine) as db:
                yield db

        try:
            with patch("mcpgateway.auth.fresh_db_session", db_session):
                context = _get_auth_context_batched_sync("member@example.com")
            self.assertEqual(context["user"]["id"], user_id)
            self.assertEqual(_user_from_cached_dict(context["user"]).id, user_id)
        finally:
            engine.dispose()
