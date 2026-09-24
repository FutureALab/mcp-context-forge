# 父页面 Cookie 对接 ContextForge

此方案不需要 OIDC，也不调用 Spring Boot Session 接口。父页面写入 `mcp_username` 和 `mcp_email` Cookie。ContextForge 在启用 `PORTAL_SSO_ENABLED` 后，只允许 MCP 已注册且启用的普通用户登录，并设置自己的浏览器凭据。这个流程是自定义 Cookie 登录桥接，并非 OAuth 协议。

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

## 本机按钮验证

在仓库根目录运行下面的命令。脚本启动网关和演示页，网关使用 4445 端口，避开已占用或被限流的 4444 端口。脚本只为本机演示关闭网关速率限制，不修改 `.env`。

```powershell
& 'I:\anaconda\envs\py312\python.exe' .\infra\portal-session-bridge\start_local.py
```

打开 `http://localhost:5173/infra/portal-session-bridge/local-test.html`。页面默认网关地址为 `http://localhost:4445`。脚本会检查两个服务是否就绪。

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
- 工作区交换只设置 `jwt_token`；领取交换只设置 `member_key_proof`。只有工作区 Cookie 时，领取接口返回 401。
- 未注册用户不能通过登录或领取入口，管理员不能通过 Cookie 桥接。领取前检查有效 Team、所选虚拟 MCP 和 `servers.use` 权限。
- 从父页面打开两个 iframe 入口，并使用领取的 API Key 调用所选 MCP。

前端可以改写 `mcp_username` 和 `mcp_email`。此模式不验证父平台登录状态，适用于用户已经接受该信任边界的受控内网部署。网关不会把 Cookie 中的管理员标记当作权限来源。
