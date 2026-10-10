/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
import { beforeEach, expect, it, vi } from "vitest";

const overview = {
  summary: {
    calls: 23,
    successes: 22,
    errors: 1,
    success_rate: 95.65,
    avg_ms: 12,
    users: 2,
  },
  connectors: [
    {
      id: "connector-a",
      name: "Connector A",
      enabled: true,
      reachable: true,
      last_seen: "2026-10-09T10:00:00",
    },
  ],
  servers: [{ id: "server-a", name: "Server A" }],
  tool_count: 3,
  trend: [{ date: "2026-10-09", calls: 23, successes: 22, errors: 1 }],
  rankings: {
    tool: [{ name: "query", calls: 23 }],
    gateway: [],
    server: [],
    email: [],
  },
  coverage: {
    scope: "API Key tools/call",
    logging_enabled: true,
    payloads_enabled: true,
  },
};
const records = {
  total: 23,
  records: [
    {
      id: 1,
      timestamp: "2026-10-09T10:00:00",
      tool: "<img src=x onerror=alert(1)>",
      gateway: "Connector A",
      server: "Server A",
      outcome: "error",
      http_status: 200,
      latency_ms: 0,
      email: "member@example.com",
      input: '{"department":"engineering"}',
      output: '{"isError":true}',
    },
  ],
};
const response = (data) => ({ ok: true, status: 200, json: async () => data });

beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = `<div class="mcp-usage" data-view="mcp-audit" data-root="/prefix"><select data-filter="days"><option value="30">30</option></select><button data-refresh>刷新</button><p class="mcp-status"></p><form><select data-filter="status"><option value="all">全部</option><option value="error">错误</option></select><input data-filter="search"><select data-filter="gateway_id"><option value="">全部</option></select><select data-filter="server_id"><option value="">全部</option></select></form><div data-audit></div><span data-page-label></span><button data-previous>上一页</button><button data-next>下一页</button><p data-coverage></p></div>`;
  window.Admin = { getAuthToken: async () => "fixture-session" };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) =>
      response(url.includes("overview") ? overview : records)
    )
  );
});
const get = (selector) => document.querySelector(selector);
async function open() {
  await import("../../../mcpgateway/static/mcp-usage.js");
  document.dispatchEvent(
    new CustomEvent("mcp-usage:open", { detail: "mcp-audit" })
  );
  await vi.waitFor(() =>
    expect(get(".mcp-status").textContent).toContain("已更新")
  );
}

it("renders protocol errors and expands safe payload details", async () => {
  await open();
  expect(get("[data-audit]").textContent).toContain("错误 / 200");
  expect(get("[data-audit]").textContent).toContain("0 ms");
  expect(get("[data-audit] img")).toBeNull();
  const button = get("[data-audit] button");
  button.click();
  expect(button.getAttribute("aria-expanded")).toBe("true");
  expect(
    document.getElementById(button.getAttribute("aria-controls")).hidden
  ).toBe(false);
  expect(get("pre").textContent).toContain("engineering");
  expect(fetch.mock.calls[0][0]).toContain("/prefix/admin/mcp-usage/");
  expect(fetch.mock.calls[0][1].headers.Authorization).toBe(
    "Bearer fixture-session"
  );
});

it("paginates and resets the page when filters change", async () => {
  await open();
  get("[data-next]").click();
  await vi.waitFor(() =>
    expect(fetch.mock.calls.some(([url]) => url.includes("offset=20"))).toBe(
      true
    )
  );
  get('[data-filter="search"]').value = "query_%";
  get("form").dispatchEvent(new Event("submit", { cancelable: true }));
  await vi.waitFor(() =>
    expect(
      fetch.mock.calls.some(
        ([url]) => url.includes("offset=0") && url.includes("search=query_%25")
      )
    ).toBe(true)
  );
});

it("clears audit records and enables retry after an authorization failure", async () => {
  await open();
  fetch.mockImplementation(async () => ({ ok: false, status: 403 }));
  get("[data-refresh]").click();
  await vi.waitFor(() => expect(get(".mcp-status").dataset.error).toBe("true"));
  expect(get("[data-audit]").children).toHaveLength(0);
  expect(get("[data-refresh]").disabled).toBe(false);
});
