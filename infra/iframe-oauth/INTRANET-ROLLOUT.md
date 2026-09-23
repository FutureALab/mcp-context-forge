# 内网父平台嵌入 ContextForge 与自助领取 API Key

本文提供两条路径：先用已有账号密码在父平台 iframe 中领取 Key；需要父平台与 ContextForge 自动单点登录时，再配置企业 OIDC。`infra/iframe-oauth` 是第二条路径的本机演示。

本方案假定 ContextForge 已部署并使用持久化数据库。现有部署、数据库和密钥保持不变。以下域名和客户端参数均为占位值，实施前必须替换。

## 最短路径：沿用账号密码领取

ContextForge 已提供 `/admin/api-key` 页面。它直接验证已注册用户的账号密码，查询可用 Team 与虚拟 MCP，并签发限定到所选虚拟 MCP 的 Key。**这一流程不要求用户先登录网关管理页，也不要求企业 OIDC、演示身份服务、额外的 `/embed/session` 接口或 Redis。**父平台登录只控制谁能看到入口；领取时用户仍需输入自己的 ContextForge 账号密码。

1. 在现有网关部署中启用 `EMAIL_AUTH_ENABLED=true`、`SELF_SERVICE_API_KEYS_ENABLED=true` 与 `MCPGATEWAY_UI_ENABLED=true`。保持现有数据库和认证密钥。确认用户账号已注册、启用，且属于至少一个有效 Team；个人 Team 可以用于领取公开虚拟 MCP 的 Key。
2. 父平台先用自己的会话判断用户是否已登录。仅向已登录用户显示“领取 MCP API Key”入口，并把 iframe 指向网关的 `http://mcp.intra.example/admin/api-key`。不向 iframe URL、请求头或父页面脚本传递用户邮箱、密码或 Token。
3. 允许父平台嵌入该网关页面：设置网关 `X_FRAME_OPTIONS=none`，并在网关 HTML 响应上添加仅允许父平台 Origin 的 `Content-Security-Policy: frame-ancestors http://portal.intra.example`。父页面如有 CSP，加入 `frame-src http://mcp.intra.example`。
4. HTTP 内网下，父平台与网关使用同站点子域名，或同一 IP 的不同端口。确认浏览器没有阻止网关的 CSRF Cookie。不同 IP 的跨站 iframe 在 HTTP 下无法可靠带上 Cookie。限制入口只供受控内网访问，因为 HTTP 会明文传输账号密码和 Key。
5. 用普通用户打开 iframe，选择“账号密码登录”，查询 Team 和虚拟 MCP，领取短期测试 Key，再调用一次所选 MCP 验证权限。

父页面只需如下入口；将地址替换为实际网关地址，并按父平台的登录状态控制其显示：

```html
<button id="mcp-key-button" type="button">领取 MCP API Key</button>
<iframe id="mcp-key-frame" title="领取 MCP API Key" hidden></iframe>
<script>
  document.getElementById("mcp-key-button").addEventListener("click", () => {
    const frame = document.getElementById("mcp-key-frame");
    frame.src = "http://mcp.intra.example/admin/api-key";
    frame.hidden = false;
  });
</script>
```

若不需要 iframe，直接把按钮做成打开 `/admin/api-key` 的链接，便可省去嵌入页面的响应头和 Cookie 限制。下面的 OIDC 配置只用于**父平台登录后免输 ContextForge 密码**的场景。

| 角色 | 本文示例 | 要求 |
| --- | --- | --- |
| 父平台 | `http://portal.intra.example` | 用户浏览器可访问，已有企业登录 |
| ContextForge | `http://mcp.intra.example` | 用户浏览器可访问，反向代理到网关 4444 |
| 企业 OIDC | `http://id.intra.example` | 浏览器可访问，网关容器可访问其 Token、Userinfo 和 JWKS 地址 |
| OIDC 客户端 ID | `contextforge-intranet` | 在企业 OIDC 中单独注册 |
| Provider ID | `corp-oidc` | 配置、回调 URL 和页面入口使用相同值 |

