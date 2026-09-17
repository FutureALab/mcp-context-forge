# -*- coding: utf-8 -*-
"""Location: ./tests/unit/mcpgateway/test_admin_bulk_user_import.py
Copyright contributors to the MCP-CONTEXT-FORGE project
SPDX-License-Identifier: Apache-2.0

Tests for the Admin UI bulk user import endpoint and its Excel parser.
"""

# Standard
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# Third-Party
from fastapi import HTTPException, Request
import openpyxl
import pytest
from starlette.datastructures import Headers, UploadFile

# First-Party
from mcpgateway import admin
from mcpgateway.config import settings
from mcpgateway.middleware import rbac
from mcpgateway.services.email_auth_service import EmailValidationError, UserExistsError

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook_bytes(rows):
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


def _upload(content, filename="users.xlsx"):
    """Wrap raw bytes in an upload object like a multipart request would.

    Args:
        content: Raw file bytes.
        filename: Client-supplied file name.

    Returns:
        UploadFile: Starlette upload instance.
    """
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=Headers({"content-type": XLSX_MEDIA_TYPE}))


def _request(upload):
    """Build a request whose form holds the uploaded file.

    Args:
        upload: Upload to expose, or None for a form without a file field.

    Returns:
        MagicMock: Request double whose ``form()`` resolves to a mapping.
    """
    request = MagicMock(spec=Request)
    request.form = AsyncMock(return_value={} if upload is None else {"file": upload})
    return request


@pytest.fixture
def mock_db():
    """Return a database session double."""
    return MagicMock()


@pytest.fixture(autouse=True)
def _email_auth_enabled(monkeypatch):
    """Enable email authentication for every test in this module."""
    monkeypatch.setattr(settings, "email_auth_enabled", True)


@pytest.fixture
def allow_permission(monkeypatch):
    """Grant the RBAC permission check performed by the route decorator."""
    monkeypatch.setattr(rbac, "check_permission_inline", AsyncMock(return_value=True))


@pytest.fixture
def deny_permission(monkeypatch):
    """Deny the RBAC permission check performed by the route decorator."""
    monkeypatch.setattr(rbac, "check_permission_inline", AsyncMock(return_value=False))


@pytest.fixture
def password_policy_ok(monkeypatch):
    """Accept every password so tests never touch the password policy database."""
    monkeypatch.setattr(admin, "validate_password_strength", lambda password, email="", is_admin=False: (True, ""))


@pytest.fixture
def auth_service(monkeypatch):
    """Stub EmailAuthService with no existing users and successful creation."""
    service = MagicMock()
    service.get_user_by_email = AsyncMock(return_value=None)
    service.create_user = AsyncMock(return_value=SimpleNamespace(email="created@example.com"))
    monkeypatch.setattr(admin, "EmailAuthService", lambda _db: service)
    return service


# ---------------------------------------------------------------------------
# parse_bulk_user_workbook
# ---------------------------------------------------------------------------
def test_parse_workbook_reads_supported_columns_and_skips_blank_rows():
    """Map the known columns and drop rows that hold no values."""
    rows = admin.parse_bulk_user_workbook(
        _workbook_bytes(
            [
                ["email", "full_name", "password", "is_admin"],
                ["a@example.com", "Alice", "StrongPass1!", "yes"],  # pragma: allowlist secret
                [None, None, None, None],
                ["b@example.com", "Bob", None, None],
            ]
        )
    )

    assert rows == [
        {"email": "a@example.com", "full_name": "Alice", "password": "StrongPass1!", "is_admin": "yes"},  # pragma: allowlist secret
        {"email": "b@example.com", "full_name": "Bob", "password": None, "is_admin": None},
    ]


def test_parse_workbook_accepts_header_aliases_and_chinese_headers():
    """Accept aliases such as E-Mail, Full Name, and the Chinese column names."""
    rows = admin.parse_bulk_user_workbook(
        _workbook_bytes(
            [
                ["E-Mail", "Full Name", "密码", "是否管理员"],
                ["c@example.com", "Carol", "Xx1!aBcd", "是"],  # pragma: allowlist secret
            ]
        )
    )

    assert rows == [{"email": "c@example.com", "full_name": "Carol", "password": "Xx1!aBcd", "is_admin": "是"}]  # pragma: allowlist secret


