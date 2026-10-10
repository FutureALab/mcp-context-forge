/* Copyright contributors to the MCP-CONTEXT-FORGE project. SPDX-License-Identifier: Apache-2.0 */
(() => {
  const format = (value) =>
    value == null
      ? "—"
      : typeof value === "number"
        ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
        : String(value);
  const outcomes = {
    success: "成功",
    error: "错误",
    timeout: "超时",
    unknown: "未采集",
  };
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text != null) element.textContent = format(text);
    if (className) element.className = className;
    return element;
  };
  const dateTime = (value) => {
    if (!value) return "未检测";
    const date = new Date(
      /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
    );
    return Number.isNaN(date.getTime())
      ? "—"
      : date.toLocaleString("zh-CN", { hour12: false });
  };
  const states = new Map();
  document.querySelectorAll(".mcp-usage").forEach((panel) => {
    const get = (selector) => panel.querySelector(selector);
    const state = { offset: 0, total: 0, version: 0, chart: null };
    states.set(panel.dataset.view, { refresh });
    async function request(path) {
      const token = await window.Admin?.getAuthToken?.();
      const response = await fetch(
        `${panel.dataset.root}/admin/mcp-usage/${path}`,
        {
          credentials: "same-origin",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: AbortSignal.timeout(15000),
        }
      );
      if (
        response.status === 401 ||
        (response.redirected && response.url.includes("/admin/login"))
      ) {
        throw new Error("登录已过期，请重新登录。");
      }
      if (!response.ok) {
        throw new Error(
          response.status === 403
            ? "需要未限定团队的平台管理员会话和统计读取权限。"
            : "统计加载失败，请重试。"
        );
      }
      return response.json();
    }
    function ranking(container, rows) {
      container.replaceChildren();
      if (!rows.length) {
        container.append(node("p", "暂无调用记录", "mcp-empty"));
        return;
      }
      const max = Math.max(...rows.map((row) => row.calls), 1);
      rows.forEach((row) => {
        const item = node("div", null, "mcp-rank");
        const label = node("div", null, "mcp-rank-label");
        const name = node("span", row.name);
        name.title = row.name;
        label.append(name, node("span", row.calls));
        const track = node("div", null, "mcp-track");
        const bar = node("div");
        bar.style.width = `${(row.calls / max) * 100}%`;
        track.append(bar);
        item.append(label, track);
        container.append(item);
      });
    }
    function cards(rows) {
      get("[data-cards]").replaceChildren(
        ...rows.map(([label, value, detail]) => {
          const card = node("div", null, "mcp-card");
          card.append(
            node("span", label),
            node("strong", format(value)),
            node("p", detail)
          );
          return card;
        })
      );
    }
    function draw(data, days) {
      state.chart?.destroy();
      const canvas = get("canvas");
      get("[data-period]").textContent = `过去 ${days} 天`;
      get("[data-trend-empty]").textContent = data.summary.calls
        ? ""
        : "所选时段暂无工具调用";
      if (!window.Chart) throw new Error("图表组件加载失败，请刷新页面。");
      const muted = getComputedStyle(panel).getPropertyValue("--mcp-muted");
      state.chart = new window.Chart(canvas, {
        type: "bar",
        data: {
          labels: data.trend.map((row) => row.date.slice(5)),
          datasets: [
            {
              label: "成功",
              data: data.trend.map((row) => row.successes),
              backgroundColor: "#002fa7",
              borderRadius: 3,
              maxBarThickness: 48,
            },
            {
              label: "错误 / 超时",
              data: data.trend.map((row) => row.errors),
              backgroundColor: "#be123c",
              borderRadius: 3,
              maxBarThickness: 48,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { display: false } },
          scales: {
            x: {
              stacked: true,
              grid: { display: false },
              ticks: { color: muted },
            },
            y: {
              stacked: true,
              beginAtZero: true,
              ticks: { precision: 0, color: muted },
              grid: { color: "#e5e7eb" },
            },
          },
        },
      });
    }
    function dashboard(data, daily) {
      const enabled = data.connectors.filter((row) => row.enabled);
      const healthy = enabled.filter(
        (row) => row.reachable && row.last_seen
      ).length;
      cards([
        [
          "启用连接器",
          enabled.length,
          `${healthy} 个健康 · ${enabled.length - healthy} 个异常或未检测`,
        ],
        [
          "MCP 工具",
          data.tool_count,
          `来自 ${data.connectors.length} 个连接器`,
        ],
        ["调用次数 · 24 小时", daily.summary.calls, "过去 24 小时的工具调用"],
        [
          "错误数 · 24 小时",
          daily.summary.errors,
          `${daily.summary.calls ? ((daily.summary.errors / daily.summary.calls) * 100).toFixed(2) : "0.00"}% 错误率`,
        ],
      ]);
      const summary = get("[data-summary]");
      summary.replaceChildren(
        node("h3", `${get('[data-filter="days"]').value} 天概览`),
        node(
          "p",
          `成功率 ${format(data.summary.success_rate)}${data.summary.success_rate == null ? "" : "%"}`
        )
      );
      const track = node("div", null, "mcp-track");
      const progress = node("div", null, "mcp-success");
      progress.style.width = `${data.summary.success_rate || 0}%`;
      track.append(progress);
      summary.append(track);
      const numbers = node("div", null, "mcp-summary-numbers");
      [
        ["平均响应", `${format(data.summary.avg_ms)} ms`],
        ["总调用次数", data.summary.calls],
      ].forEach(([label, value]) => {
        const item = node("div");
        item.append(node("span", label), node("strong", value));
        numbers.append(item);
      });
      summary.append(numbers, node("h3", "热门工具"));
      const tools = node("div");
      ranking(tools, data.rankings.tool.slice(0, 5));
      summary.append(tools);
      const health = get("[data-health]");
      health.replaceChildren();
      if (!data.connectors.length) health.append(node("p", "暂无连接器"));
      data.connectors.forEach((row) => {
        const item = node("div", null, "mcp-health-row");
        const name = node("span");
        const outcome =
          !row.enabled || !row.last_seen
            ? "unknown"
            : row.reachable
              ? "success"
              : "error";
        name.append(
          node("i", null, `mcp-dot ${outcome}`),
          document.createTextNode(row.name)
        );
        item.append(
          name,
          node(
            "span",
            `${!row.enabled ? "已停用" : outcome === "unknown" ? "未检测" : outcome === "success" ? "健康" : "异常"} · ${dateTime(row.last_seen)}`
          )
        );
        health.append(item);
      });
    }
    function audit(data) {
      const container = get("[data-audit]");
      container.replaceChildren();
      state.total = data.total;
      get("[data-page-label]").textContent = data.total
        ? `${state.offset + 1}–${Math.min(state.offset + 20, data.total)} / 共 ${data.total} 条`
        : "共 0 条";
      if (!data.records.length) {
        container.append(node("p", "所选条件下暂无调用记录", "mcp-empty"));
        return;
      }
      const table = node("table");
      const head = table.createTHead().insertRow();
      [
        "时间",
        "工具",
        "连接器",
        "MCP 服务器",
        "状态 / HTTP",
        "耗时",
        "详情",
      ].forEach((label) => {
        const th = node("th", label);
        th.scope = "col";
        head.append(th);
      });
      const body = table.createTBody();
      data.records.forEach((record) => {
        const row = body.insertRow();
        [
          dateTime(record.timestamp),
          record.tool || "未采集",
          record.gateway || "未关联",
          record.server || "未关联",
          `${outcomes[record.outcome]} / ${format(record.http_status)}`,
          `${format(record.latency_ms)} ms`,
        ].forEach((value, index) => {
          const cell = row.insertCell();
          cell.textContent = value;
          if (index === 4) cell.className = `mcp-outcome ${record.outcome}`;
        });
        const button = node("button", "展开");
        button.type = "button";
        button.setAttribute("aria-expanded", "false");
        row.insertCell().append(button);
        const detailRow = body.insertRow();
        detailRow.hidden = true;
        detailRow.id = `${panel.dataset.view}-detail-${record.id}`;
        button.setAttribute("aria-controls", detailRow.id);
        const detailCell = detailRow.insertCell();
        detailCell.colSpan = 7;
        detailCell.append(
          node(
            "p",
            `用户：${record.email} · 认证：API Key · Key：${record.token_name || "已删除"} · 服务器：${record.server || "未关联"}`
          )
        );
        const payload = node("div", null, "mcp-details");
        [
          ["输入参数", record.input],
          ["输出", record.output],
        ].forEach(([title, value]) => {
          const column = node("div");
          let content =
            value ||
            "未采集。开启 MCP_AUDIT_PAYLOADS_ENABLED 后，新调用保存脱敏详情。";
          if (value) {
            try {
              content = JSON.stringify(JSON.parse(value), null, 2);
            } catch {
              content = value;
            }
          }
          column.append(node("h3", title), node("pre", content));
          payload.append(column);
        });
        detailCell.append(payload);
        if (record.capture_truncated) {
          detailCell.append(node("p", "采集达到大小上限，内容可能不完整。"));
        }
        button.addEventListener("click", () => {
          detailRow.hidden = !detailRow.hidden;
          button.textContent = detailRow.hidden ? "展开" : "收起";
          button.setAttribute("aria-expanded", String(!detailRow.hidden));
        });
      });
      container.append(table);
    }
    async function refresh(reset = true) {
      if (reset) state.offset = 0;
      const version = ++state.version;
      const status = get(".mcp-status");
      const button = get("[data-refresh]");
      button.disabled = true;
      if (get("[data-previous]")) {
        get("[data-previous]").disabled = true;
        get("[data-next]").disabled = true;
      }
      status.textContent = "正在加载…";
      status.dataset.error = "false";
      const days = get('[data-filter="days"]').value;
      try {
        let data;
        if (panel.dataset.view === "mcp-audit") {
          const params = new URLSearchParams({
            days,
            offset: state.offset,
            limit: 20,
          });
          panel.querySelectorAll("[data-filter]").forEach((filter) => {
            if (filter.value) {
              params.set(filter.dataset.filter, filter.value.trim());
            }
          });
          const [overview, records] = await Promise.all([
            request(`overview?days=${days}`),
            request(`audit?${params}`),
          ]);
          if (version !== state.version) return;
          data = overview;
          [
            ["gateway_id", overview.connectors],
            ["server_id", overview.servers],
          ].forEach(([key, rows]) => {
            const select = get(`[data-filter="${key}"]`);
            const selected = select.value;
            select.replaceChildren(
              new Option(
                key === "gateway_id" ? "所有连接器" : "所有 MCP 服务器",
                ""
              ),
              ...rows.map((row) => new Option(row.name, row.id))
            );
            select.value = selected;
          });
          audit(records);
        } else {
          const [overview, daily] = await Promise.all([
            request(`overview?days=${days}`),
            panel.dataset.view === "mcp-dashboard"
              ? request("overview?days=1")
              : Promise.resolve(null),
          ]);
          if (version !== state.version) return;
          data = overview;
          if (daily) dashboard(data, daily);
          else {
            cards([
              [`工具调用 · ${days} 天`, data.summary.calls, "tools/call"],
              [
                "成功率",
                data.summary.success_rate == null
                  ? "—"
                  : `${format(data.summary.success_rate)}%`,
                `${data.summary.errors} 次错误 / 超时`,
              ],
              [
                "平均响应",
                data.summary.avg_ms == null
                  ? "—"
                  : `${format(data.summary.avg_ms)} ms`,
                "HTTP 请求完成耗时",
              ],
              ["调用用户", data.summary.users, "所选时段的调用用户"],
            ]);
            panel
              .querySelectorAll("[data-ranking]")
              .forEach((container) =>
                ranking(container, data.rankings[container.dataset.ranking])
              );
          }
          draw(data, days);
        }
        get("[data-coverage]").textContent =
          `${data.coverage.scope}。趋势按 UTC 自然日统计，列表时间按浏览器时区显示。${data.coverage.logging_enabled ? "" : "调用日志采集已关闭。"}${data.coverage.payloads_enabled ? "输入输出已启用脱敏采集，单向最多 16,384 字符。" : "输入输出采集未开启；历史缺失内容无法恢复。"}`;
        status.textContent = `已更新 · ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
      } catch (error) {
        if (version !== state.version) return;
        status.dataset.error = "true";
        status.textContent =
          error.name === "TimeoutError" ? "加载超时，请重试。" : error.message;
        if (get("[data-audit]")) {
          get("[data-audit]").replaceChildren();
          state.total = 0;
          get("[data-page-label]").textContent = "加载失败";
        } else {
          state.chart?.destroy();
          state.chart = null;
          get("[data-cards]").replaceChildren();
          panel
            .querySelectorAll("[data-ranking], [data-summary], [data-health]")
            .forEach((container) => container.replaceChildren());
        }
      } finally {
        if (version === state.version) {
          button.disabled = false;
          if (get("[data-previous]")) {
            get("[data-previous]").disabled = state.offset === 0;
            get("[data-next]").disabled = state.offset + 20 >= state.total;
          }
        }
      }
    }
    get("[data-refresh]").addEventListener("click", () => refresh());
    get('[data-filter="days"]').addEventListener("change", () => refresh());
    get("form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      refresh();
    });
    ["status", "gateway_id", "server_id"].forEach((key) =>
      get(`[data-filter="${key}"]`)?.addEventListener("change", () => refresh())
    );
    get("[data-previous]")?.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - 20);
      refresh(false);
    });
    get("[data-next]")?.addEventListener("click", () => {
      state.offset += 20;
      refresh(false);
    });
  });
  document.addEventListener("mcp-usage:open", (event) =>
    states.get(event.detail)?.refresh()
  );
})();
