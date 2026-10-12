# 父页面 Cookie 对接 ContextForge

适用分支：`feature_20260917_dev`。更新日期：2026-10-10。
内网麒麟部署步骤见 [网关部署文档](../../docs/docs/deployment/intranet-portal-gateway.md)。
独立父平台的原生 JavaScript 示例和登录鉴权接口见 [内网父平台对接指南](../../docs/docs/deployment/intranet-parent-integration.md)。

此方案不需要 OIDC，也不调用 Spring Boot Session 接口。父页面写入 `mcp_username` 和 `mcp_email` Cookie。ContextForge 在启用 `PORTAL_SSO_ENABLED` 后，只允许 MCP 已注册且启用的普通用户登录，并设置自己的浏览器凭据。这个流程是自定义 Cookie 登录桥接，并非 OAuth 协议。

## 对接前确认

本文描述当前已实现的 Cookie 桥接，不包含新的 OAuth、OIDC 或一次性票据服务。
首次交换按浏览器 Cookie 中的邮箱识别账号，网关没有向父平台后端验证登录会话。
来源检查和账号存在性检查不证明身份 Cookie 的真实性。
后续 token 的签名只能保护签发后的内容，不能修复首次身份冒用。
本方案适用于已经接受此信任边界的受控内网；需要强身份验证时，另行接入父平台后端会话校验。

上线前，父平台开发人员和网关管理员确认以下信息：

| 项目 | 当前接口要求 |
| --- | --- |
| 父平台地址 | 浏览器实际 Origin，例如 `http://devops.com`，不含路径 |
| 网关地址 | 示例为 `http://devops.com:18090`，可配置反向代理路径前缀 |
| 用户身份 | 父平台用户资料中的邮箱必须与 MCP 本地账号邮箱一致 |
| 账号状态 | MCP 账号已注册、启用，且不是平台管理员 |
| 工作区权限 | 账号具有有效 Team 和所需角色；交换成功不等于工作区授权成功 |
| Key 权限 | 启用自助领取，并给用户配置可见虚拟 MCP、Team 和相应权限 |
| 浏览器 | 通过 HTTP/HTTPS 打开父页面，不使用 `file://` |

## 页面流程

1. 父页面确认用户已经登录，然后写入 `mcp_username`、`mcp_email`。退出登录时删除这两个 Cookie。
2. 父页面调用 `POST /auth/portal/exchange`，请求体为 `{"purpose":"login"}` 或 `{"purpose":"key"}`。网关检查来源、身份 Cookie 和 MCP 已注册账号，返回 `token`、`expires_at`、`next`。
3. 父页面保存 `token`。默认有效期为 12 小时。下次请求传 `{"purpose":"login","token":"..."}` 或 `{"purpose":"key","token":"..."}`。有效 token 可直接复用；失效时网关重新检查身份 Cookie 并返回新 token。两者都无效时提示刷新页面。
4. 网关还会为 iframe 设置凭据。`login` 获取一小时的 HttpOnly `jwt_token`；`key` 获取五分钟的 HttpOnly `member_key_proof`。父页面将 `next` 加载到 iframe。

两个入口均只接受已经注册、启用的普通账号，未注册邮箱不会自动创建账号。账号以邮箱为唯一标识；`mcp_username` 必须存在，但不与显示名匹配。平台管理员仍使用原有管理员登录入口。Team、虚拟 MCP 的可见性和领取权限仍由网关检查。

## Cookie 与网关配置

父页面和网关必须使用同一主机名的不同端口、同站点共享 Cookie 域名，或同源反向代理。Cookie 要覆盖网关请求路径。两个不同 IP 地址上的 HTTP 页面不能直接共享父页面 Cookie。以下配置以 `http://portal.intra.example` 为父页面 Origin：

```dotenv
EMAIL_AUTH_ENABLED=true
PORTAL_SSO_ENABLED=true
PORTAL_SSO_PARENT_ORIGIN=http://portal.intra.example
PORTAL_SSO_TOKEN_TTL_MINUTES=720
SELF_SERVICE_API_KEYS_ENABLED=true
MCPGATEWAY_UI_ENABLED=true
MCPGATEWAY_ADMIN_API_ENABLED=true
ENVIRONMENT=staging
SECURE_COOKIES=false
COOKIE_SAMESITE=lax
X_FRAME_OPTIONS=none
CORS_ENABLED=true
CORS_ALLOW_CREDENTIALS=true
ALLOWED_ORIGINS=["http://portal.intra.example","http://mcp.intra.example"]
```

