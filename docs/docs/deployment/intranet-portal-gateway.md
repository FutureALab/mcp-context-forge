# 内网麒麟系统部署网关（外部 PostgreSQL、父页面 iframe、中文界面）

适用分支：`feature_20260917_dev`。更新日期：2026-10-10。
本文面向麒麟服务器上的离线容器部署。实际操作系统版本和架构必须先确认。
本文未在真实麒麟主机执行验收；下列健康检查和父页面联调是上线验收步骤。

父平台开发人员同时阅读 [父页面接口及示例](../../../infra/portal-session-bridge/README.md)。
本文采用当前 Cookie 登录桥接，不要求父平台部署 OAuth/OIDC 服务。
网关没有验证父平台后端会话；启用前确认可以接受浏览器身份 Cookie 的信任边界。

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

### 1.1 确认麒麟版本、CPU 架构和容器环境

以运维账号执行以下只读检查，记录结果：

```bash
cat /etc/os-release
uname -m
uname -r
command -v docker
command -v nginx
docker version
docker compose version
systemctl is-active docker
df -h /opt /var/lib/docker
free -h
timedatectl status
ss -lnt
```

`/var/lib/docker` 是常用默认目录；已修改 Docker 数据目录时，检查实际目录的可用空间。
磁盘应容纳镜像压缩包、解压后的镜像层、应用日志和至少一份回滚镜像。
CPU、内存按并发量配置，先在测试环境测量，不把固定配置当成容量承诺。
服务器及客户端应使用内网时间同步，时间偏差会影响 token 有效期判断。

| `uname -m` | 选择发布包 | 说明 |
| --- | --- | --- |
| `x86_64` | `linux-amd64` | 常见 x86 服务器 |
| `aarch64` | `linux-arm64` | ARM64 服务器 |
| `loongarch64` 或其他 | 无对应现成发布包 | 停止导入，需另行构建和验证该架构 |

