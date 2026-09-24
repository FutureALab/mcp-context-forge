/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
import { readFileSync } from "node:fs";
import { expect, test, vi } from "vitest";

const template = (name) =>
  readFileSync(`mcpgateway/templates/${name}.html`, "utf8").replaceAll(
    "{{ root_path }}",
    ""
  );
const el = (id) => document.getElementById(id);
const response = (data) => ({ ok: true, json: async () => data });

test("self-service sends passwords and invalidates changed account input", async () => {
  document.body.innerHTML = template("member_key");
  const fetchMock = vi.fn(async (url) => {
    if (url.endsWith("/auth/sso/providers")) {
      return response([{ id: "example", display_name: "Example" }]);
    }
    if (url.endsWith("options")) {
      return response({
        teams: [{ id: "my-team", name: "My Team" }],
        servers: [
          {
            id: "public-server",
            name: "Public MCP",
            team_id: "other-team",
            visibility: "public",
            eligible_team_ids: ["my-team"],
          },
        ],
      });
    }
    return response({ api_key: "fixture-key", expires_at: "2026-10-17T12:00:00Z" });
  });
  vi.stubGlobal("fetch", fetchMock);
  await import("../../../mcpgateway/static/member-key.js");
  await vi.waitFor(() => expect(el("member-sso-provider").value).toBe("example"));
  el("member-mode-password").click();
  el("member-email").value = "member@example.com";
  el("member-password").value = "fixture-password";
  el("load-memberships").click();
  await vi.waitFor(() => expect(el("member-team").disabled).toBe(false));
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).password).toBe(
    "fixture-password"
  );
  el("member-team").value = "my-team";
  el("member-team").dispatchEvent(new Event("change"));
  expect(el("member-server").options[1].value).toBe("public-server");
  el("member-server").value = "public-server";
  el("member-server").dispatchEvent(new Event("change"));
  el("member-key-form").dispatchEvent(
    new Event("submit", { cancelable: true })
  );
  await vi.waitFor(() =>
    expect(el("member-key-value").value).toBe("fixture-key")
  );
  expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toMatchObject({
    password: "fixture-password",
    team_id: "my-team",
    server_id: "public-server",
  });
  fetchMock.mockResolvedValueOnce(response({ renewed: true, api_key: "", expires_at: "2027-10-17T12:00:00Z" }));
  el("member-days").value = "365";
  el("member-key-form").dispatchEvent(new Event("submit", { cancelable: true }));
  await vi.waitFor(() => expect(document.body.textContent).toContain("原 API Key 已续期至"));
  expect(el("member-key-value").value).toBe("");
  expect(JSON.parse(fetchMock.mock.calls[3][1].body).days).toBe(365);
  el("member-password").dispatchEvent(new Event("input"));
  expect(el("member-team").disabled).toBe(true);
  expect(el("issue-member-key").disabled).toBe(true);
  expect(el("member-key-value").value).toBe("");
  vi.unstubAllGlobals();
});

test("self-service OAuth checks the session and issues without password fields", async () => {
  document.body.innerHTML = template("member_key");
  const fetchMock = vi.fn(async (url) => {
    if (url.endsWith("/auth/sso/providers")) {
      return response([{ id: "example", display_name: "Example" }]);
    }
    if (url.endsWith("sso/options")) {
      return response({
        email: "member@example.com",
        full_name: "Member",
        teams: [{ id: "my-team", name: "My Team" }],
        servers: [{ id: "server-a", name: "MCP", eligible_team_ids: ["my-team"] }],
      });
    }
    return response({ api_key: "oauth-key", expires_at: "2026-10-17T12:00:00Z" });
  });
  vi.stubGlobal("fetch", fetchMock);
  await import("../../../mcpgateway/static/member-key.js?oauth-flow");
  await vi.waitFor(() => expect(el("member-sso-provider").value).toBe("example"));
  el("load-memberships").click();
  await vi.waitFor(() => expect(el("member-team").disabled).toBe(false));
  expect(fetchMock.mock.calls[1][0]).toContain("sso/options");
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({});
  el("member-team").value = "my-team";
  el("member-team").dispatchEvent(new Event("change"));
  el("member-server").value = "server-a";
  el("member-server").dispatchEvent(new Event("change"));
  el("member-key-form").dispatchEvent(new Event("submit", { cancelable: true }));
  await vi.waitFor(() => expect(el("member-key-value").value).toBe("oauth-key"));
  expect(fetchMock.mock.calls[2][0]).toContain("sso/issue");
  expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ team_id: "my-team", server_id: "server-a", days: 30 });
  vi.unstubAllGlobals();
});

