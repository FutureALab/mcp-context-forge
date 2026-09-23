(async () => {
  const parentOrigin = `${location.protocol}//${location.hostname}:18080`;
  try {
    const current = await fetch("/embed/session");
    if (current.ok) {
      location.replace("/admin/");
      return;
    }
    const callback = `${location.origin}/auth/sso/callback/intranet-demo`;
    const response = await fetch(
      `/auth/sso/login/intranet-demo?redirect_uri=${encodeURIComponent(callback)}`
    );
    if (!response.ok)
    {throw new Error("无法发起 MCP SSO，请检查网关的 SSO 配置。");}
    const data = await response.json();
    const authorization = new URL(data.authorization_url);
    if (
      authorization.origin !== parentOrigin ||
      authorization.pathname !== "/oidc/authorize"
    ) {
      throw new Error("身份服务地址与演示配置不一致。");
    }
    location.replace(authorization.href);
  } catch (error) {
    document.querySelector("#message").textContent = error.message;
    parent.postMessage(
      { type: "mcp-sso-error", message: error.message },
      parentOrigin
    );
  }
})();
