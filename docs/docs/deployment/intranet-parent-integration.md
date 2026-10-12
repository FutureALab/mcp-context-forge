# 内网父平台对接指南：登录、鉴权和 API Key

本文给内网父平台的开发人员和运维人员使用。父平台可以使用任意前端框架，
不需要复制本项目的演示页面，也不需要修改父平台原有登录页面。
本文描述当前分支已实现的接口；部署镜像必须包含 `PORTAL_SSO_ENABLED` 和 `/auth/portal/exchange`。

最小对接只有四步：取得父平台已登录用户、写入两个 Cookie、调用交换接口、把返回地址放入 iframe。
父平台还要显示交换错误，监听 iframe 消息，并在退出或切换用户时清理状态。

## 1. 先确认地址和账号

本文使用以下示例。上线时统一替换域名、IP 和端口。

| 项目 | 示例 | 用途 |
| --- | --- | --- |
| 父平台浏览器地址 | `http://devops.com` | 用户原来登录的内网平台 |
| 网关浏览器地址 | `http://devops.com:18090` | 父页面调用接口和加载 iframe 的地址 |
| Nginx 服务器 | `10.20.0.10` | `devops.com` 解析到这台服务器 |
| 网关服务器 | `10.20.0.15:4444` | Nginx 转发请求的目标 |

```text
用户浏览器
  ├─ http://devops.com             → 父平台
  └─ http://devops.com:18090       → Nginx 服务器
                                      └─ http://10.20.0.15:4444 → 网关服务器
```

Nginx 和网关可以在不同服务器。浏览器始终通过域名访问，不直接使用网关服务器 IP。
同一主机名的不同端口可以共享 Cookie；服务器是否相同不影响 Cookie 共享。

父平台用户名与网关显示名不必相同，但邮箱必须与网关已注册账号一致。
账号必须启用，且为普通账号。平台管理员使用独立的网关登录入口。
进入工作区还需要有效 Team 和相应工作区角色。领取 Key 还需要资源访问权和 `servers.use` 权限。
管理员的账号创建、Team 和角色配置步骤见 [内网部署说明](intranet-portal-gateway.md)。
**交换接口成功只表示身份桥接成功，不表示所有页面和 MCP 都已授权。**

### 当前方案的身份信任范围

当前方案按浏览器发送的邮箱 Cookie 匹配账号，不向父平台后端验证登录会话。
用户可以修改这些 Cookie；`Origin` 检查和“账号已注册”不能证明 Cookie 中的身份真实。
签发后的 token 有签名，但不能修复首次交换时的身份冒用。
因此，此方案只适用于接受该信任范围的受控内网。
如果要求严格验证父平台登录身份，需要另行实现后端会话校验或签名票据；当前接口没有这项功能。

## 2. 运维配置

### 2.1 网关环境变量

在现有网关 `.env` 中配置以下变量。数据库、密钥和管理员设置沿用部署配置。

```dotenv
APP_DOMAIN=http://devops.com:18090
AUTH_REQUIRED=true
EMAIL_AUTH_ENABLED=true
PUBLIC_REGISTRATION_ENABLED=false
MCPGATEWAY_UI_ENABLED=true
MCPGATEWAY_ADMIN_API_ENABLED=true
SELF_SERVICE_API_KEYS_ENABLED=true

PORTAL_SSO_ENABLED=true
PORTAL_SSO_PARENT_ORIGIN=http://devops.com
PORTAL_SSO_TOKEN_TTL_MINUTES=720
CORS_ENABLED=true
CORS_ALLOW_CREDENTIALS=true
ALLOWED_ORIGINS='["http://devops.com","http://devops.com:18090"]'
X_FRAME_OPTIONS=none

ENVIRONMENT=staging
SECURE_COOKIES=false
COOKIE_SAMESITE=lax
```

