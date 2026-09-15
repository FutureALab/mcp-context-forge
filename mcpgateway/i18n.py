"""Internationalization (i18n) support for ContextForge.

This module is the single policy point for locale handling:

* it maps an incoming request to a supported locale,
* it loads the compiled gettext catalog for that locale,
* it exposes translation callables that resolve the locale at call time.

Locale resolution order (first match wins):

1. Explicit 'lang' query parameter, for example '?lang=zh-CN'.
2. The locale cookie named by 'settings.i18n_cookie_name'.
3. The authenticated user's stored preference.
4. The 'Accept-Language' request header, honouring quality values.
5. 'settings.i18n_default_locale'.

The active locale lives in a contextvars.ContextVar, so services that never see
a Request -- API error builders, MCP transports, email senders -- still
translate through the module-level gettext() helper. Call set_locale() to bind a
locale, and use the LocaleContext context manager when the binding must be
scoped to a block.
"""

from __future__ import annotations

import contextvars
import gettext as gettext_module
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from mcpgateway.config import settings

#: Locale codes ContextForge ships catalogs for, mapped to their native name.
#: Insertion order drives the language switcher order.
SUPPORTED_LOCALES: Mapping[str, str] = {
    "en": "English",
    "zh-CN": "简体中文",
}

#: Locale used when nothing else matches, and the source language of the catalogs.
FALLBACK_LOCALE = "en"

#: gettext expects '<localedir>/<name>/LC_MESSAGES/<domain>.mo'. Babel writes
#: underscores ('zh_CN') while BCP 47 tags use hyphens ('zh-CN'), so the two
#: spellings are bridged here instead of leaking into catalogs or settings.
_CATALOG_DIR_NAMES: Mapping[str, str] = {
    "en": "en",
    "zh-CN": "zh_CN",
}

#: Base-language and legacy tags accepted as aliases for a supported locale.
_LOCALE_ALIASES: Mapping[str, str] = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-hans-cn": "zh-CN",
    "zh-sg": "zh-CN",
    "en-us": "en",
    "en-gb": "en",
    "en_us": "en",
}

_DOMAIN = "messages"

_catalog_dir = Path(__file__).resolve().parent / "translations"

#: Brace placeholder used by catalogs that are shared with the Admin UI
#: JavaScript helper, for example 'Deleted {count} tools'.
_BRACE_PLACEHOLDER = re.compile(r"\{(\w+)\}")

_active_locale: contextvars.ContextVar[str] = contextvars.ContextVar("contextforge_locale", default=FALLBACK_LOCALE)


def interpolate(message: str, variables: Mapping[str, Any]) -> str:
    """Fill placeholders in a translated message.

    Brace placeholders ('{name}') use the same syntax as the Admin UI
    JavaScript helper, so one catalog entry serves both. Gettext-style
    '%(name)s' placeholders are still expanded for compatibility with
    conventional catalogs. Unknown placeholders are left unchanged.

    Args:
        message: Translated message, possibly containing placeholders.
        variables: Values to substitute.

    Returns:
        The message with every known placeholder replaced.
    """
    if not variables:
        return message

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(variables[name]) if name in variables else match.group(0)

    interpolated = _BRACE_PLACEHOLDER.sub(replace, message)
    if "%(" in interpolated:
        try:
            return interpolated % variables
        except (KeyError, TypeError, ValueError):
            return interpolated
    return interpolated


def _canonical(tag: Optional[str]) -> Optional[str]:
    """Normalise a locale tag to a key of SUPPORTED_LOCALES.

    Args:
        tag: A raw locale tag such as 'zh-Hans-CN' or 'en_US'.

    Returns:
        The matching supported locale code, or None when no match exists.
    """
    if not tag:
        return None
    candidate = tag.strip()
    if not candidate:
        return None

    for locale in SUPPORTED_LOCALES:
        if candidate.lower() == locale.lower():
            return locale

    return _LOCALE_ALIASES.get(candidate.lower())


def supported_locales() -> Mapping[str, str]:
    """Return the locale codes ContextForge can display.

    Returns:
        Mapping of locale code to native display name.
    """
    return SUPPORTED_LOCALES


