# ContextForge 内网部署与用户访问指南（使用现有 PostgreSQL）

## 最新父页面与麒麟部署入口（2026-10-10）

父平台 iframe 和内网麒麟服务器部署，使用以下最新文档：

- [麒麟离线部署、Nginx、中文包、验收及升级回滚](docs/docs/deployment/intranet-portal-gateway.md)
- [父页面 Cookie 交换、token 复用、Vue 示例、退出及故障排查](infra/portal-session-bridge/README.md)
- [父页面前端 helper](infra/portal-session-bridge/portal-client.js)

最新发布工作流会将上述材料打成独立文档包，并附带 SHA-256 校验文件。
文档包名为 `contextforge-deployment-docs-<版本>-linux-<架构>.tar.gz`。
镜像归档仍用 `docker load` 导入；文档包用 `tar -xzf` 解压，两者不能混用。
已下载的旧发布包不会自动获得新文档或编译后的中文，需使用更新后重新构建的包。

最新 iframe 方案只运行网关，复用外部 PostgreSQL 和现有 Nginx，不要求 Phoenix 或 OIDC。
首次桥接信任浏览器身份 Cookie，没有验证父平台后端会话；详细信任边界见父页面文档。
下面保留原网关加 Phoenix 部署方案，适用于明确需要 Phoenix 的现场。

适用分支：`feature_20260917_dev`。文档日期：2026-09-18。

适用场景：已下载 Docker Release Bundle，部署到 Linux 内网服务器，连接内网已有 PostgreSQL。
部署完成后，其他内网电脑和服务器通过部署服务器的内网 IP 或内网域名访问服务。
本方案不需要公网 IP，也不需要将服务发布到互联网。
本文提供独立的 Compose 配置，不需要下载整个项目，也不需要部署 PostgreSQL 容器。

**已经按旧版文档部署的环境：直接执行第 5.1、5.3、6 节。**
保留当前 `.env`、数据库地址、密码和密钥，不要重新执行第 4 节的密钥生成命令。
功能开关靠 Compose 配置生效；中文还需要编译后的 `messages.mo` 文件。
本文将中文文件保存到宿主机并挂载，重启或重建容器后都保留，无需每次重新编译。

## 1. 部署前准备

内网服务器需要预装并启动 Docker Engine，安装 Docker Compose v2 插件。
下面的命令使用 Bash，并需要 `openssl`、`sha256sum` 和 `curl`。
离线服务器请提前准备与操作系统匹配的安装包，或让运维安装这些工具。

```bash
docker version
docker compose version
uname -m
```

如果服务器使用 `docker-compose` 命令，将本文所有 `docker compose` 替换为 `docker-compose`。
两种写法都应使用支持本文配置的 Compose 版本。

- `x86_64`：使用 `linux-amd64` 镜像包。
- `aarch64`：使用 `linux-arm64` 镜像包。
- 当前用户需要拥有 Docker 操作权限。
- 镜像内已包含应用运行环境，不需要在主机安装 Python、Node 或项目依赖。

部署结构：

```text
内网用户浏览器/客户端 ──4444──> ContextForge ──5432──> 内网已有 PostgreSQL
                    │
                    └──4317──> Phoenix
运维浏览器 ──6006──────────────────> Phoenix 链路页面
```

网关和 Phoenix 通过 Docker 内部网络通信，不需要对外映射 4317。
允许用户网段和管理网段访问服务器 TCP 4444，允许可信管理网段访问 TCP 6006。
本文没有为 Phoenix 配置登录认证，6006 仅允许可信管理网段访问。
数据库侧需要允许容器实际使用的出口地址访问数据库，通常为部署服务器地址。
使用固定内网 IP 或稳定的内网 DNS 名称，避免用户地址随服务器重启而变化。

## 2. 准备安装文件

将文件放入部署目录，例如 `/opt/contextforge`。
如果 Actions 下载的是 ZIP，先解压外层 ZIP。