test("self-service shows the administrator notice for an unregistered OAuth user", async () => {
  window.history.replaceState({}, "", "?error=unregistered");
  document.body.innerHTML = template("member_key");
  vi.stubGlobal("fetch", vi.fn(async () => response([{ id: "example", display_name: "Example" }])));
  await import("../../../mcpgateway/static/member-key.js?unregistered");
  await vi.waitFor(() => expect(el("member-key-message").textContent).toBe("该用户未在系统中注册，请联系管理员处理。"));
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
});

test("self-service OAuth keeps the provider callback address unchanged", async () => {
  document.body.innerHTML = template("member_key");
  const fetchMock = vi.fn(async (url) => {
    if (url.endsWith("/auth/sso/providers")) return response([{ id: "example", display_name: "Example" }]);
    if (url.endsWith("sso/options")) return { redirected: true, status: 302 };
    throw new Error("authorization request captured");
  });
  vi.stubGlobal("fetch", fetchMock);
  await import("../../../mcpgateway/static/member-key.js?standard-callback");
  await vi.waitFor(() => expect(el("member-sso-provider").value).toBe("example"));
  el("load-memberships").click();
  await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBe(3));
  const initiation = new URL(fetchMock.mock.calls[2][0], "https://gateway.example");
  expect(initiation.searchParams.get("flow")).toBe("member_key");
  expect(initiation.searchParams.get("redirect_uri")).toBe(`${window.location.origin}/auth/sso/callback/example`);
  vi.unstubAllGlobals();
});

test("self-service parent cookie proof loads teams without an OIDC provider", async () => {
  window.history.replaceState({}, "", "?portal=success");
  document.body.innerHTML = template("member_key")
    .replace("{{ 'true' if portal_sso_enabled else 'false' }}", "true")
    .replace("{{ 'hidden' if portal_sso_enabled else '' }}", "hidden")
    .replace("{{ portal_sso_parent_origin }}", "http://portal.test");
  const fetchMock = vi.fn(async () => response({
    email: "member@example.com",
    teams: [{ id: "my-team", name: "My Team" }],
    servers: [{ id: "server-a", name: "MCP", eligible_team_ids: ["my-team"] }],
  }));
  vi.stubGlobal("fetch", fetchMock);
  await import("../../../mcpgateway/static/member-key.js?portal-cookie");
  await vi.waitFor(() => expect(el("member-team").disabled).toBe(false));
  expect(el("member-sso-fields").classList.contains("hidden")).toBe(true);
  el("member-mode-password").click();
  el("member-mode-sso").click();
  expect(el("member-sso-fields").classList.contains("hidden")).toBe(true);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toContain("sso/options");
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
});

test("expired parent cookie proof asks the parent page to refresh", async () => {
  document.body.innerHTML = template("member_key")
    .replace("{{ 'true' if portal_sso_enabled else 'false' }}", "true")
    .replace("{{ 'hidden' if portal_sso_enabled else '' }}", "hidden")
    .replace("{{ portal_sso_parent_origin }}", "http://portal.test");
  const parent = { postMessage: vi.fn() };
  vi.stubGlobal("parent", parent);
  vi.stubGlobal("fetch", vi.fn(async () => ({ status: 401, redirected: false })));
  await import("../../../mcpgateway/static/member-key.js?portal-expired");
  el("load-memberships").click();
  await vi.waitFor(() => expect(parent.postMessage).toHaveBeenCalledWith(
    { type: "contextforge-portal-cookie-required", purpose: "key" },
    "http://portal.test"
  ));
  await vi.waitFor(() => expect(el("member-key-message").textContent).toContain("请刷新父页面"));
  vi.unstubAllGlobals();
});

