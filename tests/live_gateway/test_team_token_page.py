"""Check team-scoped token templates against a running gateway.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import os
import unittest
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


class TestTeamTokenPage(unittest.TestCase):
    """Exercise dashboard and HTMX rendering with a member session."""

    def test_team_token_templates(self):
        """Keep translations callable when pagination includes a team filter."""
        token = os.environ.get("TEST_SESSION_TOKEN")
        team_id = os.environ.get("TEST_TEAM_ID")
        if not token or not team_id:
            self.skipTest("Set TEST_SESSION_TOKEN and TEST_TEAM_ID for a team member")
        origin = os.environ.get("GATEWAY_URL", "http://127.0.0.1:4444").rstrip("/")
        opener = build_opener(ProxyHandler({}))
        for path, extra, marker in (
            ("/admin/", {}, 'id="create-token-form"'),
            ("/admin/", {"tokens_q": "regression"}, 'id="tokens-pagination-controls"'),
            ("/admin/tokens/partial", {}, 'id="tokens-pagination-controls"'),
            ("/admin/tokens/partial", {"render": "controls"}, "data-extra-params"),
        ):
            with self.subTest(path=path, extra=extra):
                query = urlencode({"team_id": team_id, **extra})
                request = Request(f"{origin}{path}?{query}", headers={"Authorization": f"Bearer {token}"})
                with opener.open(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn(marker, body)
                    self.assertIn(team_id, body)


if __name__ == "__main__":
    unittest.main()