- `APP_DOMAIN` 填用户访问的网关地址，不填网关服务器 IP。
- `PORTAL_SSO_PARENT_ORIGIN` 填父页面的协议、域名和非默认端口，不含页面路径。
- 默认 HTTP 80 端口写为 `http://devops.com`，不要写成 `http://devops.com:80`。
- `ALLOWED_ORIGINS` 使用明确地址，携带 Cookie 时不要配置为 `*`。
- HTTP 示例使用 `staging`。`production` 会强制给登录 Cookie 加 `Secure`，HTTP 无法使用。
- 改为 HTTPS 时同步修改 URL、Origin，并使用 `SECURE_COOKIES=true` 和 `ENVIRONMENT=production`。
- HTTPS 父页面需要 HTTPS 网关入口，避免浏览器拦截 HTTP 请求和 iframe。
- `X_FRAME_OPTIONS=none` 允许 iframe。确认上游代理没有再次添加阻止嵌入的响应头。
- 父平台自己的 CSP 如限制 `frame-src` 或 `connect-src`，也要允许网关浏览器地址。

修改 `.env` 后重新创建网关容器，让环境变量生效。例如，部署目录使用 `compose.yaml` 时执行：

```bash
docker compose --env-file .env -f compose.yaml up -d gateway
```

仅重启 Nginx 不会更新网关环境变量。

### 2.2 Nginx 与网关在不同服务器

将以下配置放到现有 Nginx 配置中。保留父平台原有的 80 端口配置。
如果已经定义 `$connection_upgrade`，复用现有定义。

```nginx
# 放在 http {} 内，与 server {} 同级。
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 18090;
    server_name devops.com;

    location / {
        proxy_pass http://10.20.0.15:4444;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

当前桥接读取 Cookie，不读取 `X-Forwarded-Email`、`X-Forwarded-User`。
不需要在 Nginx 定义 `$mcp_email` 或 `$mcp_username`。正常反向代理会转发 Cookie 和 Origin。
不要重写 Origin 为父平台地址，也不要把 18090 代理回父平台的 80 端口。

网关容器内部监听 `0.0.0.0:4444`，宿主机端口要对 Nginx 可达。
跨服务器部署不能只映射 `127.0.0.1:4444:4444`。可以绑定网关内网 IP：

```yaml
ports:
  - "10.20.0.15:4444:4444"
```

网关服务器防火墙允许 Nginx 服务器访问 TCP 4444。
Nginx 服务器允许使用网关的用户网段访问 TCP 18090。

在 Nginx 服务器执行后端检查，再检查配置。配置通过后重载：

```bash
curl --max-time 5 -fsS http://10.20.0.15:4444/health
sudo nginx -t
sudo nginx -s reload
```

再从用户电脑访问 `http://devops.com:18090/health`。成功后开始父页面对接。

## 3. 父页面要改什么

| 步骤 | 父平台负责的操作 |
| --- | --- |
| 父平台登录成功 | 从已有用户接口或登录状态中取得用户名和邮箱 |
| 打开 MCP 入口 | 写入身份 Cookie，调用交换接口 |
| 交换成功 | 保存返回的 token 和过期时间，加载返回的 `next` |
| 交换失败 | 显示错误，清空旧 iframe，停止本次打开 |
| iframe 提示过期或无权限 | 显示提示，不无限自动刷新 |
| 父平台退出或切换账号 | 删除身份 Cookie、保存的 token 和旧 iframe |

只写 Cookie、直接访问 `/admin` 不会完成桥接。必须先调用交换接口。

### 3.1 身份 Cookie 约定

| Cookie | 必填 | 示例值 | 说明 |
| --- | --- | --- | --- |
| `mcp_username` | 是 | `张三` | 非空用户名，最多 255 字符；不校验网关显示名 |
| `mcp_email` | 是 | `zhangsan@example.com` | 网关注册邮箱，最多 254 字符 |

两个 Cookie 均使用 `Path=/`。写入值时使用 `encodeURIComponent`。
同主机名部署不需要设置 `Domain`。Cookie 不按端口隔离。
父平台后端也可以写 Cookie，只要浏览器请求网关时会带上它们。

