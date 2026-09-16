# -*- coding: utf-8 -*-
"""Test MIME registration during resource service construction.

Copyright contributors to the MCP-CONTEXT-FORGE project.
SPDX-License-Identifier: Apache-2.0
"""

# Standard
import mimetypes
import unittest
from unittest.mock import patch

# First-Party
from mcpgateway.services.resource_service import ResourceService


class TestResourceMimeRegistration(unittest.TestCase):
    """Preserve application MIME mappings across resource service instances."""

    def test_preserves_registered_types(self):
        """Keep browser script types and custom resource types after repeated initialization."""
        self.addCleanup(mimetypes.init)
        mimetypes.add_type("text/javascript", ".js")
        mimetypes.add_type("application/x-contextforge-test", ".cfmime")
        for _ in range(2):
            ResourceService()
            self.assertEqual(mimetypes.guess_type("bundle.js")[0], "text/javascript")
            self.assertEqual(mimetypes.guess_type("resource.cfmime")[0], "application/x-contextforge-test")

    def test_initializes_uninitialized_registry(self):
        """Initialize the MIME registry when no previous caller initialized it."""
        mimetypes.init()
        with patch.object(mimetypes, "inited", False), patch.object(mimetypes, "init", wraps=mimetypes.init) as initialize:
            ResourceService()
            initialize.assert_called_once_with()
        self.assertIsNotNone(mimetypes.guess_type("resource.md")[0])


if __name__ == "__main__":
    unittest.main()
