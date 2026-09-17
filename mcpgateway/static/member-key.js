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
  let servers = [];
  let account = "";
  let version = 0;
  const clearResult = () => {
    value.value = "";
    result.classList.add("hidden");
  };
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
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(body),
    });
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
      .filter((s) => s.eligible_team_ids.includes(team.value))
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
  email.addEventListener("input", invalidateAccount);
  password.addEventListener("input", invalidateAccount);
  team.addEventListener("change", updateServers);
  server.addEventListener("change", () => {
    issue.disabled = !server.value;
    clearResult();
  });
  load.addEventListener("click", async () => {
    if (!email.reportValidity() || !password.reportValidity()) return;
    const current = ++version;
    load.disabled = true;
    issue.disabled = true;
    clearResult();
    message.textContent = "正在查询…";
    try {
      const requested = email.value.trim();
      const data = await post("options", {
        email: requested,
        password: password.value,
      });
      if (current !== version) return;
      account = requested;
      servers = data.servers;
      team.replaceChildren(new Option("请选择 Team", ""));
      data.teams.forEach((t) => team.add(new Option(t.name, t.id)));
      team.disabled = !data.teams.length;
      updateServers();
      message.textContent = data.teams.length
        ? "请选择 Team 和虚拟 MCP。"
        : "该账号没有有效 Team 成员关系。";
    } catch (error) {
      if (current === version) message.textContent = error.message;
    } finally {
      load.disabled = false;
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!account || account !== email.value.trim()) return;
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
      document.getElementById("member-days"),
    ];
    controls.forEach((control) => {
      control.disabled = true;
    });
    try {
      const data = await post("issue", {
        email: account,
        password: password.value,
        team_id: team.value,
        server_id: server.value,
        days: Number(document.getElementById("member-days").value),
      });
      if (current !== version) return;
      if (data.renewed) {
        message.textContent = data.expires_at
          ? `原 API Key 已续期至 ${new Date(data.expires_at).toLocaleString()}，请继续使用原 Key，无需修改客户端。`
          : "原 API Key 长期有效，请继续使用原 Key，无需修改客户端。";
        return;
      }
      value.value = data.api_key;
      result.classList.remove("hidden");
      message.textContent = `已生成；到期时间：${new Date(data.expires_at).toLocaleString()}`;
    } catch (error) {
      message.textContent = error.message;
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
  window.addEventListener("pagehide", clearResult);
})();