```text
/opt/contextforge/
├── mcpgateway-<版本>-linux-amd64.tar.gz
├── mcpgateway-<版本>-linux-amd64.tar.gz.sha256
├── DEPLOY-INTRANET.md
├── docker-compose.yaml    # 按第 5 节创建
├── .env                   # 按第 4 节创建，已有部署保留原文件
└── translations/zh_CN/LC_MESSAGES/messages.mo  # 按第 5.1 节生成
```

其中 `.tar.gz` 是镜像归档，`.sha256` 是校验文件，不是第二个镜像包。
当前分支的镜像归档包含 ContextForge 和 Phoenix。无需携带 PostgreSQL 镜像。

```bash
mkdir -p /opt/contextforge
cd /opt/contextforge
```

传入文件后，设置实际的归档名。下面的占位名称需要替换：

```bash
BUNDLE='mcpgateway-实际版本-linux-amd64.tar.gz'
sha256sum -c "${BUNDLE}.sha256"
docker load -i "$BUNDLE"
docker image ls
```

校验必须显示 `OK`，然后再导入。
`docker load` 可以直接读取 `.tar.gz`，不需要手工解压内部镜像层。

记录导入输出中的镜像标签。网关优先使用固定版本标签，例如
`mcpgateway/mcpgateway:dev-实际提交号`，避免以后导入新包时 `latest` 指向变化。
Phoenix 标签必须与包内标签一致；未修改构建参数时通常为 `arizephoenix/phoenix:latest`。

## 3. 准备现有 PostgreSQL

请数据库管理员提供以下信息：

| 项目 | 示例或要求 |
| --- | --- |
| 地址 | 内网 IP 或容器可解析的数据库域名 |
| 端口 | 通常为 `5432` |
| 数据库 | 建议专用空数据库 `mcp` |
| 账号 | 建议专用账号 `mcp_gateway` |
| 权限 | 数据库连接、目标 schema 使用和建表、迁移所需的对象修改权限 |
| TLS | 按数据库要求配置 SSL 模式和证书 |

推荐由 `mcp_gateway` 拥有专用数据库和应用对象。
不要连接其他业务正在使用的数据库执行首次初始化。
网关首次启动会创建应用表并执行迁移。

如复用已有 ContextForge 数据库，先备份数据库，并保留原部署的 `AUTH_ENCRYPTION_SECRET`。
已有管理员密码不会因为修改 `.env` 中的初始化密码而自动重置。

## 4. 创建 `.env`

以下命令仅适用于全新部署。已有部署必须保留原 `.env`，不要重新生成密钥。
命令使用禁止覆盖模式，已有 `.env` 时会失败，不会覆盖原文件。

```bash
cd /opt/contextforge
(
  set -e
  umask 077
  set -C
  JWT_VALUE=$(openssl rand -hex 32)
  ENC_VALUE=$(openssl rand -hex 32)
  ADMIN_VALUE=$(openssl rand -hex 24)
  USER_VALUE=$(openssl rand -hex 24)
  BASIC_VALUE=$(openssl rand -hex 24)
  cat > .env <<EOF
GATEWAY_IMAGE=mcpgateway/mcpgateway:latest
PHOENIX_IMAGE=arizephoenix/phoenix:latest
GATEWAY_PORT=4444
PHOENIX_UI_PORT=6006

GATEWAY_DATABASE_URL='postgresql+psycopg://mcp_gateway:REPLACE_PASSWORD@REPLACE_DB_HOST:5432/mcp'

JWT_SECRET_KEY=${JWT_VALUE}
AUTH_ENCRYPTION_SECRET=${ENC_VALUE}
PLATFORM_ADMIN_EMAIL=admin@example.com
PLATFORM_ADMIN_PASSWORD=Aa1!${ADMIN_VALUE}
DEFAULT_USER_PASSWORD=Aa1!${USER_VALUE}
BASIC_AUTH_PASSWORD=Aa1!${BASIC_VALUE}

SECURE_COOKIES=false
LOG_LEVEL=INFO
EOF
)
```

