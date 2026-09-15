"""Unit tests for ContextForge internationalization.

Covers locale normalization and negotiation, catalog loading and compilation,
the context-variable translator, Jinja2 rendering, and the ASGI middleware.
"""

from __future__ import annotations

import asyncio
import gettext as gettext_module
import json
from pathlib import Path

import pytest
from jinja2 import Environment
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcpgateway import i18n
from mcpgateway.config import settings
from mcpgateway.middleware.i18n import I18nMiddleware
from mcpgateway.scripts.i18n import compile_catalog, default_header, Entry, locale_plural_forms, parse_po, render_po
from mcpgateway.services.email_notification_service import AuthEmailNotificationService

REPO_ROOT = Path(__file__).resolve().parents[3]
ZH_PO = REPO_ROOT / "mcpgateway" / "translations" / "zh_CN" / "LC_MESSAGES" / "messages.po"


class TestLocaleNormalization:
    """Locale tags resolve to the supported locale set."""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("zh-CN", "zh-CN"),
            ("zh-cn", "zh-CN"),
            ("zh", "zh-CN"),
            ("zh_CN", "zh-CN"),
            ("zh-Hans-CN", "zh-CN"),
            ("en", "en"),
            ("en-US", "en"),
            ("fr", None),
            ("", None),
            (None, None),
        ],
    )
    def test_normalize_locale(self, tag, expected):
        """Aliases and legacy spellings map to a supported locale."""
        assert i18n.normalize_locale(tag) == expected

    def test_supported_locales_lists_chinese(self):
        """The supported set includes English and Simplified Chinese."""
        locales = i18n.supported_locales()
        assert locales["en"] == "English"
        assert locales["zh-CN"] == "简体中文"


class TestAcceptLanguage:
    """Accept-Language parsing honours quality values."""

    def test_orders_by_quality(self):
        """Ordering follows the q parameter."""
        assert i18n.parse_accept_language("en;q=0.4,zh-CN;q=0.9") == ["zh-CN", "en"]

    def test_drops_explicitly_unacceptable(self):
        """A q=0 tag is not acceptable per RFC 9110."""
        assert "zh-CN" not in i18n.parse_accept_language("zh-CN;q=0,en;q=0.8")

    def test_header_order_breaks_ties(self):
        """Equal quality values keep header order."""
        assert i18n.parse_accept_language("en,zh-CN") == ["en", "zh-CN"]

    def test_empty_header(self):
        """An absent header yields no candidates."""
        assert i18n.parse_accept_language(None) == []
        assert i18n.parse_accept_language("") == []


class TestResolveLocale:
    """Locale resolution follows the documented precedence."""

    def test_query_parameter_wins(self):
        """The lang query parameter outranks every other signal."""
        assert i18n.resolve_locale(query_param="zh-CN", cookie="en", accept_language="en") == "zh-CN"

    def test_cookie_outranks_header(self):
        """The cookie outranks Accept-Language."""
        assert i18n.resolve_locale(cookie="zh-CN", accept_language="en") == "zh-CN"

    def test_user_preference_outranks_header(self):
        """The stored user preference outranks Accept-Language."""
        assert i18n.resolve_locale(user_preference="zh-CN", accept_language="en") == "zh-CN"

    def test_header_used_when_no_explicit_choice(self):
        """Accept-Language is used when nothing explicit is set."""
        assert i18n.resolve_locale(accept_language="zh-CN,zh;q=0.9") == "zh-CN"

    def test_default_when_nothing_matches(self):
        """Unsupported signals fall back to the configured default."""
        assert i18n.resolve_locale(query_param="fr", accept_language="de") == i18n.default_locale()


