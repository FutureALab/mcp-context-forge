/** Open the gateway iframe after exchanging parent-page account cookies. */

export async function openContextForge(frame, purpose, { gatewayOrigin }) {
  if (purpose !== "login" && purpose !== "key") throw new Error("Unsupported ContextForge purpose");
  const baseUrl = gatewayOrigin.replace(/\/$/, "");
  const exchangeResponse = await fetch(`${baseUrl}/auth/portal/exchange`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ purpose }),
  });
  if (!exchangeResponse.ok) {
    const error = await exchangeResponse.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "登录已过期，请刷新页面");
  }
  const { next } = await exchangeResponse.json();
  const destination = new URL(next, baseUrl);
  if (destination.origin !== new URL(baseUrl).origin) throw new Error("MCP 返回了无效的页面地址");
  if (purpose === "key") destination.searchParams.set("portal", "success");
  frame.src = destination.href;
}

export function listenForCredentialExpiry(frame, config, onError) {
  const listener = (event) => {
    if (event.origin !== new URL(config.gatewayOrigin).origin || event.source !== frame.contentWindow) return;
    if (event.data?.type !== "contextforge-portal-cookie-required" || !["login", "key"].includes(event.data.purpose)) return;
    onError(new Error("MCP 凭据已过期，请刷新父页面"));
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}