编辑 `.env`，完成以下修改：

1. 将 `GATEWAY_IMAGE` 改成第 2 节确认的固定版本标签。
2. 确认 `PHOENIX_IMAGE` 与实际导入标签一致。
3. 将数据库主机、端口、数据库名、用户名和密码替换为实际信息。
4. 可将 `PLATFORM_ADMIN_EMAIL` 改为本单位管理员邮箱。

数据库地址示例结构如下，不能直接使用其中的占位值：

```dotenv
GATEWAY_DATABASE_URL='postgresql+psycopg://mcp_gateway:URL编码后的密码@数据库地址:5432/mcp'
```

密码中的特殊字符必须进行 URL 编码，例如 `@` → `%40`，`#` → `%23`，`%` → `%25`。
保留外层单引号，避免 Compose 对值中的 `$` 执行变量插值。
数据库在另一台机器时，使用数据库内网地址，不能使用 `localhost`。

如果数据库要求 TLS，按管理员要求添加连接参数。
例如 `?sslmode=require` 要求加密；需要验证服务器身份时使用 `verify-full` 并配置可信证书。
证书文件必须挂载到容器，连接参数中的证书路径必须指向容器内路径。

`SECURE_COOKIES=false` 适用于本文直接通过 HTTP 访问的配置。
正式接入 HTTPS 后改成 `true`，再执行第 6 节启动命令使配置生效。

妥善备份 `.env`。尤其不要随意更换 `AUTH_ENCRYPTION_SECRET`，否则已存储凭据可能无法解密。
不要将真实 `.env` 提交到 Git 或发送到公共聊天、工单中。

## 5. 创建 `docker-compose.yaml`

### 5.1 先生成并持久化中文翻译

在部署目录执行。已有服务不用停止；新环境也不需要先启动网关或连接数据库。
下面使用本地镜像中的翻译源文件编译，不联网，不安装依赖，不启动应用。

先查看本地镜像，并将 `GATEWAY_IMAGE` 设置为当前 `.env` 中同名变量的实际值。
不要执行 `source .env`，数据库连接串等内容不一定适合直接作为 Shell 脚本执行。

```bash
cd /opt/contextforge
docker image ls
GATEWAY_IMAGE='mcpgateway/mcpgateway:latest'
```

上面的 `latest` 仅为示例。使用固定版本时，必须替换为该版本标签。

```bash
(
  set -e
  mkdir -p ./translations/zh_CN/LC_MESSAGES
  if [ -f ./translations/zh_CN/LC_MESSAGES/messages.mo ]; then
    cp -p ./translations/zh_CN/LC_MESSAGES/messages.mo \
      "./translations/zh_CN/LC_MESSAGES/messages.mo.bak.$(date +%Y%m%d-%H%M%S)"
  fi
  docker run --rm --pull=never --network none \
    --user "$(id -u):$(id -g)" \
    --entrypoint python3 \
    -v "$PWD/translations/zh_CN/LC_MESSAGES:/catalogs:Z" \
    "$GATEWAY_IMAGE" -c '
import gettext
from pathlib import Path
import mcpgateway
from mcpgateway.scripts.i18n import compile_catalog
source = Path(mcpgateway.__file__).parent / "translations/zh_CN/LC_MESSAGES/messages.po"
target = Path("/catalogs/messages.mo")
compile_catalog(source, target)
with target.open("rb") as stream:
    catalog = gettext.GNUTranslations(stream)
assert catalog.gettext("Language") == "语言"
print("中文编译和校验成功")
'
  test -s ./translations/zh_CN/LC_MESSAGES/messages.mo
  chmod 755 ./translations ./translations/zh_CN ./translations/zh_CN/LC_MESSAGES
  chmod 644 ./translations/zh_CN/LC_MESSAGES/messages.mo
)
```