def test_parse_workbook_ignores_unmapped_columns():
    """Leave columns that carry no canonical name out of the parsed rows."""
    rows = admin.parse_bulk_user_workbook(_workbook_bytes([["email", "department"], ["d@example.com", "Sales"]]))

    assert rows == [{"email": "d@example.com"}]


def test_parse_workbook_requires_the_email_column():
    """Reject a workbook whose header has no email column."""
    with pytest.raises(ValueError, match="缺少必填列：邮箱"):
        admin.parse_bulk_user_workbook(_workbook_bytes([["full_name", "password"], ["Alice", "StrongPass1!"]]))  # pragma: allowlist secret


def test_parse_workbook_rejects_an_unreadable_file():
    """Reject bytes that are not a workbook."""
    with pytest.raises(ValueError, match="无法读取 Excel 文件"):
        admin.parse_bulk_user_workbook(b"this is not a workbook")


def test_parse_workbook_rejects_an_empty_workbook():
    """Reject a workbook with no header row."""
    with pytest.raises(ValueError, match="Excel 文件为空。"):
        admin.parse_bulk_user_workbook(_workbook_bytes([]))


def test_parse_workbook_enforces_the_row_cap(monkeypatch):
    """Stop reading once the configured row cap is exceeded."""
    monkeypatch.setattr(admin, "BULK_USER_IMPORT_MAX_ROWS", 2)

    with pytest.raises(ValueError, match="不能超过 2 行"):
        admin.parse_bulk_user_workbook(_workbook_bytes([["email"], ["a@example.com"], ["b@example.com"], ["c@example.com"]]))


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("yes", True),
        ("TRUE", True),
        ("no", False),
        ("", False),
        ("是", True),
        ("否", False),
        (None, False),
        ("unexpected", False),
    ],
)
def test_coerce_bulk_user_bool(value, expected):
    """Interpret the is_admin cell across the accepted value shapes."""
    assert admin._coerce_bulk_user_bool(value) is expected


# ---------------------------------------------------------------------------
# Route contract
# ---------------------------------------------------------------------------
def test_bulk_import_route_is_registered():
    """Expose the import endpoint at the path the Admin UI posts to."""
    paths = {route.path for route in admin.admin_router.routes}

    assert "/admin/users/bulk-import" in paths


def test_bulk_import_route_fails_closed_on_permission():
    """Require the granular permission and refuse the admin bypass."""
    assert admin.admin_bulk_import_users._required_permission == "admin.user_management"
    assert admin.admin_bulk_import_users._allow_admin_bypass is False


# ---------------------------------------------------------------------------
# Deny paths
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_import_requires_authentication(mock_db, allow_permission):
    """Reject a caller with no authenticated identity."""
    with pytest.raises(HTTPException) as excinfo:
        await admin.admin_bulk_import_users(request=_request(None), db=mock_db, user={})

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_bulk_import_denies_without_user_management_permission(mock_db, deny_permission):
    """Reject an authenticated caller who lacks admin.user_management."""
    with pytest.raises(HTTPException) as excinfo:
        await admin.admin_bulk_import_users(request=_request(None), db=mock_db, user={"email": "viewer@example.com"})

    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_bulk_import_is_disabled_without_email_auth(mock_db, allow_permission, monkeypatch):
    """Refuse the import when email authentication is turned off."""
    monkeypatch.setattr(settings, "email_auth_enabled", False)

    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ["a@example.com"]]))), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 403
    assert "邮箱认证未启用" in response.body.decode()


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [[], ["other-team"]])
async def test_team_assignment_denies_narrowed_admin(mock_db, allow_permission, auth_service, scope):
    """Reject team assignment outside unrestricted platform administration."""
    request = _request(_upload(_workbook_bytes([["邮箱", "团队 ID"], ["a@example.com", "target-team"]])))
    response = await admin.admin_bulk_import_users(request=request, db=mock_db, user={"email": "admin@example.com", "is_admin": True, "token_teams": scope})
    assert response.status_code == 403
    auth_service.create_user.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("team", [None, SimpleNamespace(is_active=False, is_personal=False), SimpleNamespace(is_active=True, is_personal=True)])
