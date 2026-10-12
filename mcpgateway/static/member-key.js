/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
(() => {
  const form = document.getElementById("member-key-form");
  const email = document.getElementById("member-email");
  const password = document.getElementById("member-password");
  const team = document.getElementById("member-team");
  const server = document.getElementById("member-server");
  const issue = document.getElementById("issue-member-key");
  const load = document.getElementById("load-memberships");
  const message = document.getElementById("member-key-message");
  const result = document.getElementById("member-key-result");
  const value = document.getElementById("member-key-value");
  const configValue = document.getElementById("member-config-value");
  const transport = document.getElementById("member-transport");
  const ssoFields = document.getElementById("member-sso-fields");
  const passwordFields = document.getElementById("member-password-fields");
  const provider = document.getElementById("member-sso-provider");
  const ssoMode = document.getElementById("member-mode-sso");
  const passwordMode = document.getElementById("member-mode-password");
  const portalSso = form.dataset.portalSso === "true";
  const portalParentOrigin = form.dataset.parentOrigin;
  const hasSession = form.dataset.sessionCookie === "true";
  if (hasSession) {
    ssoFields.classList.add("hidden");
    ssoMode.textContent = "已登录账号";
  }
  const publicChoice = "__public__";
  let servers = [];
  let account = "";
  let mode = "sso";
  let version = 0;
  let issuedServer = null;
  const renderConfig = () => {
    if (!issuedServer || !value.value) return;
    const sse = transport.value === "sse";
    configValue.value = JSON.stringify({
      mcpServers: {
        [issuedServer.name]: {
          type: transport.value,
          url: new URL(`${form.dataset.root}/servers/${encodeURIComponent(issuedServer.id)}/${sse ? "sse" : "mcp/"}`, window.location.origin).href,
          headers: { Authorization: `Bearer ${value.value}` },
        },
      },
    }, null, 2);
  };
  const clearResult = () => {
    issuedServer = null;
    value.value = "";
    configValue.value = "";
    result.classList.add("hidden");
  };
  transport.addEventListener("change", renderConfig);
  const csrf = () =>
    decodeURIComponent(
      document.cookie
        .split("; ")
        .find((c) => c.startsWith("mcpgateway_csrf_token="))
        ?.split("=")
        .slice(1)
        .join("=") || ""
    );
  async function post(path, body) {
    const response = await fetch(`${form.dataset.root}/admin/api-key/${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf(), Accept: "text/html, application/json" },
      body: JSON.stringify(body),
    });
    if (response.redirected || response.status === 401) {
      throw new Error("AUTH_REQUIRED");
    }
    const data = await response.json();
    if (!response.ok) {
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "请求失败，请检查输入后重试"
      );
    }
    return data;
  }
  function updateServers() {
    server.replaceChildren(new Option("请选择虚拟 MCP", ""));
    servers
      .filter((s) => team.value === publicChoice ? s.public_access : s.eligible_team_ids.includes(team.value))
      .forEach((s) =>
        server.add(
          new Option(
            s.name + (s.visibility === "public" ? " · 公开" : ""),
            s.id
          )
        )
      );
    server.disabled = !team.value;
    issue.disabled = true;
    clearResult();
  }
  function invalidateAccount() {
    version++;
    account = "";
    servers = [];
    team.replaceChildren(new Option("请重新查询账号", ""));
    team.disabled = true;
    updateServers();
    message.textContent = "";
  }
  function switchMode(nextMode) {
    mode = nextMode;
    ssoFields.classList.toggle("hidden", mode !== "sso" || portalSso || hasSession);
    passwordFields.classList.toggle("hidden", mode !== "password");
    email.required = mode === "password";
    password.required = mode === "password";
    ssoMode.setAttribute("aria-pressed", String(mode === "sso"));
    passwordMode.setAttribute("aria-pressed", String(mode === "password"));
    invalidateAccount();
  }
  async function loadProviders() {
    if (portalSso || hasSession) return;
    try {
      const response = await fetch(`${form.dataset.root}/auth/sso/providers`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("OAuth 未启用");
      const providers = await response.json();
      provider.replaceChildren(new Option("请选择 OAuth 服务", ""));
      providers.forEach((item) => provider.add(new Option(item.display_name || item.name, item.id)));
      if (providers.length === 1) provider.value = providers[0].id;
      if (!providers.length) throw new Error("OAuth 未启用");
    } catch {
      provider.replaceChildren(new Option("OAuth 未启用，请使用账号密码", ""));
      switchMode("password");
    }
  }
  async function startSso() {
    if (portalSso) {
      if (window.parent === window || !portalParentOrigin) throw new Error("请从内网父平台打开领取页面。");
      window.parent.postMessage({ type: "contextforge-portal-cookie-required", purpose: "key" }, portalParentOrigin);
      message.textContent = "领取凭据已过期，请刷新父页面。";
      return;
    }
    if (hasSession) {
      message.textContent = "登录已过期，请重新登录系统后打开领取页面。";
      return;
    }
    if (!provider.value) {
      message.textContent = "请选择 OAuth 服务。";
      return;
    }
    const callback = `${window.location.origin}${form.dataset.root}/auth/sso/callback/${encodeURIComponent(provider.value)}`;
    const response = await fetch(`${form.dataset.root}/auth/sso/login/${encodeURIComponent(provider.value)}?redirect_uri=${encodeURIComponent(callback)}&flow=member_key`, { credentials: "same-origin" });
    if (!response.ok) throw new Error("OAuth 授权启动失败，请稍后重试。");
    const data = await response.json();
    window.location.assign(data.authorization_url);
  }
  ssoMode.addEventListener("click", () => switchMode("sso"));
  passwordMode.addEventListener("click", () => switchMode("password"));
  email.addEventListener("input", invalidateAccount);
  password.addEventListener("input", invalidateAccount);
  team.addEventListener("change", updateServers);
  server.addEventListener("change", () => {
    issue.disabled = !server.value;
    clearResult();
  });
  load.addEventListener("click", async () => {
    if (mode === "password" && (!email.reportValidity() || !password.reportValidity())) return;
    const current = ++version;
    account = "";
    load.disabled = true;
    issue.disabled = true;
    clearResult();
    message.textContent = "正在查询…";
    try {
      const requested = email.value.trim();
      const data = mode === "sso" ? await post("sso/options", {}) : await post("options", {
        email: requested,
        password: password.value,
      });
      if (current !== version) return;
      account = data.email || requested;
      servers = data.servers;
      team.replaceChildren(new Option("请选择空间", ""));
      data.teams.forEach((t) => team.add(new Option(t.name + (t.is_personal ? " · 个人空间" : ""), t.id)));
      if (servers.some((s) => s.public_access)) team.add(new Option("公开 MCP（不绑定 Team）", publicChoice));
      team.disabled = team.options.length === 1;
      updateServers();
      message.textContent = team.disabled
        ? "该账号没有可领取的虚拟 MCP。"
        : `已检测 ${data.full_name || account}，请选择空间和虚拟 MCP。`;
    } catch (error) {
      if (current === version && mode === "sso" && error.message === "AUTH_REQUIRED") {
        try {
          await startSso();
        } catch (ssoError) {
          message.textContent = ssoError.message;
        }
      } else if (current === version) {
        message.textContent = error.message;
      }
    } finally {
      load.disabled = false;
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!account || (mode === "password" && account !== email.value.trim())) return;
    issue.disabled = true;
    clearResult();
    message.textContent = "正在生成…";
    const current = version;
    const controls = [
      email,
      password,
      team,
      server,
      load,
      ssoMode,
      passwordMode,
      document.getElementById("member-days"),
    ];
    controls.forEach((control) => {
      control.disabled = true;
    });
    try {
      const data = await post(mode === "sso" ? "sso/issue" : "issue", {
        ...(mode === "password" ? { email: account, password: password.value } : {}),
        team_id: team.value === publicChoice ? null : team.value,
        server_id: server.value,
        days: Number(document.getElementById("member-days").value),
      });
      if (current !== version) return;
      if (data.api_key) {
        value.value = data.api_key;
        issuedServer = { id: data.server_id, name: data.server_name || data.server_id };
        renderConfig();
        result.classList.remove("hidden");
      }
      if (data.renewed) {
        if (data.limit_reached) {
          message.textContent = `已达到从首次创建日起累计 365 天的上限，到期时间为 ${new Date(data.expires_at).toLocaleString()}，请继续使用原 Key。`;
        } else {
          message.textContent = data.expires_at
            ? `原 API Key 已续期至 ${new Date(data.expires_at).toLocaleString()}，请继续使用原 Key，无需修改客户端。`
            : "原 API Key 长期有效，请继续使用原 Key，无需修改客户端。";
        }
        message.textContent += data.api_key
          ? "原 Key 和客户端配置已显示在下方，可重新复制保存。"
          : `原 Key 无法展示：${data.key_message || "未保存可恢复的原文"}。如已丢失，请联系管理员处理。`;
        return;
      }
      message.textContent = `已生成可保存的 API Key；到期时间：${new Date(data.expires_at).toLocaleString()}。请复制下方 Key 和配置 JSON，原有 Key 不受影响。`;
    } catch (error) {
      if (mode === "sso" && error.message === "AUTH_REQUIRED") {
        try {
          await startSso();
        } catch (ssoError) {
          message.textContent = ssoError.message;
        }
      } else {
        message.textContent = error.message;
      }
    } finally {
      controls.forEach((control) => {
        control.disabled = false;
      });
      issue.disabled = !server.value;
    }
  });
  document
    .getElementById("copy-member-key")
    .addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(value.value);
        message.textContent = "已复制 API Key。";
      } catch {
        value.select();
        message.textContent = "请按 Ctrl+C 复制。";
      }
    });
  document
    .getElementById("copy-member-config")
    .addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(configValue.value);
        message.textContent = "已复制 MCP 配置 JSON。";
      } catch {
        configValue.select();
        message.textContent = "请按 Ctrl+C 复制。";
      }
    });
  window.addEventListener("pagehide", clearResult);
  loadProviders().then(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") === "unregistered") {
      message.textContent = "该用户未在系统中注册，请联系管理员处理。";
    } else if (params.has("error")) {
      message.textContent = "授权失败，请重试。";
    } else if ((hasSession || params.get("sso") === "success" || params.get("portal") === "success") && mode === "sso") {
      load.click();
    }
  });
})();
