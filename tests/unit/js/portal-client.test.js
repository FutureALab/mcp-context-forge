import { afterEach, describe, expect, test, vi } from "vitest";
import { listenForKeyRefresh, openContextForge } from "../../../infra/portal-session-bridge/portal-client.js";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("parent Session ticket bridge", () => {
  test("exchanges a login ticket before opening the gateway iframe", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ticket: "signed-ticket" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ next: "/admin" }) });
    vi.stubGlobal("fetch", fetchMock);

    await openContextForge(frame, "login", { gatewayOrigin: "http://mcp.test", ticketHeaders: { "X-CSRF-TOKEN": "csrf" } });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "include", headers: { "X-CSRF-TOKEN": "csrf" } });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ purpose: "login" });
    expect(fetchMock.mock.calls[1][0]).toBe("http://mcp.test/auth/portal/exchange");
    expect(fetchMock.mock.calls[1][1].credentials).toBe("include");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ ticket: "signed-ticket" });
    expect(frame.src).toBe("http://mcp.test/admin");
  });

  test("rejects an unexpected destination and wrong-origin refresh messages", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ticket: "signed-ticket" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ next: "http://attacker.test/" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(openContextForge(frame, "key", { gatewayOrigin: "http://mcp.test" })).rejects.toThrow("无效的页面地址");

    fetchMock.mockClear();
    const stop = listenForKeyRefresh(frame, { gatewayOrigin: "http://mcp.test" }, vi.fn());
    window.dispatchEvent(new MessageEvent("message", { origin: "http://attacker.test", source: frame.contentWindow, data: { type: "contextforge-portal-ticket-required", purpose: "key" } }));
    expect(fetchMock).not.toHaveBeenCalled();
    stop();
  });
});