如果父页面地址是一个 IP，网关浏览器地址是另一个 IP，两者不能直接共享这些 Cookie。
先让两个浏览器入口共用主机名，或使用适合实际部署的同源代理。
同站点子域名共享 Cookie 需要共同的 `Domain`；写入和删除必须使用相同 Domain 和 Path。
以下示例仅适用于同主机名、不同端口，跨站部署不要直接照搬。

### 3.2 原生 JavaScript 示例

在父页面提供两个按钮、一个提示区域和一个 iframe：

```html
<button id="mcp-login" type="button" disabled>打开 MCP 工作区</button>
<button id="mcp-key" type="button" disabled>领取 MCP API Key</button>
<p id="mcp-status" role="alert"></p>
<iframe id="mcp-frame" title="MCP 页面" hidden
        style="width:100%;height:800px;border:0"></iframe>
```

把以下脚本放在这些元素之后。修改 `gatewayBase`，并在父平台登录成功后调用 `setMcpUser()`。
不要把示例邮箱写死在真实页面中。

```javascript
const gatewayBase = "http://devops.com:18090";
const gatewayOrigin = new URL(gatewayBase).origin;
const tokenKey = "contextforge-parent-authorization";
const frame = document.getElementById("mcp-frame");
const statusText = document.getElementById("mcp-status");
const loginButton = document.getElementById("mcp-login");
const keyButton = document.getElementById("mcp-key");
let currentUser = null;
let requestVersion = 0;
let exchangeInProgress = false;
let pendingController = null;

function updateMcpButtons() {
  loginButton.disabled = keyButton.disabled = !currentUser || exchangeInProgress;
}

function clearMcpState() {
  requestVersion += 1;
  pendingController?.abort();
  sessionStorage.removeItem(tokenKey);
  frame.src = "about:blank";
  frame.hidden = true;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  for (const name of ["mcp_username", "mcp_email"]) {
    document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
  }
}

function setMcpUser(user) {
  clearMcpState();
  currentUser = user ? {
    username: String(user.username || "").trim(),
    email: String(user.email || "").trim().toLowerCase()
  } : null;
  updateMcpButtons();
  statusText.textContent = currentUser ? "请选择 MCP 入口。" : "请先登录父平台。";
}

function writeIdentityCookies() {
  if (!currentUser?.username || !currentUser?.email) {
    throw new Error("父平台没有取得用户名或邮箱，请重新登录。");
  }
  const secure = location.protocol === "https:" ? "; Secure" : "";
  for (const [name, value] of [
    ["mcp_username", currentUser.username], ["mcp_email", currentUser.email]
  ]) {
    document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; SameSite=Lax${secure}`;
  }
}

function readSavedToken() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(tokenKey) || "null");
    return saved?.email === currentUser.email && saved.expires_at * 1000 > Date.now()
      ? saved.token : null;
  } catch {
    return null;
  }
}

