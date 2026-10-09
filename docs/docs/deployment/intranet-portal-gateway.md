# 内网独立部署网关（HTTP、外部 PostgreSQL、中文界面）

本文部署一个 ContextForge 网关容器，复用现有 PostgreSQL 和 Nginx，不部署 OIDC、Phoenix 或本机演示页。
示例中，父平台是 `http://devops.com`，网关对外地址是 `http://devops.com:18090`。
两者使用同一主机名、不同端口。将示例域名、数据库地址和镜像标签替换为实际值。

```text
浏览器 ── http://devops.com:80 ──────> 现有父平台
       └─ http://devops.com:18090 ──> 现有 Nginx ──> 网关容器:4444 ──> 外部 PostgreSQL
```

此对接使用父页面的 `mcp_username`、`mcp_email` Cookie 和网关的 `/auth/portal/exchange`。
它是本项目的 Cookie 登录桥接，不依赖标准 OAuth/OIDC 服务。
网关只接受已注册、启用的普通 MCP 账号；平台管理员从网关原有登录入口登录。

## 1. 准备镜像和数据库

在内网 Linux 主机安装 Docker Engine、Compose v2，并准备包含本项目 Cookie 桥接功能的固定版本镜像。
离线环境先将镜像归档传入主机，再执行 `docker load -i <镜像归档>`。
记下 `docker image ls` 显示的**完整镜像标签**；下文的 `GATEWAY_IMAGE` 使用这个标签。

提前准备一个 PostgreSQL 数据库和可建表、迁移的专用账号。
网关容器必须能连接数据库的内网地址；数据库部署在其他主机时，`DATABASE_URL` 不能填 `localhost`。
已有 ContextForge 数据库先备份，并保留原 `JWT_SECRET_KEY` 和 `AUTH_ENCRYPTION_SECRET`。

创建部署目录：

```bash
mkdir -p /opt/contextforge/translations/zh_CN/LC_MESSAGES
cd /opt/contextforge
```

## 2. 配置 `.env`

将以下模板保存为 `/opt/contextforge/.env`。所有尖括号占位值都必须替换。
首次部署可用 `openssl rand -hex 32` 分别生成 `JWT_SECRET_KEY` 和 `AUTH_ENCRYPTION_SECRET`。
现有部署沿用原密钥；更换密钥会使原 token 失效，并可能导致已存储凭据无法解密。

```dotenv
GATEWAY_IMAGE=<已导入的固定版本镜像标签>
DATABASE_URL=postgresql+psycopg://mcp_gateway:<URL编码后的密码>@<数据库内网地址>:5432/mcp
JWT_SECRET_KEY=<随机生成的密钥>
AUTH_ENCRYPTION_SECRET=<随机生成的密钥>
PLATFORM_ADMIN_EMAIL=<管理员邮箱>
PLATFORM_ADMIN_PASSWORD=<管理员初始密码>
DEFAULT_USER_PASSWORD=<新用户初始密码>
BASIC_AUTH_PASSWORD=<独立的基础认证密码>

APP_DOMAIN=http://devops.com:18090
AUTH_REQUIRED=true
EMAIL_AUTH_ENABLED=true
PUBLIC_REGISTRATION_ENABLED=false
MCPGATEWAY_UI_ENABLED=true
MCPGATEWAY_ADMIN_API_ENABLED=true
SELF_SERVICE_API_KEYS_ENABLED=true
MCPGATEWAY_UI_AIRGAPPED=true
MCPGATEWAY_SKIP_MIGRATIONS=false
CACHE_TYPE=database
RATE_LIMITING_REDIS_ENABLED=false

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
I18N_ENABLED=true
I18N_DEFAULT_LOCALE=zh-CN
I18N_COOKIE_SECURE=false
```

密码中的 `@`、`#`、`%`、`$` 等字符要先进行 URL 编码，再写入 `DATABASE_URL`。
限制 `.env` 的读取权限：`chmod 600 /opt/contextforge/.env`。
不要将真实 `.env` 提交到 Git。

`PORTAL_SSO_PARENT_ORIGIN` 必须是浏览器实际发送的父页面 Origin。默认 HTTP 80 端口写作
`http://devops.com`，不写路径，也不写 `:80`。`ALLOWED_ORIGINS` 包含父页面 Origin。
网关对外的 `18090` 是 Nginx 端口，不要求容器也监听 18090。

此示例使用 HTTP。应用在 `ENVIRONMENT=production` 时强制为登录 Cookie 加 `Secure`；
因此 HTTP 部署使用 `staging` 和 `SECURE_COOKIES=false`。
改用 HTTPS 后，调整对外 URL、Origin、Cookie 设置和 Nginx 配置。

## 3. 准备并挂载中文翻译包

当前项目的 `Containerfile` 在构建时编译 `messages.po`，将 `messages.mo` 放在镜像的
`/app/mcpgateway/translations/zh_CN/LC_MESSAGES/`。镜像自带该文件时，直接启用
`I18N_ENABLED=true` 和 `I18N_DEFAULT_LOCALE=zh-CN` 就能使用中文。
若只使用镜像内置翻译，可跳过导出操作，并删除下面 Compose 示例中的 `volumes` 挂载。

如需在镜像升级后保留指定的中文翻译版本，可从已导入的镜像导出编译文件，再只读挂载：

