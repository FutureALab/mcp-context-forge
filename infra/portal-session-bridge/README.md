# 使用现有 Spring Boot Session 登录 ContextForge

此方案不部署 OIDC。Vue 页面从现有 Spring Boot 会话取得一次性票据，然后向 ContextForge 兑换浏览器 Cookie。工作区票据建立网关登录会话；API Key 票据只允许领取，不建立网关会话。两个用途不能互换。

Spring Boot 项目不在此仓库中。下面的签发代码是需要接入实际登录会话的示例；不要在 Vue、Node 静态服务或浏览器中保存共享密钥。

## 1. 浏览器流程

1. 用户按原方式登录父平台，浏览器保留 Spring Boot 的 Session Cookie。
2. Vue 向 Spring Boot 发 `POST /api/mcp/ticket`，带 `credentials: include` 和 `purpose: login` 或 `purpose: key`。Spring Boot 从自己的服务端 Session 获取当前用户。
3. Spring Boot 签发有效期不超过 60 秒的 HS256 票据。票据包含 `iss`、`aud`、`sub`、`email`、`purpose`、`iat`、`exp`、`jti`。
4. Vue 将票据放在 JSON 请求体中，调用 `POST http://mcp.intra.example/auth/portal/exchange`。两个请求都不把票据放在 URL。
5. 网关核对签名、用途、时效、来源、用户状态和一次性 `jti`。登录用途返回 `jwt_token` Cookie；领取用途返回路径限于 `/admin/api-key` 的 `member_key_proof` Cookie。
6. Vue 根据网关返回的 `next` 加载 iframe。领取页在证明过期时通过 `postMessage` 请父页面重取票据。

新用户只在工作区登录时创建，默认不是管理员。领取页不创建账号。已有本地或其他身份服务账号不会仅凭相同邮箱自动关联；管理员须先完成受控迁移，不能直接把父平台票据映射成原管理员账号。父平台应向网关提供已核实且稳定的用户邮箱。

## 2. Spring Boot 签发端

以下代码展示票据格式。把 `session.getAttribute("LOGIN_USER")` 改成现有登录代码读取当前用户的方法。`PortalUser` 表示你现有的用户对象，其 `id` 应是稳定用户 ID，`email` 应是已核实的邮箱。

```java
@RestController
public class McpTicketController {
    private static final Base64.Encoder B64 = Base64.getUrlEncoder().withoutPadding();
    private final ObjectMapper json;
    private final byte[] secret;

    public McpTicketController(ObjectMapper json, @Value("${mcp.ticket-secret}") String secret) {
        if (secret.length() < 32) throw new IllegalArgumentException("mcp.ticket-secret must have at least 32 characters");
        this.json = json;
        this.secret = secret.getBytes(StandardCharsets.UTF_8);
    }

    public record TicketRequest(String purpose) {}

    @PostMapping("/api/mcp/ticket")
    public Map<String, String> ticket(@RequestBody TicketRequest request, HttpSession session) throws Exception {
        PortalUser user = (PortalUser) session.getAttribute("LOGIN_USER");
        if (user == null) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        if (!"login".equals(request.purpose()) && !"key".equals(request.purpose())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        long now = Instant.now().getEpochSecond();
        String header = B64.encodeToString(json.writeValueAsBytes(Map.of("alg", "HS256", "typ", "JWT")));
        String payload = B64.encodeToString(json.writeValueAsBytes(Map.of(
            "iss", "parent-portal", "aud", "contextforge-portal",
            "sub", user.id(), "email", user.email(), "purpose", request.purpose(),
            "iat", now, "exp", now + 60, "jti", UUID.randomUUID().toString()
        )));
        String unsigned = header + "." + payload;
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        String signature = B64.encodeToString(mac.doFinal(unsigned.getBytes(StandardCharsets.US_ASCII)));
        return Map.of("ticket", unsigned + "." + signature);
    }
}
```

所需 Java 类来自 `java.time.Instant`、`java.util.Base64`、`java.util.Map`、`java.util.UUID`、`java.nio.charset.StandardCharsets`、`javax.crypto.Mac`、`javax.crypto.spec.SecretKeySpec`、Jackson 和 Spring Web。Spring Boot 3 使用 `jakarta.servlet.http.HttpSession`。保留父平台原有的 Session Cookie 和 CSRF 防护；不要让前端传入邮箱或管理员标记。给 `/api/mcp/ticket` 响应加 `Cache-Control: no-store`，并限制只有已登录用户能调用。

