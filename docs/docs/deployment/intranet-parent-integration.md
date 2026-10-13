# 父页面对接接口文档

适用日期：2026-10-13。父页面完成自己的登录后，调用交换接口，再打开 iframe。
工作区和 API Key 领取页共用 `jwt_token`。普通用户和管理员都能登录，操作权限由网关决定。

## 1. 地址和流程

| 环境 | 父页面 Origin | 网关地址 |
| --- | --- | --- |
| 内网示例 | `http://devops.com` | `http://devops.com:18090` |
| 本地测试 | `http://localhost:5173` | `http://localhost:4445` |

1. 父页面取得当前登录用户的用户名和邮箱。
2. 写入 `mcp_username`、`mcp_email` Cookie。
3. 调用 `POST /auth/portal/exchange`，携带 Cookie。
4. 浏览器保存接口设置的 `jwt_token`，iframe 加载返回的 `next`。

示例要求父页面和网关使用同一主机名。Cookie 不按端口隔离，Nginx 和网关可以在不同服务器。
邮箱必须对应网关中已启用的账号。运维需配置父页面 Origin、CORS 和 iframe 嵌入。
当前交换接口按身份 Cookie 识别用户，不调用父平台后端验证登录状态。

## 2. 登录交换接口：必接

**`POST /auth/portal/exchange`**

| 请求项 | 要求 |
| --- | --- |
| `Content-Type` | `application/json` |
| `Origin` | 等于配置的父页面 Origin，包含协议和非默认端口；浏览器自动发送 |
| Cookie | 首次带 `mcp_username`、`mcp_email`，值用 URL 编码，`Path=/` |
| 浏览器请求 | `credentials: "include"` |

请求体：

```json
{"purpose":"login"}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `purpose` | 是 | `login` 进入工作区；`key` 进入 Key 页。两者建立相同的登录会话 |
| `token` | 否 | 上次返回的父页面授权 token；有效时可复用，不必再带身份 Cookie |

成功返回 HTTP `200`，同时通过 `Set-Cookie` 设置 HttpOnly `jwt_token`：

```json
{"next":"/admin","token":"<父页面授权token>","expires_at":1900000000}
```

| 返回字段 | 说明 |
| --- | --- |
| `next` | `login` 为 `/admin`；`key` 为 `/admin/api-key`。有路径前缀时包含前缀 |
| `token` | 父页面可保存并在下次交换时传回，默认有效期 12 小时 |
| `expires_at` | 返回 token 的到期时间，Unix 秒。复用有效 token 不延长其到期时间 |

本接口签发的 `jwt_token` 有效期为 1 小时，浏览器自动保存和携带，父页面无需读取或设置。
**返回的 `token` 与 Cookie 中的 `jwt_token` 是不同的值，二者都不是 MCP API Key。**
网关页面自动验证 `jwt_token`；父页面无需向 iframe URL 添加 token。

### curl：首次登录

主示例使用 Bash。将 `user@example.com` 换成已启用的网关账号，Cookie 中的 `@` 编码为 `%40`。
`mcp_username` 是非空用户名；空格、中文等字符也需 URL 编码。

```bash
GATEWAY='http://devops.com:18090'
PARENT='http://devops.com'
# 本地测试改为：http://localhost:4445 和 http://localhost:5173

curl -i -X POST "$GATEWAY/auth/portal/exchange" \
  -H "Origin: $PARENT" \
  -H 'Content-Type: application/json' \
  -b 'mcp_username=Zhang%20San; mcp_email=user%40example.com' \
  -c mcp-cookies.txt \
  --data-raw '{"purpose":"login"}'
```

检查 JSON 和 `Set-Cookie: jwt_token=...`。`-c` 保存 Cookie，后续 curl 用 `-b` 携带。
Cookie 文件仅用于 curl 测试。浏览器不会读取它，需要在浏览器内调用交换接口。

Windows PowerShell 本地示例用 `curl.exe`，通过管道传 JSON，避免命令行引号被丢弃：

```powershell
'{"purpose":"login"}' | curl.exe -i -X POST 'http://localhost:4445/auth/portal/exchange' `
  -H 'Origin: http://localhost:5173' `
  -H 'Content-Type: application/json' `
  -b 'mcp_username=Zhang%20San; mcp_email=user%40example.com' `
  -c mcp-cookies.txt --data-binary '@-'
```

### curl：复用授权进入 Key 页

将 `<上次返回的token>` 换成交换接口返回的 `token`，不是 Cookie 中的 `jwt_token`。
本例不带身份 Cookie，使用返回 token 建立相同的登录会话。

```bash
curl -i -X POST "$GATEWAY/auth/portal/exchange" \
  -H "Origin: $PARENT" \
  -H 'Content-Type: application/json' \
  -c mcp-cookies.txt \
  --data-raw '{"purpose":"key","token":"<上次返回的token>"}'