必须看到“中文编译和校验成功”，且命令没有报错，再继续。
如果镜像中缺少 `mcpgateway.scripts.i18n` 或 `messages.po`，需要使用包含中文源码的分支镜像。
不要创建空文件来绕过错误。
这一步只需首次部署或升级翻译时执行，普通重启、重建无需重复。

### 5.2 全新部署的完整配置

将下面内容保存为 `/opt/contextforge/docker-compose.yaml`。
这是完整的外部 PostgreSQL 配置，可代替仓库中包含 PostgreSQL 容器的示例文件。
已有部署按第 5.3 节合并修改，不要覆盖原有定制配置。

```yaml
name: mcpgateway-phoenix

services:
  phoenix:
    image: ${PHOENIX_IMAGE:?Set PHOENIX_IMAGE in .env}
    pull_policy: never
    restart: unless-stopped
    environment:
      PHOENIX_WORKING_DIR: /data
      PHOENIX_LOG_LEVEL: info
    ports:
      - "${PHOENIX_UI_PORT:-6006}:6006"
    volumes:
      - phoenix-data:/data
    healthcheck:
      test:
        - CMD
        - python3
        - -c
        - "import urllib.request; urllib.request.urlopen('http://localhost:6006/health', timeout=5)"
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s

  gateway:
    image: ${GATEWAY_IMAGE:?Set GATEWAY_IMAGE in .env}
    pull_policy: never
    restart: unless-stopped
    depends_on:
      phoenix:
        condition: service_healthy
    environment:
      HOST: 0.0.0.0
      PORT: "4444"
      DATABASE_URL: ${GATEWAY_DATABASE_URL:?Set GATEWAY_DATABASE_URL in .env}
      MCPGATEWAY_SKIP_MIGRATIONS: "false"
      JWT_SECRET_KEY: ${JWT_SECRET_KEY:?Set JWT_SECRET_KEY in .env}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET:?Set AUTH_ENCRYPTION_SECRET in .env}
      PLATFORM_ADMIN_EMAIL: ${PLATFORM_ADMIN_EMAIL:-admin@example.com}
      PLATFORM_ADMIN_PASSWORD: ${PLATFORM_ADMIN_PASSWORD:?Set PLATFORM_ADMIN_PASSWORD in .env}
      DEFAULT_USER_PASSWORD: ${DEFAULT_USER_PASSWORD:?Set DEFAULT_USER_PASSWORD in .env}
      BASIC_AUTH_PASSWORD: ${BASIC_AUTH_PASSWORD:?Set BASIC_AUTH_PASSWORD in .env}
      AUTH_REQUIRED: "true"
      EMAIL_AUTH_ENABLED: "true"
      SELF_SERVICE_API_KEYS_ENABLED: "true"
      PUBLIC_REGISTRATION_ENABLED: "false"
      I18N_ENABLED: "true"
      I18N_DEFAULT_LOCALE: "zh-CN"
      MCPGATEWAY_UI_ENABLED: "true"
      MCPGATEWAY_ADMIN_API_ENABLED: "true"
      SECURE_COOKIES: ${SECURE_COOKIES:-false}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      OTEL_ENABLE_OBSERVABILITY: "true"
      OTEL_TRACES_EXPORTER: otlp
      OTEL_EXPORTER_OTLP_ENDPOINT: http://phoenix:4317
      OTEL_EXPORTER_OTLP_PROTOCOL: grpc
      OTEL_EXPORTER_OTLP_INSECURE: "true"
      OTEL_SERVICE_NAME: mcp-gateway
      OTEL_RESOURCE_ATTRIBUTES: openinference.project.name=mcp-gateway,deployment.environment=intranet
      OTEL_SQLALCHEMY_INSTRUMENTATION_ENABLED: "false"
    ports:
      - "${GATEWAY_PORT:-4444}:4444"
    volumes:
      - ./translations/zh_CN/LC_MESSAGES/messages.mo:/app/mcpgateway/translations/zh_CN/LC_MESSAGES/messages.mo:ro,Z
    healthcheck:
      test:
        - CMD
        - python3
        - -c
        - "import httpx; httpx.get('http://127.0.0.1:4444/health', timeout=5).raise_for_status()"
      interval: 15s
      timeout: 10s
      retries: 12
      start_period: 60s

volumes:
  phoenix-data:
```