async def test_team_assignment_denies_invalid_team(mock_db, allow_permission, auth_service, team):
    """Reject missing, disabled, and personal teams before creating users."""
    mock_db.get.return_value = team
    request = _request(_upload(_workbook_bytes([["邮箱", "团队 ID"], ["a@example.com", "target-team"]])))
    response = await admin.admin_bulk_import_users(request=request, db=mock_db, user={"email": "admin@example.com", "is_admin": True, "token_teams": None})
    assert response.status_code == 400
    auth_service.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_import_rejects_a_missing_file(mock_db, allow_permission):
    """Reject a submission with no file field."""
    response = await admin.admin_bulk_import_users(request=_request(None), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "请选择 Excel 文件" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_rejects_a_non_xlsx_file(mock_db, allow_permission):
    """Reject a file whose extension is not xlsx."""
    response = await admin.admin_bulk_import_users(request=_request(_upload(b"email\na@example.com", filename="users.csv")), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "仅支持 Excel 文件。" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_rejects_an_empty_file(mock_db, allow_permission):
    """Reject a zero-byte upload."""
    response = await admin.admin_bulk_import_users(request=_request(_upload(b"")), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "为空" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_rejects_an_oversized_file(mock_db, allow_permission, monkeypatch):
    """Reject an upload larger than the byte cap, before parsing it."""
    monkeypatch.setattr(admin, "BULK_USER_IMPORT_MAX_BYTES", 16)

    response = await admin.admin_bulk_import_users(request=_request(_upload(b"x" * 32)), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "不能超过" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_reports_an_unparseable_workbook(mock_db, allow_permission):
    """Surface the parser error instead of creating any user."""
    response = await admin.admin_bulk_import_users(request=_request(_upload(b"not a workbook")), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "无法读取 Excel 文件" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_rejects_a_workbook_without_data_rows(mock_db, allow_permission):
    """Reject a workbook that holds only a header row."""
    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email", "full_name"]]))), db=mock_db, user={"email": "admin@example.com"})

    assert response.status_code == 400
    assert "没有用户数据" in response.body.decode()


# ---------------------------------------------------------------------------
# Import behaviour
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_import_creates_every_row_and_reports_a_summary(mock_db, allow_permission, password_policy_ok, auth_service):
    """Create one user per row and return the per-row summary."""
    content = _workbook_bytes(
        [
            ["email", "full_name", "password", "is_admin"],
            ["first@example.com", "First User", "StrongPass1!", "no"],  # pragma: allowlist secret
            ["second@example.com", "Second User", "StrongPass2!", "yes"],  # pragma: allowlist secret
        ]
    )

    response = await admin.admin_bulk_import_users(request=_request(_upload(content)), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "userCreated"
    assert "新增 2，跳过 0，失败 0" in body
    assert body.count("<tr") == 3  # header row plus two data rows
    assert auth_service.create_user.await_count == 2

    first_call, second_call = auth_service.create_user.await_args_list
    assert first_call.kwargs["email"] == "first@example.com"
    assert first_call.kwargs["full_name"] == "First User"
    assert first_call.kwargs["is_admin"] is False
    assert first_call.kwargs["auth_provider"] == "local"
    assert first_call.kwargs["granted_by"] == "admin@example.com"
    assert first_call.kwargs["password_change_required"] is False
    assert first_call.kwargs["skip_password_validation"] is False
    assert second_call.kwargs["is_admin"] is True


@pytest.mark.asyncio
async def test_bulk_import_skips_existing_users(mock_db, allow_permission, password_policy_ok, auth_service):
    """Skip a row whose email already exists and never call create_user."""
    auth_service.get_user_by_email = AsyncMock(return_value=SimpleNamespace(email="dup@example.com"))

    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ["dup@example.com"]]))), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert response.status_code == 200
    assert "新增 0，跳过 1，失败 0" in body
    assert "账号已存在" in body
    assert "HX-Trigger" not in response.headers
    auth_service.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_import_treats_a_creation_race_as_skipped(mock_db, allow_permission, password_policy_ok, auth_service):
    """Report a duplicate raised by create_user as skipped, not failed."""
    auth_service.create_user = AsyncMock(side_effect=UserExistsError("User with email a@example.com already exists"))

    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ["a@example.com"]]))), db=mock_db, user={"email": "admin@example.com"})

    assert "新增 0，跳过 1，失败 0" in response.body.decode()