## 3. ContextForge 配置

将相同的随机共享密钥分别放入 Spring Boot 和网关服务端配置。示例值只是变量名，不能照抄作为密钥：

```dotenv
EMAIL_AUTH_ENABLED=true
PORTAL_SSO_ENABLED=true
PORTAL_SSO_SHARED_SECRET=${从安全配置注入的随机值}
PORTAL_SSO_ISSUER=parent-portal
PORTAL_SSO_PARENT_ORIGIN=http://portal.intra.example
SELF_SERVICE_API_KEYS_ENABLED=true
MCPGATEWAY_UI_ENABLED=true
MCPGATEWAY_ADMIN_API_ENABLED=true
ENVIRONMENT=staging
SECURE_COOKIES=false
COOKIE_SAMESITE=lax
CORS_ENABLED=true
CORS_ALLOW_CREDENTIALS=true
ALLOWED_ORIGINS=["http://portal.intra.example","http://mcp.intra.example"]
```

将这些变量传入实际网关容器，再执行 Alembic 迁移到 `head` 并重建网关容器。`portal_ticket_uses` 表记录已兑换的 `jti`，防止多进程或多节点重复兑换。网关默认关闭此入口；密钥短于 32 字符、缺少父平台 Origin 或签发方时会拒绝兑换。

父页面与网关必须在同站点 HTTP 子域名，或同一 IP 的不同端口。若是不同 IP，HTTP iframe Cookie 可能被浏览器阻止。HTTP 会明文传输父平台会话、票据和 API Key，仅供受控内网使用。生产环境如设置 `ENVIRONMENT=production`，网关 Cookie 会带 `Secure`，入口需使用 HTTPS。

## 4. Vue 父页面

把 [portal-client.js](portal-client.js) 放进 Vue 项目，按现有 CSRF 规则传入 `ticketHeaders`。以下示例假定 Spring Boot API 与 Vue 页面同源；若不同源，还需按现有父平台配置处理 CORS 和 Session Cookie。

```vue
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { openContextForge, listenForKeyRefresh } from './portal-client.js'

const frame = ref(null)
const error = ref('')
const config = {
  gatewayOrigin: 'http://mcp.intra.example',
  ticketEndpoint: '/api/mcp/ticket',
  ticketHeaders: { 'X-CSRF-TOKEN': /* 使用父平台现有 CSRF token */ '' },
}
let stopListening

async function open(purpose) {
  try {
    error.value = ''
    await openContextForge(frame.value, purpose, config)
  } catch (cause) {
    error.value = cause.message
  }
}

onMounted(() => { stopListening = listenForKeyRefresh(frame.value, config, cause => { error.value = cause.message }) })
onBeforeUnmount(() => stopListening?.())
</script>

<template>
  <button @click="open('login')">MCP 工作区</button>
  <button @click="open('key')">领取 MCP API Key</button>
  <p role="alert">{{ error }}</p>
  <iframe ref="frame" title="MCP" />
</template>
```

只向已登录的父平台用户显示这两个按钮。网关必须允许该父页面的 `frame-ancestors`，父页面 CSP 必须允许网关的 `frame-src` 和 `connect-src`。Vue 不保存共享密钥，不解析票据来决定用户权限。

## 5. 验收

- 未登录父平台、关闭桥接开关、签名错误、过期、重复兑换、错误 Origin 与禁用用户必须被拒绝。
- 登录票据只能设置网关会话；领取票据只能设置领取凭据。只有 `jwt_token` 时，领取接口仍返回 401。
- 首次普通用户登录后检查个人 Team 和默认角色。领取前确认有效 Team、所选虚拟 MCP 的访问权及 `servers.use` 权限。
- 使用领取的 Key 调用所选 MCP；尝试其他虚拟 MCP 应被拒绝。

父平台实际的 Session 属性、用户对象、CSRF 头和内网 Origin 尚未提供。部署时需将示例接到真实代码，并完成这四项配置。
