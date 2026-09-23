# SPDX-License-Identifier: Apache-2.0
"""Verify the demo against the live portal, identity service, and gateway."""

import http.cookiejar
import json
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Expose each OAuth redirect for explicit validation."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Return no redirect request so tests inspect the original response."""
        return None


def main() -> None:
    """Exercise SSO, scoped identity, framing headers, denial, and logout."""
    config = json.loads((Path(__file__).parent / ".runtime/config.json").read_text(encoding="utf-8"))
    portal = config["portalOrigin"]
    gateway = config["gatewayOrigin"]
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect())

    def request(url, data=None, headers=None):
        body = data if isinstance(data, bytes) else urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, headers={"Accept": "text/html,application/json", **(headers or {})})
        try:
            return opener.open(req, timeout=30)
        except urllib.error.HTTPError as response:
            return response

    assert request(gateway + "/embed/session").status == 401
    assert request(gateway + "/admin/api-key").status == 200
    assert request(gateway + "/admin/api-key/sso/options", b"{}", {"Content-Type": "application/json"}).status in (302, 401, 403)
    start = request(portal + "/portal/login")
    assert start.status == 302
    form = request(start.headers["Location"]).read().decode()
    request_id = re.search(r'name="request" value="([^"]+)"', form)[1]
    signed_in = request(portal + "/oidc/login", {"request": request_id, "email": "demo@aiops.example", "password": config["password"]}, {"Origin": portal})
    assert signed_in.status == 302
    assert request(signed_in.headers["Location"]).status == 302
    assert json.load(request(portal + "/portal/me"))["email"] == "demo@aiops.example"
    assert request(gateway + "/embed/session").status == 401, "Portal session must not authenticate the gateway"
    callback = gateway + "/auth/sso/callback/intranet-demo"
    login = request(gateway + "/auth/sso/login/intranet-demo?" + urllib.parse.urlencode({"redirect_uri": callback}))
    assert login.status == 200
    authorization = request(json.load(login)["authorization_url"])
    assert authorization.status == 302, "Existing IdP session must avoid a second login form"
    gateway_callback = request(authorization.headers["Location"])
    assert gateway_callback.status == 302
    assert "error=" not in gateway_callback.headers["Location"], gateway_callback.headers["Location"]
    user_response = request(gateway + "/embed/session", headers={"Origin": portal})
    assert user_response.status == 200
    assert user_response.headers["Access-Control-Allow-Origin"] == portal
    user = json.load(user_response)
    assert user["email"] == "demo@aiops.example"
    assert user["is_admin"] is False

    fixture_server_id = uuid.uuid4().hex
    database = Path(__file__).parent / ".runtime/gateway.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO servers (id, name, created_at, updated_at, enabled, tags, version, owner_email, visibility, oauth_enabled) VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, '[]', 1, ?, 'public', 0)",
            (fixture_server_id, "Key verification MCP", "admin@aiops.example"),
        )
    try:
        key_page = request(gateway + "/admin/api-key")
        assert key_page.status == 200
        assert b'id="member-key-form"' in key_page.read()
        csrf = next(cookie.value for cookie in jar if cookie.name == "mcpgateway_csrf_token")
        key_headers = {"Content-Type": "application/json", "X-CSRF-Token": csrf, "Origin": gateway}
        assert request(gateway + "/admin/api-key/sso/options", b"{}", key_headers).status == 401, "Gateway login must not authorize Key issuance"
        key_login = request(gateway + "/auth/sso/login/intranet-demo?" + urllib.parse.urlencode({"redirect_uri": callback, "flow": "member_key"}))
        assert key_login.status == 200
        key_authorization = request(json.load(key_login)["authorization_url"])
        assert key_authorization.status == 302
        key_callback = request(key_authorization.headers["Location"])
        assert key_callback.status == 302
        assert key_callback.headers["Location"].endswith("/admin/api-key?sso=success")
        assert "member_key_proof=" in key_callback.headers.get("Set-Cookie", "")
        assert "jwt_token=" not in key_callback.headers.get("Set-Cookie", "")
        options = request(gateway + "/admin/api-key/sso/options", b"{}", key_headers)
        assert options.status == 200, options.read().decode()
        available = json.load(options)
        team_id = available["teams"][0]["id"]
        assert fixture_server_id in [item["id"] for item in available["servers"]]
        assert "AIOps 演示 MCP" in [item["name"] for item in available["servers"]]
        body = json.dumps({"team_id": team_id, "server_id": fixture_server_id, "days": 7}).encode()
        issued = request(gateway + "/admin/api-key/sso/issue", body, key_headers)
        assert issued.status == 200, issued.read().decode()
        api_key = json.load(issued)["api_key"]
        assert api_key
        initialize = request(
            gateway + f"/servers/{fixture_server_id}/mcp/",
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "iframe-demo-check", "version": "1"}}}
            ).encode(),
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        assert initialize.status == 200, initialize.read().decode()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM email_api_tokens WHERE server_id = ? AND user_email = ?", (fixture_server_id, "demo@aiops.example"))
            connection.execute("DELETE FROM servers WHERE id = ?", (fixture_server_id,))

    admin = request(gateway + "/admin")
    for _ in range(5):
        if admin.status not in (302, 303, 307, 308):
            break
        target = urllib.parse.urljoin(gateway, admin.headers["Location"])
        assert target.startswith(gateway + "/admin"), target
        assert "/login" not in target, target
        admin = request(target)
    assert admin.status == 200, (admin.status, admin.headers.get("Location"))
    assert f"frame-ancestors {portal}" in ";".join(admin.headers.get_all("Content-Security-Policy", []))
    assert admin.headers.get("X-Frame-Options") is None
    for path in ("/admin/servers/partial", "/admin/tools/partial"):
        assert request(gateway + path).status == 200, path
    assert request(gateway + "/auth/sso/admin/providers").status == 403
    assert request(gateway + "/auth/sso/login/missing?" + urllib.parse.urlencode({"redirect_uri": callback})).status == 404
    assert request(gateway + "/auth/sso/login/intranet-demo?redirect_uri=https%3A%2F%2Fforeign.example%2Fcallback").status == 400
    assert request(authorization.headers["Location"]).headers["Location"].endswith("error=sso_failed")
    foreign = request(gateway + "/embed/session", headers={"Origin": "http://foreign.example"})
    assert foreign.headers.get("Access-Control-Allow-Origin") is None
    assert request(portal + "/portal/logout", {}, {"Origin": "http://foreign.example"}).status == 403
    assert request(portal + "/portal/logout", {}, {"Origin": portal}).status == 200
    assert request(portal + "/portal/me").status == 401
    assert request(gateway + "/embed/session").status == 401
    print("PASS: live portal OAuth, iframe SSO, API Key issuance and MCP use, non-admin RBAC, framing/CORS, rejection paths, and logout")


if __name__ == "__main__":
    main()
