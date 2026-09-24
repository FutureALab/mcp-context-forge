import { afterEach, describe, expect, test, vi } from "vitest";
import { listenForCredentialExpiry, openContextForge } from "../../../infra/portal-session-bridge/portal-client.js";

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("parent identity cookie bridge", () => {
  test("exchanges account cookies before opening the gateway iframe", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ next: "/admin", token: "parent-token", expires_at: 123 }) });
    vi.stubGlobal("fetch", fetchMock);

    const result = await openContextForge(frame, "login", { gatewayOrigin: "http://mcp.test" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://mcp.test/auth/portal/exchange");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "include" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ purpose: "login" });
    expect(frame.src).toBe("http://mcp.test/admin");
    expect(result).toEqual({ token: "parent-token", expiresAt: 123 });
  });

  test("reuses a parent token for the Key page", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ next: "/admin/api-key", token: "parent-token", expires_at: 123 }) });
    vi.stubGlobal("fetch", fetchMock);

    await openContextForge(frame, "key", { gatewayOrigin: "http://mcp.test", token: "parent-token" });

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ purpose: "key", token: "parent-token" });
    expect(frame.src).toBe("http://mcp.test/admin/api-key?portal=success");
  });

  test("uses the configured proxy prefix for the exchange", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ next: "/mcp/admin" }) });
    vi.stubGlobal("fetch", fetchMock);

    await openContextForge(frame, "login", { gatewayOrigin: "http://portal.test/mcp" });

    expect(fetchMock.mock.calls[0][0]).toBe("http://portal.test/mcp/auth/portal/exchange");
    expect(frame.src).toBe("http://portal.test/mcp/admin");
  });

  test("rejects an unexpected destination and wrong-origin refresh messages", async () => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ next: "http://attacker.test/" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(openContextForge(frame, "key", { gatewayOrigin: "http://mcp.test" })).rejects.toThrow("无效的页面地址");

    fetchMock.mockClear();
    const onError = vi.fn();
    const stop = listenForCredentialExpiry(frame, { gatewayOrigin: "http://mcp.test" }, onError);
    window.dispatchEvent(new MessageEvent("message", { origin: "http://attacker.test", source: frame.contentWindow, data: { type: "contextforge-portal-cookie-required", purpose: "key" } }));
    expect(onError).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent("message", { origin: "http://mcp.test", source: frame.contentWindow, data: { type: "contextforge-portal-cookie-required", purpose: "key" } }));
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0].message).toContain("刷新父页面");
    window.dispatchEvent(new MessageEvent("message", { origin: "http://mcp.test", source: frame.contentWindow, data: { type: "contextforge-portal-cookie-required", purpose: "login" } }));
    expect(onError).toHaveBeenCalledTimes(2);
    stop();
  });
});
