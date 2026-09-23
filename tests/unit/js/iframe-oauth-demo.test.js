/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
import { readFileSync } from "node:fs";
import { expect, test, vi } from "vitest";

test("iframe demo opens API Key issuance after the MCP session is ready", async () => {
  document.body.innerHTML = readFileSync("infra/iframe-oauth/public/index.html", "utf8");
  vi.stubGlobal("fetch", vi.fn(async (url) => {
    if (url === "/portal/me") return { ok: true, json: async () => ({ name: "Demo", email: "demo@aiops.example" }) };
    if (url.endsWith("/embed/session")) return { ok: true, json: async () => ({ email: "demo@aiops.example" }) };
    throw new Error(`Unexpected request: ${url}`);
  }));

  await import("../../../infra/iframe-oauth/public/portal.js?key-switch");
  const frame = document.querySelector("#mcp");
  const key = document.querySelector("#open-key");
  const workspace = document.querySelector("#open-workspace");
  expect(frame.src).toBe(`${location.protocol}//${location.hostname}:18081/embed/start.html`);
  expect(key.hidden).toBe(true);

  frame.dispatchEvent(new Event("load"));
  await vi.waitFor(() => expect(key.hidden).toBe(false));
  key.click();
  expect(frame.src).toBe(`${location.protocol}//${location.hostname}:18081/admin/api-key`);
  workspace.click();
  expect(frame.src).toBe(`${location.protocol}//${location.hostname}:18081/admin/`);
  vi.unstubAllGlobals();
});