```

返回 `next: "/admin/api-key"`。首次直接进 Key 页，也可用首次登录示例，只把 `purpose` 改为 `key`。
**已有有效 `jwt_token` 时，iframe 直接打开 `/admin/api-key` 即可，无需再次交换。**
父页面无需调用领取页内部接口，网关页面自动处理资源查询和 Key 领取。

## 3. 会话检查接口：可选

**`GET /auth/validate`**，无请求体。浏览器用 `credentials: "include"` 携带 `jwt_token`。

```bash
curl -i -b mcp-cookies.txt "$GATEWAY/auth/validate"
```

成功返回 HTTP `200`。示例只展示常用字段，实际响应还包含用户资料和会话配置：

```json
{
  "valid": true,
  "expires_at": "2026-10-13T07:00:00+00:00",
  "expires_in": 3599,
  "user": {"email":"user@example.com","is_admin":false,"is_active":true},
  "session_source": "sso"
}
```

`expires_in` 为会话剩余秒数；`expires_at` 为 ISO 8601 时间，与交换接口的 Unix 秒格式不同。
会话缺失、无效或过期返回 `401`，不会返回 `valid: false`。账号停用等情况也可能返回 `403`。

```bash
# 不带 Cookie，验证未登录返回 401
curl -i "$GATEWAY/auth/validate"
```

## 4. 父页面自动登录示例

页面准备 `<iframe id="mcp-frame" title="MCP 页面"></iframe>`。
`currentUser` 使用父平台当前用户的 `{username, email}`；`showError` 换成父页面提示函数。

```javascript
const gatewayBase = "http://devops.com:18090"; // 本地改为 http://localhost:4445
const frame = document.getElementById("mcp-frame");
const tokenKey = `mcp-portal:${gatewayBase}`;

async function openMcp(user, purpose = "login") {
  frame.src = "about:blank";
  if (!user?.username || !user?.email) throw new Error("请先登录父平台");
  const suffix = "; Path=/; SameSite=Lax"
    + (location.protocol === "https:" ? "; Secure" : "");
  document.cookie = `mcp_username=${encodeURIComponent(user.username)}${suffix}`;
  document.cookie = `mcp_email=${encodeURIComponent(user.email)}${suffix}`;
  const savedToken = sessionStorage.getItem(tokenKey);
  const response = await fetch(`${gatewayBase}/auth/portal/exchange`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ purpose, ...(savedToken ? { token: savedToken } : {}) })
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === "string"
    ? result.detail : `MCP 登录失败，HTTP ${response.status}`);
  if (typeof result.next !== "string") throw new Error("网关没有返回页面地址");
  const destination = new URL(result.next, gatewayBase);
  if (destination.origin !== new URL(gatewayBase).origin) throw new Error("网关返回地址不正确");
  sessionStorage.setItem(tokenKey, result.token);
  frame.src = destination.href;
}

// 在模块初始化或菜单点击时触发，失败时显示提示。
openMcp(currentUser).catch(error => showError(error.message));
// 首次进入 Key 页：openMcp(currentUser, "key").catch(error => showError(error.message));
```

网络或 CORS 错误时提示用户联系运维。切换用户时清除保存的 token，再重新交换。
不要并发交换，也不要在每次页面渲染时重复调用。

## 5. 过期、权限不足和退出

- `jwt_token` 过期：父平台仍已登录时，再调用交换接口，成功后重新加载 iframe。
- 返回 token 有效：交换接口复用它并签发新的 `jwt_token`。
- 返回 token 过期或无效：自动回退到身份 Cookie；Cookie 也缺失时返回 `401`。
- `403`：显示接口 `detail`，检查账号或来源；不要循环重试。

iframe 消息也可用于提示。先检查消息来源和窗口：

```javascript
window.addEventListener("message", event => {
  if (event.origin !== new URL(gatewayBase).origin || event.source !== frame.contentWindow) return;
  if (event.data?.type === "contextforge-portal-cookie-required") {
    showError("MCP 登录已过期，请重新打开入口或刷新父页面");
  } else if (event.data?.type === "contextforge-portal-access-denied") {
    showError("没有 MCP 工作区权限，请联系管理员");
  }
});
```

示例显示提示。需要自动恢复时，确认父平台仍已登录，再调用 `openMcp(currentUser, 当前入口)` 一次。
`/auth/validate` 成功表示会话有效，不代表拥有工作区或所选 MCP 的操作权限。

父平台退出时删除身份 Cookie、保存的 token，并清空 iframe。
这些操作不会清除 HttpOnly `jwt_token`；注销网关会话需使用网关退出功能。
已签发的父页面授权 token 和 API Key 也不会因父平台退出自动撤销。

## 6. Cookie 与错误码

| Cookie | 设置方 | 用途 |
| --- | --- | --- |
| `mcp_username` | 父页面 | 非空用户名 |
| `mcp_email` | 父页面 | 网关账号邮箱 |
| `jwt_token` | 网关 | HttpOnly 登录会话，工作区和 Key 页共用 |
| `mcpgateway_csrf_token` | 网关 | 操作防伪造令牌；网关页面处理，父页面无需设置 |

父页面无需设置 `member_key_proof`、`Authorization` 或 URL token。
交换接口不要求父页面提交 CSRF token，它检查父页面 Origin。

错误响应通常为 `{"detail":"具体原因"}`；`422` 的 `detail` 是参数校验错误数组。

| HTTP 状态 | 交换接口常见原因 |
| --- | --- |
| `400` | 网关登录 Cookie 过大 |
| `401` | 身份 Cookie 缺失或邮箱无效，且没有可复用的 token |
| `403` | Origin 不匹配，账号不存在或已停用 |
| `404` | 父平台登录未启用，或 `key` 自助领取未启用 |
| `422` | 请求参数错误，或 token 超过长度限制 |
| `429` | 请求过多；按 `Retry-After` 等待（响应可能不是上述 JSON 格式） |
| `503` | 未配置父页面 Origin |
