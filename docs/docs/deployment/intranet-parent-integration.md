# 内网父页面前端对接

父页面确认用户已登录后，调用一次 `POST /auth/portal/exchange`，再把返回的 `next` 加载到 iframe。
工作区和 API Key 领取页共用 `jwt_token`。已登录后，直接打开领取页即可。

## 1. 接入条件

- 本例父页面为 `http://devops.com`，网关为 `http://devops.com:18090`。
  浏览器访问地址使用同一主机名即可共享 Cookie，Nginx 和网关可以在不同服务器。
  不同 IP 或不同主机名不能直接使用本例共享 Cookie。
- 用户邮箱对应网关中已启用的账号；普通用户和平台管理员均可登录，权限由网关账号和角色决定。
- 运维已启用父平台登录，并配置父页面来源、跨域请求和 iframe 嵌入。

## 2. 父页面调用的接口

**`POST http://devops.com:18090/auth/portal/exchange`**

请求使用 `Content-Type: application/json` 和 `credentials: "include"`，不需要 `Authorization`。
先写入当前用户的 `mcp_username`、`mcp_email` Cookie，使用 `Path=/` 和 URL 编码。

```json
{"purpose":"login"}
```

| 请求字段 | 必填 | 含义 |
| --- | --- | --- |
| `purpose` | 是 | `login` 进入工作区；`key` 直接进入领取页。两者都建立相同的登录会话 |
| `token` | 否 | 上次接口返回的授权 token；不传也可以按身份 Cookie 交换 |

成功返回 HTTP `200`，同时通过 `Set-Cookie` 写入 `jwt_token`：

```json
{"next":"/admin","token":"<父平台授权token>","expires_at":1900000000}
```

| 返回字段 | 含义 |
| --- | --- |
| `next` | iframe 页面路径；`login` 返回 `/admin`，`key` 返回 `/admin/api-key` |
| `token` | 可在下次交换时传回。它不是 Cookie 中的 `jwt_token`，也不是 MCP API Key |
| `expires_at` | 返回 token 的到期时间，Unix 秒；默认有效期 12 小时 |

`jwt_token` 默认有效期 1 小时。浏览器自动保存和携带，父页面不需要读取或手动设置。
不要把任何 token 拼到 iframe URL 中。

## 3. 最小示例与自动登录触发

把脚本放在这些元素之后；`currentUser` 使用父平台自己的登录用户资料。
把用户资料映射为 `{username, email}`，在 MCP 模块初始化或菜单点击时调用 `openMcp(currentUser)`。

```html
<p id="mcp-error" role="alert"></p>
<iframe id="mcp-frame" title="MCP 页面" hidden style="width:100%;height:800px;border:0"></iframe>
```

```javascript
const gatewayBase = "http://devops.com:18090";
const frame = document.getElementById("mcp-frame");
const errorText = document.getElementById("mcp-error");

async function openMcp(user, purpose = "login") {
  errorText.textContent = "";
  frame.hidden = true;
  frame.src = "about:blank";
  try {
    if (!user?.username || !user?.email) throw new Error("请先登录父平台。");
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
    frame.src = destination.href;
    frame.hidden = false;
  } catch (error) {
    errorText.textContent = error instanceof TypeError ? "无法访问 MCP，请联系运维。" : error.message;
  }
}

window.addEventListener("message", (event) => {
  if (event.origin !== new URL(gatewayBase).origin || event.source !== frame.contentWindow) return;
  if (event.data?.type === "contextforge-portal-access-denied") {
    errorText.textContent = "没有 MCP 工作区权限，请联系管理员。";
  } else if (event.data?.type === "contextforge-portal-cookie-required") {
    errorText.textContent = "MCP 登录已过期，请重新打开入口或刷新父页面。";
  }
});
```

首次直接进入领取页：`openMcp(currentUser, "key")`。
**已登录后打开领取页：`frame.src = gatewayBase + "/admin/api-key"`，不用再次交换授权。**
不要在每次渲染时重复调用，也不要并发交换。切换用户时，等待旧交换结束，再用新用户重新交换。

## 4. Cookie 与失败提示

| Cookie | 谁设置 | 用途 |
| --- | --- | --- |
| `mcp_username` | 父页面 | 当前用户名称 |
| `mcp_email` | 父页面 | 当前用户邮箱 |
| `jwt_token` | 网关 | HttpOnly 登录 Cookie，工作区与领取页共用 |
| `mcpgateway_csrf_token` | 网关 | 防止跨站伪造操作；网关页面自动处理，父页面无需设置 |

父页面不需要设置 `member_key_proof`，也不需要直接调用领取页内部接口。
接口失败返回 `{"detail":"具体原因"}`；示例会把原因显示在父页面。
`401` 表示身份缺失或无效，`403` 表示账号不可用或来源不匹配，`404` 表示功能未启用。
`422` 表示请求参数错误，`429` 表示请求过多，`503` 表示父页面来源尚未配置。
交换后的权限不足或会话过期，通过示例中的 `message` 监听显示提示。

父平台退出时删除两个身份 Cookie、清空 iframe，并删除保存的返回 token。
这些清理不会注销网关会话；网关退出仍需使用网关的退出功能。
当前桥接根据身份 Cookie 识别用户，不校验父平台后端登录会话。