test("monitoring renders charts, methods and formatted times; member actions target the selected MCP", async () => {
  document.body.innerHTML =
    template("member_usage") +
    template("server_members") +
    '<button id="open-member-fixture" data-server-members="server-a">Manage</button>';
  const metric = {
    calls: 2,
    errors: 0,
    success_rate: 100,
    avg_ms: 12,
    p95_ms: 15,
    usage_reported_calls: 0,
  };
  const data = {
    summary: metric,
    members: [],
    tokens: [],
    methods: [{ method: "tools/call", resource: "ping", ...metric }],
    trend: [{ date: "2026-09-17", ...metric }],
    recent: [
      {
        timestamp: "2026-09-17T02:30:05Z",
        method: "tools/call",
        resource: "ping",
        latency_ms: 12,
      },
    ],
    coverage: {
      matching_requests: 2,
      logging_enabled: true,
      latency: "HTTP",
      model_usage: "Reported only",
    },
  };
  const fetchMock = vi.fn(async (url) =>
    response(
      url.endsWith("/servers")
        ? {
          teams: [{ id: "team-a", name: "Team A" }],
          servers: [
            {
              id: "server-a",
              name: "Server A",
              team_id: "team-a",
              team_name: "Team A",
              enabled: true,
              can_import: true,
            },
          ],
        }
        : url.endsWith("/keys")
          ? {
            results: [
              {
                status: "created",
                server_id: "server-a",
                email: "member@example.com",
                api_key: "fixture",
              },
            ],
          }
          : data
    )
  );
  vi.stubGlobal("fetch", fetchMock);
  const charts = [];
  window.Chart = class {
    constructor(_canvas, config) {
      charts.push(config);
    }
    destroy() {}
  };
  el("server-members-dialog").showModal = vi.fn();
  await import("../../../mcpgateway/static/member-usage.js");
  document.dispatchEvent(new CustomEvent("member-usage:open"));
  await vi.waitFor(() => expect(charts.length).toBe(6));
  expect(charts.map((c) => c.type)).toEqual(["line", "bar", "bar", "bar", "bar", "doughnut"]);
  expect(charts[1].options.indexAxis).toBe("y");
  expect(charts[1].options.plugins.legend.display).toBe(false);
  expect(charts[0].options.plugins.legend.labels.usePointStyle).toBe(true);
  expect(charts[4].options.scales.x.max).toBe(100);
  expect(el("recent-table").textContent).toContain("tools/call");
  expect(el("recent-table").textContent).toContain("ping");
  expect(el("recent-table").querySelector("tbody td").textContent).toMatch(
    /^2026-09-17 \d{2}:30:05$/
  );
  expect(el("member-panel").querySelector("#import-members")).toBeNull();
  el("open-member-fixture").click();
  await vi.waitFor(() =>
    expect(el("management-server").value).toBe("server-a")
  );
  el("bulk-selected").click();
  await vi.waitFor(() => expect(el("download-keys").disabled).toBe(false));
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith("/keys"));
  expect(JSON.parse(call[1].body)).toEqual({ server_id: "server-a", team_id: "team-a", days: 30 });
  expect(el("management-results").textContent).toContain("member@example.com");
  expect(el("management-results").textContent).not.toContain("fixture");
  fetchMock.mockResolvedValueOnce(response({ total: 2, offset: 0, limit: 50, results: [
    { token_id: "saved-key", email: "other@example.com", name: "Saved", status: "有效", key_available: true },
    { token_id: "legacy-key", email: "legacy@example.com", name: "Legacy", status: "已停用", key_available: false },
  ] }));
  el("load-key-history").click();
  await vi.waitFor(() => expect(el("key-history-status").textContent).toContain("共 2 条"));
  expect(el("key-history-table").textContent).toContain("other@example.com");
  expect(el("key-history-table").textContent).toContain("无法恢复");
  expect(fetchMock.mock.calls.at(-1)[0]).toContain("/key-history/server-a?");
  fetchMock.mockResolvedValueOnce(response({ token_id: "saved-key", email: "other@example.com", api_key: "stored-secret", key_message: "可查看", permissions: ["tools.read"] }));
  el("key-history-table").querySelector("button").click();
  await vi.waitFor(() => expect(el("key-history-value").value).toBe("stored-secret"));
  expect(el("key-history-metadata").textContent).toContain("tools.read");
  el("close-history-key").click();
  expect(el("key-history-value").value).toBe("");
  expect(el("key-history-detail").hidden).toBe(true);
  let resolveDetail;
  fetchMock.mockImplementationOnce(() => new Promise(resolve => { resolveDetail = resolve; }));
  el("key-history-table").querySelector("button").click();
  await vi.waitFor(() => expect(resolveDetail).toBeDefined());
  el("server-members-dialog").dispatchEvent(new Event("close"));
  resolveDetail(response({ api_key: "late-secret" }));
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(el("key-history-value").value).toBe("");
  fetchMock.mockResolvedValueOnce({ status: 401, ok: false });
  el("open-member-fixture").click();
  await vi.waitFor(() => expect(el("management-status").textContent).toContain("登录已过期"));
  expect(el("management-status").querySelector("a").getAttribute("href")).toBe("/admin/login");
  expect(el("management-server").textContent).not.toContain("正在加载");
  expect(el("management-server").disabled).toBe(true);
  expect(el("bulk-selected").disabled).toBe(true);
  fetchMock.mockResolvedValueOnce({ status: 500, ok: false, json: async () => ({ detail: "服务暂不可用" }) });
  el("open-member-fixture").click();
  await vi.waitFor(() => expect(el("retry-member-servers").hidden).toBe(false));
  expect(el("management-server").textContent).toContain("加载失败");
  el("retry-member-servers").click();
  await vi.waitFor(() => expect(el("management-server").value).toBe("server-a"));
  expect(el("import-members").disabled).toBe(true);
  Object.defineProperty(el("members-file"), "files", { configurable: true, value: [new File(["fixture"], "members.csv")] });
  el("members-file").dispatchEvent(new Event("change"));
  expect(el("import-members").disabled).toBe(true);
  expect(el("members-file-info").textContent).toContain("请选择");
  Object.defineProperty(el("members-file"), "files", { configurable: true, value: [new File(["fixture"], "members.xlsx")] });
  el("members-file").dispatchEvent(new Event("change"));
  expect(el("members-file-name").textContent).toBe("members.xlsx");
  expect(el("import-members").disabled).toBe(false);
  fetchMock.mockResolvedValueOnce(response({ results: [{ status: "added", email: "member@example.com" }] }));
  el("import-members").click();
  await vi.waitFor(() => expect(el("management-results").textContent).toContain("added"));
  expect(fetchMock.mock.calls.at(-1)[0]).toBe("/admin/member-usage/import/server-a");
  expect(fetchMock.mock.calls.at(-1)[1].body.get("file").name).toBe("members.xlsx");
  expect(fetchMock.mock.calls.at(-1)[1].body.get("team_id")).toBe("team-a");
  fetchMock.mockResolvedValueOnce(response({ teams: [{ id: "team-a", name: "Team A" }], servers: [{ id: "server-a", name: "Personal public MCP", team_id: "personal", is_personal: true, visibility: "public", enabled: true, can_import: false }] }));
  el("open-member-fixture").click();
  await vi.waitFor(() => expect(el("management-team").textContent).toContain("个人空间"));
  expect(el("bulk-selected").disabled).toBe(true);
  el("management-target-team").value = "team-a";
  el("management-target-team").dispatchEvent(new Event("change"));
  expect(el("bulk-selected").disabled).toBe(false);
  expect(el("import-members").disabled).toBe(false);
  vi.unstubAllGlobals();
});