def default_locale() -> str:
    """Return the configured default locale, normalised to a supported code.

    Returns:
        A supported locale code. Returns FALLBACK_LOCALE when the configured
        value names an unsupported locale.
    """
    return _canonical(getattr(settings, "i18n_default_locale", FALLBACK_LOCALE)) or FALLBACK_LOCALE


def normalize_locale(tag: Optional[str]) -> Optional[str]:
    """Normalise a locale tag to a supported locale code.

    Args:
        tag: A raw locale tag, for example 'zh-Hans-CN'.

    Returns:
        A supported locale code, or None when the tag is unsupported.
    """
    return _canonical(tag)


def parse_accept_language(header: Optional[str]) -> list[str]:
    """Order locale tags from an Accept-Language header by quality value.

    Quality values order the result. Entries with 'q=0' are dropped because
    RFC 9110 defines them as explicitly unacceptable.

    Args:
        header: Raw Accept-Language value, for example 'zh-CN,zh;q=0.9,en;q=0.8'.

    Returns:
        Locale tags ordered from most to least preferred.
    """
    if not header:
        return []

    weighted: list[tuple[float, int, str]] = []
    for position, part in enumerate(header.split(",")):
        token = part.strip()
        if not token:
            continue
        tag, _, parameters = token.partition(";")
        tag = tag.strip()
        if not tag:
            continue
        quality = 1.0
        for parameter in parameters.split(";"):
            name, _, value = parameter.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        # The negated position keeps header order for equal quality values.
        weighted.append((quality, -position, tag))

    weighted.sort(reverse=True)
    return [tag for _, _, tag in weighted]


def resolve_locale(
    query_param: Optional[str] = None,
    cookie: Optional[str] = None,
    user_preference: Optional[str] = None,
    accept_language: Optional[str] = None,
) -> str:
    """Resolve the locale for one request.

    Args:
        query_param: Value of the 'lang' query parameter, if present.
        cookie: Value of the locale cookie, if present.
        user_preference: Locale persisted on the authenticated user record.
        accept_language: Raw Accept-Language header value.

    Returns:
        The resolved supported locale code. Returns the configured default when
        no candidate matches.
    """
    for candidate in (query_param, cookie, user_preference):
        resolved = _canonical(candidate)
        if resolved:
            return resolved

    for tag in parse_accept_language(accept_language):
        resolved = _canonical(tag)
        if resolved:
            return resolved

    return default_locale()


@lru_cache(maxsize=16)
def _catalog(locale: str) -> gettext_module.NullTranslations:
    """Load and cache the compiled gettext catalog for a locale.

    Args:
        locale: A supported locale code.

    Returns:
        The catalog, or a pass-through catalog when no .mo file is present.
    """
    directory_name = _CATALOG_DIR_NAMES.get(locale, locale)
    return gettext_module.translation(
        _DOMAIN,
        localedir=str(_catalog_dir),
        languages=[directory_name],
        fallback=True,
    )


class Translator:
    """Translate messages with an explicit locale.

    Use this when the target locale differs from the request locale, such as a
    notification email sent to a user who prefers another language.

    Example:
        >>> Translator("en").gettext("Welcome")
        'Welcome'
    """

    def __init__(self, locale: Optional[str] = None) -> None:
        """Bind the translator to a locale.

        Args:
            locale: Target locale. Defaults to the active request locale.
        """
        self.locale = _canonical(locale) or get_locale()
        self._translations = _catalog(self.locale)

    def gettext(self, message: str, **variables: Any) -> str:
        """Translate a singular message.

        Args:
            message: Source message, written in English.
            **variables: Values interpolated into the message with '%' placeholders.

        Returns:
            The translated message, interpolated when variables are supplied.
        """
        return interpolate(self._translations.gettext(message), variables)

    def ngettext(self, singular: str, plural: str, count: int, **variables: Any) -> str:
        """Translate a message that depends on a count.

        Args:
            singular: Source singular form.
            plural: Source plural form.
            count: Number the message refers to.
            **variables: Values interpolated into the message.

        Returns:
            The translated message for the plural form that count selects.
        """
        return interpolate(self._translations.ngettext(singular, plural, count), variables)

    def pgettext(self, context: str, message: str, **variables: Any) -> str:
        """Translate a message disambiguated by a context prefix.

        Args:
            context: Disambiguating context, joined to the message by U+0004.
            message: Source message, written in English.
            **variables: Values interpolated into the message.

        Returns:
            The translated message, interpolated when variables are supplied.
        """
        return self.gettext(context + "\x04" + message, **variables)

    def catalog(self) -> dict[str, str]:
        """Return every source-to-translation pair in this locale's catalog.

        Returns:
            Mapping of source message to translated message.
        """
        return dict(getattr(self._translations, "_catalog", {}))