说明：

- 只有 `gateway` 和 `phoenix` 两个服务，不包含 PostgreSQL 容器或依赖。
- `.env` 中的配置通过 `environment` 显式传入容器。
- `GATEWAY_DATABASE_URL` 映射为应用读取的 `DATABASE_URL`。
- Phoenix 地址使用 Docker 服务名 `phoenix`，不要改成 `localhost`。
- 禁止自动拉取镜像，启动只使用已经导入的本地镜像。
- 中文文件从宿主机只读挂载；`:Z` 为启用 SELinux 的主机设置容器访问标签。
- 不发布开放注册入口；账号由管理员创建，已有用户可领取权限范围内的 MCP Key。

### 5.3 已有部署的更新步骤

先完成第 5.1 节，再备份现有 Compose：

```bash
cp -p docker-compose.yaml "docker-compose.yaml.bak.$(date +%Y%m%d-%H%M%S)"
```

在现有 `gateway.environment` 中增加或更新下面五项；同名项仅保留一次：

```yaml
      SELF_SERVICE_API_KEYS_ENABLED: "true"
      EMAIL_AUTH_ENABLED: "true"
      I18N_ENABLED: "true"
      I18N_DEFAULT_LOCALE: "zh-CN"
      PUBLIC_REGISTRATION_ENABLED: "false"
```

在 `gateway` 下增加挂载，`volumes` 与 `environment` 同级。
已有 `volumes` 时，只追加这一条，不要重复声明整个键：

```yaml
    volumes:
      - ./translations/zh_CN/LC_MESSAGES/messages.mo:/app/mcpgateway/translations/zh_CN/LC_MESSAGES/messages.mo:ro,Z
```

保留原有数据库、密钥、镜像、端口、其他挂载和 Phoenix 配置，然后执行：

```bash
docker compose --env-file .env -f docker-compose.yaml config --quiet
```

校验无误后执行：

```bash
docker compose --env-file .env -f docker-compose.yaml \
  up -d --no-deps --force-recreate --pull never --no-build gateway
```

此命令只重建网关，会短暂中断网关请求，不重建 Phoenix，也不删除外部数据库。
随后按第 6 节验收。

## 6. 启动与验收

以下命令均在 `/opt/contextforge` 执行：

```bash
docker compose --env-file .env -f docker-compose.yaml config --quiet
docker compose --env-file .env -f docker-compose.yaml config --images
docker compose --env-file .env -f docker-compose.yaml up -d --pull never --no-build
docker compose -f docker-compose.yaml ps
docker compose -f docker-compose.yaml logs --tail=100 gateway
docker compose -f docker-compose.yaml logs --tail=100 phoenix
curl -f --max-time 10 http://127.0.0.1:4444/health
curl -f --max-time 10 http://127.0.0.1:6006/health
```

如果修改了端口，对应修改 `curl` 中的主机端口。
首次启动需要等待 Phoenix 健康检查、数据库初始化和迁移完成。
不要发送不带 `--quiet` 的完整 Compose 配置输出，它可能包含密码。

| 验收项目 | 成功表现 |
| --- | --- |
| 镜像匹配 | `config --images` 输出的标签均存在于本地 |
| 容器状态 | 两个服务均为运行状态，健康检查通过 |
| 网关健康检查 | `/health` 返回成功状态 |
| 数据库连接 | 网关日志中没有持续的连接、权限或迁移错误 |
| 管理页面 | 可以登录并打开管理页面 |
| Phoenix | 可以打开页面，执行请求后检查 `mcp-gateway` 项目的链路 |

