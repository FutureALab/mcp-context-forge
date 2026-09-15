"""Middleware that resolves and binds the request locale.

The middleware is the only place that reads locale signals off the wire. It
binds the resolved locale to the context variable defined in mcpgateway.i18n,
records it on the request state, and annotates the response with
'Content-Language' and 'Vary: Accept-Language'.

When the request carries an explicit '?lang=' value, the middleware also
persists it as a cookie so the choice survives navigation and later requests.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any, Awaitable, Callable, MutableMapping, Optional

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from mcpgateway.config import settings
from mcpgateway.i18n import default_locale, normalize_locale, resolve_locale, reset_locale, set_locale

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class I18nMiddleware:
    """Bind the request locale and advertise it on the response.

    The middleware runs outside the route handlers, so error responses produced
    by inner middleware (authentication, rate limiting) are translated too.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Store the wrapped application.

        Args:
            app: The next ASGI application in the stack.
        """
        self.app = app
        self.enabled: bool = bool(getattr(settings, "i18n_enabled", True))
        self.cookie_name: str = str(getattr(settings, "i18n_cookie_name", "cf_lang"))
        self.cookie_max_age: int = int(getattr(settings, "i18n_cookie_max_age", 31536000))
        self.cookie_secure: bool = bool(getattr(settings, "i18n_cookie_secure", False))

    def _cookie_header(self, locale: str, scope: Scope) -> str:
        """Build a Set-Cookie header that stores the locale choice.

        Args:
            locale: Locale code to persist.
            scope: ASGI scope, used to derive the cookie path.

        Returns:
            A serialised Set-Cookie header value.
        """
        cookie: SimpleCookie = SimpleCookie()
        cookie[self.cookie_name] = locale
        morsel = cookie[self.cookie_name]
        morsel["path"] = scope.get("root_path") or "/"
        morsel["max-age"] = str(self.cookie_max_age)
        morsel["samesite"] = "lax"
        morsel["httponly"] = True
        if self.cookie_secure:
            morsel["secure"] = True
        return morsel.OutputString()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Resolve the locale, bind it, and annotate the response.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        requested = request.query_params.get("lang")
        explicit = normalize_locale(requested)

        locale = resolve_locale(
            query_param=requested,
            cookie=request.cookies.get(self.cookie_name),
            accept_language=request.headers.get("accept-language"),
        )

        set_cookie = self._cookie_header(explicit, scope) if explicit else None
        token = set_locale(locale)

        state: Optional[MutableMapping[str, Any]] = scope.get("state")
        if state is not None:
            state["locale"] = locale

        async def send_with_locale(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["content-language"] = locale
                existing_vary = headers.get("vary", "")
                if "accept-language" not in existing_vary.lower():
                    headers.append("vary", "Accept-Language")
                if set_cookie:
                    headers.append("set-cookie", set_cookie)
            await send(message)

        try:
            await self.app(scope, receive, send_with_locale)
        finally:
            reset_locale(token)


def current_locale_from_scope(scope: Scope) -> str:
    """Read the locale recorded on an ASGI scope.

    Args:
        scope: ASGI connection scope.

    Returns:
        The locale bound by I18nMiddleware, or the configured default when the
        middleware did not run for this scope.
    """
    state = scope.get("state") or {}
    return str(state.get("locale") or default_locale())
