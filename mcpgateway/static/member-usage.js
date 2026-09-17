/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
(() => {
  const el = (id) => document.getElementById(id);
  const base = `${el("member-panel").dataset.root}/admin/member-usage`;
  let generated = [];
  let serverOptions = [];
  let teamOptions = [];
  let charts = [];
  let busy = false;
  let initialized = false;
  let sessionExpired = false;
  let selectedServer = "";
  let historyVersion = 0;
  let historyOffset = 0;
  let historyTotal = 0;
  let historyBusy = false;
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
  async function request(path, body, download = false) {
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
    return download ? response.blob() : response.json();
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
      const s = data.tool_summary || data.summary;
      el("usage-cards").replaceChildren();
      [
        ["工具调用次数", s.calls],
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
      const color = dark ? "#cbd5e1" : "#475569";
      const grid = dark ? "#334155" : "#edf0f4";
      const blue = "#002FA7";
      const baseOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color,
              usePointStyle: true,
              pointStyle: "circle",
              boxWidth: 7,
              boxHeight: 7,
              pointStyleWidth: 7,
              padding: 20,
            },
          },
        },
      };
      const axis = { ticks: { color }, grid: { color: grid } };
      function draw(
        id,
        type,
        labels,
        datasets,
        horizontal = false,
        max = undefined
      ) {
        if (!window.Chart) return;
        charts.push(
          new window.Chart(el(id), {
            type,
            data: { labels, datasets },
            options: {
              ...baseOptions,
              indexAxis: horizontal ? "y" : "x",
              plugins: {
                ...baseOptions.plugins,
                legend: {
                  ...baseOptions.plugins.legend,
                  display: datasets.length > 1 || type === "doughnut",
                },
              },
              ...(type === "doughnut"
                ? { cutout: "72%" }
                : {
                  scales: horizontal
                    ? {
                      x: { ...axis, beginAtZero: true, max },
                      y: {
                        type: "category",
                        ticks: {
                          color,
                          callback(value) {
                            const label = this.getLabelForValue(value);
                            return label.length > 26
                              ? label.slice(0, 24) + "…"
                              : label;
                          },
                        },
                        grid: { display: false },
                      },
                    }
                    : {
                      x: { ...axis, grid: { display: false } },
                      y: {
                        ...axis,
                        beginAtZero: true,
                        ticks: { color, precision: 0 },
                      },
                    },
                }),
            },
          })
        );
      }
      const trend = data.tool_trend || data.trend;
      draw(
        "usage-trend",
        "line",
        trend.map((r) => r.date.replace("T", " ").slice(5, 16)),
        [
          {
            label: "调用次数",
            data: trend.map((r) => r.calls),
            borderColor: blue,
            backgroundColor: "#002FA712",
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            borderWidth: 2,
          },
          {
            label: "错误次数",
            data: trend.map((r) => r.errors),
            borderColor: "#e05260",
            tension: 0.3,
            pointRadius: 2,
            borderWidth: 2,
          },
        ]
      );
      const ranked = data.methods
        .filter((r) => r.method === "tools/call")
        .sort((a, b) => b.calls - a.calls)
        .slice(0, 10);
      draw(
        "usage-method-chart",
        "bar",
        ranked.map((r) => r.resource || "未采集工具名"),
        [
          {
            label: "调用次数",
            data: ranked.map((r) => r.calls),
            backgroundColor: blue,
            borderRadius: 5,
            maxBarThickness: 22,
          },
        ],
        true
      );
      const users = [...(data.tool_members || data.members)]
        .filter((r) => r.calls > 0)
        .sort((a, b) => b.calls - a.calls)
        .slice(0, 10);
      const labels = users.map((r) => r.name || r.email);
      draw(
        "usage-users",
        "bar",
        labels,
        [
          {
            label: "调用次数",
            data: users.map((r) => r.calls),
            backgroundColor: blue,
            borderRadius: 5,
            maxBarThickness: 22,
          },
        ],
        true
      );
      draw(
        "usage-latency",
        "bar",
        labels,
        [
          {
            label: "平均延时",
            data: users.map((r) => r.avg_ms),
            backgroundColor: blue,
            borderRadius: 4,
          },
          {
            label: "P95 延时",
            data: users.map((r) => r.p95_ms),
            backgroundColor: "#9aaff2",
            borderRadius: 4,
          },
        ],
        true
      );
      draw(
        "usage-success",
        "bar",
        labels,
        [
          {
            label: "成功率 %",
            data: users.map((r) => r.success_rate),
            backgroundColor: "#168577",
            borderRadius: 5,
            maxBarThickness: 22,
          },
        ],
        true,
        100
      );
      const states = data.member_states || {
        active: users.length,
        errors: 0,
        idle: 0,
      };
      draw(
        "usage-states",
        "doughnut",
        ["调用正常", "出现错误", "未调用"],
        [
          {
            data: [states.active - states.errors, states.errors, states.idle],
            backgroundColor: [blue, "#e05260", "#dce3ed"],
            borderWidth: 0,
          },
        ]
      );
      el("member-state-cards").replaceChildren();
      [
        ["发生调用的用户", states.active],
        ["出现错误的用户", states.errors],
        ["未调用的用户", states.idle],
      ].forEach(([label, value]) => {
        const item = document.createElement("div");
        item.textContent = `${label}  ${value}`;
        el("member-state-cards").append(item);
      });
      el("trend-empty").textContent = trend.some((r) => r.calls > 0)
        ? ""
        : "当前时段暂无已采集的工具调用";
      el("methods-empty").textContent = ranked.length
        ? ""
        : "当前时段暂无工具调用；初始化和工具发现不计入排行";
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
    historyControls();
    [
      "import-members",
      "bulk-selected",
      "bulk-all",
      "management-server",
      "management-target-team",
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
        "management-target-team",
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
      data.append("team_id", el("management-target-team").value);
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
          team_id: server ? el("management-target-team").value : null,
          days: Number(el("bulk-days").value),
        });
        generated = data.results.map((row) => {
          const previous = generated.find(
            (r) => r.token_id && r.token_id === row.token_id
          );
          return { ...row, api_key: row.api_key || previous?.api_key || "" };
        });
        el("download-keys").disabled = !generated.some((r) =>
          ["created", "renewed"].includes(r.status)
        );
        return data;
      })
    )
  );
  el("download-keys").addEventListener("click", async () => {
    el("download-keys").disabled = true;
    try {
      const blob = await request("/keys/export", { results: generated }, true);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "mcp-member-keys.xlsx";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      showFailure("management-status", error);
    } finally {
      el("download-keys").disabled = false;
    }
  });
  el("refresh-usage").addEventListener("click", refresh);
  el("filter-server").addEventListener("change", () => {
    el("filter-token").value = "";
  });
  window.addEventListener("pagehide", () => {
    generated = [];
    resetHistory();
  });
  function hideHistoryDetail() {
    el("key-history-value").value = "";
    el("key-history-metadata").textContent = "";
    el("key-history-message").textContent = "";
    el("key-history-detail").hidden = true;
  }
  function historyControls() {
    const disabled =
      historyBusy || busy || sessionExpired || !el("management-server").value;
    el("load-key-history").disabled = disabled;
    el("export-key-history").disabled = disabled;
    el("key-history-prev").disabled = disabled || !historyOffset;
    el("key-history-next").disabled =
      disabled || historyOffset + 50 >= historyTotal;
  }
  function resetHistory() {
    historyVersion++;
    historyOffset = historyTotal = 0;
    historyBusy = false;
    hideHistoryDetail();
    el("key-history-table").replaceChildren();
    el("key-history-status").textContent = "";
    el("key-history-page").textContent = "";
    historyControls();
  }
  async function loadHistory(offset = 0) {
    const server = el("management-server").value;
    if (!server || historyBusy || busy) return;
    const version = ++historyVersion;
    historyBusy = true;
    hideHistoryDetail();
    historyControls();
    el("key-history-status").textContent = "正在查询已有 Key…";
    try {
      const data = await request(
        `/key-history/${encodeURIComponent(server)}?offset=${offset}&limit=50`
      );
      if (version !== historyVersion) return;
      historyOffset = data.offset;
      historyTotal = data.total;
      table("key-history-table", data.results, [
        ["成员", "email"],
        ["团队", "team_name"],
        ["名称", "name"],
        ["状态", "status"],
        ["账号", "account_status"],
        ["到期时间", (r) => dateTime(r.expires_at)],
        ["Key 原文", (r) => (r.key_available ? "可查看" : "无法恢复")],
      ]);
      const header = el("key-history-table").querySelector("thead tr");
      if (header) {
        const th = document.createElement("th");
        th.textContent = "操作";
        header.append(th);
        el("key-history-table")
          .querySelectorAll("tbody tr")
          .forEach((tr, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "secondary-button";
            button.textContent = "查看详情 / Key";
            button.addEventListener("click", () =>
              showHistoryDetail(server, data.results[index].token_id)
            );
            tr.insertCell().append(button);
          });
      }
      el("key-history-status").textContent =
        `共 ${data.total} 条已有 Key，包含到期、停用和吊销记录。`;
      el("key-history-page").textContent = data.total
        ? `${offset + 1}–${offset + data.results.length} / ${data.total}`
        : "0 条";
    } catch (error) {
      if (version === historyVersion) showFailure("key-history-status", error);
    } finally {
      if (version === historyVersion) {
        historyBusy = false;
        historyControls();
      }
    }
  }
  async function showHistoryDetail(server, tokenId) {
    if (historyBusy || busy) return;
    const version = ++historyVersion;
    hideHistoryDetail();
    try {
      const row = await request(
        `/key-history/${encodeURIComponent(server)}/${encodeURIComponent(tokenId)}`,
        {}
      );
      if (version !== historyVersion) return;
      const fields = [
        ["成员", row.email],
        ["团队", row.team_name],
        ["名称", row.name],
        ["Key ID", row.token_id],
        ["状态", row.status],
        ["账号", row.account_status],
        ["创建时间", dateTime(row.created_at)],
        ["到期时间", dateTime(row.expires_at)],
        ["最后使用", dateTime(row.last_used)],
        ["权限", row.permissions],
        ["IP 限制", row.ip_restrictions],
        ["时间限制", row.time_restrictions],
        ["使用限制", row.usage_limits],
        ["说明", row.description],
        ["吊销时间", dateTime(row.revoked_at)],
        ["吊销原因", row.revocation_reason],
      ];
      el("key-history-metadata").textContent = fields
        .map(
          ([label, value]) =>
            `${label}：${typeof value === "object" && value !== null ? JSON.stringify(value) : value || "—"}`
        )
        .join("\n");
      el("key-history-value").value = row.api_key || "";
      el("key-history-message").textContent = row.key_message;
      el("copy-history-key").disabled = !row.api_key;
      el("key-history-detail").hidden = false;
    } catch (error) {
      if (version === historyVersion) showFailure("key-history-status", error);
    }
  }
  el("load-key-history").addEventListener("click", () => loadHistory());
  el("key-history-prev").addEventListener("click", () =>
    loadHistory(Math.max(0, historyOffset - 50))
  );
  el("key-history-next").addEventListener("click", () =>
    loadHistory(historyOffset + 50)
  );
  el("close-history-key").addEventListener("click", () => {
    historyVersion++;
    hideHistoryDetail();
  });
  el("copy-history-key").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(el("key-history-value").value);
      el("key-history-message").textContent = "已复制";
    } catch {
      el("key-history-message").textContent = "复制失败，请手动选择复制。";
    }
  });
  el("export-key-history").addEventListener("click", async () => {
    const server = el("management-server").value;
    if (!server || historyBusy) return;
    historyBusy = true;
    historyControls();
    try {
      const blob = await request(
        `/key-history/${encodeURIComponent(server)}/export`,
        {},
        true
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `mcp-${server}-keys.xlsx`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      showFailure("key-history-status", error);
    } finally {
      historyBusy = false;
      historyControls();
    }
  });
  dialog.addEventListener("close", resetHistory);
  function updateManagement() {
    const server = serverOptions.find(
      (s) => s.id === el("management-server").value
    );
    const teamId = el("management-target-team").value;
    el("management-team").textContent = server
      ? `归属：${server.is_personal ? "个人空间" : server.team_name || "未关联团队"} · ${server.visibility === "public" ? "公众可见（仍需调用权限）" : "按服务器可见性授权"}${teamId ? "" : "。请先选择共享团队；如无选项，请先创建团队或调整 MCP 归属。"}`
      : "请先选择虚拟 MCP";
    el("selected-server-description").textContent = server
      ? `当前操作对象：${server.name}`
      : "选择虚拟 MCP，导入成员或生成独立 Key。";
    el("import-members").disabled =
      sessionExpired || !server?.enabled || !teamId || !validFile();
    el("bulk-selected").disabled =
      sessionExpired || !teamId || !server?.enabled;
    el("bulk-all").hidden = Boolean(server);
    el("bulk-all").disabled = sessionExpired || !serverOptions.length;
    historyControls();
  }
  function updateTeams() {
    const server = serverOptions.find(
      (s) => s.id === el("management-server").value
    );
    el("management-target-team").replaceChildren(
      new Option("请选择共享团队", "")
    );
    teamOptions
      .filter(
        (t) =>
          server && (server.visibility === "public" || server.team_id === t.id)
      )
      .forEach((t) => {
        el("management-target-team").add(new Option(t.name, t.id));
      });
    if (server?.can_import) el("management-target-team").value = server.team_id;
    updateManagement();
  }
  el("management-target-team").addEventListener("change", updateManagement);
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
    resetHistory();
    el("management-status").textContent = "";
    el("management-results").replaceChildren();
    updateTeams();
  });
  el("close-server-members").addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => {
    if (busy) event.preventDefault();
  });
  async function loadServers() {
    resetHistory();
    serverOptions = [];
    teamOptions = [];
    el("management-target-team").replaceChildren(
      new Option("请选择共享团队", "")
    );
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
      teamOptions = data.teams || [];
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
      updateTeams();
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