检查新容器加载的中文文件：

```bash
docker compose exec -T gateway python3 -c 'import gettext,pathlib,mcpgateway; p=pathlib.Path(mcpgateway.__file__).parent/"translations"; t=gettext.translation("messages",localedir=str(p),languages=["zh_CN"]); print(t.gettext("Language"))'
```

应输出 `语言`。再检查应用实际读取的功能开关：

```bash
docker compose exec -T gateway python3 -c 'from mcpgateway.config import settings; names=["self_service_api_keys_enabled","email_auth_enabled","i18n_enabled","i18n_default_locale","public_registration_enabled"]; [print(n,"=",getattr(settings,n)) for n in names]'
```

预期依次为 `True`、`True`、`True`、`zh-CN`、`False`。
浏览器访问：

- 管理页面：`http://服务器IP:4444/admin?lang=zh-CN`
- 自助领取 Key：`http://服务器IP:4444/admin/api-key?lang=zh-CN`
- Phoenix：`http://服务器IP:6006`

首次登录使用 `.env` 中的 `PLATFORM_ADMIN_EMAIL` 和 `PLATFORM_ADMIN_PASSWORD`。
若页面要求修改密码，按提示完成。后续登录使用修改后的密码。
用户在自助领取页使用已有账号的邮箱和密码，选择有权限的团队及虚拟服务器。
开启自助领取不会自动创建账号或授予资源权限，也不需要因此开启公开注册。

`I18N_DEFAULT_LOCALE` 是回退语言，不会覆盖已有语言 Cookie 或浏览器语言偏好。
用 `?lang=zh-CN` 或页面语言选择框切换中文。未翻译条目仍可能显示英文。
本设置影响 ContextForge，不会改变独立的 Phoenix 界面语言。

添加 MCP 服务时，目标必须是内网可访问地址。
镜像包不包含额外的 MCP 服务、模型服务或其依赖，不会自动部署这些系统。

## 7. 向内网用户提供服务

### 7.1 确定访问地址

例如部署服务器固定内网 IP 为 `192.168.10.50`，保持 `GATEWAY_PORT=4444` 时，用户访问：

```text
http://192.168.10.50:4444/admin
```

将示例 IP 替换为实际部署服务器地址，不能向用户提供 `localhost`、`127.0.0.1` 或容器 IP。
如果公司提供内网 DNS，可将内网域名解析到服务器地址，通过域名访问相同端口。

第 5 节的配置已经满足对其他机器提供服务的监听条件：

```yaml
    environment:
      HOST: 0.0.0.0
      PORT: "4444"
    ports:
      - "${GATEWAY_PORT:-4444}:4444"
```

此片段仅用于说明，不要替换完整的 `environment` 配置。
`HOST=0.0.0.0` 让应用监听容器网络接口；端口映射将服务发布到宿主机接口。
不要把端口映射改成 `127.0.0.1:4444:4444`，否则其他机器无法直接访问。

### 7.2 配置网络访问权限

向网络或运维管理员提交以下规则。来源应填写实际用户网段和管理网段。

| 来源 | 目标 | 端口 | 用途 |
| --- | --- | --- | --- |
| 内网用户网段、管理网段 | 部署服务器 IP | TCP 4444 | 页面、API 和 MCP 访问 |
| 可信管理网段 | 部署服务器 IP | TCP 6006 | Phoenix 运维页面 |
| 网关容器实际出口地址 | 数据库地址 | PostgreSQL 实际端口，通常为 TCP 5432 | 数据库连接 |

