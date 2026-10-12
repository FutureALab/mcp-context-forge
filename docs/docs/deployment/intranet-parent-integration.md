# 父页面前端对接：自动登录 MCP

父页面只需要调用 **一个接口：`POST /auth/portal/exchange`**。
父平台登录成功后，写入身份 Cookie，调用接口，再把返回地址加载进 iframe，就能触发 MCP 自动登录。
不需要另外调用 `/auth/login`，也不需要父页面收集网关密码。

## 1. 准备什么

- 网关浏览器地址，例如 `http://devops.com:18090`。
- 父平台当前登录用户的用户名、邮箱；邮箱必须对应网关已注册、启用的普通账号。
- 一个 iframe 和一个错误提示区域。

下面按父页面 `http://devops.com`、网关 `http://devops.com:18090` 举例。
两个浏览器地址共用主机名，因此可以共享 Cookie；不同服务器不影响这一点。
如果两个入口使用不同 IP，本例的 Cookie 不能共享，需要先统一访问地址。

## 2. 接口请求和返回值

**地址：`POST http://devops.com:18090/auth/portal/exchange`**

| 请求项 | 内容 |
| --- | --- |
| Content-Type | `application/json` |
| fetch 参数 | `credentials: "include"`，让浏览器携带并接收 Cookie |
| 身份 Cookie | `mcp_username`：当前用户名；`mcp_email`：当前用户邮箱；均使用 `Path=/` |
| Authorization | 不需要 |

请求体：

```json
{"purpose":"login"}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `purpose` | 是 | `login` 自动登录工作区；`key` 打开 API Key 领取页 |
| `token` | 否 | 上次接口返回的 token，可用于复用授权 |

成功返回 HTTP `200`：

```json
{
  "next": "/admin",
  "token": "<父平台授权token>",
  "expires_at": 1900000000
}
```

| 返回字段 | 前端怎么用 |
| --- | --- |
| `next` | 与网关地址拼接，作为 iframe 的 src；key 模式返回 `/admin/api-key` |
| `token` | 可保存，在下次交换请求中传回；不保存也可以再次按 Cookie 交换 |
| `expires_at` | token 的到期时间，单位是 Unix 秒；默认有效期 12 小时 |

网关同时设置自己的登录 Cookie，浏览器自动保存，父页面不需要读取。
**自动登录发生在“交换成功后加载 next”这一步，不是写入身份 Cookie 时。**
`token` 不是 MCP API Key，也不要把它放到 Authorization header 或 iframe URL。

## 3. 最小前端代码

页面放置提示区域和 iframe：

```html
<p id="mcp-error" role="alert"></p>
<iframe id="mcp-frame" title="MCP 页面" hidden
        style="width:100%;height:800px;border:0"></iframe>
```

将以下脚本放在这些元素之后。Vue/React 项目可以把 DOM 操作换成组件状态。

```javascript
const gatewayBase = "http://devops.com:18090"; // 改成实际网关地址。
const frame = document.getElementById("mcp-frame");
const errorText = document.getElementById("mcp-error");

async function openMcp(user, purpose = "login") {
  errorText.textContent = "";
  frame.hidden = true;
  frame.src = "about:blank";
  try {
    if (!user?.username || !user?.email) throw new Error("请先登录父平台并取得用户名和邮箱。");
    const suffix = "; Path=/; SameSite=Lax"
      + (location.protocol === "https:" ? "; Secure" : "");
    document.cookie = `mcp_username=${encodeURIComponent(user.username)}${suffix}`;
    document.cookie = `mcp_email=${encodeURIComponent(user.email)}${suffix}`;

    const response = await fetch(`${gatewayBase}/auth/portal/exchange`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ purpose })
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof result.detail === "string"
      ? result.detail : `MCP 登录失败，HTTP ${response.status}`);
    if (typeof result.next !== "string") throw new Error("网关没有返回页面地址。");
    const destination = new URL(result.next, gatewayBase);
    if (destination.origin !== new URL(gatewayBase).origin) throw new Error("网关返回地址不正确。");
    if (purpose === "key") destination.searchParams.set("portal", "success");
    frame.src = destination.href;
    frame.hidden = false;
  } catch (error) {
    errorText.textContent = error instanceof TypeError
      ? "无法访问 MCP，请检查网络或联系运维。" : error.message;
  }
}
```

**什么时候调用？** 父页面确认用户已登录，并取得当前用户资料后调用：

```javascript
// currentUser 来自父平台自己的登录状态或用户资料接口。
// 如果字段名不同，先映射成 username 和 email。
await openMcp({ username: currentUser.username, email: currentUser.email });
```

把这次调用放到 MCP 模块的初始化流程中，就能进入模块后自动登录。
如果只想点击菜单后打开，就放到菜单点击事件里。不要在每次页面渲染时重复调用。
打开 API Key 领取页使用同一个接口，改传 `key`：

```javascript
await openMcp({ username: currentUser.username, email: currentUser.email }, "key");
```

## 4. 失败时怎么提示

接口失败通常返回：

```json
{"detail":"登录已过期，请刷新页面"}
```

| 状态 | 常见原因或提示 |
| --- | --- |
| 401 | Cookie 缺失，提示“登录已过期，请刷新页面”；邮箱无效也返回 401 |
| 403 | 账号不存在或已停用、管理员不能走此入口，或父平台来源不匹配 |
| 404 | 父平台登录或自助领取功能未启用，联系运维 |
| 422 | purpose 或其他请求字段不合法 |
| 429 | 请求过多，稍后重试；不要无限自动调用 |

前端检查 `response.ok` 并显示 `detail`。上面的示例已包含这个处理。
交换成功后，工作区还会检查角色权限。监听以下消息，才能在父页面显示这类提示：

```javascript
window.addEventListener("message", (event) => {
  if (event.origin !== new URL(gatewayBase).origin
      || event.source !== frame.contentWindow) return;
  if (!["login", "key"].includes(event.data?.purpose)) return;
  if (event.data.type === "contextforge-portal-access-denied") {
    errorText.textContent = "没有 MCP 工作区权限，请联系管理员分配 Team 和角色。";
  } else if (event.data.type === "contextforge-portal-cookie-required") {
    errorText.textContent = "MCP 登录凭据已过期，请重新打开入口或刷新父页面。";
  }
});
```

## 5. 退出和切换账号

父平台退出时，删除两个身份 Cookie，清空 iframe。如果保存过返回的 token，也要删除。
组件卸载时移除消息监听。不要并发交换；切换账号时取消旧请求并忽略旧请求结果。
取消请求也不能保证阻止已到达浏览器的响应写入 Cookie。

注意：清理父页面不会撤销已签发的网关凭据。当前 Cookie 桥接不验证父平台后端登录会话，
只适用于接受该身份信任方式的内网。上线前用真实父页面验证登录、无权限提示和账号切换。