本文按用户现有的 HTTP 内网入口设计。父平台与网关使用同协议、同一站点下的不同子域名，浏览器将它们视为同站点、不同源。也可改用**同一个内网 IP 的不同端口**，例如父平台 `http://192.168.10.50:8080`、网关 `http://192.168.10.50:8081`。不能将两个不同 IP 当作同站点；跨站 iframe 的 Cookie 在 HTTP 下无法可靠使用。

两个应用分别保管自己的会话 Cookie。父平台不能把自己的 Cookie、邮箱或 Token 当作 ContextForge 的登录凭证。同一 IP 的不同端口**不隔离 Cookie**；父平台不能使用与网关相同的 Cookie 名称，例如 `jwt_token` 或 `sso_session_id`。不同子域名部署时，也要避免设置覆盖两个应用的共享 `Domain` 属性。HTTP 会明文传输登录信息、Cookie 和 API Key；因此只在受控内网网段提供入口，并限制路由、代理和端口的访问范围。

## 1. 部署边界与准备

1. 给父平台、ContextForge 和身份服务配置稳定的内网 DNS；若没有 DNS，使用同一 IP 的不同端口访问父平台和网关。
2. 放通浏览器到三个 HTTP 入口；放通网关到身份服务的 Token、Userinfo、JWKS 地址及原有数据库。
3. 将网关的后端 4444 端口限制为反向代理等必要来源。用户统一从 `http://mcp.intra.example` 访问。
4. 备份现有数据库、Compose 文件和 `.env`。保留原 `JWT_SECRET_KEY` 与 `AUTH_ENCRYPTION_SECRET`。
5. 核对当前网关镜像含 `/admin/api-key`、`/admin/api-key/sso/options` 与 `/admin/api-key/sso/issue`。

不要部署演示目录的 `server.mjs`、测试账号或 `.runtime/` 作为企业身份服务。它们只服务于本机功能验证。

## 2. 在企业 OIDC 中注册 ContextForge

新建一个 Web/OIDC 客户端，使用授权码流程，并按身份服务要求启用 PKCE。设置精确回调地址：

```text
http://mcp.intra.example/auth/sso/callback/corp-oidc
```

记录 Client ID、Client Secret，以及 OIDC discovery 文档中的 `issuer`、`authorization_endpoint`、`token_endpoint`、`userinfo_endpoint` 和 `jwks_uri`。`issuer` 必须与身份服务签发的 ID Token 完全一致。允许 `openid profile email` Scope，确保返回稳定的邮箱和已验证邮箱状态。先确认企业身份服务允许非 `localhost` 的 HTTP 回调；若它只接受 HTTPS，当前 HTTP 入口无法完成此 OIDC 流程。

父平台继续使用自己的 OIDC 客户端。父平台与 ContextForge 的两个客户端共享企业身份服务的登录会话，但不共享应用 Cookie。管理员权限应通过明确的角色或群组映射授予；普通用户默认使用 `platform_viewer`。
网关的本地管理员密码不等于企业身份服务密码；管理员若要走企业登录，需在身份服务中授予对应的管理员群组并配置网关角色映射。

如果内网当前**没有 OIDC 身份服务**，不要部署本机演示 `server.mjs` 代替它。可以先开启 `EMAIL_AUTH_ENABLED=true` 与 `SELF_SERVICE_API_KEYS_ENABLED=true`，让已注册用户在 `/admin/api-key` 选择“账号密码登录”领取；此时父平台登录不会自动登录网关。要实现一次登录两处使用，需要先让父平台和网关接入同一个正式身份服务。

## 3. 配置 ContextForge

在现有部署的 `.env` 中保存真实 Client Secret 和身份服务地址。下面只列新增参数；不要覆盖已有数据库和密钥配置：