如果通过 `/mcp` 反向代理网关，还需设置 `APP_ROOT_PATH=/mcp`，并将 Vue 示例的 `gatewayOrigin` 改为 `http://portal.intra.example/mcp`。父页面的 Cookie 使用 `Path=/`。同站点子域名部署时，父页面还需给 Cookie 设置共同的 `Domain`。

网关默认发送禁止 iframe 嵌入的响应头。`X_FRAME_OPTIONS=none` 会关闭这项限制；只在受控内网入口使用此配置。

## Vue 父页面

将 [portal-client.js](portal-client.js) 复制到 Vue 项目。下面的例子假定父页面和网关共用 `intra.example` Cookie 域名。按实际域名修改 `cookieDomain` 与 `gatewayOrigin`；同主机名部署时可以去掉 `Domain` 属性。

```vue
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { openContextForge, listenForCredentialExpiry } from './portal-client.js'

const frame = ref(null)
const error = ref('')
const gatewayOrigin = 'http://mcp.intra.example'
const cookieDomain = '; Domain=intra.example'
let stopListening
const tokenKey = 'mcp-portal-token'

function setIdentity(user) {
  document.cookie = `mcp_username=${encodeURIComponent(user.username)}; Path=/; SameSite=Lax${cookieDomain}`
  document.cookie = `mcp_email=${encodeURIComponent(user.email)}; Path=/; SameSite=Lax${cookieDomain}`
}

async function open(purpose) {
  try {
    error.value = ''
    const result = await openContextForge(frame.value, purpose, {
      gatewayOrigin,
      token: sessionStorage.getItem(tokenKey),
    })
    sessionStorage.setItem(tokenKey, result.token)
  } catch (cause) {
    error.value = cause.message
  }
}

onMounted(() => {
  stopListening = listenForCredentialExpiry(frame.value, { gatewayOrigin }, cause => { error.value = cause.message })
})
onBeforeUnmount(() => stopListening?.())
</script>

<template>
  <button @click="open('login')">MCP 工作区</button>
  <button @click="open('key')">领取 MCP API Key</button>
  <p role="alert">{{ error }}</p>
  <iframe ref="frame" title="MCP" />
</template>
```

在父页面取得已登录用户资料后调用 `setIdentity(user)`，然后显示入口。退出登录时，删除两个身份 Cookie，调用 `sessionStorage.removeItem(tokenKey)`，并卸载 iframe。用户切换时先清除旧 token，再写入新 Cookie。token 有效时可复用；过期时 `open()` 自动从 Cookie 重新取得授权。iframe 提示凭据过期时，刷新父页面并重新打开入口。

## HTTP 接口约定

父页面使用 `POST <网关地址>/auth/portal/exchange`。配置了 `APP_ROOT_PATH=/mcp` 时，
请求地址为 `<网关来源>/mcp/auth/portal/exchange`。
必须设置 `Content-Type: application/json` 和 `credentials: include`。
浏览器自动发送 `Origin` 和 Cookie，前端不要手工设置这两个请求头。

首次请求：

```json
{"purpose":"login"}
```

请求 `purpose=login` 或 `purpose=key` 时，网关都设置一小时的 HttpOnly `jwt_token`。
工作区和领取页共用登录会话。已登录时直接打开 `/admin/api-key`，无需再次交换或设置 `member_key_proof`。
Key 页仍需选择 Team、虚拟 MCP 和有效期，再通过自助领取接口获得实际 API Key。

成功响应的结构如下。这里的 token 是占位示例：

```json
{
  "next": "/admin",
  "token": "<父平台授权token>",
  "expires_at": 1791604800
}
```