不能仅凭“麒麟系统”选择 amd64 包；麒麟存在多种 CPU 架构版本。
镜像架构不匹配可能导致 `exec format error`。
官方版本架构信息见 [麒麟 V10 版本说明](https://product.kylinos.cn/static/img/2024/12/e6ba94c6864e40d71ba86fa62eec80cc.pdf)。

Docker Engine、Compose v2、Nginx、OpenSSL、curl、tar 和 SHA-256 校验工具需提前安装。
安装包由运维按麒麟版本、架构及内网软件源准备，包括依赖包。
不要直接套用其他发行版仓库地址，也不要在隔离网络运行在线安装脚本。
Docker 的安装文档按发行版区分，参见 [Docker 安装说明](https://docs.docker.com/engine/install/)。
使用单位批准的容器运行环境；本文命令按 Docker Engine 和 Compose v2 编写。
如果现场只提供 Podman，需要另行验证 Compose、网络和权限，不能直接认为等价。

若运维已安装但未启动 Docker，经运维确认后执行：

```bash
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

后续命令要求当前账号有 Docker 权限；否则逐条使用 `sudo`，不要开放 Docker TCP 管理端口。
不要为消除权限错误修改 Docker socket 为所有用户可写。
Nginx 已运行时保留现有配置，不重装、不停父平台服务。

### 1.2 网络和离线交付清单

| 通路 | 用途 | 开放范围 |
| --- | --- | --- |
| 用户电脑 → 父平台 80 或 443 | 父平台页面 | 现有用户网段 |
| 用户电脑 → 网关 Nginx 18090 | iframe、交换接口、MCP | 需要使用网关的内网网段 |
| Nginx → 网关 127.0.0.1:4444 | 反向代理 | 同主机，不对用户网段开放 |
| 网关容器 → PostgreSQL 5432 或实际端口 | 数据访问 | 数据库管理员批准的地址 |

父平台和网关示例共用 `devops.com` 主机名，父平台为 80 端口，网关为 18090。
所有用户电脑应解析到 Nginx 的实际内网 IP。不要只在服务器自身配置 hosts 后就宣布 DNS 可用。
Nginx 在其他主机时，下面的回环端口映射不可直接使用，需调整网络和访问控制。

离线交付至少准备以下文件：

```text
mcpgateway-<版本>-linux-<架构>.tar.gz
mcpgateway-<版本>-linux-<架构>.tar.gz.sha256
contextforge-deployment-docs-<版本>-linux-<架构>.tar.gz
contextforge-deployment-docs-<版本>-linux-<架构>.tar.gz.sha256
```

文档包包含本文、根目录部署指南、父页面 README 和 `portal-client.js`。
它不是 Docker 镜像归档，不要对文档包执行 `docker load`。
父平台需自行集成 helper；部署网关不会自动修改父平台页面。

### 1.3 校验并导入镜像

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

将镜像包及校验文件传入此目录，再设置实际文件名：

```bash
cd /opt/contextforge
BUNDLE='mcpgateway-实际版本-linux-amd64.tar.gz'
DOCS_BUNDLE='contextforge-deployment-docs-实际版本-linux-amd64.tar.gz'
sha256sum -c "${BUNDLE}.sha256"
sha256sum -c "${DOCS_BUNDLE}.sha256"
mkdir -p deployment-docs
tar -xzf "$DOCS_BUNDLE" -C deployment-docs
docker load -i "$BUNDLE"
docker image ls
```

ARM64 主机将两个文件名中的 `amd64` 改成实际的 `arm64` 包。
两次校验均显示 `OK` 后才导入。
使用 `docker load` 输出中的固定标签，不依赖以后会改变的 `latest`。
发布镜像包可能同时包含 Phoenix；本指南仅运行网关，无需启动 Phoenix 或 PostgreSQL 容器。

确认已导入镜像的架构和入口：

```bash
IMAGE='<实际网关固定标签>'
docker image inspect "$IMAGE" --format '{{.Os}}/{{.Architecture}}'
docker run --rm --pull=never --network none --entrypoint /bin/sh "$IMAGE" \
  -c 'test -x /app/docker-entrypoint.sh'
```

### 1.4 准备外部 PostgreSQL

数据库管理员提供地址、端口、库名、账号、密码、TLS 要求和备份方式。
建议使用专用数据库，应用账号拥有应用对象及迁移权限。
数据库防火墙和 `pg_hba.conf` 允许网关的实际出口地址；该地址通常为容器主机地址。
数据库域名必须在容器内也可解析；主机 hosts 条目不会自动复制进容器。
不要连接父平台业务数据库执行初始化。
已有网关数据库先做可恢复备份，再启动新版本迁移。

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
OBSERVABILITY_ENABLED=false
OTEL_ENABLE_OBSERVABILITY=false
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

## 6. 创建用户、分配工作区并接入父页面

管理员从独立网关登录页登录，父页面桥接拒绝平台管理员账号。
管理员创建或导入普通用户；用户邮箱与父平台用户资料保持一致。
本地账号需要保持启用状态，不会因为父页面发送新邮箱而自动注册。

给普通用户分配有效 Team 和工作区角色，并检查虚拟 MCP 的可见性及调用权限。
父页面交换接口成功只说明桥接凭据签发成功，不能替代资源可见性和 RBAC 检查。
使用真实普通测试账号完成联调，不使用平台管理员模拟普通用户。

父平台前端实施顺序：

1. 从自身登录状态取得当前用户名和邮箱。
2. 写入 `mcp_username`、`mcp_email`，保证 `Path=/`，覆盖网关交换路径。
3. 集成文档包中的 `portal-client.js`，把 `gatewayOrigin` 设置为网关对外地址。
4. 工作区传 `purpose=login`，API Key 页面传 `purpose=key`。
5. 交换成功后保存响应 token，加载 helper 生成的 iframe 地址。
6. 交换失败时清空旧 iframe，显示错误，避免持续刷新。
7. 切换用户或退出时清理身份 Cookie、保存的 token 和 iframe。

默认父平台 token 有效期为 12 小时，工作区 Cookie 为一小时，Key 校验 Cookie 为五分钟。
复用父平台 token 不延长其到期时间；过期后可从有效身份 Cookie 重新交换。
身份 Cookie 清除不撤销已签发 token、网关会话或 MCP API Key。
需要即时单点退出时，另行设计服务端撤销；本文没有实现该能力。
完整请求、响应、Vue 示例和消息约定见 [父页面对接文档](../../../infra/portal-session-bridge/README.md)。

## 7. 防火墙、SELinux 和 HTTPS

先确认现场使用的防火墙和网段策略，不要停止防火墙或关闭 SELinux。
使用 firewalld 时，先检查当前 zone、规则和接口：

```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --list-all
getenforce
```

运维仅给需要使用网关的内网网段开放 18090；数据库端口仍由数据库侧限制来源。
示例规则需要替换网段和实际 zone；先应用临时规则，验证后再持久化：

```bash
sudo firewall-cmd --zone=public \
  --add-rich-rule='rule family="ipv4" source address="10.20.0.0/16" port port="18090" protocol="tcp" accept'
sudo firewall-cmd --zone=public --permanent \
  --add-rich-rule='rule family="ipv4" source address="10.20.0.0/16" port port="18090" protocol="tcp" accept'
```

不使用 firewalld 的现场由运维按实际防火墙实施等价规则。
SELinux 拒绝访问时查看 AVC 记录，由运维配置 Nginx 监听端口、上游连接及挂载目录标签。
可用工具存在时执行 `sudo ausearch -m AVC -ts recent`；不要用 `setenforce 0` 作为部署步骤。
共享目录和独占目录的标签策略不同，`:Z` 示例只适合本部署独占的挂载文件。

HTTP 示例只适用于批准的内网环境。接入 HTTPS 时同步修改：

- Nginx 配置证书和 TLS 监听，父平台与网关均使用 HTTPS。
- `APP_DOMAIN`、`PORTAL_SSO_PARENT_ORIGIN`、`ALLOWED_ORIGINS` 和父页面 `gatewayOrigin`。
- `ENVIRONMENT=production`、`SECURE_COOKIES=true`、`I18N_COOKIE_SECURE=true`。
- 父页面身份 Cookie 添加 `Secure`，确认浏览器接受 Cookie。

同主机名方案可继续使用 `COOKIE_SAMESITE=lax`。
不同站点的 HTTPS iframe 需评估第三方 Cookie 限制；不要只改为 `none` 就认为自动登录完成。
已有 Nginx 若追加 `X-Frame-Options: DENY` 或 CSP `frame-ancestors 'none'`，网关配置无法覆盖它。
由运维在最终响应中配置仅允许父页面嵌入的策略，并检查没有冲突响应头。

## 8. 验收清单和故障定位

| 验收项 | 通过标准 |
| --- | --- |
| 镜像 | 校验值匹配，架构正确，固定标签已记录 |
| 配置 | Compose `config --quiet` 通过，没有输出真实秘密 |
| 数据库 | 初始化或迁移成功，没有连接、权限或多 head 错误 |
| 服务 | 容器运行且健康，主机和其他用户电脑均可访问 `/health` |
| 中文 | gettext 输出 `语言`，浏览器指定中文后正常显示 |
| 普通账号工作区 | 首次交换、token 复用、Team 和角色均有效 |
| API Key | 只展示授权范围内的 MCP，领取后真实客户端可完成 MCP 调用 |
| 拒绝路径 | 未注册、停用、管理员及错误 Origin 均拒绝桥接 |
| 父平台退出 | 本地 token、Cookie 和 iframe 已清理，记录剩余有效期限制 |
| 重建 | 重建容器后仍正常，数据库、密钥和中文配置保持一致 |

只通过 `/health` 不能证明父页面登录、API Key 或 MCP 调用正常。
MCP 客户端使用 Key 页生成的 Streamable HTTP 或 SSE 配置进行真实调用。
记录虚拟 MCP、客户端版本、调用结果和验收时间，不记录完整 API Key。

| 故障 | 定位顺序 |
| --- | --- |
| `exec format error` | 主机架构 → 镜像架构 → 重新导入正确包 |
| Compose 命令不存在 | 已批准的 Compose v2 安装路径、版本和权限 |
| `permission denied` | Docker socket 权限、挂载权限、SELinux AVC |
| 容器不断重启 | `docker compose logs --tail=100 gateway`，先修启动错误 |
| PostgreSQL 连不上 | 容器 DNS、路由、出口地址、防火墙、`pg_hba.conf`、TLS |
| Nginx 502 | 容器健康、回环 4444、上游地址和 SELinux |
| 用户电脑连接超时 | DNS 解析、防火墙网段、Nginx 18090 监听 |
| iframe 登录失败 | 交换状态、Origin、身份 Cookie、网关 Set-Cookie、嵌入响应头 |
| 中文仍是英文 | 语言 Cookie、`?lang=zh-CN`、镜像 MO 文件、挂载覆盖 |
| `/health` 成功但页面拒绝 | 普通账号状态、Team、角色和浏览器会话 |

常用只读诊断：

```bash
cd /opt/contextforge
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail=100 gateway
sudo nginx -t
sudo ss -lntp
curl --max-time 5 -fsS http://127.0.0.1:4444/health
curl --max-time 5 -fsS http://devops.com:18090/health
```

日志可能包含业务信息，发送工单前脱敏。
不要发送完整 `.env`、token、API Key、Cookie 或数据库连接串。

## 9. 升级、回滚和日常维护

### 9.1 升级前备份

记录当前网关镜像固定标签和数据库备份点。
备份 `.env`、Compose、Nginx 配置及自定义翻译，确保备份目录权限为 700。
数据库管理员完成一致性备份，并确认恢复方法及恢复到独立库的演练结果。
备份数据库时保留匹配的 `JWT_SECRET_KEY` 和 `AUTH_ENCRYPTION_SECRET`。
不要只备份容器文件系统，也不要重新生成密钥作为升级步骤。

```bash
cd /opt/contextforge
STAMP=$(date +%Y%m%d-%H%M%S)
install -d -m 700 "backup/$STAMP"
cp -p .env compose.yaml "backup/$STAMP/"
```

翻译存在自定义挂载时，另行复制该文件到备份目录。
Nginx 配置路径和 PostgreSQL 备份命令由现场运维、数据库管理员确定。

### 9.2 升级并复验

校验并导入新架构匹配的镜像包，保留旧固定标签，不执行 `docker image prune`。
只修改 `.env` 中的 `GATEWAY_IMAGE`；保留数据库、密钥、账号和对外地址配置。
使用内置中文包时无需挂载；已有 MO 挂载会覆盖新镜像中文包，升级翻译需同步更新它。

```bash
cd /opt/contextforge
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f compose.yaml up -d --pull never --no-build
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f compose.yaml logs --tail=100 gateway
curl --max-time 5 -fsS http://devops.com:18090/health
```

容器启动后重新执行第 8 节验收，尤其是父页面 token 复用、Key 领取及真实 MCP 调用。
修改 `.env` 后只执行 `restart` 不会更新容器配置；使用上述 `up -d` 重新创建发生配置变化的服务。

### 9.3 回滚

无数据库不兼容变更时，将 `GATEWAY_IMAGE` 改回旧固定标签，执行相同的 Compose 启动命令。
若新版本迁移改变数据库结构，不能仅切回旧镜像。
暂停业务写入，由数据库管理员恢复升级前备份，再配套恢复旧镜像和配置。
不要未经确认直接运行 Alembic downgrade；数据恢复需要单独评估。

普通维护仅停止本项目服务：

```bash
docker compose --env-file .env -f compose.yaml stop gateway
docker compose --env-file .env -f compose.yaml up -d --pull never --no-build
```

禁止在日常重启中删除数据库、卷或密钥。
应用日志通过现有日志系统保留，运维定期检查磁盘、数据库备份和证书到期时间。