class TestTranslator:
    """The translator reads compiled catalogs and degrades safely."""

    def test_translates_known_message(self):
        """A catalogued message returns its Chinese translation."""
        assert i18n.Translator("zh-CN").gettext("Tools") == "工具"

    def test_unknown_message_passes_through(self):
        """An uncatalogued message returns the source text."""
        source = "This message is deliberately absent from the catalog"
        assert i18n.Translator("zh-CN").gettext(source) == source

    def test_placeholders_are_interpolated(self):
        """Brace placeholders use the same syntax as the Admin UI JavaScript."""
        assert i18n.Translator("zh-CN").gettext("Deleted {count} tools", count=3) == "已删除 3 个工具"

    def test_unknown_placeholders_are_left_alone(self):
        """A placeholder without a value stays in the message."""
        assert i18n.interpolate("Hello {name}", {}) == "Hello {name}"
        assert i18n.interpolate("Hello {name}", {"other": 1}) == "Hello {name}"

    def test_gettext_style_placeholders_still_expand(self):
        """Conventional %(name)s placeholders remain supported."""
        assert i18n.interpolate("Deleted %(count)s tools", {"count": 3}) == "Deleted 3 tools"

    def test_english_catalog_is_identity(self):
        """The source locale returns the message unchanged."""
        assert i18n.Translator("en").gettext("Tools") == "Tools"

    def test_unsupported_locale_falls_back(self):
        """An unsupported locale falls back to the active locale."""
        assert i18n.Translator("fr").gettext("Tools") in {"Tools", "工具"}

    def test_catalog_mapping_exposes_entries(self):
        """The browser dictionary is built from the same catalog."""
        mapping = i18n.catalog_mapping("zh-CN")
        assert mapping["Tools"] == "工具"
        assert mapping["Search"] == "搜索"


class TestLocaleContext:
    """The context variable binds and restores locales."""

    def test_gettext_uses_bound_locale(self):
        """Module-level gettext resolves through the context variable."""
        assert i18n.get_locale() == i18n.default_locale()
        with i18n.LocaleContext("zh-CN"):
            assert i18n.get_locale() == "zh-CN"
            assert i18n.gettext("Tools") == "工具"
        assert i18n.get_locale() == i18n.default_locale()

    def test_unsupported_locale_binding_falls_back(self):
        """Binding an unsupported locale binds the default instead."""
        with i18n.LocaleContext("fr"):
            assert i18n.get_locale() == i18n.default_locale()

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_locale_keeps_active_locale(self, empty):
        """An empty preference keeps the locale bound by the request."""
        with i18n.LocaleContext("zh-CN"):
            with i18n.LocaleContext(empty):
                assert i18n.get_locale() == "zh-CN"
            assert i18n.get_locale() == "zh-CN"


class TestJinjaIntegration:
    """Templates translate through the shared Jinja2 environment setup."""

    def _render(self, source: str, locale: str) -> str:
        """Render a template with the same i18n wiring as the application.

        Args:
            source: Template source to render.
            locale: Locale to bind while rendering.

        Returns:
            The rendered template.
        """
        environment = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
        environment.install_gettext_callables(i18n.gettext, i18n.ngettext, newstyle=True)
        environment.globals["_"] = i18n.gettext
        with i18n.LocaleContext(locale):
            return environment.from_string(source).render()

    def test_interpolation_expression(self):
        """The underscore helper translates at render time."""
        assert self._render("{{ _('Tools') }}", "zh-CN") == "工具"
        assert self._render("{{ _('Tools') }}", "en") == "Tools"

    def test_trans_block(self):
        """A trans block uses the installed gettext callable."""
        assert self._render("{% trans %}Search{% endtrans %}", "zh-CN") == "搜索"