跨 VLAN 或不同内网网段时，需要同时检查路由、网络 ACL 和服务器侧访问策略。
如果服务器位于云上，还需要配置对应安全组。
Docker 发布端口的过滤可能与普通主机服务不同，按实际 Docker 防火墙后端配置规则。
必须从允许和不允许的来源分别测试，不能仅凭防火墙规则已添加就认定限制生效。
不要关闭防火墙来替代配置访问规则。

无需将数据库端口开放给普通用户。4317 仅用于容器内部通信，不需要发布到宿主机。
本方案中的 Phoenix 未启用登录认证，不能向普通用户网段开放 6006。

### 7.3 创建用户并分配权限

1. 管理员使用第 6 节的账号登录管理页面。
2. 在用户和团队管理功能中，为使用者创建独立账号并加入对应团队。
3. 根据职责分配角色；普通使用者不要授予平台管理员权限。
4. 将用户账号、初始密码和访问地址通过公司认可的渠道交付。
5. 使用一个普通用户账号验证登录、资源可见性和允许的操作。

不要向普通用户分发 `.env`、管理员密码、`JWT_SECRET_KEY` 或 `AUTH_ENCRYPTION_SECRET`。
资源访问同时受团队可见性和角色权限控制，页面可访问不等于可以访问所有资源。

如果用户通过 Agent 或程序调用 MCP：

1. 注册内网可访问的上游 MCP 服务，并创建包含所需工具的虚拟服务器。
2. 获取该虚拟服务器对应的连接地址和传输方式。
3. 若生成的连接地址使用本机地址，将主机和端口替换为对用户开放的地址，保留路径。
4. 为调用方准备适当团队范围和权限的独立 Token。
5. 在客户端使用 `Authorization: Bearer <Token>`，不要将 Token 放入 URL 查询参数。
6. 用该客户端实际连接并调用一个获授权工具，确认未授权资源不可访问。

`/admin` 是管理页面地址，不是 MCP 连接地址。
Token 的创建和使用仍需满足账号本身的权限要求。

### 7.4 从用户机器验收

不能只在部署服务器上执行健康检查。请在另一台用户电脑或服务器执行：

Linux 或 macOS：

```bash
curl -f http://192.168.10.50:4444/health
```

Windows PowerShell：

```powershell
Test-NetConnection 192.168.10.50 -Port 4444
curl.exe -f http://192.168.10.50:4444/health
```

替换为实际 IP 和端口，然后在该电脑浏览器打开 `/admin`，使用普通用户账号登录。
验证该用户只能看到和操作授权范围内的资源。
若交付 MCP 服务，还需完成客户端连接、工具发现和实际调用验证。

成功标准：用户机器能连接，页面能登录，授权操作成功，越权操作被拒绝。
服务端本地检查成功而用户机器连接失败时，优先检查地址、路由、ACL 和端口开放情况。

### 7.5 HTTP 与内网 HTTPS

本文默认直接提供 HTTP 服务，`.env` 保持 `SECURE_COOKIES=false`。
HTTP 不加密登录信息和 Token；持续向用户提供服务时，建议接入公司的内网 HTTPS 网关。

接入 HTTPS 时，由网关配置域名、客户端信任的证书，并转发到部署服务器的 4444 端口。
MCP 流式连接需要网关支持长连接、合适的超时和关闭响应缓冲。
限制后端 4444 仅允许该网关等必要来源访问，用户统一使用 HTTPS 地址。
随后设置 `SECURE_COOKIES=true` 并重新执行 `up -d`，重新验证登录和 MCP 调用。
仅修改 Cookie 开关不会自动启用 HTTPS。

## 8. 日常管理与升级

查看运行状态和最近日志：

```bash
docker compose -f docker-compose.yaml ps
docker compose -f docker-compose.yaml logs --tail=200 gateway
```

修改 `.env` 或 Compose 后，重新执行：

```bash
docker compose --env-file .env -f docker-compose.yaml up -d --pull never --no-build
```

仅执行 `restart` 不会应用新的容器环境变量。

