/** Local-only OIDC fixture and portal backend. Do not deploy as an identity provider. */
import http from "node:http";
import {
  createHash,
  generateKeyPairSync,
  randomBytes,
  sign,
  timingSafeEqual,
  verify,
} from "node:crypto";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const random = () => randomBytes(32).toString("base64url");
const digest = (value) =>
  createHash("sha256").update(value).digest("base64url");
const equal = (left, right) =>
  timingSafeEqual(
    createHash("sha256")
      .update(left ?? "")
      .digest(),
    createHash("sha256")
      .update(right ?? "")
      .digest()
  );
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]
  );
const encode = (value) =>
  Buffer.from(JSON.stringify(value)).toString("base64url");

/** Create isolated, expiring fixture state for one demo process. */
export function createDemoServer(config, now = () => Date.now()) {
  const portal = config.portalOrigin;
  const gateway = config.gatewayOrigin;
  const issuer = `${portal}/oidc`;
  const clients = new Map([
    [
      "portal-demo",
      { secret: config.portalSecret, callback: `${portal}/portal/callback` },
    ],
    [
      "contextforge-demo",
      {
        secret: config.gatewaySecret,
        callback: `${gateway}/auth/sso/callback/intranet-demo`,
      },
    ],
  ]);
  const { privateKey, publicKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  const exportedKey = publicKey.export({ format: "jwk" });
  const jwk = {
    ...exportedKey,
    kid: digest(exportedKey.n),
    use: "sig",
    alg: "RS256",
  };
  const codes = new Map();
  const accessTokens = new Map();
  const sessions = new Map();
  const forms = new Map();
  const flows = new Map();
  const portalSessions = new Map();
  const user = {
    sub: "demo-user-001",
    email: "demo@aiops.example",
    name: "内网演示用户",
    email_verified: true,
    groups: [],
  };
  const put = (map, value, seconds) => {
    const key = random();
    map.set(key, { ...value, until: now() + seconds * 1000 });
    return key;
  };
  const cookie = (name, value, path, age = 3600) =>
    `${name}=${value}; Path=${path}; HttpOnly; SameSite=Lax; Max-Age=${age}`;

  return http.createServer(async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Referrer-Policy", "strict-origin");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader(
      "Content-Security-Policy",
      `default-src 'none'; form-action 'self'; frame-ancestors ${portal} ${gateway}`
    );
    const json = (status, value) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(value));
    };
    const redirect = (url) => {
      res.writeHead(302, { Location: url });
      res.end();
    };
    const cookies = Object.fromEntries(
      (req.headers.cookie || "")
        .split(";")
        .filter((c) => c.includes("="))
        .map((c) => c.trim().split(/=(.*)/s).slice(0, 2))
    );
    const readBody = async () => {
      let body = "";
      for await (const chunk of req) {
        body += chunk;
        if (body.length > 16384) throw new Error("body_too_large");
      }
      return new URLSearchParams(body);
    };
    const issueCode = (params) => {
      const code = put(codes, { params }, 60);
      const target = new URL(params.redirect_uri);
      target.searchParams.set("code", code);
      target.searchParams.set("state", params.state);
      redirect(target.href);
    };
    const loginForm = (id, message = "") => {
      res.writeHead(message ? 401 : 200, {
        "Content-Type": "text/html; charset=utf-8",
      });
      res.end(
        `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>测试身份服务</title><h1>测试身份服务</h1><p>仅供本地 OAuth 演示。请使用 .runtime/account.txt 中的账号。</p><p role="alert">${escape(message)}</p><form method="post" action="/oidc/login"><input type="hidden" name="request" value="${escape(id)}"><p><label>邮箱 <input name="email" type="email" autocomplete="username" required></label></p><p><label>密码 <input name="password" type="password" autocomplete="current-password" required></label></p><button>登录</button></form></html>`
      );
    };
    try {
      for (const map of [
        codes,
        accessTokens,
        sessions,
        forms,
        flows,
        portalSessions,
      ]) {
        for (const [key, value] of map)
        {if (value.until <= now()) map.delete(key);}
      }
      const url = new URL(req.url, portal);
      if (
        req.method === "GET" &&
        url.pathname === "/oidc/.well-known/openid-configuration"
      ) {
        return json(200, {
          issuer,
          authorization_endpoint: `${issuer}/authorize`,
          token_endpoint: `${issuer}/token`,
          userinfo_endpoint: `${issuer}/userinfo`,
          jwks_uri: `${issuer}/jwks`,
          response_types_supported: ["code"],
          subject_types_supported: ["public"],
          id_token_signing_alg_values_supported: ["RS256"],
          scopes_supported: ["openid", "profile", "email"],
          token_endpoint_auth_methods_supported: [
            "client_secret_basic",
            "client_secret_post",
          ],
          code_challenge_methods_supported: ["S256"],
        });
      }
      if (req.method === "GET" && url.pathname === "/oidc/jwks")
      {return json(200, { keys: [jwk] });}
      if (req.method === "GET" && url.pathname === "/oidc/authorize") {
        const params = Object.fromEntries(url.searchParams);
        const client = clients.get(params.client_id);
        if (
          !client ||
          client.callback !== params.redirect_uri ||
          params.response_type !== "code" ||
          !params.state ||
          !params.nonce ||
          params.code_challenge_method !== "S256" ||
          !/^[\w-]{43}$/.test(params.code_challenge || "") ||
          !(params.scope || "").split(" ").includes("openid")
        ) {
          return json(400, { error: "invalid_request" });
        }
        if (sessions.has(cookies.demo_idp)) return issueCode(params);
        const binding = random();
        const id = put(forms, { params, binding, attempts: 0 }, 300);
        res.setHeader(
          "Set-Cookie",
          cookie("demo_login", binding, "/oidc", 300)
        );
        return loginForm(id);
      }
      if (req.method === "POST" && url.pathname === "/oidc/login") {
        const body = await readBody();
        const form = forms.get(body.get("request"));
        if (
          req.headers.origin !== portal ||
          !form ||
          !equal(form.binding, cookies.demo_login)
        )
        {return json(403, { error: "invalid_login_flow" });}
        form.attempts++;
        if (form.attempts > 5) {
          forms.delete(body.get("request"));
          return json(429, { error: "restart_login" });
        }
        if (
          !equal(body.get("email"), user.email) ||
          !equal(body.get("password"), config.password)
        )
        {return loginForm(body.get("request"), "邮箱或密码错误");}
        forms.delete(body.get("request"));
        const session = put(sessions, {}, 3600);
        res.setHeader("Set-Cookie", [
          cookie("demo_idp", session, "/oidc"),
          cookie("demo_login", "", "/oidc", 0),
        ]);
        return issueCode(form.params);
      }
      if (req.method === "POST" && url.pathname === "/oidc/token") {
        const body = await readBody();
        const basic = (req.headers.authorization || "").startsWith("Basic ")
          ? Buffer.from(req.headers.authorization.slice(6), "base64")
            .toString()
            .split(":")
          : [];
        const clientId = basic[0] || body.get("client_id");
        const client = clients.get(clientId);
        if (
          !client ||
          !equal(client.secret, basic[1] || body.get("client_secret"))
        )
        {return json(401, { error: "invalid_client" });}
        const code = codes.get(body.get("code"));
        if (
          !code ||
          body.get("grant_type") !== "authorization_code" ||
          code.params.client_id !== clientId ||
          body.get("redirect_uri") !== client.callback ||
          !equal(
            digest(body.get("code_verifier") || ""),
            code.params.code_challenge
          )
        )
        {return json(400, { error: "invalid_grant" });}
        codes.delete(body.get("code"));
        const issued = Math.floor(now() / 1000);
        const payload = {
          ...user,
          iss: issuer,
          aud: clientId,
          iat: issued,
          exp: issued + 300,
          nonce: code.params.nonce,
        };
        const unsigned = `${encode({ alg: "RS256", typ: "JWT", kid: jwk.kid })}.${encode(payload)}`;
        const idToken = `${unsigned}.${sign("RSA-SHA256", Buffer.from(unsigned), privateKey).toString("base64url")}`;
        return json(200, {
          access_token: put(accessTokens, { user }, 300),
          token_type: "Bearer",
          expires_in: 300,
          id_token: idToken,
          scope: "openid profile email",
        });
      }
      if (req.method === "GET" && url.pathname === "/oidc/userinfo") {
        const token = (req.headers.authorization || "").replace(/^Bearer /, "");
        const access = accessTokens.get(token);
        return access
          ? json(200, access.user)
          : json(401, { error: "invalid_token" });
      }
      if (req.method === "GET" && url.pathname === "/portal/login") {
        const verifier = random();
        const nonce = random();
        const state = put(flows, { verifier, nonce }, 300);
        res.setHeader("Set-Cookie", cookie("demo_flow", state, "/portal", 300));
        const params = new URLSearchParams({
          client_id: "portal-demo",
          redirect_uri: clients.get("portal-demo").callback,
          response_type: "code",
          scope: "openid profile email",
          state,
          nonce,
          code_challenge: digest(verifier),
          code_challenge_method: "S256",
        });
        return redirect(`${issuer}/authorize?${params}`);
      }
      if (req.method === "GET" && url.pathname === "/portal/callback") {
        const state = url.searchParams.get("state");
        const flow = flows.get(state);
        if (!flow || !equal(cookies.demo_flow, state))
        {return json(403, { error: "invalid_state" });}
        flows.delete(state);
        const tokenResponse = await fetch(
          `http://127.0.0.1:${res.socket.localPort}/oidc/token`,
          {
            method: "POST",
            body: new URLSearchParams({
              grant_type: "authorization_code",
              client_id: "portal-demo",
              client_secret: config.portalSecret,
              code: url.searchParams.get("code") || "",
              redirect_uri: clients.get("portal-demo").callback,
              code_verifier: flow.verifier,
            }),
            signal: AbortSignal.timeout(5000),
          }
        );
        if (!tokenResponse.ok)
        {return json(401, { error: "token_exchange_failed" });}
        const tokens = await tokenResponse.json();
        const [header, body, signature] = tokens.id_token.split(".");
        const claims = JSON.parse(Buffer.from(body, "base64url"));
        if (
          !verify(
            "RSA-SHA256",
            Buffer.from(`${header}.${body}`),
            publicKey,
            Buffer.from(signature, "base64url")
          ) ||
          claims.iss !== issuer ||
          claims.aud !== "portal-demo" ||
          claims.nonce !== flow.nonce ||
          claims.exp <= now() / 1000
        )
        {return json(401, { error: "invalid_id_token" });}
        res.setHeader("Set-Cookie", [
          cookie(
            "demo_portal",
            put(portalSessions, { user: claims }, 3600),
            "/portal"
          ),
          cookie("demo_flow", "", "/portal", 0),
        ]);
        return redirect("/");
      }
      if (req.method === "GET" && url.pathname === "/portal/me") {
        const session = portalSessions.get(cookies.demo_portal);
        return session
          ? json(200, { email: session.user.email, name: session.user.name })
          : json(401, { error: "login_required" });
      }
      if (req.method === "POST" && url.pathname === "/portal/logout") {
        if (
          req.headers.origin !== portal ||
          !portalSessions.has(cookies.demo_portal)
        )
        {return json(403, { error: "forbidden" });}
        portalSessions.delete(cookies.demo_portal);
        // Cookies share a host across ports; logout clears both relying-party cookies.
        res.setHeader("Set-Cookie", [
          cookie("demo_portal", "", "/portal", 0),
          cookie("demo_idp", "", "/oidc", 0),
          cookie("jwt_token", "", "/", 0),
          cookie("sso_session_id", "", "/", 0),
        ]);
        return json(200, { logged_out: true });
      }
      return json(404, { error: "not_found" });
    } catch {
      if (!res.headersSent) json(400, { error: "invalid_request" });
      else res.end();
    }
  });
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const config = JSON.parse(
    readFileSync(process.env.DEMO_CONFIG || "./config.json", "utf8")
  );
  const server = createDemoServer(config);
  server.on("request", (req, res) => {
    res.on("finish", () =>
      console.log(
        req.method,
        new URL(req.url, config.portalOrigin).pathname,
        res.statusCode
      )
    );
  });
  server.listen(8080, "0.0.0.0", () =>
    console.log("Local OIDC fixture listening on 8080")
  );
}
