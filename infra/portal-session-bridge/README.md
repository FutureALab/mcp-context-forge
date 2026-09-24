# 父页面 Cookie 对接 ContextForge

此方案不需要 OIDC，也不调用 Spring Boot Session 接口。父页面写入 `mcp_username` 和 `mcp_email` Cookie。ContextForge 在启用 `PORTAL_SSO_ENABLED` 后，按这些 Cookie 查找或创建普通用户，并设置自己的浏览器凭据。这个流程是自定义 Cookie 登录桥接，并非 OAuth 协议。

## 页面流程

1. 父页面确认用户已经登录，然后写入 `mcp_username`、`mcp_email`。退出登录时删除这两个 Cookie。
2. 打开工作区前，父页面调用 `POST /auth/portal/exchange`，请求体为 `{"purpose":"login"}`。网关设置一小时的 HttpOnly `jwt_token` Cookie，并返回 `{"next":"/admin"}`。
3. 打开 API Key 领取页前，用同一个接口传 `{"purpose":"key"}`。网关设置五分钟的 HttpOnly `member_key_proof` Cookie，并返回 `{"next":"/admin/api-key"}`。此 Cookie 不能登录工作区。
4. 父页面将返回的 `next` 加载到 iframe。工作区或领取凭据过期时，iframe 通知父页面显示“请刷新页面”。刷新后重新交换 Cookie。

领取页仅接受已经注册、启用且绑定 `portal` 的账号。工作区首次登录可创建普通账号。已有其他登录方式的账号不会按邮箱自动绑定。平台管理员仍使用原有管理员登录入口。Team、虚拟 MCP 的可见性和领取权限仍由网关检查。

## Cookie 与网关配置

父页面和网关必须使用同一主机名的不同端口、同站点共享 Cookie 域名，或同源反向代理。Cookie 要覆盖网关请求路径。两个不同 IP 地址上的 HTTP 页面不能直接共享父页面 Cookie。以下配置以 `http://portal.intra.example` 为父页面 Origin：

```dotenv
EMAIL_AUTH_ENABLED=true
PORTAL_SSO_ENABLED=true
PORTAL_SSO_PARENT_ORIGIN=http://portal.intra.example
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

function setIdentity(user) {
  document.cookie = `mcp_username=${encodeURIComponent(user.username)}; Path=/; SameSite=Lax${cookieDomain}`
  document.cookie = `mcp_email=${encodeURIComponent(user.email)}; Path=/; SameSite=Lax${cookieDomain}`
}

async function open(purpose) {
  try {
    error.value = ''
    await openContextForge(frame.value, purpose, { gatewayOrigin })
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

在父页面取得已登录用户资料后调用 `setIdentity(user)`，然后再显示入口。父页面退出登录时，用相同的 `Path` 和 `Domain` 将两个 Cookie 的 `Max-Age` 设为 `0`。领取凭据过期后刷新父页面，再调用 `open('key')`。

## 验收

- 缺少任一身份 Cookie、错误 Origin、关闭桥接开关或停用账号时，交换必须失败。
- 工作区交换只设置 `jwt_token`；领取交换只设置 `member_key_proof`。只有工作区 Cookie 时，领取接口返回 401。
- 新用户首次登录不是管理员。领取前检查有效 Team、所选虚拟 MCP 和 `servers.use` 权限。
- 从父页面打开两个 iframe 入口，并使用领取的 API Key 调用所选 MCP。

前端可以改写 `mcp_username` 和 `mcp_email`。此模式不验证父平台登录状态，适用于用户已经接受该信任边界的受控内网部署。网关不会把 Cookie 中的管理员标记当作权限来源。