async function openMcp(purpose) {
  if (exchangeInProgress) return;
  exchangeInProgress = true;
  updateMcpButtons();
  const version = ++requestVersion;
  const controller = new AbortController();
  pendingController = controller;
  const timeout = setTimeout(() => controller.abort(), 15000);
  frame.hidden = true;
  frame.src = "about:blank";
  statusText.textContent = "正在验证 MCP 账号…";
  try {
    writeIdentityCookies();
    const token = readSavedToken();
    const response = await fetch(`${gatewayBase}/auth/portal/exchange`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ purpose, ...(token ? { token } : {}) }),
      signal: controller.signal
    });
    const result = await response.json().catch(() => ({}));
    if (version !== requestVersion) return;
    if (!response.ok) {
      throw new Error(typeof result.detail === "string"
        ? result.detail : `MCP 鉴权失败，HTTP ${response.status}`);
    }
    if (typeof result.next !== "string" || typeof result.token !== "string"
        || !Number.isFinite(result.expires_at)) {
      throw new Error("网关返回格式不正确，请联系运维检查部署版本。");
    }
    const destination = new URL(result.next, gatewayBase);
    if (destination.origin !== gatewayOrigin) throw new Error("网关返回地址不正确。");
    sessionStorage.setItem(tokenKey, JSON.stringify({
      email: currentUser.email, token: result.token, expires_at: result.expires_at
    }));
    if (purpose === "key") destination.searchParams.set("portal", "success");
    else destination.searchParams.set("lang", "zh-CN");
    frame.src = destination.href;
    frame.hidden = false;
    statusText.textContent = "身份验证成功，正在加载页面；页面权限由网关继续检查。";
  } catch (error) {
    if (version !== requestVersion) return;
    sessionStorage.removeItem(tokenKey);
    statusText.textContent = error.name === "AbortError" ? "网关请求超时，请稍后重试。"
      : error instanceof TypeError ? "无法访问网关，请检查网络、CORS 和浏览器 Cookie 设置。"
      : error.message;
  } finally {
    clearTimeout(timeout);
    pendingController = null;
    exchangeInProgress = false;
    updateMcpButtons();
  }
}

window.addEventListener("message", (event) => {
  if (event.origin !== gatewayOrigin || event.source !== frame.contentWindow) return;
  if (!["login", "key"].includes(event.data?.purpose)) return;
  const messages = {
    "contextforge-portal-cookie-required": "MCP 凭据已过期，请重新打开入口；仍失败时刷新父页面。",
    "contextforge-portal-access-denied": "该账号没有 MCP 工作区权限，请联系管理员分配有效 Team 和角色。"
  };
  if (!messages[event.data?.type]) return;
  requestVersion += 1;
  pendingController?.abort();
  frame.hidden = true;
  frame.src = "about:blank";
  statusText.textContent = messages[event.data.type];
});

loginButton.addEventListener("click", () => openMcp("login"));
keyButton.addEventListener("click", () => openMcp("key"));

// 在父平台登录成功后，传入实际用户资料：
// setMcpUser({ username: 已登录用户的用户名, email: 已登录用户的邮箱 });
// 在父平台退出或切换账号前调用 setMcpUser(null)。
```

父平台刷新后，应从自身登录状态重新调用 `setMcpUser()`。
该示例会清理旧 token，再按 Cookie 交换；同一次页面生命周期内可复用 token。
Vue/React 等框架只需把 DOM 提示和 iframe 地址改成组件状态，接口调用方式相同。
组件卸载时移除消息监听，并让未完成请求的结果失效。

## 4. 登录交换接口文档

### 4.1 请求

**`POST /auth/portal/exchange`**

完整示例地址：`http://devops.com:18090/auth/portal/exchange`。
父页面使用浏览器 `fetch` 调用，不由父平台后端代替浏览器调用。
这样网关的 `Set-Cookie` 才能直接进入用户浏览器。

| 项目 | 要求 |
| --- | --- |
| Content-Type | `application/json` |
| Origin | 浏览器自动发送，必须匹配 `PORTAL_SSO_PARENT_ORIGIN` |
| Cookie | 首次交换携带 `mcp_username` 和 `mcp_email` |
| fetch 设置 | `credentials: "include"` |
| Authorization | 不需要；不要把父平台 token 当作网关 Bearer token |
| CSRF | 此交换接口校验精确 Origin，不要求额外 CSRF header |

浏览器 JavaScript 不手动设置 `Cookie` 或 `Origin` header。

请求体：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `purpose` | string | 是 | `login` 打开工作区；`key` 打开 API Key 领取页 |
| `token` | string 或 null | 否 | 上次交换返回的父平台授权 token，最多 4096 字符 |

首次登录工作区：

```json
{"purpose":"login"}
```

首次打开领取页：

```json
{"purpose":"key"}
```

