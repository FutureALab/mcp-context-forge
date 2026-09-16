"""Verify token usage ownership and administrator isolation."""

# Standard
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Third-Party
from fastapi import HTTPException

# First-Party
from mcpgateway.routers.tokens import get_token_usage_stats


class TestTokenUsageOversight(unittest.IsolatedAsyncioTestCase):
    """Keep usage oversight restricted to owners and unrestricted admins."""

    async def test_ownership_matrix(self):
        """Check owner access and deny cross-user access for restricted callers."""
        cases = [
            ("owner@example.com", False, ["team"], True),
            ("admin@example.com", True, None, True),
            ("other@example.com", False, ["team"], False),
            ("admin@example.com", True, ["team"], False),
            ("admin@example.com", True, [], False),
        ]
        for email, is_admin, teams, allowed in cases:
            with self.subTest(email=email, is_admin=is_admin, teams=teams):
                user = {"email": email, "is_admin": is_admin, "token_teams": teams, "auth_method": "session"}
                service = MagicMock()
                service.get_token = AsyncMock(return_value=SimpleNamespace(user_email="owner@example.com") if allowed else None)
                service.get_token_usage_stats = AsyncMock(return_value={
                    "period_days": 30, "total_requests": 7, "successful_requests": 6,
                    "blocked_requests": 1, "success_rate": 6 / 7,
                    "average_response_time_ms": 10, "top_endpoints": [("/mcp", 7)],
                })
                with patch("mcpgateway.routers.tokens.TokenCatalogService", return_value=service):
                    if allowed:
                        result = await get_token_usage_stats.__wrapped__("token-id", 30, user, MagicMock())
                        self.assertEqual(result.total_requests, 7)
                        service.get_token_usage_stats.assert_awaited_once_with(user_email="owner@example.com", token_id="token-id", days=30)
                    else:
                        with self.assertRaises(HTTPException) as error:
                            await get_token_usage_stats.__wrapped__("token-id", 30, user, MagicMock())
                        self.assertEqual(error.exception.status_code, 404)
                        service.get_token_usage_stats.assert_not_called()
                service.get_token.assert_awaited_once_with("token-id", None if is_admin and teams is None else email)

    async def test_non_session_denied(self):
        """Reject anonymous and API-token callers before retrieving usage."""
        for method in (None, "anonymous", "api_token"):
            with self.subTest(method=method), patch("mcpgateway.routers.tokens.TokenCatalogService") as service:
                with self.assertRaises(HTTPException) as error:
                    await get_token_usage_stats.__wrapped__("token-id", 30, {"auth_method": method}, MagicMock())
                self.assertEqual(error.exception.status_code, 403)
                service.assert_not_called()


if __name__ == "__main__":
    unittest.main()