```dotenv
MCP_PUBLIC_ORIGIN=http://mcp.intra.example
PORTAL_PUBLIC_ORIGIN=http://portal.intra.example
OIDC_CLIENT_ID=contextforge-intranet
OIDC_CLIENT_SECRET=替换为真实Secret
OIDC_ISSUER=http://id.intra.example/替换为真实Issuer路径
OIDC_AUTHORIZATION_URL=http://id.intra.example/替换为authorization_endpoint
OIDC_TOKEN_URL=http://id.intra.example/替换为token_endpoint
OIDC_USERINFO_URL=http://id.intra.example/替换为userinfo_endpoint
OIDC_JWKS_URI=http://id.intra.example/替换为jwks_uri
```

在实际部署的 `gateway.environment` 中追加或合并以下配置。示例使用 Compose 映射形式；若现有文件采用 `- NAME=value` 形式，请沿用原格式。同名环境变量只能保留一项。

```yaml
APP_DOMAIN: ${MCP_PUBLIC_ORIGIN}
ENVIRONMENT: staging
SSO_ENABLED: "true"
SSO_GENERIC_ENABLED: "true"
SSO_GENERIC_PROVIDER_ID: corp-oidc
SSO_GENERIC_DISPLAY_NAME: 内网统一认证
SSO_GENERIC_CLIENT_ID: ${OIDC_CLIENT_ID}
SSO_GENERIC_CLIENT_SECRET: ${OIDC_CLIENT_SECRET}
SSO_GENERIC_ISSUER: ${OIDC_ISSUER}
SSO_GENERIC_AUTHORIZATION_URL: ${OIDC_AUTHORIZATION_URL}
SSO_GENERIC_TOKEN_URL: ${OIDC_TOKEN_URL}
SSO_GENERIC_USERINFO_URL: ${OIDC_USERINFO_URL}
SSO_GENERIC_JWKS_URI: ${OIDC_JWKS_URI}
SSO_GENERIC_SCOPE: openid profile email
SSO_GENERIC_DEFAULT_ROLE: platform_viewer
SSO_AUTO_CREATE_USERS: "true"
AUTO_CREATE_PERSONAL_TEAMS: "true"
SELF_SERVICE_API_KEYS_ENABLED: "true"
MCPGATEWAY_UI_ENABLED: "true"
MCPGATEWAY_ADMIN_API_ENABLED: "true"
MCPGATEWAY_UI_EMBEDDED: "true"
SECURE_COOKIES: "false"
COOKIE_SAMESITE: lax
X_FRAME_OPTIONS: none
CORS_ENABLED: "true"
CORS_ALLOW_CREDENTIALS: "true"
ALLOWED_ORIGINS: '["http://portal.intra.example","http://mcp.intra.example"]'
```

`SSO_GENERIC_*`、`X_FRAME_OPTIONS` 和 `ALLOWED_ORIGINS` 必须传进网关容器。仓库根目录的 `docker-compose.yml` 只显式传入部分 SSO 设置，因此仅修改 `.env` 不够。先运行 `docker compose ... config --quiet`，再重建网关容器以加载新环境变量；普通 `restart` 不会更新容器环境。不要向日志或工单输出包含 Secret 的完整 Compose 配置。

已有部署且 Compose 服务名为 `gateway` 时，可在完成备份和配置修改后执行：

```bash
docker compose --env-file .env -f docker-compose.yaml config --quiet
docker compose --env-file .env -f docker-compose.yaml up -d --no-deps --force-recreate gateway
```

若实际 Compose 文件名或服务名不同，替换命令中的对应值。新部署应先启动数据库等依赖，再运行完整的 `up -d`。