```bash
cd /opt/contextforge
IMAGE='<与 .env 中 GATEWAY_IMAGE 相同的镜像标签>'
CONTAINER_ID=$(docker create "$IMAGE")
docker cp \
  "$CONTAINER_ID:/app/mcpgateway/translations/zh_CN/LC_MESSAGES/messages.mo" \
  ./translations/zh_CN/LC_MESSAGES/messages.mo
docker rm "$CONTAINER_ID"
test -s ./translations/zh_CN/LC_MESSAGES/messages.mo
chmod 755 ./translations ./translations/zh_CN ./translations/zh_CN/LC_MESSAGES
chmod 644 ./translations/zh_CN/LC_MESSAGES/messages.mo
```

若 `docker cp` 报文件不存在，说明该镜像没有编译后的中文包。
请使用包含本项目翻译目录的镜像，或先用 `python -m mcpgateway.scripts.i18n compile` 编译
`mcpgateway/translations/zh_CN/LC_MESSAGES/messages.po`。
不要把 `.po` 直接挂载为 `.mo`，也不要用空文件占位。

挂载目标必须是容器内的**文件路径**：

```text
/app/mcpgateway/translations/zh_CN/LC_MESSAGES/messages.mo
```

## 4. 运行独立网关

将下面内容保存为 `/opt/contextforge/compose.yaml`：

```yaml
services:
  gateway:
    image: ${GATEWAY_IMAGE:?Set GATEWAY_IMAGE in .env}
    pull_policy: never
    restart: unless-stopped
    env_file: .env
    environment:
      HOST: 0.0.0.0
      PORT: "4444"
    ports:
      - "127.0.0.1:4444:4444"
    volumes:
      - ./translations/zh_CN/LC_MESSAGES/messages.mo:/app/mcpgateway/translations/zh_CN/LC_MESSAGES/messages.mo:ro
```

此配置仅启动网关。`127.0.0.1:4444` 只供**同一台主机上的 Nginx** 转发，
不直接向内网用户开放容器端口。若 Nginx 在另一个容器或主机，改用双方可达的地址与网络。
启用 SELinux 且宿主机拒绝读取挂载文件时，按主机策略处理文件标签；
Docker Compose 的 bind mount 可在 `:ro` 后追加 `,Z`。

在已有 Nginx 中，为 `devops.com:18090` 配置反向代理，目标指向
`http://127.0.0.1:4444`。转发原始 `Host`、请求路径和 `Origin`，并保留
`X-Forwarded-Proto`、`X-Forwarded-For`。不要把 18090 请求代理到父平台的 80 端口。
如需代理 MCP 流式请求，关闭该入口的响应缓冲并设置合适的读取超时。
与网关容器在同一台主机上的 Nginx 可使用下面的独立 `server` 配置：

```nginx
server {
    listen 18090;
    server_name devops.com;

    location / {
        proxy_pass http://127.0.0.1:4444;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

保留现有父平台 80 端口配置。保存后执行 `nginx -t`，通过后重载 Nginx。

启动与检查：

```bash
cd /opt/contextforge
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f compose.yaml up -d --pull never --no-build
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail=100 gateway
curl -fsS http://127.0.0.1:4444/health
curl -fsS http://devops.com:18090/health
```

首次启动会按 `MCPGATEWAY_SKIP_MIGRATIONS=false` 初始化或迁移数据库。
不要输出完整的 `docker compose config`，其中可能包含数据库密码。

## 5. 验证中文和父页面接入

先验证容器实际加载了挂载文件：

```bash
docker compose -f compose.yaml exec -T gateway python3 -c \
  'import gettext,pathlib,mcpgateway; p=pathlib.Path(mcpgateway.__file__).parent/"translations"; t=gettext.translation("messages",localedir=str(p),languages=["zh_CN"]); print(t.gettext("Language"))'
```

应输出 `语言`。再用浏览器打开 `http://devops.com:18090/admin?lang=zh-CN`。
默认中文只在没有语言 Cookie、用户偏好或浏览器语言优先级覆盖时生效；
`?lang=zh-CN` 可明确指定中文。未翻译的条目可能仍显示英文。

父页面完成自身登录后，写入 `mcp_username` 和 `mcp_email` Cookie，且 Cookie 的 `Path=/`。
同为 `devops.com` 时无需设置 Cookie `Domain`；Cookie 不按端口隔离。
父页面以 `credentials: include` 请求 `http://devops.com:18090/auth/portal/exchange`，
工作区使用 `purpose=login`，Key 页面使用 `purpose=key`。
网关返回 `next`、12 小时的 `token` 和 `expires_at`；父页面将 `next` 装入 iframe。
网关另外设置工作区一小时会话 Cookie，或 Key 页五分钟校验 Cookie。
用户退出或切换账号时，父页面清除身份 Cookie、保存的 token 和 iframe。
详细接口约定见仓库中的 `infra/portal-session-bridge/README.md`。

从**另一台内网电脑**完成以下验收：

1. 访问 `http://devops.com:18090/health`，确认 DNS、Nginx 和网关连通。
2. 用管理员邮箱和密码访问网关登录页，并确认中文界面可切换。
3. 用一个已注册、启用的普通账号从父页面打开工作区和 API Key 领取页。
4. 验证未注册账号、停用账号或管理员账号不能通过父页面 Cookie 桥接。
5. 验证用户退出父平台后，父页面不再复用旧 token 或旧 iframe。

常见故障：`403 父平台来源不匹配` 表示父页面实际 Origin 与
`PORTAL_SSO_PARENT_ORIGIN` 不一致；`401 登录已过期` 表示身份 Cookie 未到达网关；
iframe 显示登录页时，先检查交换接口是否成功，再检查网关 Cookie、Nginx 转发和浏览器响应头。
