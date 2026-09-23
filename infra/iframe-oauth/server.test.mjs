import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { once } from "node:events";
import test from "node:test";
import { createDemoServer } from "./server.mjs";

async function fixture(t) {
  const config = {
    portalOrigin: "http://localhost:18080",
    gatewayOrigin: "http://localhost:18081",
    portalSecret: randomBytes(24).toString("hex"),
    gatewaySecret: randomBytes(24).toString("hex"),
    password: randomBytes(24).toString("hex"),
  };
  let clock = Date.now();
  const server = createDemoServer(config, () => clock);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(
    () =>
      new Promise((resolve) => {
        server.close(resolve);
        server.closeAllConnections();
      })
  );
  const base = `http://127.0.0.1:${server.address().port}`;
  const jar = new Map();
  const request = async (path, options = {}) => {
    const parsed = new URL(path, config.portalOrigin);
    const response = await fetch(base + parsed.pathname + parsed.search, {
      redirect: "manual",
      ...options,
      headers: {
        Cookie: [...jar].map(([name, value]) => `${name}=${value}`).join("; "),
        ...options.headers,
      },
    });
    for (const item of response.headers.getSetCookie()) {
      const [name, value] = item.split(";")[0].split("=");
      jar.set(name, value);
    }
    return response;
  };
  const verifier = randomBytes(32).toString("base64url");
  const params = new URLSearchParams({
    client_id: "contextforge-demo",
    redirect_uri: config.gatewayOrigin + "/auth/sso/callback/intranet-demo",
    response_type: "code",
    state: "bound-test-state",
    nonce: "bound-test-nonce",
    scope: "openid profile email",
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
  });
  const login = async (
    authorization = `/oidc/authorize?${params}`,
    password = config.password
  ) => {
    const response = await request(authorization);
    const html = await response.text();
    const id = html.match(/name="request" value="([^"]+)"/)?.[1];
    assert.ok(id, "Authorization requires credentials without an IdP session");
    return request("/oidc/login", {
      method: "POST",
      headers: { Origin: config.portalOrigin },
      body: new URLSearchParams({
        request: id,
        email: "demo@aiops.example",
        password,
      }),
    });
  };
  const redeem = (code, overrides = {}) =>
    request("/oidc/token", {
      method: "POST",
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: "contextforge-demo",
        client_secret: config.gatewaySecret,
        redirect_uri: params.get("redirect_uri"),
        code_verifier: verifier,
        code,
        ...overrides,
      }),
    });
  return {
    config,
    request,
    jar,
    params,
    login,
    redeem,
    advance: (milliseconds) => {
      clock += milliseconds;
    },
  };
}

test("authorization code produces signed identity and cannot be replayed", async (t) => {
  const f = await fixture(t);
  const login = await f.login();
  assert.equal(login.status, 302);
  const code = new URL(login.headers.get("location")).searchParams.get("code");
  const result = await f.redeem(code);
  assert.equal(result.status, 200);
  const tokens = await result.json();
  const claims = JSON.parse(
    Buffer.from(tokens.id_token.split(".")[1], "base64url")
  );
  assert.equal(claims.aud, "contextforge-demo");
  assert.equal(claims.nonce, "bound-test-nonce");
  const me = await f.request("/oidc/userinfo", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  assert.equal((await me.json()).email, "demo@aiops.example");
  assert.equal((await f.redeem(code)).status, 400);
  f.advance(301000);
  assert.equal(
    (
      await f.request("/oidc/userinfo", {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      })
    ).status,
    401
  );
});

test("rejects unknown clients, foreign callbacks, and missing PKCE", async (t) => {
  const f = await fixture(t);
  for (const [key, value] of [
    ["client_id", "unknown"],
    ["redirect_uri", "https://foreign.example/callback"],
    ["code_challenge", ""],
    ["nonce", ""],
  ]) {
    const params = new URLSearchParams(f.params);
    params.set(key, value);
    assert.equal((await f.request(`/oidc/authorize?${params}`)).status, 400);
  }
});

test("rejects wrong password, forged login origin, and missing browser binding", async (t) => {
  const f = await fixture(t);
  assert.equal((await f.login(undefined, "incorrect")).status, 401);
  assert.equal(
    (
      await f.request("/oidc/login", {
        method: "POST",
        headers: { Origin: "https://foreign.example" },
        body: new URLSearchParams({
          email: "demo@aiops.example",
          password: f.config.password,
        }),
      })
    ).status,
    403
  );
  const page = await f.request(`/oidc/authorize?${f.params}`);
  const id = (await page.text()).match(/name="request" value="([^"]+)"/)[1];
  f.jar.clear();
  assert.equal(
    (
      await f.request("/oidc/login", {
        method: "POST",
        headers: { Origin: f.config.portalOrigin },
        body: new URLSearchParams({
          request: id,
          email: "demo@aiops.example",
          password: f.config.password,
        }),
      })
    ).status,
    403
  );
});

test("rejects wrong client secret, wrong verifier, wrong audience, and expired codes", async (t) => {
  const f = await fixture(t);
  const response = await f.login();
  const code = new URL(response.headers.get("location")).searchParams.get(
    "code"
  );
  assert.equal(
    (await f.redeem(code, { client_secret: "incorrect" })).status,
    401
  );
  assert.equal(
    (await f.redeem(code, { code_verifier: "incorrect" })).status,
    400
  );
  assert.equal(
    (
      await f.redeem(code, {
        client_id: "portal-demo",
        client_secret: f.config.portalSecret,
      })
    ).status,
    400
  );
  f.advance(61000);
  assert.equal((await f.redeem(code)).status, 400);
});

test("portal authenticates through code flow; second client reuses the IdP session", async (t) => {
  const f = await fixture(t);
  assert.equal((await f.request("/portal/me")).status, 401);
  assert.equal((await f.request("/oidc/userinfo")).status, 401);
  assert.equal(
    (await f.request("/portal/callback?state=forged&code=forged")).status,
    403
  );
  const start = await f.request("/portal/login");
  const authorization = start.headers.get("location");
  const login = await f.login(authorization);
  const callback = await f.request(login.headers.get("location"));
  assert.equal(callback.status, 302);
  assert.equal(
    (await (await f.request("/portal/me")).json()).email,
    "demo@aiops.example"
  );
  assert.equal((await f.request(`/oidc/authorize?${f.params}`)).status, 302);
  assert.equal(
    (
      await f.request("/portal/logout", {
        method: "POST",
        headers: { Origin: "https://foreign.example" },
      })
    ).status,
    403
  );
  assert.equal(
    (
      await f.request("/portal/logout", {
        method: "POST",
        headers: { Origin: f.config.portalOrigin },
      })
    ).status,
    200
  );
  assert.equal((await f.request("/portal/me")).status, 401);
  assert.equal((await f.request(`/oidc/authorize?${f.params}`)).status, 200);
});

test("portal callback requires the initiating browser cookie", async (t) => {
  const f = await fixture(t);
  const start = await f.request("/portal/login");
  const login = await f.login(start.headers.get("location"));
  f.jar.delete("demo_flow");
  assert.equal((await f.request(login.headers.get("location"))).status, 403);
});