复用已取得的授权：

```json
{"purpose":"login","token":"<上次交换返回的token>"}
```

### 4.2 成功响应

HTTP `200`，响应示例：

```json
{
  "next": "/admin",
  "token": "<父平台授权token>",
  "expires_at": 1900000000
}
```

| 字段 | 含义 |
| --- | --- |
| `next` | iframe 目标路径；`key` 返回 `/admin/api-key` |
| `token` | 只用于后续交换，不能用于调用 MCP 或普通网关 API |
| `expires_at` | Unix 时间戳，单位为秒；默认有效期 12 小时 |

`expires_at` 示例仅用于说明格式，不是实际有效期。
配置 `APP_ROOT_PATH` 时，`next` 包含路径前缀；调用接口也要带上该前缀。
例如前缀 `/mcp` 时，调用 `/mcp/auth/portal/exchange`，加载返回的 `/mcp/admin`。
本文 Nginx 示例没有配置路径前缀，直接使用根路径。

网关同时通过响应设置 HttpOnly Cookie，父页面不用读取或复制：

| purpose | 设置的 Cookie | 有效期 | 用途 |
| --- | --- | --- | --- |
| `login` | `jwt_token` | 1 小时 | 工作区会话；路径由网关部署路径决定 |
| `key` | `member_key_proof` | 5 分钟 | 领取页校验；路径为 `/admin/api-key` 或带前缀的对应路径 |

工作区会话不能代替领取页校验。只带 `jwt_token` 调用领取的 SSO 接口仍会失败。
`portal=success` 只是领取页面的显示标记，不是鉴权凭据。

有效 token 可以在没有身份 Cookie 时复用。每次仍检查账号存在、启用且不是管理员。
token 无效或过期时，接口回退到 Cookie 重新交换，不一定直接返回 token 过期错误。
如果 `mcp_email` 与 token 所属账号不一致，接口按 Cookie 中的新账号重新鉴权。
父平台应在切换账号时主动清理状态，而不是依赖这项回退。

### 4.3 错误响应与页面展示

业务错误通常返回 `{"detail":"错误说明"}`。HTTP `422` 的 `detail` 是字段错误数组。
限流、中间件和代理错误可能使用其他响应格式；父页面需要保留 HTTP 状态作为兜底提示。

| HTTP | detail 或原因 | 父平台处理 |
| --- | --- | --- |
| 401 | `登录已过期，请刷新页面` | 检查身份 Cookie；提示用户重新登录或刷新 |
| 401 | `父平台账号邮箱无效` | 检查传入邮箱 |
| 403 | `父平台来源不匹配` | 核对实际浏览器 Origin 与环境变量 |
| 403 | `账号不存在、已停用或不具备所选资源的访问权限` | 首次交换时检查注册和启用状态 |
| 403 | `请使用管理员登录入口` | 管理员使用 `/admin/login` |
| 403 | `MCP 账号不存在、已停用或需管理员登录` | 复用 token 时账号状态已变化 |
| 404 | `父平台登录未启用` | 启用 `PORTAL_SSO_ENABLED` |
| 404 | `自助领取未启用` | 核对 `SELF_SERVICE_API_KEYS_ENABLED` |
| 503 | `未配置父平台来源` | 配置 `PORTAL_SSO_PARENT_ORIGIN` |
| 400 | `网关登录会话过大` | 联系管理员检查账号和 Cookie 大小 |
| 422 | 请求字段不合法 | 检查 purpose、token 类型及长度 |
| 429 | 请求过多 | 等待后手动重试；不要循环交换 |
| 500/502/504 | 应用异常或代理错误 | 检查网关日志、数据库和 Nginx 后端连接 |

交换接口限流为每分钟 20 次，部署中的其他限流也可能生效。
`fetch` 遇到 HTTP 401/403 不会自动抛错，必须检查 `response.ok`。
父页面不显示错误时，用户可能只看到空白或旧 iframe。