`next` 是相对网关地址的页面路径。Key 页为 `/admin/api-key`。
使用路径前缀时，两者也包含该前缀。
`expires_at` 是 Unix 秒时间戳，前端显示时使用 `new Date(expires_at * 1000)`。
不要将响应中的 token 当成 MCP API Key；它有独立的签名密钥派生、用途和 audience。
登录 JWT 由浏览器保存，父页面不读取它。

复用请求：

```json
{"purpose":"key","token":"<上次返回的父平台授权token>"}
```

一个有效父平台 token 可以用于工作区和 Key 页两种交换。
有效 token 的复用不会延长它的 `expires_at`，但会重新设置对应 iframe 凭据。
网关每次检查 token 对应账号是否存在、启用且为普通账号。
token 失效时，网关尝试从身份 Cookie 重新授权，并返回新的 token。
有效 token 可以在身份 Cookie 缺失时使用；这是当前接口的实际行为。
如果请求携带的 `mcp_email` 与 token 所属账号不同，网关放弃旧 token，改按新 Cookie 匹配账号。

父平台 token 默认有效期为 720 分钟，可用 `PORTAL_SSO_TOKEN_TTL_MINUTES` 调整。
工作区和 Key 页 Cookie 的有效期不会随此配置变成 12 小时。
接口每分钟限制 20 次请求，不要用高频轮询维持会话。

## 父页面完整接入顺序

1. 完成父平台自身登录，从父平台可信用户资料中取得用户名和邮箱。
2. 写入身份 Cookie，再调用 `openContextForge()`；不要先加载受保护的 iframe。
3. 将返回的 token 保存到当前用户的 `sessionStorage` 项下，同时保存过期时间用于显示。
4. 后续打开工作区或 Key 页时传回 token，始终以交换接口结果为准。
5. 交换失败时隐藏或清空旧 iframe，显示错误；不要保留上个用户的页面。
6. 监听网关消息，提示重新打开入口或联系管理员，避免无限自动重试。
7. 用户切换或父平台退出时，先清理 token、身份 Cookie 和 iframe，再处理下一账号。

同主机名、不同端口部署的父页面可以这样写身份 Cookie：

```javascript
function writeMcpIdentity(user) {
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `mcp_email=${encodeURIComponent(user.email)}; Path=/; SameSite=Lax${secure}`;
  document.cookie = `mcp_username=${encodeURIComponent(user.username)}; Path=/; SameSite=Lax${secure}`;
}

function clearMcpIdentity() {
  document.cookie = 'mcp_email=; Max-Age=0; Path=/; SameSite=Lax';
  document.cookie = 'mcp_username=; Max-Age=0; Path=/; SameSite=Lax';
  sessionStorage.removeItem('mcp-portal-token');
  sessionStorage.removeItem('mcp-portal-expires-at');
}
```

调用时使用父平台已登录用户对象，不从 URL 参数取得邮箱。
如果写 Cookie 时用了 `Domain`，删除时也必须带相同 `Domain`；否则会残留另一份 Cookie。
Cookie 不按端口隔离，命名需与父平台现有 Cookie 避免冲突。
不同主机名的父页面不能写入网关主机专属 Cookie；共享子域名部署需使用可共享的父域。
两个无共同 Cookie 域的地址不能直接使用本文首次 Cookie 交换。

保存返回值的调用示例：

```javascript
import { openContextForge, listenForCredentialExpiry } from './portal-client.js';

const frame = document.querySelector('#mcp-frame');
const config = { gatewayOrigin: 'http://devops.com:18090' };

async function openMcp(purpose) {
  try {
    const result = await openContextForge(frame, purpose, {
      ...config,
      token: sessionStorage.getItem('mcp-portal-token'),
    });
    sessionStorage.setItem('mcp-portal-token', result.token);
    sessionStorage.setItem('mcp-portal-expires-at', String(result.expiresAt));
  } catch (error) {
    frame.src = 'about:blank';
    throw error;
  }
}

const stopListening = listenForCredentialExpiry(frame, config, error => {
  frame.src = 'about:blank';
  console.error(error.message);
});
```

在组件卸载时调用 `stopListening()`。产品页面用可见提示替换示例中的 `console.error`。
页面刷新后 `sessionStorage` 仍存在，但关闭当前标签页后不再保留。
在新标签页首次进入时，从身份 Cookie 重新交换即可。
不要将 token 放入 URL、日志、埋点或 iframe 的查询参数。
现有 helper 给 Key 页添加的 `portal=success` 只是界面标记，不是授权凭据。