停止服务并保留数据：

```bash
docker compose -f docker-compose.yaml down
```

不要添加 `-v`，它会删除 Phoenix 数据卷。
外部 PostgreSQL 数据由数据库管理员备份，Compose 不负责管理它。

升级前备份：外部 PostgreSQL、`.env`、Compose 文件、`translations` 目录，以及需要保留的 Phoenix 数据卷。
导入新包后，修改 `.env` 的固定镜像标签，再执行启动和验收步骤。
升级镜像时，用第 5.1 节从新镜像重新生成匹配的中文文件，再重建网关。
若新镜像已经包含经过验证的中文编译文件，可以移除该挂载，改用镜像自带翻译。
普通重启和重建无需编译；保留 `.env`、Compose 和 `translations` 目录即可保持配置和中文文件。
保留原密钥，不要重新生成 `.env`。
升级可能执行数据库迁移，回退旧镜像前必须确认数据库兼容性，不能假定直接换回镜像即可回退。

## 9. 常见问题

| 现象 | 排查方式 |
| --- | --- |
| `No such image` | 比较 `config --images` 与 `docker image ls`，确保已导入且标签一致 |
| `exec format error` | 镜像架构与服务器不一致，重新准备对应架构包 |
| 数据库连接超时 | 检查路由、防火墙、数据库监听地址和容器出口地址 |
| `no pg_hba.conf entry` | 请 DBA 授权正确来源、用户和数据库，并确认 TLS 要求 |
| 密码认证失败 | 核对用户名、密码、数据库实例及密码 URL 编码 |
| `permission denied for schema` | 请 DBA 授予目标 schema 使用、建表和迁移所需权限 |
| Phoenix 不健康 | 查看 Phoenix 日志，检查镜像是否包含 `python3`、存储权限和可用空间 |
| `/admin` 不可用 | 确认 UI、Admin API 开关已通过 Compose 传入，修改后重新执行 `up -d` |
| `/admin/api-key` 提示自助领取未启用 | 按第 5.3 节传入自助领取和邮箱认证开关，再重建网关 |
| 重建后中文消失 | 按第 5.1、5.3 节编译并挂载中文文件，按第 6 节检查新容器 |
| 设置默认中文后仍显示英文 | 使用 `?lang=zh-CN` 覆盖原语言偏好，并检查编译文件是否可读 |
| 翻译挂载提示目录或权限错误 | 确认宿主机 `messages.mo` 是非空文件，检查权限及 SELinux 标签 |
| 服务器本地正常，用户无法连接 | 按第 7 节检查实际 IP、端口映射、跨网段路由、ACL 和防火墙 |
| 用户登录后看不到资源或收到 403 | 核对团队归属、资源可见性和角色权限，不要通过关闭认证解决 |
| HTTP 登录后跳回登录页 | 检查 `SECURE_COOKIES=false` 是否生效，并清理浏览器旧 Cookie |
| 旧管理员密码没有变化 | 初始化密码不会覆盖已有账号，请使用应用密码修改或恢复流程 |
| 原有凭据无法解密 | 检查是否沿用原来的 `AUTH_ENCRYPTION_SECRET` |
| Phoenix 暂无链路 | 先执行网关请求，再检查网关 OTLP 配置、导出日志和项目选择 |

## 10. 范围与验证说明

本文覆盖全新部署和已有部署的中文、功能开关更新，不会迁移旧环境数据库、用户配置或历史链路。
镜像归档仅携带镜像，不携带运行环境的数据。

文档依据当前分支的 Compose、配置校验和数据库初始化代码编写。
实际内网连接、权限、登录和链路上报需要按第 6、7 节在部署服务器和用户机器分别验收。

参考：

- [Docker 镜像导入](https://docs.docker.com/reference/cli/docker/image/load/)
- [Docker Compose 启动参数](https://docs.docker.com/reference/cli/docker/compose/up/)
