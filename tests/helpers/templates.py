"""Helpers for rendering the shipped Jinja2 templates in tests.

Templates call the gettext helpers that the application registers at startup,
so a bare Jinja2 Environment cannot render them. build_jinja_env() returns an
environment wired the same way as mcpgateway.main, plus the custom filters that
main.py adds.
"""

from __future__ import annotations

import html
import json
from typing import Any

from jinja2 import Environment, FileSystemLoader

from mcpgateway.config import settings
from mcpgateway.i18n import default_locale, get_locale, gettext, ngettext, supported_locales


def tojson_attr(value: object) -> str:
    """JSON-encode a value for safe use inside a double-quoted HTML attribute.

    Args:
        value: Any JSON-serialisable value.

    Returns:
        Plain string with HTML-sensitive characters escaped.
    """
    encoded = json.dumps(value)
    return encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("'", "\\u0027")


def decode_html(value: str) -> str:
    """Decode HTML entities for display, matching the application filter.

    Args:
        value: String that may contain HTML entities.

    Returns:
        String with entities decoded, or the original falsy value.
    """
    return html.unescape(value) if value else value


def build_jinja_env(**overrides: Any) -> Environment:
    """Build a Jinja2 environment wired like the running application.

    Args:
        **overrides: Extra Environment keyword arguments, for example
            autoescape=False for templates that are not HTML.

    Returns:
        An environment that can render the templates shipped in
        mcpgateway/templates.
    """
    options: dict[str, Any] = {
        "loader": FileSystemLoader(str(settings.templates_dir)),
        "autoescape": True,
        "extensions": ["jinja2.ext.i18n"],
    }
    options.update(overrides)
    env = Environment(**options)
    env.install_gettext_callables(gettext, ngettext, newstyle=True)
    env.globals["_"] = gettext
    env.globals["gettext"] = gettext
    env.globals["ngettext"] = ngettext
    env.globals["supported_locales"] = supported_locales
    env.globals["current_locale"] = get_locale
    env.globals["default_locale"] = default_locale
    env.globals["catalog_mapping"] = lambda locale=None: {}
    env.globals["csp_nonce"] = lambda request=None: ""
    env.filters["decode_html"] = decode_html
    env.filters["tojson_attr"] = tojson_attr
    return env