当前工作区无权限时，iframe 登录页的提示可能被通用“需要管理员权限”覆盖。
父平台接入下一节的消息监听后，可以显示明确的 Team 和角色提示。

## 5. iframe 鉴权消息

网关以 `postMessage` 通知父平台。父平台必须同时检查消息来源和发送窗口，
即 `event.origin === gatewayOrigin` 和 `event.source === iframe.contentWindow`。

| type | purpose | 含义 | 处理 |
| --- | --- | --- | --- |
| `contextforge-portal-cookie-required` | `login` 或 `key` | 页面凭据缺失或过期 | 提示重新打开入口；不要无限刷新 |
| `contextforge-portal-access-denied` | `login` | 缺少工作区授权 | 提示管理员分配有效 Team 和工作区角色 |

消息示例：

```json
{"type":"contextforge-portal-access-denied","purpose":"login"}
```

这些消息不是所有 API 错误的统一通道。交换错误仍由父页面读取 HTTP 响应。
领取页内部的资源权限错误由领取页处理。
没有消息监听时，网关不会自动在父页面弹窗。

## 6. API Key 领取接口文档

最简单的做法是调用交换接口，使用 `purpose=key`，再加载返回的领取页面。
网关页面负责选择 Team、选择 MCP、生成 Key 和显示客户端配置，父平台不用再实现这些表单。

以下接口供需要了解领取鉴权或自定义领取 UI 的人员使用。
这些接口的 `sso` 路径也用于当前 Cookie 桥接，不表示父平台必须实现 OAuth。

### 6.1 必须先建立领取校验和 CSRF

1. 调用 `POST /auth/portal/exchange`，传 `{"purpose":"key"}`。
2. 浏览器保存 `member_key_proof`，加载 `GET /admin/api-key`。
3. 领取页响应设置 `mcpgateway_csrf_token` Cookie。
4. 后续 POST 携带这些 Cookie，并把 CSRF Cookie 值放到 `x-csrf-token` header。

领取接口同时检查 Origin/Referer、CSRF 和账号；不要发送 Authorization header。
五分钟校验过期后重新执行 key 交换。
如果父平台不能读取网关域下的 CSRF Cookie，使用网关领取页，不直接跨域拼装领取请求。
`/auth/csrf-token` 属于工作区会话流程，不能代替领取页的 CSRF Cookie。

### 6.2 查询可选 Team 和 MCP

**`POST /admin/api-key/sso/options`**，无请求体。
成功返回 HTTP `200`：

```json
{
  "email": "zhangsan@example.com",
  "full_name": "张三",
  "teams": [
    {"id":"<team-id>","name":"研发团队","is_personal":false}
  ],
  "servers": [
    {
      "id":"<server-id>",
      "name":"研发 MCP",
      "team_id":"<team-id>",
      "visibility":"team",
      "eligible_team_ids":["<team-id>"],
      "public_access":false
    }
  ]
}
```

只返回账号可见的资源。列表为空时，提示管理员检查 Team 和资源配置。
列表可见不代表已经通过 Key 签发权限检查。

### 6.3 生成或续期 Key

**`POST /admin/api-key/sso/issue`**，JSON 请求体：

```json
{"team_id":"<team-id>","server_id":"<server-id>","days":30}
```

| 字段 | 要求 |
| --- | --- |
| `team_id` | 可选；Team ID 最长 36 字符。公开资源可使用 null，但仍检查权限 |
| `server_id` | 必填；启用且有权访问的虚拟 MCP ID，最长 36 字符 |
| `days` | 可选；整数 1–365，默认 30 |

身份来自 `member_key_proof`，不要在请求体传邮箱替换当前账号。
成功响应包含以下字段，HTTP `200`：

