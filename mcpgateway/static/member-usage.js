/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
(() => {
  const el = (id) => document.getElementById(id);
  const base = `${el("member-panel").dataset.root}/admin/member-usage`;
  let generated = [];
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
    const init = { credentials: "same-origin", headers };
    if (body) {
      init.method = "POST";
      init.body = body instanceof FormData ? body : JSON.stringify(body);
      if (!(body instanceof FormData)) {
        headers["Content-Type"] = "application/json";
      }
    }
    const response = await fetch(base + path, init);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(
        typeof data.detail === "string" ? data.detail : "请求失败"
      );
    }
    return response.json();
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
        ["最近使用 UTC", "last_used"],
      ]);
      table("method-table", data.methods, [
        ["MCP 方法", "method"],
        ["工具 / 资源", "resource"],
        ...metrics,
      ]);
      table("token-table", data.tokens, [
        ["成员", "email"],
        ["Key 名称", "name"],
        ["虚拟 MCP", "server"],
        ["状态", "status"],
        ["到期时间 UTC", "expires_at"],
        ...metrics,
        ["最近使用 UTC", "last_used"],
      ]);
      table("recent-table", data.recent, [
        ["时间 UTC", "timestamp"],
        ["成员", "email"],
        ["Key", "token_name"],
        ["虚拟 MCP", "server"],
        ["MCP 方法", "method"],
        ["工具 / 资源", "resource"],
        ["HTTP", "http_status"],
        ["MCP 结果", "outcome"],
        ["延时 ms", "latency_ms"],
      ]);
      el("usage-trend").replaceChildren();
      const max = Math.max(1, ...data.trend.map((d) => d.calls));
      data.trend.forEach((day) => {
        const group = document.createElement("div");
        const column = document.createElement("div");
        const bar = document.createElement("div");
        const label = document.createElement("span");
        group.className = "trend-day";
        column.className = "trend-column";
        bar.className = "trend-bar";
        bar.style.height = `${(day.calls / max) * 100}%`;
        label.textContent = `${day.date.slice(5)} · ${day.calls}`;
        column.append(bar);
        group.append(column, label);
        el("usage-trend").append(group);
      });
      if (!data.trend.length) el("usage-trend").textContent = "暂无调用数据";
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
      el("panel-status").textContent = error.message;
    } finally {
      el("refresh-usage").disabled = false;
    }
  }
  async function manage(button, work) {
    button.disabled = true;
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
      el("management-status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }
  el("import-members").addEventListener("click", (event) =>
    manage(event.target, async () => {
      const id = el("filter-server").value;
      const file = el("members-file").files[0];
      if (!id || !file) throw new Error("请选择一个虚拟 MCP 和 Excel 文件");
      const data = new FormData();
      data.append("file", file);
      return request(`/import/${encodeURIComponent(id)}`, data);
    })
  );
  ["bulk-selected", "bulk-all"].forEach((id) =>
    el(id).addEventListener("click", (event) =>
      manage(event.target, async () => {
        const server = id === "bulk-all" ? null : el("filter-server").value;
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
  request("/servers")
    .then((data) => {
      data.servers.forEach((s) =>
        el("filter-server").add(
          new Option(`${s.name} · ${s.team_name || "未关联 Team"}`, s.id)
        )
      );
      const selected = new URLSearchParams(location.search).get("server_id");
      if (selected) el("filter-server").value = selected;
      return refresh();
    })
    .catch((error) => {
      el("panel-status").textContent = error.message;
    });
})();