**HTTP 的关键限制：**当前代码在 `ENVIRONMENT=production` 时强制为网关认证 Cookie 加 `Secure`，即使 `SECURE_COOKIES=false` 也无法经普通 HTTP 完成浏览器登录。因此该 HTTP 部署必须显式设 `ENVIRONMENT=staging` 或 `development`，并保持 `SECURE_COOKIES=false`、`COOKIE_SAMESITE=lax`。这属于当前代码的运行限制，不代表 HTTP 获得了生产环境的传输保护。若现有网关坚持 `ENVIRONMENT=production`，需先为入口接入 HTTPS。

以上 `ALLOWED_ORIGINS` 值须改成实际父平台和网关 Origin。它是完整的协议、域名与端口组合；使用非默认端口时必须包含端口。网关的 SSO 回调校验对非 `localhost` 的 HTTP 地址要求它出现在该精确白名单中。身份服务即使使用 HTTPS，也可与 HTTP 父平台和网关配合；其 URL 应按真实 OIDC discovery 文档填写。若 OIDC 服务器使用内网自签证书，先让网关容器信任企业 CA，不要关闭 TLS 校验。

若没有内网 DNS，按同一 IP 的两个端口替换本文示例：

```text
父平台 Origin:       http://192.168.10.50:8080
网关公开 Origin:     http://192.168.10.50:8081
OIDC 精确回调:       http://192.168.10.50:8081/auth/sso/callback/corp-oidc
APP_DOMAIN:          http://192.168.10.50:8081
ALLOWED_ORIGINS:     ["http://192.168.10.50:8080","http://192.168.10.50:8081"]
父页面 iframe 地址:  http://192.168.10.50:8081/admin/api-key
```

同时替换父页面链接、CSP `frame-src`/`connect-src`、网关 `frame-ancestors` 和企业 OIDC 客户端回调。`8081` 是反向代理的公开端口，网关后端仍可使用受限的 `4444`。不要只修改浏览器地址而遗漏 OAuth 回调或白名单。

首次 OIDC 登录可自动创建网关用户。**API Key 页的 OAuth 领取流程不会创建用户**。先让用户通过普通 SSO 登录一次，确认本地账号已建立；已有账号可由管理员维护。之后给用户有效 Team 成员关系和 `servers.use` 权限。个人 Team 可用于领取公开 MCP 的 Key；完全没有 Team 的用户不能领取。公开 MCP 不要求用户加入该 MCP 的所属 Team。

## 4. 配置网关反向代理

在 `mcp.intra.example` 的现有 HTTP 反向代理中，把普通请求转发到网关后端 4444。保留 `Host`、`X-Forwarded-Proto: http` 和客户端来源信息，确保回调 URL 与公开地址一致。流式 MCP 请求需要较长的读取超时和关闭响应缓冲。若网关目前直接向用户开放 4444，可将后端改为内部监听，并由反向代理承接原公开入口；也可给代理另设一个公开端口，并同步修改所有 Origin 与回调地址。

允许父平台嵌入网关页面，但只允许指定父平台 Origin。网关的 `X_FRAME_OPTIONS=none` 会关闭应用自身的限制；确认其他反向代理没有重新添加 `X-Frame-Options: DENY` 或 `SAMEORIGIN`。在 HTML 响应上设置：

```nginx
add_header Content-Security-Policy "frame-ancestors http://portal.intra.example" always;
```

此 CSP 只约束谁可以嵌入网关，不替换网关原有的脚本与资源 CSP。上线前检查实际响应头；若代理或网关另有 `frame-ancestors`，各策略会同时生效，必须避免冲突。

父平台若要在跨源页面中只读检查网关登录状态，可增加演示中相同用途的代理路径。该路径由 **网关域名的反向代理** 提供，不接收父页面传入的邮箱或 Token：

```nginx
location = /embed/session {
    limit_except GET { deny all; }
    proxy_pass http://127.0.0.1:4444/auth/email/me;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization "Bearer $cookie_jwt_token";
    add_header Cache-Control "no-store" always;
}
```