## iframe 消息、退出和账号切换

网关通过 `postMessage` 向配置的父页面 Origin 发送以下消息：

| 消息 type | 含义 | 父页面处理 |
| --- | --- | --- |
| `contextforge-portal-cookie-required` | iframe 需要重新取得凭据 | 提示刷新父页面并重新交换 |
| `contextforge-portal-access-denied` | 账号缺少工作区授权 | 提示管理员配置 Team 和角色 |

消息包含 `purpose=login` 或 `purpose=key`。
现有 helper 同时验证 `event.origin` 和 `event.source === frame.contentWindow`。
保留这两个检查，不接受其他窗口伪造的续期通知。

父平台退出仅删除本地 token 和身份 Cookie，**不会撤销已经签发的网关凭据**。
现有网关会话最长仍可持续一小时，工作区和 Key 页共用该会话。
父平台 token 没有逐个 token 的撤销接口；只要仍有效且账号可用，它仍能进行交换。
因此，清理浏览器存储不等于服务端单点退出，已经领取的 MCP API Key 也不会随父平台退出失效。
需要即时联动退出时，必须另行实现父平台 token 撤销和网关会话退出，不属于本文现有功能。

切换用户时先将 iframe 设为 `about:blank`，清理旧凭据，再写入新用户 Cookie 并重新交换。
同一浏览器的网关会话 Cookie 在多个标签页间共享；多账号同时打开会互相影响。

## 联调验收与排查

在浏览器开发者工具的 Network 中观察交换请求；不要复制真实 token 到工单。

| 检查 | 预期结果 |
| --- | --- |
| 首次 `purpose=login` | HTTP 200，返回三项字段，工作区 iframe 成功打开 |
| 复用 token 且不带身份 Cookie | HTTP 200，重新设置对应凭据 |
| 用同一 token 打开 Key 页 | 只建立领取校验；领取后显示 API Key 和 MCP 客户端配置 |
| token 过期但身份 Cookie 有效 | HTTP 200，返回新 token 和新过期时间 |
| token 与 Cookie 所属邮箱不同 | 按 Cookie 中新账号交换，不保留旧用户 iframe |
| 未注册、停用、管理员账号 | 拒绝父平台桥接；管理员走独立登录入口 |
| 工作区缺少 Team 或角色 | 显示访问拒绝，不陷入自动刷新循环 |
| 普通账号领取 Key | 只能访问当前账号有权限的 Team 和虚拟 MCP |
| 父平台退出 | 清空本地存储和 iframe；按上文记录服务端剩余有效期 |

常见错误：

| 现象 | 检查方法 |
| --- | --- |
| 404 父平台登录未启用 | 检查 `PORTAL_SSO_ENABLED`，重建容器应用配置 |
| 503 未配置父平台来源 | 检查 `PORTAL_SSO_PARENT_ORIGIN` |
| 403 来源不匹配 | 比对真实 `Origin` 的协议、域名、端口；不能填写页面路径 |
| 401 登录已过期 | 查看请求 Cookie 是否有两项身份字段，检查 Domain、Path 和 token |
| 403 账号拒绝 | 检查注册、停用状态和平台管理员标记 |
| `Failed to fetch` | 检查 DNS、端口、CORS 预检、HTTPS 页面请求 HTTP、Nginx |
| HTTP 200 但 iframe 回登录页 | 查看 `Set-Cookie`、浏览器拒绝原因和下一请求的 Cookie |
| iframe 拒绝显示 | 检查网关及 Nginx 的 `X-Frame-Options`、CSP 和 iframe sandbox |
| 429 | 停止循环重试，等待限流窗口；不要关闭业务环境限流排障 |

跨来源请求需允许明确的父页面 Origin、POST、Content-Type 和凭据；不要使用 `*` 代替来源。
参考部署采用同主机名、不同端口，浏览器仍会执行 CORS 检查。
跨站 iframe 的 Cookie 还受浏览器第三方 Cookie 策略影响。
`SameSite=None; Secure` 不能保证所有浏览器都接受，部署前用目标浏览器验证。
参见 [MDN 第三方 Cookie 说明](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies)。

