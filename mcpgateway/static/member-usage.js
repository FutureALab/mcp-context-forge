/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
(() => {
  const el = (id) => document.getElementById(id);
  const base = `${el("member-panel").dataset.root}/admin/member-usage`;
  let generated = [];
  let serverOptions = [];
  let charts = [];
  let busy = false;
  let initialized = false;
  let sessionExpired = false;
  let selectedServer = "";
  const dialog = el("server-members-dialog");
  const dateTime = (value) => {
    if (!value) return "—";
    const date = new Date(
      /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
    );
    if (Number.isNaN(date.getTime())) return "—";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
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
  const fmt = (value) =>
    value == null
      ? "未提供"
      : typeof value === "number"
        ? value.toLocaleString()
        : String(value);
  async function request(path, body) {
    const headers = { "X-CSRF-Token": csrf() };
    const token = await window.Admin?.getAuthToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const init = { credentials: "same-origin", headers };
    if (!body) init.signal = AbortSignal.timeout(15000);
    if (body) {
      init.method = "POST";
      init.body = body instanceof FormData ? body : JSON.stringify(body);
      if (!(body instanceof FormData)) {
        headers["Content-Type"] = "application/json";
      }
    }
    const response = await fetch(base + path, init);
    if (
      response.status === 401 ||
      (response.redirected && response.url.includes("/admin/login"))
    ) {
      sessionExpired = true;
      const error = new Error("登录已过期，请重新登录后加载虚拟 MCP。");
      error.authExpired = true;
      throw error;
    }
    if (!response.ok) {
      const data = await response.json();
      throw new Error(
        typeof data.detail === "string" ? data.detail : "请求失败"
      );
    }
    return response.json();
  }
  function showFailure(id, error) {
    const status = el(id);
    status.textContent = ["TimeoutError", "AbortError"].includes(error.name)
      ? "请求超时，请检查服务后重试。"
      : error.message;
    if (error.authExpired) {
      const link = document.createElement("a");
      link.href = `${dialog.dataset.root}/admin/login`;
      link.textContent = "重新登录";
      status.append(" ", link);
    }
  }
  function table(id, rows, columns) {
    const container = el(id);
    container.replaceChildren();
    if (!rows.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "暂无记录";
      container.append(p);
      return;
    }
    const t = document.createElement("table");
    const head = t.createTHead().insertRow();
    const body = t.createTBody();
    columns.forEach(([label]) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      head.append(th);
    });
    rows.forEach((row) => {
      const tr = body.insertRow();
      columns.forEach(([, field]) => {
        tr.insertCell().textContent = fmt(
          typeof field === "function" ? field(row) : row[field]
        );
      });
    });
    container.append(t);
  }
  const metrics = [
    ["次数", "calls"],
    ["错误", "errors"],
    ["拦截", "blocked"],
    ["成功率 %", "success_rate"],
    ["平均延时 ms", "avg_ms"],
    ["P95 ms", "p95_ms"],
    ["输入 Tokens", "input_tokens"],
    ["输出 Tokens", "output_tokens"],
    ["用量覆盖次数", "usage_reported_calls"],
  ];
  async function refresh() {
    el("refresh-usage").disabled = true;
    el("panel-status").textContent = "正在加载统计…";
    try {
      const params = new URLSearchParams({ days: el("filter-days").value });
      [
        ["server_id", "server"],
        ["email", "email"],
        ["token_id", "token"],
        ["method", "method"],
      ].forEach(([key, id]) => {
        const v = el(`filter-${id}`).value.trim();
        if (v) params.set(key, v);
      });
      const data = await request(`/data?${params}`);
      const s = data.summary;
      el("usage-cards").replaceChildren();
      [
        ["请求次数", s.calls],
        ["成功率 %", s.success_rate],
        ["平均延时 ms", s.avg_ms],
        ["P95 延时 ms", s.p95_ms],
        ["输入 Tokens", s.input_tokens],
        ["输出 Tokens", s.output_tokens],
      ].forEach(([label, value]) => {
        const card = document.createElement("div");
        const title = document.createElement("span");
        const number = document.createElement("strong");
        card.className = "card";
        title.textContent = label;
        number.textContent = fmt(value);
        card.append(title, number);
        el("usage-cards").append(card);
      });
      el("coverage-note").textContent =
        `${data.coverage.latency}。${data.coverage.model_usage}。${s.usage_reported_calls} 次请求提供模型用量。${data.coverage.truncated ? `仅统计最近 ${data.coverage.included_requests} 条，共匹配 ${data.coverage.matching_requests} 条，请缩小时间范围。` : ""}${data.coverage.logging_enabled ? "" : "调用日志采集当前已关闭。"}`;
      table("member-table", data.members, [
        ["成员", "email"],
        ["姓名", "name"],
        ["Key 数", "token_count"],
        ["有效 Key", "active_tokens"],
        ...metrics,
        ["最近使用", (r) => dateTime(r.last_used)],
      ]);
      table("method-table", data.methods, [
        ["MCP 方法", (r) => r.method || "历史记录未采集"],
        ["工具 / 资源", "resource"],
        ...metrics,
      ]);
      table("token-table", data.tokens, [
        ["成员", "email"],
        ["Key 名称", "name"],
        ["虚拟 MCP", "server"],
        ["状态", "status"],
        ["到期时间", (r) => dateTime(r.expires_at)],
        ...metrics,
        ["最近使用", (r) => dateTime(r.last_used)],
      ]);
      table("recent-table", data.recent, [
        ["调用时间", (r) => dateTime(r.timestamp)],
        ["成员", "email"],
        ["Key", "token_name"],
        ["虚拟 MCP", "server"],
        ["MCP 方法", (r) => r.method || "历史记录未采集"],
        ["工具 / 资源", "resource"],
        ["HTTP", "http_status"],
        ["MCP 结果", "outcome"],
        ["延时 ms", "latency_ms"],
      ]);
      charts.forEach((chart) => chart.destroy());
      charts = [];
      const dark = document.documentElement.classList.contains("dark");
      const color = dark ? "#d1d5db" : "#4b5563";
      const grid = dark ? "#374151" : "#e5e7eb";
      const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color } } },
        scales: {
          x: { ticks: { color }, grid: { color: grid } },
          y: {
            beginAtZero: true,
            ticks: { color, precision: 0 },
            grid: { color: grid },
          },
        },
      };
      if (window.Chart) {
        charts.push(
          new window.Chart(el("usage-trend"), {
            type: "line",
            data: {
              labels: data.trend.map((d) => d.date.slice(5)),
              datasets: [
                {
                  label: "调用次数",
                  data: data.trend.map((d) => d.calls),
                  borderColor: "#6366f1",
                  backgroundColor: "#6366f120",
                  fill: true,
                  tension: 0.2,
                },
                {
                  label: "错误次数",
                  data: data.trend.map((d) => d.errors),
                  borderColor: "#ef4444",
                  tension: 0.2,
                },
              ],
            },
            options,
          })
        );
        const ranked = [...data.methods]
          .sort((a, b) => b.calls - a.calls)
          .slice(0, 10);
        charts.push(
          new window.Chart(el("usage-method-chart"), {
            type: "bar",
            data: {
              labels: ranked.map((m) =>
                m.resource ? `${m.method} · ${m.resource}` : m.method
              ),
              datasets: [
                {
                  label: "调用次数",
                  data: ranked.map((m) => m.calls),
                  backgroundColor: "#6366f1",
                  borderRadius: 4,
                },
              ],
            },
            options: {
              ...options,
              indexAxis: "y",
              scales: {
                ...options.scales,
                x: {
                  ...options.scales.x,
                  beginAtZero: true,
                  ticks: { color, precision: 0 },
                },
              },
            },
          })
        );
      }
      el("trend-empty").textContent = data.trend.length
        ? ""
        : "当前筛选条件下暂无调用数据";
      el("methods-empty").textContent = data.methods.length
        ? ""
        : "当前筛选条件下暂无方法数据";
      el("usage-timezone").textContent =
        `表格时间：${Intl.DateTimeFormat().resolvedOptions().timeZone} · YYYY-MM-dd HH:mm:ss；历史未采集的方法无法回填。`;
      const selected = el("filter-token").value;
      if (!selected) {
        el("filter-token").replaceChildren(new Option("全部 Key", ""));
        data.tokens.forEach((t) =>
          el("filter-token").add(new Option(`${t.email} · ${t.name}`, t.id))
        );
      }
      el("panel-status").textContent =
        `已更新，共 ${data.coverage.matching_requests} 条匹配请求。`;
    } catch (error) {
      showFailure("panel-status", error);
    } finally {
      el("refresh-usage").disabled = false;
    }
  }
  async function manage(work) {
    if (busy) return;
    busy = true;
    [
      "import-members",
      "bulk-selected",
      "bulk-all",
      "management-server",
      "close-server-members",
    ].forEach((id) => {
      el(id).disabled = true;
    });
    el("management-status").textContent = "正在处理…";
    try {
      const data = await work();
      table("management-results", data.results, [
        ["行号", "row"],
        ["成员", "email"],
        ["服务器", "server_id"],
        ["状态", "status"],
        ["说明", "message"],
      ]);
      el("management-status").textContent =
        `处理完成：${data.results.length} 条；失败 ${data.results.filter((r) => r.status === "failed").length} 条。`;
    } catch (error) {
      showFailure("management-status", error);
    } finally {
      busy = false;
      [
        "import-members",
        "bulk-selected",
        "bulk-all",
        "management-server",
        "close-server-members",
      ].forEach((id) => {
        el(id).disabled = false;
      });
      updateManagement();
    }
  }
  el("import-members").addEventListener("click", () =>
    manage(async () => {
      const id = el("management-server").value;
      const file = el("members-file").files[0];
      if (!id || !file) throw new Error("请选择一个虚拟 MCP 和 Excel 文件");
      const data = new FormData();
      data.append("file", file);
      return request(`/import/${encodeURIComponent(id)}`, data);
    })
  );
  ["bulk-selected", "bulk-all"].forEach((id) =>
    el(id).addEventListener("click", () =>
      manage(async () => {
        const server = id === "bulk-all" ? null : el("management-server").value;
        if (id === "bulk-selected" && !server) {
          throw new Error("请先选择一个虚拟 MCP");
        }
        const data = await request("/keys", {
          server_id: server,
          days: Number(el("bulk-days").value),
        });
        generated.push(...data.results);
        el("download-keys").disabled = !generated.some(
          (r) => r.status === "created"
        );
        return data;
      })
    )
  );
  el("download-keys").addEventListener("click", () => {
    const blob = new Blob(
      [
        JSON.stringify(
          { generated_at: new Date().toISOString(), results: generated },
          null,
          2
        ),
      ],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "mcp-member-keys.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  el("refresh-usage").addEventListener("click", refresh);
  el("filter-server").addEventListener("change", () => {
    el("filter-token").value = "";
  });
  window.addEventListener("pagehide", () => {
    generated = [];
  });
  function updateManagement() {
    const server = serverOptions.find(
      (s) => s.id === el("management-server").value
    );
    el("management-team").textContent = server
      ? `Team：${server.team_name || "未关联"}${server.enabled ? "" : " · 服务器已停用"}`
      : "请先选择虚拟 MCP";
    el("selected-server-description").textContent = server
      ? `当前操作对象：${server.name}`
      : "选择虚拟 MCP，导入成员或生成独立 Key。";
    el("import-members").disabled =
      sessionExpired || !server?.team_id || !server?.can_import || !validFile();
    el("bulk-selected").disabled =
      sessionExpired || !server?.team_id || !server?.enabled;
    el("bulk-all").hidden = Boolean(server);
    el("bulk-all").disabled = sessionExpired || !serverOptions.length;
  }
  function validFile() {
    const file = el("members-file").files[0];
    return (
      file &&
      /\.xlsx$/i.test(file.name) &&
      file.size > 0 &&
      file.size <= 5 * 1024 * 1024
    );
  }
  function updateFile() {
    const file = el("members-file").files[0];
    el("members-file-name").textContent = file
      ? file.name
      : "点击选择 Excel 文件";
    el("members-file-info").textContent = file
      ? validFile()
        ? `${(file.size / 1024).toFixed(1)} KB · 已选择，可导入`
        : "请选择不超过 5 MB 的非空 .xlsx 文件"
      : ".xlsx 格式 · 最多 500 行 · 最大 5 MB";
    el("clear-members-file").hidden = !file;
    updateManagement();
  }
  el("members-file").addEventListener("change", updateFile);
  el("clear-members-file").addEventListener("click", () =>
    el("members-file").click()
  );
  el("management-server").addEventListener("change", () => {
    el("management-status").textContent = "";
    el("management-results").replaceChildren();
    updateManagement();
  });
  el("close-server-members").addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => {
    if (busy) event.preventDefault();
  });
  async function loadServers() {
    serverOptions = [];
    el("retry-member-servers").hidden = true;
    el("management-server").replaceChildren(new Option("正在加载…", ""));
    el("management-server").disabled = true;
    el("management-results").replaceChildren();
    updateManagement();
    el("management-status").textContent = "正在加载虚拟 MCP…";
    try {
      const data = await request("/servers");
      sessionExpired = false;
      serverOptions = data.servers;
      el("management-server").replaceChildren(
        new Option(
          serverOptions.length ? "请选择虚拟 MCP" : "暂无可管理的虚拟 MCP",
          ""
        )
      );
      serverOptions.forEach((s) =>
        el("management-server").add(new Option(s.name, s.id))
      );
      el("management-server").value = selectedServer;
      updateManagement();
      el("management-status").textContent = "";
    } catch (error) {
      el("management-server").replaceChildren(
        new Option(error.authExpired ? "登录已过期" : "加载失败，请重试", "")
      );
      showFailure("management-status", error);
      el("retry-member-servers").hidden = Boolean(error.authExpired);
    } finally {
      el("management-server").disabled = !serverOptions.length;
    }
  }
  el("retry-member-servers").addEventListener("click", loadServers);
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-server-members]");
    if (!button) return;
    selectedServer = button.dataset.serverMembers || "";
    el("members-file").value = "";
    updateFile();
    dialog.showModal();
    await loadServers();
  });
  document.addEventListener("member-usage:open", async () => {
    try {
      if (!initialized) {
        const data = await request("/servers");
        data.servers.forEach((s) =>
          el("filter-server").add(
            new Option(`${s.name} · ${s.team_name || "未关联 Team"}`, s.id)
          )
        );
        initialized = true;
      }
      await refresh();
    } catch (error) {
      showFailure("panel-status", error);
    }
  });
})();