将 `proxy_pass` 改为代理实际可访问的网关地址。Nginx 若运行在容器内，`127.0.0.1` 指向 Nginx 容器自身，应改用容器网络中的网关服务地址。浏览器只收到身份信息，不收到 `jwt_token` 原文。网关 CORS 仅向 `http://portal.intra.example` 等显式允许的 Origin 返回带凭据的响应；不能使用 `*`。不要给该代理路径添加缓存。

## 5. 父页面必须修改的内容

现有演示页面位于 `public/index.html` 与 `public/portal.js`。企业父平台可直接按下表改造自身页面，无需复制演示的身份服务：

| 演示行为 | 内网父平台改法 |
| --- | --- |
| `/portal/me` 和 `/portal/login` | 使用父平台已有的会话查询与登录入口 |
| `/portal/logout` | 使用父平台已有的退出接口；另行决定是否退出网关和企业身份服务 |
| `location.hostname:18081` | 从父平台部署配置读取固定的 `http://mcp.intra.example` |
| `/embed/start.html` 内固定的 `intranet-demo` | 推荐先在顶层窗口完成网关 SSO，再直接加载网关页面 |
| “MCP 工作区”按钮 | 设置 iframe `src` 为 `${gatewayOrigin}/admin/` |
| “领取 API Key”按钮 | 设置 iframe `src` 为 `${gatewayOrigin}/admin/api-key` |
| 演示账号和本地 OIDC 提示 | 删除，改成企业登录与授权说明 |

父页面可使用以下最小示例。调用它之前，应先通过**父平台自己的后端会话**确认当前用户已登录。`/embed/session` 按上一节配置；不可用时应显示故障，不能根据父平台邮箱假定网关已登录。

```html
<a id="mcp-login" href="http://mcp.intra.example/admin/login"
   target="_blank" rel="noopener" hidden>连接 MCP 账号</a>
<button id="mcp-workspace" type="button">MCP 工作区</button>
<button id="mcp-key" type="button">领取 API Key</button>
<span id="mcp-status" role="status"></span>
<iframe id="mcp-frame" title="MCP 管理平台" hidden></iframe>
<script type="module" src="/assets/mcp-embed.js"></script>
```

```js
const gatewayOrigin = "http://mcp.intra.example";
const frame = document.querySelector("#mcp-frame");
const login = document.querySelector("#mcp-login");
const status = document.querySelector("#mcp-status");
let requestedPath = "/admin/";

async function showMcp(path) {
  requestedPath = path;
  try {
    const response = await fetch(`${gatewayOrigin}/embed/session`, {
      credentials: "include",
      cache: "no-store",
    });
    if (response.status === 401) {
      frame.hidden = true;
      login.hidden = false;
      status.textContent = "请先在新窗口连接 MCP 账号，然后返回本页。";
      return;
    }
    if (!response.ok) throw new Error("MCP 会话检查失败");
    login.hidden = true;
    frame.src = new URL(path, gatewayOrigin).href;
    frame.hidden = false;
    status.textContent = "MCP 已连接";
  } catch {
    frame.hidden = true;
    status.textContent = "暂时无法连接 MCP，请检查网关或网络。";
  }
}

document.querySelector("#mcp-workspace").onclick = () => showMcp("/admin/");
document.querySelector("#mcp-key").onclick = () => showMcp("/admin/api-key");
window.addEventListener("focus", () => {
  if (!login.hidden) void showMcp(requestedPath);
});
void showMcp(requestedPath);
```

父页面的 CSP 至少允许 `frame-src http://mcp.intra.example` 和 `connect-src 'self' http://mcp.intra.example`，同时保留父平台原有的其他来源。使用非默认端口时，CSP 也必须包含端口。CSS 应给 iframe 预留可用宽高。父页面不能读取 iframe DOM，这是浏览器跨源保护的正常结果。