def get_locale() -> str:
    """Return the locale bound to the current context.

    Returns:
        The active locale code.
    """
    return _active_locale.get()


def set_locale(locale: Optional[str]) -> contextvars.Token[str]:
    """Bind a locale to the current context.

    Args:
        locale: Locale to bind. An empty value keeps the locale already bound,
            so callers can pass an optional preference without discarding the
            request locale. Unsupported values fall back to the default.

    Returns:
        A token that restores the previous locale when passed to
        contextvars.ContextVar.reset().
    """
    if locale is None or not str(locale).strip():
        return _active_locale.set(get_locale())
    return _active_locale.set(_canonical(locale) or default_locale())


def reset_locale(token: contextvars.Token[str]) -> None:
    """Restore the locale that was active before set_locale().

    Args:
        token: Token returned by set_locale().
    """
    _active_locale.reset(token)


class LocaleContext:
    """Bind a locale for the duration of a 'with' block.

    Example:
        >>> with LocaleContext("en"):
        ...     gettext("Welcome")
        'Welcome'
    """

    def __init__(self, locale: Optional[str]) -> None:
        """Store the locale to bind.

        Args:
            locale: Locale to bind for the block. None keeps the active locale,
                which lets callers forward an optional preference.
        """
        self._locale = locale
        self._token: Optional[contextvars.Token[str]] = None

    def __enter__(self) -> "LocaleContext":
        """Bind the locale.

        Returns:
            This context manager.
        """
        self._token = set_locale(self._locale)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Restore the previous locale.

        Args:
            exc_type: Exception type, if any.
            exc: Exception instance, if any.
            traceback: Traceback object, if any.
        """
        if self._token is not None:
            reset_locale(self._token)


def gettext(message: str, **variables: Any) -> str:
    """Translate a singular message into the active locale.

    Args:
        message: Source message, written in English.
        **variables: Values interpolated into the message.

    Returns:
        The translated message.
    """
    return Translator(get_locale()).gettext(message, **variables)


def ngettext(singular: str, plural: str, count: int, **variables: Any) -> str:
    """Translate a count-dependent message into the active locale.

    Args:
        singular: Source singular form.
        plural: Source plural form.
        count: Number the message refers to.
        **variables: Values interpolated into the message.

    Returns:
        The translated message for the selected plural form.
    """
    return Translator(get_locale()).ngettext(singular, plural, count, **variables)


def protocol_gettext(message: str, **variables: Any) -> str:
    """Translate a protocol-layer message when protocol translation is enabled.

    MCP and A2A carry 'error.message' on the wire, and clients may match on that
    text. Translation therefore stays off unless
    'settings.i18n_translate_protocol_messages' is enabled. Placeholders are
    always interpolated, so the messages keep their current text when the
    setting is off.

    Args:
        message: Source message, written in English.
        **variables: Values interpolated into the message.

    Returns:
        The translated message when protocol translation is enabled, otherwise
        the interpolated source message.
    """
    if getattr(settings, "i18n_translate_protocol_messages", False):
        return Translator(get_locale()).gettext(message, **variables)
    return interpolate(message, variables)


def catalog_mapping(locale: Optional[str] = None) -> dict[str, str]:
    """Return the source-to-translation mapping for a locale.

    The Admin UI sends this mapping to the browser so client-side code can use
    the same catalogs as the templates.

    Args:
        locale: Target locale. Defaults to the active request locale.

    Returns:
        Mapping of source message to translated message.
    """
    return Translator(locale).catalog()


#: Conventional gettext alias, imported as the underscore helper.
_ = gettext