class TestCatalogCompilation:
    """The shipped catalog compiles into a readable binary catalog."""

    @staticmethod
    def _is_prose(msgid: str) -> bool:
        """Report whether a message is prose that translators must cover.

        Sample values, identifiers, URLs, and product names stay in the source
        language on purpose, so they are not required to have a translation.

        Args:
            msgid: Source message from the catalog.

        Returns:
            True when the message is ordinary prose.
        """
        if " " not in msgid:
            return False
        # Product, protocol, and sample-person names keep their upstream spelling.
        if msgid in {"AWS Bedrock", "Azure OpenAI", "Google Vertex AI", "IBM watsonx", "Together AI", "OAuth 2.0", "Streamable HTTP", "John Smith"}:
            return False
        if msgid == msgid.lower():
            return False
        if any(token in msgid for token in (",", "://", "@", "example.")):
            return False
        if msgid.startswith("e.g.,"):
            return False
        return not all(word[:1].isupper() or not word[:1].isalpha() for word in msgid.split())

    def test_core_messages_are_translated(self):
        """Messages the Admin UI depends on always have a translation."""
        catalog = i18n.catalog_mapping("zh-CN")
        core = [
            "Overview",
            "Tools",
            "MCP Servers",
            "Gateway Administration",
            "Search",
            "Language",
            "Sign In",
            "Password",
            "Email address",
            "Forgot password?",
            "Save Changes",
            "Add Tool",
            "Tool Name",
            "Status:",
        ]
        missing = [message for message in core if message not in catalog]
        assert missing == []

    def test_catalog_coverage_stays_high(self):
        """Translated coverage stays above the floor as new strings arrive."""
        entries = [entry for entry in parse_po(ZH_PO.read_text(encoding="utf-8")) if entry.msgid]
        assert entries
        translated = [entry for entry in entries if entry.msgstr]
        assert len(translated) / len(entries) >= 0.9

    def test_only_non_prose_messages_are_untranslated(self):
        """Every untranslated entry is a sample value, identifier, or product name."""
        entries = [entry for entry in parse_po(ZH_PO.read_text(encoding="utf-8")) if entry.msgid]
        missing = [entry.msgid for entry in entries if not entry.msgstr]
        prose = [msgid for msgid in missing if self._is_prose(msgid)]
        assert prose == []

    def test_compile_round_trip(self, tmp_path):
        """A compiled catalog is readable by the standard library gettext."""
        po_text = render_po(
            [
                Entry(msgid="Hello", msgstr="你好"),
                Entry(msgid="Untranslated", msgstr=""),
            ],
            default_header("zh-CN", locale_plural_forms("zh-CN")),
        )
        po_path = tmp_path / "zh_CN" / "LC_MESSAGES" / "messages.po"
        po_path.parent.mkdir(parents=True)
        po_path.write_text(po_text, encoding="utf-8")

        count = compile_catalog(po_path, po_path.with_suffix(".mo"))
        assert count >= 1

        catalog = gettext_module.translation("messages", localedir=str(tmp_path), languages=["zh_CN"])
        assert catalog.gettext("Hello") == "你好"
        assert catalog.gettext("Untranslated") == "Untranslated"


class TestI18nMiddleware:
    """The middleware binds the locale and annotates the response."""

    @staticmethod
    def _client() -> TestClient:
        """Build a client whose endpoint reports the bound locale.

        Returns:
            A test client for an app wrapped in I18nMiddleware.
        """

        async def homepage(_request):
            return PlainTextResponse(i18n.get_locale())

        app = Starlette(routes=[Route("/", homepage)])
        app.add_middleware(I18nMiddleware)
        return TestClient(app)

    def test_accept_language_binds_locale(self):
        """Accept-Language selects the locale for the request."""
        response = self._client().get("/", headers={"accept-language": "zh-CN,zh;q=0.9"})
        assert response.status_code == 200
        assert response.text == "zh-CN"
        assert response.headers["content-language"] == "zh-CN"
        assert "accept-language" in response.headers["vary"].lower()

    def test_query_parameter_sets_cookie(self):
        """An explicit lang parameter persists as a cookie."""
        response = self._client().get("/?lang=zh-CN")
        assert response.text == "zh-CN"
        assert "cf_lang=zh-CN" in response.headers["set-cookie"]

    def test_cookie_binds_locale_without_query_parameter(self):
        """The cookie selects the locale on later requests."""
        response = self._client().get("/", headers={"cookie": "cf_lang=zh-CN"})
        assert response.text == "zh-CN"
        assert "set-cookie" not in response.headers

    def test_unsupported_query_parameter_does_not_set_cookie(self):
        """An unsupported lang value is ignored and not persisted."""
        response = self._client().get("/?lang=fr")
        assert response.text == i18n.default_locale()
        assert "set-cookie" not in response.headers

    def test_language_endpoint_is_exempt_from_admin_auth(self):
        """The switcher must stay reachable on the sign-in page."""
        from mcpgateway.main import AdminAuthMiddleware

        exempt = {AdminAuthMiddleware._strip_v1(path) for path in AdminAuthMiddleware.EXEMPT_PATHS}
        assert "/admin/language" in exempt


class TestProtocolMessages:
    """Protocol-layer text stays on the wire unless translation is enabled."""

    def test_disabled_keeps_source_text(self, monkeypatch):
        """With the setting off, the message is unchanged apart from values."""
        monkeypatch.setattr(settings, "i18n_translate_protocol_messages", False)
        with i18n.LocaleContext("zh-CN"):
            assert i18n.protocol_gettext("Tool not found: {name}", name="alpha") == "Tool not found: alpha"

    def test_enabled_translates(self, monkeypatch):
        """With the setting on, the message is translated."""
        monkeypatch.setattr(settings, "i18n_translate_protocol_messages", True)
        with i18n.LocaleContext("zh-CN"):
            assert i18n.protocol_gettext("Tool not found: {name}", name="alpha") == "未找到工具：alpha"
            assert i18n.protocol_gettext("Missing tool name in parameters") == "参数中缺少工具名称"

    def test_enabled_keeps_english_for_english_locale(self, monkeypatch):
        """English output is unchanged even when translation is enabled."""
        monkeypatch.setattr(settings, "i18n_translate_protocol_messages", True)
        with i18n.LocaleContext("en"):
            assert i18n.protocol_gettext("Tool not found: {name}", name="alpha") == "Tool not found: alpha"


