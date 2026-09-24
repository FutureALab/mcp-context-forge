/** Open the gateway iframe after exchanging parent-page account cookies. */

export async function openContextForge(frame, purpose, { gatewayOrigin, token }) {
  if (purpose !== "login" && purpose !== "key") throw new Error("Unsupported ContextForge purpose");
  const baseUrl = gatewayOrigin.replace(/\/$/, "");
  const exchangeResponse = await fetch(`${baseUrl}/auth/portal/exchange`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ purpose, ...(token ? { token } : {}) }),
  });
  if (!exchangeResponse.ok) {
    const error = await exchangeResponse.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "登录已过期，请刷新页面");
  }
  const { next, token: authorizedToken, expires_at: expiresAt } = await exchangeResponse.json();
  const destination = new URL(next, baseUrl);
  if (destination.origin !== new URL(baseUrl).origin) throw new Error("MCP 返回了无效的页面地址");
  if (purpose === "key") destination.searchParams.set("portal", "success");
  frame.src = destination.href;
  return { token: authorizedToken, expiresAt };
}

export function listenForCredentialExpiry(frame, config, onError) {
  const listener = (event) => {
    if (event.origin !== new URL(config.gatewayOrigin).origin || event.source !== frame.contentWindow) return;
    if (!["login", "key"].includes(event.data?.purpose)) return;
    if (event.data.type === "contextforge-portal-access-denied") onError(new Error("该账号没有 MCP 工作区权限，请联系管理员分配有效 Team 和工作区角色"));
    if (event.data.type === "contextforge-portal-cookie-required") onError(new Error("MCP 凭据已过期，请刷新父页面"));
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}
