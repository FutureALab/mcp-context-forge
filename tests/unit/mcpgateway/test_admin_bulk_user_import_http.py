# -*- coding: utf-8 -*-
"""Location: ./tests/unit/mcpgateway/test_admin_bulk_user_import_http.py
Copyright contributors to the MCP-CONTEXT-FORGE project
SPDX-License-Identifier: Apache-2.0

Black-box HTTP tests for POST /admin/users/bulk-import.

These exercise the real request path — multipart parsing, the admin router
mount, the RBAC decorator, and the HTMX response headers — through a
TestClient on the assembled app. Handler-level behaviour is covered by
``test_admin_bulk_user_import.py``.
"""

# Standard
import io
from unittest.mock import AsyncMock, MagicMock, patch

# Third-Party
from fastapi.testclient import TestClient
import openpyxl
import pytest

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook(rows):
    """Build an in-memory ``.xlsx`` file from a list of rows.

    Args:
        rows: Row values, written in order starting at A1.

    Returns:
        bytes: Raw workbook bytes.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def client(main_app_with_admin_api):
    """Yield a TestClient on the admin-mounted app with auth mocked.

    The app fixture flips the admin API settings and mounts the admin router;
    this fixture disables the auth middleware check and stubs the permission
    service, mirroring ``test_admin_catalog_htmx.py``.

    Args:
        main_app_with_admin_api: App fixture that mounts the admin router.

    Yields:
        TestClient: Client bound to the assembled application.
    """
    app = main_app_with_admin_api

    # First-Party
    from mcpgateway.auth import get_current_user
    from mcpgateway.config import settings
    from mcpgateway.db import EmailUser
    from mcpgateway.middleware.rbac import get_current_user_with_permissions
    from mcpgateway.services.permission_service import PermissionService

    original_auth_required = settings.auth_required
    settings.auth_required = False

    mock_user = EmailUser(email="admin@example.com", full_name="Admin", is_admin=True, is_active=True, auth_provider="test")
    mock_security_logger = MagicMock()
    mock_security_logger.log_authentication_attempt = MagicMock(return_value=None)
    mock_security_logger.log_security_event = MagicMock(return_value=None)
    security_logger_patcher = patch("mcpgateway.middleware.auth_middleware.security_logger", mock_security_logger)
    security_logger_patcher.start()

    app.dependency_overrides[get_current_user] = lambda credentials=None, db=None: mock_user

    def _mock_user_with_permissions(request=None, credentials=None, jwt_token=None):
        return {"email": "admin@example.com", "full_name": "Admin", "is_admin": True}

    app.dependency_overrides[get_current_user_with_permissions] = _mock_user_with_permissions

    original_check_permission = PermissionService.check_permission
    PermissionService.check_permission = AsyncMock(return_value=True)

    # Avoid StreamableHTTPSessionManager reuse errors across repeated lifespans.
    streamable_init = patch("mcpgateway.main.streamable_http_session.initialize", new_callable=AsyncMock)
    streamable_shutdown = patch("mcpgateway.main.streamable_http_session.shutdown", new_callable=AsyncMock)
    streamable_init.start()
    streamable_shutdown.start()

    # First-Party
    from mcpgateway.services.http_client_service import SharedHttpClient

    shared_client = MagicMock()
    shared_client.close = AsyncMock()
    original_shared_instance = SharedHttpClient._instance
    SharedHttpClient._instance = shared_client
    shared_get_instance = patch("mcpgateway.services.http_client_service.SharedHttpClient.get_instance", new=AsyncMock(return_value=shared_client))
    shared_shutdown = patch("mcpgateway.services.http_client_service.SharedHttpClient.shutdown", new=AsyncMock())
    shared_get_instance.start()
    shared_shutdown.start()

    yield TestClient(app)

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_with_permissions, None)
    PermissionService.check_permission = original_check_permission
    security_logger_patcher.stop()
    streamable_init.stop()
    streamable_shutdown.stop()
    shared_get_instance.stop()
    shared_shutdown.stop()
    SharedHttpClient._instance = original_shared_instance
    settings.auth_required = original_auth_required


def test_bulk_import_creates_users_over_http(client):
    """Accept a multipart workbook and return the summary with the refresh signal."""
    created = {}

    class RecordingAuthService:
        """Capture the create_user calls made by the endpoint."""

        def __init__(self, db):
            """Accept the request-scoped session, which the fake never uses.

            Args:
                db: Database session from the route dependency.
            """

        async def get_user_by_email(self, email):
            """Report that no user exists yet.

            Args:
                email: Email looked up by the endpoint.

            Returns:
                None: Always, so every row is treated as new.
            """
            return None

        async def create_user(self, **kwargs):
            """Record the call and return a minimal user object.

            Args:
                **kwargs: Keyword arguments passed by the endpoint.

            Returns:
                MagicMock: Stand-in user carrying the email attribute.
            """
            created[kwargs["email"]] = kwargs
            return MagicMock(email=kwargs["email"])

    content = _workbook(
        [
            ["email", "full_name", "password", "is_admin"],
            ["http1@example.com", "HTTP One", "StrongPass1!", "no"],  # pragma: allowlist secret
            ["http2@example.com", "HTTP Two", None, "yes"],
        ]
    )

    with (
        patch("mcpgateway.admin.EmailAuthService", RecordingAuthService),
        patch("mcpgateway.admin.validate_password_strength", lambda password, email="", is_admin=False: (True, "")),
    ):
        response = client.post(
            "/admin/users/bulk-import",
            files={"file": ("users.xlsx", content, XLSX_MEDIA_TYPE)},
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert "2 created, 0 skipped, 0 failed" in response.text
    assert response.headers.get("hx-trigger") == "userCreated"
    assert sorted(created) == ["http1@example.com", "http2@example.com"]
    assert created["http2@example.com"]["is_admin"] is True
    assert created["http1@example.com"]["granted_by"] == "admin@example.com"


def test_bulk_import_requires_a_file_over_http(client):
    """Return the 400 fragment when the multipart body has no file field."""
    response = client.post("/admin/users/bulk-import", data={"other": "x"}, headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert 'data-error-message="Select an .xlsx file to import."' in response.text


def test_bulk_import_rejects_a_non_xlsx_upload_over_http(client):
    """Return the 400 fragment for an upload that is not a workbook."""
    response = client.post("/admin/users/bulk-import", files={"file": ("users.csv", b"email\n", "text/csv")}, headers={"HX-Request": "true"})

    assert response.status_code == 400
    assert 'data-error-message="Only .xlsx files are supported."' in response.text
