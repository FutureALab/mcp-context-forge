/** Parent Vue integration for the existing Spring Boot Session Cookie. */

export async function openContextForge(frame, purpose, { gatewayOrigin, ticketEndpoint = "/api/mcp/ticket", ticketHeaders = {} }) {
  if (purpose !== "login" && purpose !== "key") throw new Error("Unsupported ContextForge purpose");
  const ticketResponse = await fetch(ticketEndpoint, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...ticketHeaders },
    body: JSON.stringify({ purpose }),
  });
  if (!ticketResponse.ok) throw new Error("父平台登录已失效，请重新登录");
  const { ticket } = await ticketResponse.json();
  const exchangeResponse = await fetch(`${gatewayOrigin}/auth/portal/exchange`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticket }),
  });
  if (!exchangeResponse.ok) throw new Error("MCP 鉴权失败，请联系管理员检查票据配置");
  const { next } = await exchangeResponse.json();
  const destination = new URL(next, gatewayOrigin);
  if (destination.origin !== gatewayOrigin) throw new Error("MCP 返回了无效的页面地址");
  if (purpose === "key") destination.searchParams.set("portal", "success");
  frame.src = destination.href;
}

export function listenForKeyRefresh(frame, config, onError) {
  const listener = async (event) => {
    if (event.origin !== config.gatewayOrigin || event.source !== frame.contentWindow) return;
    if (event.data?.type !== "contextforge-portal-ticket-required" || event.data.purpose !== "key") return;
    try {
      await openContextForge(frame, "key", config);
    } catch (error) {
      onError(error);
    }
  };
  window.addEventListener("message", listener);
  return () => window.removeEventListener("message", listener);
}
