const frame = document.querySelector("#mcp");
const status = document.querySelector("#status");
const gatewayOrigin = `${location.protocol}//${location.hostname}:18081`;
let loginTimer;

function openWorkspace() {
  status.textContent = "平台已登录，正在建立 MCP 登录会话…";
  document.querySelector("#retry").hidden = true;
  frame.hidden = false;
  frame.src = `${gatewayOrigin}/embed/start.html`;
  clearTimeout(loginTimer);
  loginTimer = setTimeout(() => {
    status.textContent = "MCP 尚未就绪，请检查网关日志或重新加载。";
    document.querySelector("#retry").hidden = false;
  }, 45000);
}

window.addEventListener("message", (event) => {
  if (event.origin !== gatewayOrigin || event.source !== frame.contentWindow)
  {return;}
  if (event.data?.type === "mcp-sso-error") {
    clearTimeout(loginTimer);
    status.textContent = event.data.message;
    document.querySelector("#retry").hidden = false;
  }
});

frame.addEventListener("load", async () => {
  try {
    const response = await fetch(`${gatewayOrigin}/embed/session`, {
      credentials: "include",
    });
    if (!response.ok) return;
    const user = await response.json();
    clearTimeout(loginTimer);
    status.textContent = `MCP 已登录 · ${user.email}`;
    document.querySelector("#retry").hidden = false;
  } catch {
    /* The initial authorization navigation can precede the gateway session. */
  }
});

document.querySelector("#retry").onclick = openWorkspace;
document.querySelector("#logout").onclick = async () => {
  const response = await fetch("/portal/logout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (response.ok) location.replace("/");
};

try {
  const response = await fetch("/portal/me");
  if (response.ok) {
    const user = await response.json();
    document.querySelector("#identity").textContent =
      `${user.name} · ${user.email}`;
    document.querySelector("#login-panel").hidden = true;
    document.querySelector("#logout").hidden = false;
    openWorkspace();
  } else if (response.status === 401) {
    document.querySelector("#identity").textContent = "未登录";
  } else throw new Error("身份服务暂不可用");
} catch {
  document.querySelector("#identity").textContent = "连接失败";
  status.textContent = "无法连接身份服务，请检查演示容器。";
}