上例先用顶层新窗口打开网关登录页。用户在网关选择“内网统一认证”；身份服务已有父平台登录会话时，通常无需再次输入密码。用户返回父页面时，页面重新检查网关会话并加载 iframe。这个入口避开了多数企业身份服务禁止在 iframe 内显示授权页的限制。若身份服务经验证允许完整的 iframe 授权流程，才将演示的 `embed/start.js` 改成真实网关 Origin、Provider ID、Issuer/授权地址，并部署到网关域名；不要保留固定的 `localhost` 或 `intranet-demo`。

## 6. 验收步骤

1. 在网关容器中确认 `sso_enabled`、`sso_generic_enabled`、`self_service_api_keys_enabled`、`secure_cookies` 与 `x_frame_options` 的实际值。不要打印 Client Secret。
2. 打开 `http://mcp.intra.example/auth/sso/providers`，确认出现预期身份服务，并且显示名正确。
3. 在父平台用普通用户登录。点“连接 MCP 账号”，完成网关 OIDC 回调，再返回父平台。
4. 点“MCP 工作区”和“领取 API Key”，确认 iframe 能显示页面，且无 CSP、Cookie 或 CORS 错误。
5. 在 Key 页点“检测账号并查询所属 Team”。确认能看到用户自己的 Team 和有权访问的公开 MCP。
6. 领取短期测试 Key，使用该 Key 对选中的虚拟 MCP 发起一次 MCP `initialize`。测试后撤销该 Key。
7. 用未注册用户、无 Team 用户、无 `servers.use` 用户和不可访问的私有 MCP 分别验证拒绝路径。
8. 验证父平台退出、网关退出与 Key 撤销是独立操作。退出浏览器会话不会自动撤销已发放的 API Key。

可用以下只读检查定位配置问题：

```bash
curl -fsS http://mcp.intra.example/health
curl -fsS http://mcp.intra.example/auth/sso/providers
curl -fsS -o /dev/null -w '%{http_code}\n' http://mcp.intra.example/admin/api-key
docker compose -f docker-compose.yaml logs --tail=100 gateway
docker compose -f docker-compose.yaml exec -T gateway python3 -c 'from mcpgateway.config import settings; names=["environment","app_domain","sso_enabled","sso_generic_enabled","self_service_api_keys_enabled","secure_cookies","x_frame_options","allowed_origins"]; [print(n, "=", getattr(settings,n)) for n in names]'
```

如果只有服务器本机能用，先检查 DNS、端口映射和防火墙。如果出现回调不匹配，核对 HTTP 协议、域名、端口、路径及 Provider ID，并确认身份服务接受 HTTP 回调。若登录后又返回登录页，检查 `ENVIRONMENT`、`Secure` Cookie 标志及 `SECURE_COOKIES`。若 iframe 空白，检查 `X-Frame-Options` 和所有 CSP `frame-ancestors` 响应头。若父页面会话检查失败，核对网关 Cookie、`ALLOWED_ORIGINS`、`Access-Control-Allow-Credentials` 和 `/embed/session` 代理。

## 7. 上线与回退

先在测试域名与测试 OIDC 客户端完成验收，再切换正式域名和正式客户端。记录网关镜像标签、配置版本和数据库备份时间。发布时仅重建网关及对应反向代理；不要清空数据库，也不要重新生成网关密钥。

回退父页面时移除两个 MCP 入口和 iframe。回退网关 SSO 时恢复上一版 Compose 与反向代理配置，再重建容器；保留数据库及已有用户。已发放的 API Key 不会随页面回退自动失效，需要按运维流程单独撤销。升级过数据库迁移时，先核对旧镜像与当前数据库是否兼容，再决定是否回退镜像。

相关源码：`run_gateway.py` 展示演示环境的网关变量；`public/portal.js` 展示父页面切换；`nginx.conf.template` 展示只读会话代理和 iframe 响应头。企业环境使用自己的 OIDC 和真实父平台，不部署演示账号与测试身份服务。
