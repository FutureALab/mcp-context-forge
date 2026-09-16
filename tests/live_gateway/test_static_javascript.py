# -*- coding: utf-8 -*-
"""Verify JavaScript response types against a running gateway.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0

Set GATEWAY_URL to the gateway origin before running this module with unittest.
"""

# Standard
import os
import unittest
from urllib.request import ProxyHandler, build_opener


class TestStaticJavaScript(unittest.TestCase):
    """Check that browsers can execute static JavaScript files."""

    def test_javascript_content_type(self):
        """Serve scripts as JavaScript even when host MIME mappings differ."""
        base_url = os.environ.get("GATEWAY_URL", "http://127.0.0.1:4444").rstrip("/")
        opener = build_opener(ProxyHandler({}))
        for path in ("/static/js/password-validator.js", "/static/gantt-chart.js"):
            with self.subTest(path=path):
                with opener.open(f"{base_url}{path}", timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(response.headers.get_content_type(), ("text/javascript", "application/javascript"))


if __name__ == "__main__":
    unittest.main()
