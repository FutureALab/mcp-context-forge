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
  const fetchMock = vi.fn(async (url) =>
    response(
      url.endsWith("options")
        ? {
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
        }
        : { api_key: "fixture-key", expires_at: "2026-10-17T12:00:00Z" }
    )
  );
  vi.stubGlobal("fetch", fetchMock);
  await import("../../../mcpgateway/static/member-key.js");
  el("member-email").value = "member@example.com";
  el("member-password").value = "fixture-password";
  el("load-memberships").click();
  await vi.waitFor(() => expect(el("member-team").disabled).toBe(false));
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).password).toBe(
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
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({
    password: "fixture-password",
    team_id: "my-team",
    server_id: "public-server",
  });
  el("member-password").dispatchEvent(new Event("input"));
  expect(el("member-team").disabled).toBe(true);
  expect(el("issue-member-key").disabled).toBe(true);
  expect(el("member-key-value").value).toBe("");
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
  await vi.waitFor(() => expect(charts.length).toBe(2));
  expect(charts.map((c) => c.type)).toEqual(["line", "bar"]);
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
  expect(JSON.parse(call[1].body)).toEqual({ server_id: "server-a", days: 30 });
  expect(el("management-results").textContent).toContain("member@example.com");
  expect(el("management-results").textContent).not.toContain("fixture");
  vi.unstubAllGlobals();
});