## 本机按钮验证

在仓库根目录运行下面的命令。脚本启动网关和演示页，网关使用 4445 端口。默认连接 `.env` 中的数据库；先确认该数据库已经启动。脚本只为本机演示关闭网关速率限制，不修改 `.env`。复制命令时不要包含 PowerShell 提示符 `PS D:\...>`。

```powershell
& 'I:\anaconda\envs\py312\python.exe' .\infra\portal-session-bridge\start_local.py
```

如果提示 `PostgreSQL localhost:5432 未启动或无法连接`，可以先启动自己的 PostgreSQL，以使用其中已有的账号。只想立即测试页面和接口时，改用独立的 SQLite 演示数据库：

```powershell
& 'I:\anaconda\envs\py312\python.exe' .\infra\portal-session-bridge\start_local.py --demo-db
```

演示账号填 `Demo User` 和 `demo@example.com`。脚本会创建个人空间和一个公开虚拟 MCP。演示数据库保存在系统临时目录；它与 `.env` 中的 PostgreSQL 数据互不影响。脚本会打印演示数据库的路径。该账号只用于本机演示，不能代表内网的真实账号。

打开 `http://localhost:5173/infra/portal-session-bridge/local-test.html`。页面默认网关地址为 `http://localhost:4445`。脚本会检查两个服务是否就绪。脚本返回命令提示符后，网关和页面服务仍在后台运行。

也可以手动启动两个服务：

1. 在第一个窗口启动网关。下面的变量只对当前窗口有效；本机基础环境的 `python` 缺少 `uvicorn`，因此使用已安装项目依赖的 `py312` 环境。这里指定网关监听 4445 端口。

   ```powershell
   $env:PORTAL_SSO_ENABLED = 'true'
   $env:PORTAL_SSO_PARENT_ORIGIN = 'http://localhost:5173'
   $env:ALLOWED_ORIGINS = '["http://localhost:5173","http://localhost:4445"]'
   $env:HOST = '127.0.0.1'
   $env:PORT = '4445'
   $env:X_FRAME_OPTIONS = 'none'
   $env:SECURE_COOKIES = 'false'
   $env:RATE_LIMITING_ENABLED = 'false'
   $env:PYTHONIOENCODING = 'utf-8'
   & 'I:\anaconda\envs\py312\python.exe' -m mcpgateway
   ```

2. 在第二个窗口运行 `python -m http.server 5173 --bind localhost`。
3. 打开 `http://localhost:5173/infra/portal-session-bridge/local-test.html`。不要双击 HTML 文件或使用 `file://`。

如果使用 `make dev`，网关端口为 8000，请把页面中的网关地址改为 `http://localhost:8000`。输入 MCP 已注册普通用户的用户名和邮箱，依次点击“打开工作区”和“打开 API Key 领取页”。页面展示首次授权、token 复用和到期时间，并在 iframe 中加载网关。工作区仍要求有效 Team 和工作区角色；没有 Team 的账号可通过身份验证，但不能进入工作区。

## 验收

- 首次授权缺少任一身份 Cookie、错误 Origin、关闭桥接开关或停用账号时，交换必须失败。
- 有效 token 可在没有身份 Cookie 时复用；过期 token 须由身份 Cookie 重新授权。
- 两种交换均设置 `jwt_token`。领取接口验证现有登录会话，不要求独立的 `member_key_proof`。
- 过期、撤销、伪造的会话和 API token 均不能领取 Key。会话限定的 Team 仍限制领取范围。
- 未注册用户不能通过登录或领取入口，管理员不能通过 Cookie 桥接。领取前检查有效 Team、所选虚拟 MCP 和 `servers.use` 权限。
- 从父页面打开两个 iframe 入口，并使用领取的 API Key 调用所选 MCP。

前端可以改写 `mcp_username` 和 `mcp_email`。此模式不验证父平台登录状态，适用于用户已经接受该信任边界的受控内网部署。网关不会把 Cookie 中的管理员标记当作权限来源。