| 字段 | 含义 |
| --- | --- |
| `email`、`team_id`、`server_id`、`server_name` | Key 对应的账号和资源 |
| `token_id` | Key 记录 ID |
| `api_key` | 可用于 MCP 客户端的 Key；属于敏感信息 |
| `created_at`、`expires_at` | 创建与到期时间 |
| `renewed` | 是否续期现有 Key |
| `limit_reached` | 是否到达自创建起累计 365 天上限 |
| `message` | 生成、续期或上限提示 |

资源或 Team 无权限返回 `403`；缺少 `servers.use` 返回 `403` 和 `该账号没有 MCP 使用权限`。
校验凭据缺失或过期可返回 `401`；CSRF 不匹配返回 `403` 和 `请刷新页面后重试`。
账号每小时最多生成 10 个 Key，超限返回 `429`；接口还有限流每分钟 10 次。
续期响应可能包含原 Key 恢复字段，不要将整个响应写入浏览器控制台或日志。
Key 的时间字段使用 ISO 8601 字符串；交换接口的 `expires_at` 则是秒级 Unix 时间戳。

Key 调用 MCP 时使用 `Authorization: Bearer <api_key>`。
工作区会话、父平台授权 token 和 MCP API Key 是三种不同凭据，不能互换。

### 6.4 使用本地密码领取的备用接口

不使用父平台桥接时，领取页也支持网关本地邮箱和密码。
同样先打开领取页取得 CSRF Cookie，后续 POST 携带匹配的 `x-csrf-token`。

| 接口 | 请求体 | 作用 |
| --- | --- | --- |
| `POST /admin/api-key/options` | `email`、`password` | 验证本地账号并查询可选资源 |
| `POST /admin/api-key/issue` | `email`、`password`、`server_id`、可选 `team_id`、`days` | 验证密码后签发 Key |

父平台已有登录并不意味着拥有网关本地密码。不要把父平台密码当作网关密码发送。

## 7. 独立登录和会话鉴权接口

本节为备用方式。第 3 节 Cookie 桥接不需要先调用 `/auth/login`。

| 接口 | 鉴权和参数 | 返回或作用 |
| --- | --- | --- |
| `GET /admin/login` | 浏览器访问 | 网关独立登录页；管理员使用此入口 |
| `POST /auth/login` | JSON：`email`、`password` | 本地密码登录，返回会话 `access_token` |
| `GET /auth/validate` | Bearer 会话 token 或 `jwt_token` Cookie | 检查会话有效性及过期信息 |
| `POST /auth/refresh` | 有效会话 token；Cookie 请求遵循 CSRF 设置 | 轮换会话，返回新 token 和到期信息 |
| `POST /auth/logout` | Bearer 会话 token | 撤销该会话 token；不是父平台退出接口 |

`POST /auth/login` 请求：

```json
{"email":"zhangsan@example.com","password":"<网关本地密码>"}
```

成功响应包含 `access_token`、`token_type`、`expires_in`、`user`。
`token_type` 为 `bearer`，`expires_in` 单位为秒。
`user` 包含邮箱等账号资料。后续 API 请求使用 `Authorization: Bearer <access_token>`。
这个 JSON 登录接口不会替父页面建立 iframe 的 `jwt_token` Cookie；嵌入页面继续使用交换接口。
错误密码返回 `401`；启用 SSO 且限制本地密码登录时，普通账号可返回 `400`。

`GET /auth/validate` 成功响应包含 `valid`、`expires_at`、`expires_in`、`user`、`session_source`、`config`。
`valid=true` 只表示会话验证成功，具体资源访问仍检查权限。
`POST /auth/refresh` 返回 `access_token`、`token_type`、`expires_in`、`expires_at` 和可选 `csrf_token`。
刷新有会话生命周期限制；API Key 不能通过这个接口刷新。
`POST /auth/logout` 必须传网关 Bearer token，仅携带 Cookie 不够。
父平台交换返回的 `token` 不能传给这些会话接口。

完整运行版本的接口可从网关 `/docs` 或 `/openapi.json` 查看，前提是部署启用了这些入口。

## 8. 退出、账号切换和有效期