class TestHttpExceptionBoundary:
    """The HTTP exception handler localizes detail messages."""

    @staticmethod
    def _call(detail: str, locale: str) -> dict:
        """Run the application HTTP exception handler.

        Args:
            detail: Exception detail message.
            locale: Locale to bind while handling.

        Returns:
            Parsed JSON body of the response.
        """
        from mcpgateway.main import http_exception_handler

        exc = StarletteHTTPException(status_code=401, detail=detail)
        with i18n.LocaleContext(locale):
            response = asyncio.run(http_exception_handler(None, exc))
        return json.loads(response.body)

    def test_catalogued_detail_is_translated(self):
        """A catalogued detail is returned in the request language."""
        assert self._call("Authorization token required", "zh-CN")["detail"] == "需要授权令牌"
        assert self._call("Authorization token required", "en")["detail"] == "Authorization token required"

    def test_uncatalogued_detail_passes_through(self):
        """A detail without a catalog entry keeps its original text."""
        detail = "A message that is deliberately absent from the catalog"
        assert self._call(detail, "zh-CN")["detail"] == detail

    def test_shared_message_covers_raise_sites(self):
        """One catalog entry localizes every raise site that reuses the text."""
        assert self._call("Access denied", "zh-CN")["detail"] == "拒绝访问"


class TestEmailLocalization:
    """Authentication email renders in the recipient locale."""

    @staticmethod
    def _reset_context(display_name: str) -> dict:
        """Build the password-reset template context.

        Args:
            display_name: Recipient display name.

        Returns:
            Template context values.
        """
        return {"display_name": display_name, "reset_url": "https://example.test/reset", "expires_minutes": 30, "recipient_email": "user@example.test"}

    def test_password_reset_renders_chinese(self):
        """The Chinese catalog renders the password-reset email."""
        service = AuthEmailNotificationService()
        html = service._render_template("password_reset_email.html", self._reset_context("张三"), "t", "f", locale="zh-CN")
        assert "密码重置请求" in html
        assert "您好 张三，" in html
        assert 'lang="zh-CN"' in html

    def test_password_reset_renders_english(self):
        """The English catalog renders the password-reset email."""
        service = AuthEmailNotificationService()
        html = service._render_template("password_reset_email.html", self._reset_context("Zhang"), "t", "f", locale="en")
        assert "Password Reset Request" in html
        assert "Hello Zhang," in html
        assert 'lang="en"' in html

    def test_unknown_locale_falls_back_to_default(self):
        """An unsupported locale renders the default locale."""
        service = AuthEmailNotificationService()
        html = service._render_template("password_reset_email.html", self._reset_context("Zhang"), "t", "f", locale="fr")
        assert "Password Reset Request" in html

    @pytest.mark.asyncio
    async def test_subject_and_text_body_are_localized(self, monkeypatch):
        """Subjects and plain-text bodies follow the recipient locale."""
        service = AuthEmailNotificationService()
        captured = {}

        async def fake_send(to_email, subject, html_body, text_body=None):
            captured.update({"to_email": to_email, "subject": subject, "html_body": html_body, "text_body": text_body})
            return True

        monkeypatch.setattr(service, "_send_email", fake_send)

        await service.send_password_reset_email("user@example.test", "张三", "https://example.test/reset", 30, locale="zh-CN")
        assert captured["subject"] == "重置您的 ContextForge 密码"

        await service.send_team_invitation_email(
            to_email="user@example.test",
            team_name="平台组",
            inviter_name="李四",
            role="developer",
            invitation_url="https://example.test/invite",
            expires_at="2026-01-01T00:00:00Z",
            token="tok",
            locale="zh-CN",
        )
        assert captured["subject"] == "邀请您加入 ContextForge 上的 平台组"
        assert "李四 邀请您以 developer 的身份加入 平台组。" in captured["text_body"]
        assert "备用邀请令牌：tok" in captured["text_body"]