@pytest.mark.asyncio
async def test_bulk_import_fails_a_row_with_a_weak_password(mock_db, allow_permission, auth_service, monkeypatch):
    """Reject a supplied password that breaks the policy without creating the user."""
    monkeypatch.setattr(admin, "validate_password_strength", lambda password, email="", is_admin=False: (False, "Password is too weak"))

    response = await admin.admin_bulk_import_users(
        request=_request(_upload(_workbook_bytes([["email", "password"], ["weak@example.com", "short"]]))), db=mock_db, user={"email": "admin@example.com"}
    )  # pragma: allowlist secret
    body = response.body.decode()

    assert "新增 0，跳过 0，失败 1" in body
    assert "Password is too weak" in body
    auth_service.create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_import_fails_a_row_without_an_email(mock_db, allow_permission, password_policy_ok, auth_service):
    """Fail a row whose email cell is empty."""
    content = _workbook_bytes(
        [
            ["email", "full_name"],
            ["", "No Email"],
            ["kept@example.com", "Kept"],
        ]
    )

    response = await admin.admin_bulk_import_users(request=_request(_upload(content)), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert "新增 1，跳过 0，失败 1" in body
    assert "邮箱不能为空。" in body
    assert auth_service.create_user.await_count == 1


@pytest.mark.asyncio
async def test_bulk_import_uses_the_default_password_and_forces_a_change(mock_db, allow_permission, auth_service, monkeypatch):
    """Use the configured default password and flag the account for rotation."""
    monkeypatch.setattr(settings, "password_change_enforcement_enabled", True)
    monkeypatch.setattr(settings, "require_password_change_for_default_password", True)

    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ["defaulted@example.com"]]))), db=mock_db, user={"email": "admin@example.com"})
    call = auth_service.create_user.await_args

    assert response.status_code == 200
    assert call.kwargs["password"] == settings.default_user_password.get_secret_value()
    assert call.kwargs["skip_password_validation"] is True
    assert call.kwargs["password_change_required"] is True


@pytest.mark.asyncio
async def test_bulk_import_keeps_going_after_a_row_fails(mock_db, allow_permission, password_policy_ok, auth_service):
    """Create the remaining rows when one row raises an unexpected error."""
    auth_service.create_user = AsyncMock(side_effect=[RuntimeError("database exploded"), SimpleNamespace(email="ok@example.com")])
    content = _workbook_bytes(
        [
            ["email"],
            ["boom@example.com"],
            ["ok@example.com"],
        ]
    )

    response = await admin.admin_bulk_import_users(request=_request(_upload(content)), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert "新增 1，跳过 0，失败 1" in body
    assert "创建用户或分配团队失败" in body
    assert auth_service.create_user.await_count == 2


@pytest.mark.asyncio
async def test_bulk_import_escapes_spreadsheet_content(mock_db, allow_permission, password_policy_ok, auth_service):
    """Escape workbook and service text so the fragment cannot inject markup."""
    payload = "<script>alert(1)</script>"
    auth_service.create_user = AsyncMock(side_effect=EmailValidationError(payload))

    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ["victim@example.com"]]))), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert "<script>" not in body
    assert "&lt;script&gt;" in body


@pytest.mark.asyncio
async def test_bulk_import_escapes_a_malicious_email(mock_db, allow_permission, password_policy_ok, auth_service):
    """Escape an email cell that carries markup."""
    response = await admin.admin_bulk_import_users(request=_request(_upload(_workbook_bytes([["email"], ['<img src=x onerror="x">@example.com']]))), db=mock_db, user={"email": "admin@example.com"})
    body = response.body.decode()

    assert "<img" not in body
    assert "&lt;img" in body


@pytest.mark.asyncio
async def test_bulk_import_derives_granted_by_from_the_session(mock_db, allow_permission, password_policy_ok, auth_service):
    """Ignore spreadsheet-supplied ownership and use the authenticated admin."""
    content = _workbook_bytes(
        [
            ["email", "granted_by", "owner_email"],
            ["owned@example.com", "attacker@example.com", "attacker@example.com"],
        ]
    )

    await admin.admin_bulk_import_users(request=_request(_upload(content)), db=mock_db, user={"email": "real-admin@example.com"})

    assert auth_service.create_user.await_args.kwargs["granted_by"] == "real-admin@example.com"