父平台退出或切换账号时，执行以下步骤：

1. 清除 `mcp_username` 和 `mcp_email`，使用写入时的 Domain 和 Path。
2. 清除保存的父平台授权 token。
3. 将 iframe 改成 `about:blank` 并隐藏。
4. 使未完成的交换请求失效，避免旧账号请求完成后重新打开页面。
5. 取得新用户资料后，再写 Cookie 并交换。

上面的示例已包含这些处理，但仅清理父页面和浏览器中的状态。
示例禁止同一页面同时交换，并在切换账号时取消未完成请求。
忽略旧响应结果或取消 fetch 不能保证阻止已到达浏览器的响应写入 Cookie。
快速切换账号或多个标签页操作仍可能覆盖网关 Cookie；出现身份不一致时重新打开当前账号入口。
当前没有逐个撤销父平台授权 token 的接口。
清理父平台状态不会撤销已签发 token、网关会话或 MCP API Key。
已复制的父平台 token 在有效期内仍可能交换；账号每次仍要通过状态检查。
HttpOnly 的网关 Cookie 不能由父页面脚本直接删除，领取校验和工作区会话分别保留自身有效期。
如果要求父平台退出后立即使全部凭据失效，需要另行设计服务端撤销和退出联动。
同一浏览器的网关 Cookie 由多个标签页共享，多账号同时打开可能互相覆盖。

## 9. 联调验收和常见问题

| 测试 | 预期结果 |
| --- | --- |
| 用户电脑访问网关 `/health` | 返回健康响应 |
| 父平台登录后打开工作区 | 交换 200，浏览器保存 Cookie，iframe 打开有权访问的工作区 |
| 未注册或停用用户打开入口 | 交换拒绝，父页面显示错误，旧 iframe 被清空 |
| 普通用户缺少工作区权限 | 父页面显示 Team/角色提示，不自动循环刷新 |
| 身份 Cookie 缺失且没有有效 token | 401，提示刷新或重新登录 |
| 非配置 Origin 请求交换 | 403，父平台来源不匹配 |
| 使用 purpose=key | 领取页能列出可见资源并按权限生成 Key |
| 领取不属于用户的 Team/MCP | 403，不返回 Key |
| 工作区 Cookie 直接调用 SSO 领取接口 | 校验失败，要求独立领取凭据 |
| 父平台退出或切换账号 | 旧 iframe 和保存的 token 清空，新请求按新账号交换 |
| 父平台不实现错误展示 | 交换失败不会自动弹窗；先补上第 3 节处理 |

浏览器开发者工具中检查交换请求的 Request Cookies、Origin、HTTP 状态和 Set-Cookie。
不要把真实 token、Key 或密码复制到日志和工单。

| 现象 | 优先检查 |
| --- | --- |
| 用户连接 18090 超时 | DNS、Nginx 监听和用户网段防火墙 |
| Nginx 返回 502 | Nginx 到网关 IP:4444 的连通性、容器端口映射 |
| 401，身份 Cookie 不存在 | 主机名是否相同、Cookie Path、Secure、浏览器限制 |
| CORS 拦截或 fetch 网络错误 | 父平台 Origin、ALLOWED_ORIGINS、代理错误和 HTTP/HTTPS |
| 交换成功，iframe 仍显示登录页 | 网关 Cookie 是否保存、账号 Team/角色、Cookie 是否过期 |
| iframe 被浏览器拒绝 | X-Frame-Options、CSP frame-ancestors 和父平台 frame-src |
| Key 领取提示刷新页面 | CSRF Cookie/header、Origin、五分钟领取校验是否到期 |
| Nginx 报 unknown variable | 移除未定义的 mcp_email/mcp_username，或确认 connection_upgrade 的 map |

网关完整部署步骤见 [内网网关部署说明](intranet-portal-gateway.md)。
项目 helper 和框架示例见 [父页面桥接说明](../../../infra/portal-session-bridge/README.md)。
