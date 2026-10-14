# ContextForge 离线 Release 详细部署文档

更新日期：2026-10-14。本文面向部署人员，说明文件选择、`.env`、Compose、启动验收和升级。

本次实例为 [build-1168227-38372867939-1](https://github.com/FutureALab/mcp-context-forge/releases/tag/build-1168227-38372867939-1)。
现场使用现有 PostgreSQL。默认运行网关和 Phoenix；只需网关时，使用第 7 节配置。

## 1. 必须下载哪些文件

首次部署只下载以下两个文件，放在同一目录，并保留原文件名：

1. `contextforge-build-1168227-38372867939-1-linux-amd64.tar.gz`
2. `contextforge-build-1168227-38372867939-1-linux-amd64.tar.gz.sha256`

第一个是约 443 MB 的完整包，包含镜像、Compose、配置模板、密钥生成脚本、源码和文档。
第二个用于校验下载和传输是否完整。每个 `.sha256` 只校验同名归档。

下表中的 `…` 表示版本 `build-1168227-38372867939-1`：

| Release 文件 | 用途 | 下载完整包后是否还要下载 |
| --- | --- | --- |
| `contextforge-…-linux-amd64.tar.gz` | 完整部署包，约 443 MB | 首次部署必须下载 |
| 同名 `.sha256` | 校验完整包 | 必须配套下载 |
| `mcpgateway-…-linux-amd64.tar.gz` | 网关和 Phoenix 镜像归档，约 429 MB | 可以不用，完整包已有 `images.tar.gz` |
| 同名 `.sha256` | 校验单独镜像归档 | 未下载单独镜像归档时可以不用 |
| `contextforge-deployment-docs-…-linux-amd64.tar.gz` | 内网、麒麟、父页面文档和 helper | 可以不用，完整包已包含 |
| 同名 `.sha256` | 校验单独文档归档 | 未下载单独文档归档时可以不用 |
| `docker-compose.yaml` | 容器启动配置 | 可以不用单独下载，完整包已有 |
| `Source code (zip)` | GitHub 自动生成的源码 ZIP | 容器部署可以不用 |
| `Source code (tar.gz)` | GitHub 自动生成的源码归档 | 容器部署可以不用 |

`mcpgateway-…tar.gz` 同时包含网关和 Phoenix，不是“仅网关”镜像包。
已有配置且只更新镜像时，可以下载单独镜像归档及其校验文件，沿用原 `.env` 和自定义 Compose。
单独镜像归档不包含配置模板、密钥生成脚本或源码。

## 2. 部署前准备

### 2.1 架构和工具

本次 Release 只有 amd64 包，适用于 Intel/AMD 的 `x86_64` Linux 服务器。
麒麟服务器也需要确认实际架构。

```bash
uname -m
docker version
docker compose version
bash --version
openssl version
command -v sha256sum curl tar
```

`uname -m` 显示 `aarch64` 时，重新打包 arm64 版本。
Docker Engine 必须已启动，Compose 使用 v2，当前账号需要 Docker 操作权限。
运维提前安装 Docker、Compose、Bash、OpenSSL、tar、sha256sum 和 curl。
包内不包含宿主机工具安装程序；通过镜像部署无需在宿主机安装 Python、Node 或项目依赖。
已注册的外部 MCP 服务仍需要网络可达，镜像包不提供这些外部服务。

### 2.2 现有 PostgreSQL

向数据库管理员确认：

| 项目 | 示例 | 要求 |
| --- | --- | --- |
| 地址 | `192.168.10.20` | 网关容器能够访问的内网 IP 或域名 |
| 端口 | `5432` | 使用实际监听端口 |
| 数据库 | `mcp` | 新部署使用专用空数据库 |
| 账号 | `mcp_gateway` | 拥有应用 schema、表及迁移所需权限 |
| 密码 | 管理员提供 | 填入 URL 前进行编码 |
| TLS | 按现场要求提供 | 确认 SSL 模式和证书 |

新部署首次启动会初始化应用表并执行迁移。
不要连接其他业务正在使用的数据库进行首次初始化。
若账号、数据库尚不存在，数据库管理员可在 `psql` 中执行示例：

```sql
CREATE ROLE mcp_gateway LOGIN;
\password mcp_gateway
CREATE DATABASE mcp OWNER mcp_gateway;
```

`\password` 交互设置密码。已有同名对象时，不重复执行创建命令。
数据库监听地址、访问规则和防火墙必须允许部署服务器或容器实际出口地址连接。

### 2.3 服务和端口

| 服务 | 端口 | 作用 |
| --- | --- | --- |
| 网关 | 宿主机默认 `4444` | 管理页面、API 和 MCP 入口 |
| Phoenix | 宿主机默认 `6006` | 调用链页面，只向可信管理网段开放 |
| Phoenix OTLP | 容器 `4317` | 接收网关链路数据，网关通过 Docker 内部网络访问 |
| PostgreSQL | 数据库实际端口，通常 `5432` | 现有数据库允许网关访问 |

发布配置映射了宿主机 `4317`。没有外部采集需求时，可用第 6 节配置，仅保留内部通信。
默认 Phoenix 没有额外配置登录认证。

## 3. 解压并导入

把完整包和校验文件传入 `/opt/contextforge`。
按现场权限要求创建目录并授权；以下命令由具有相应权限的账号执行：

```bash
sudo mkdir -p /opt/contextforge
sudo chown "$(id -u):$(id -g)" /opt/contextforge
cd /opt/contextforge

BUNDLE='contextforge-build-1168227-38372867939-1-linux-amd64.tar.gz'
sha256sum -c "${BUNDLE}.sha256"
tar -xzf "$BUNDLE"
cd "${BUNDLE%.tar.gz}"

sha256sum -c SHA256SUMS
docker load -i images.tar.gz
docker image ls
```

每次校验均应显示 `OK`，失败时重新下载或传输，校验成功后再继续。
完整包使用 `tar -xzf`；内部 `images.tar.gz` 使用 `docker load`。
完整包外层不能直接交给 `docker load`。
首次解压使用新目录，避免覆盖已有 `.env` 或自定义 Compose。

主要文件如下：

```text
contextforge-build-1168227-38372867939-1-linux-amd64/
├── README.md
├── images.tar.gz
├── docker-compose.yaml
├── .env.example
├── init-env.sh
├── source.tar.gz
├── VERSION.json
├── SHA256SUMS
├── DEPLOY-INTRANET.md
├── docs/docs/deployment/intranet-portal-gateway.md
└── infra/portal-session-bridge/
    ├── README.md
    └── portal-client.js
```

`.env` 下一步生成，不在公开下载包中。
本次 Release 的网关标签为 `mcpgateway/mcpgateway:build-1168227-38372867939-1`，
Phoenix 标签为 `arizephoenix/phoenix:latest`。
其他网关标签可能指向同一镜像，无需逐个启动。
后续版本以其包内 Compose、`VERSION.json` 和 `docker load` 输出为准。
启动时使用 `--pull never`，Phoenix 的 `latest` 来自已导入归档，不会在线更新。
修改配置后，原 `SHA256SUMS` 对被修改文件的校验会失败，这是配置变更的结果。

## 4. `.env` 的配置方法

### 4.1 首次生成

在解压目录执行：

```bash
bash init-env.sh
chmod 600 .env
```

脚本随机生成以下四个值，保留它们：

| 变量 | 作用 | 使用规则 |
| --- | --- | --- |
| `JWT_SECRET_KEY` | 登录令牌签发和验证 | 升级沿用原值 |
| `AUTH_ENCRYPTION_SECRET` | 加密网关保存的凭据 | 必须备份，升级沿用原值 |
| `PLATFORM_ADMIN_PASSWORD` | 初始化管理员密码 | 保存生成值，用于新数据库首次登录 |
| `DEFAULT_USER_PASSWORD` | 初始化新用户的默认密码 | 保存生成值，按用户管理规则使用 |

已有 `.env` 时，脚本拒绝覆盖。升级或复用已有 ContextForge 数据库时，沿用原文件和密钥。
修改 `.env` 的初始化密码不会自动重置数据库中已有账号的密码。
已有账号使用应用账号管理或密码重置流程。

### 4.2 编辑现场参数

打开 `.env`，保留四个生成值，修改或补充以下内容。
相同变量只保留一行。以下示例没有列出四个密钥和密码，不能用它覆盖整个 `.env`：

```dotenv
GATEWAY_DATABASE_URL='postgresql+psycopg://mcp_gateway:替换为URL编码后的密码@192.168.10.20:5432/mcp'
PLATFORM_ADMIN_EMAIL=admin@example.com
EMAIL_AUTH_ENABLED=true
MCPGATEWAY_UI_ENABLED=true
MCPGATEWAY_ADMIN_API_ENABLED=true
GATEWAY_PORT=4444
PHOENIX_UI_PORT=6006
PHOENIX_OTLP_PORT=4317
GUNICORN_WORKERS=2
SECURE_COOKIES=false
LOG_LEVEL=INFO
```

数据库 IP、账号、密码、库名均替换为现场实际值。
`SECURE_COOKIES` 和 `LOG_LEVEL` 不在本次包的初始模板中，需要补充。

| 配置 | 说明 |
| --- | --- |
| `GATEWAY_DATABASE_URL` | 必填，Compose 将它转换为应用的 `DATABASE_URL` |
| `PLATFORM_ADMIN_EMAIL` | 新数据库初始化时使用的管理员邮箱 |
| `EMAIL_AUTH_ENABLED` | 邮箱密码登录，本方案保持 `true` |
| `MCPGATEWAY_UI_ENABLED` | 内置管理页面，本方案保持 `true` |
| `MCPGATEWAY_ADMIN_API_ENABLED` | 管理 API，本方案保持 `true` |
| `GATEWAY_PORT` | 宿主机网关端口；容器内部保持 `4444` |
| `PHOENIX_UI_PORT` | 方案 A 的宿主机 Phoenix 页面端口 |
| `PHOENIX_OTLP_PORT` | 原发布配置的宿主机 OTLP 端口，第 6、7 节配置无需使用 |
| `GUNICORN_WORKERS` | 网关工作进程数，先保留 `2` |
| `SECURE_COOKIES` | 直接 HTTP 访问设 `false`，HTTPS 访问设 `true` |
| `LOG_LEVEL` | 首次部署可使用 `INFO` |

HTTP 访问且保持 `SECURE_COOKIES=true` 时，浏览器不发送安全 Cookie，可能出现登录后跳回登录页。
设置 `SECURE_COOKIES=true` 本身不会启用 HTTPS，HTTPS 由现场 TLS 或反向代理配置提供。

### 4.3 数据库连接字符串

格式为：

```text
postgresql+psycopg://用户名:URL编码后的密码@数据库地址:端口/数据库名
```

| 密码中的字符 | URL 编码 |
| --- | --- |
| `@` | `%40` |
| `#` | `%23` |
| `%` | `%25` |
| `$` | `%24` |
| `/` | `%2F` |
| `:` | `%3A` |

只编码用户名、密码等对应部分，不编码整个连接字符串，也不重复编码已编码的密码。
保留 `.env` 值外层的单引号，避免 Compose 对 `$` 插值。单引号不会传入应用的连接字符串。

| 数据库位置 | 地址写法 |
| --- | --- |
| 另一台内网服务器 | 数据库内网 IP 或容器可解析域名 |
| 当前 Docker 宿主机 | 可使用 `host.docker.internal`，Compose 配置了 Linux host-gateway |
| 现有 Docker 数据库容器 | 使用宿主机已映射的端口，或由运维配置共享网络和服务名 |

容器内 `localhost` 指网关容器自身，不指宿主机。
宿主机数据库需要监听容器能够访问的地址，不能只监听 `127.0.0.1`。
`host.docker.internal` 不会启动数据库，也不会绕过访问规则。
数据库要求 TLS 时，按管理员要求提供参数。
`sslmode=require` 要求加密；校验服务器身份需要 `verify-full`、可信证书和容器内证书路径。

## 5. `.env` 与 Compose 的关系

发布包使用文件名 `docker-compose.yaml`。
本文默认命令在它所在目录执行，自动读取该文件和同目录 `.env`。
`.env` 保存现场参数和秘密值；Compose 定义镜像、服务、端口、数据卷和环境变量传递。
发布配置的 `env_file: .env` 把配置传给网关。
服务内的 `environment` 优先于 `env_file` 中同名变量。

Compose 显式使用 `GATEWAY_DATABASE_URL` 设置 `DATABASE_URL`。
只在 `.env` 填写应用的 `DATABASE_URL`，不能满足该 Compose 的必填检查。
镜像标签已经固定在发布配置的 `image:` 中。
在 `.env` 加入 `GATEWAY_IMAGE` 或 `PHOENIX_IMAGE` 不会改动固定标签。
切换版本使用新包的 Compose，或明确修改自定义 Compose 的 `image:`。

如果采用名称 `compose.yml`，每次明确指定文件：

```bash
docker compose -f compose.yml config --quiet
docker compose -f compose.yml up -d --pull never --wait --wait-timeout 300
```

一个目录只保留一个作为默认入口的 Compose 文件。多个方案使用 `-f` 明确选择。
`config --quiet` 检查配置但不启动服务；完整 `config` 输出可能包含秘密值，避免公开发送。

## 6. 方案 A：网关与 Phoenix

需要监控时，直接使用包内 `docker-compose.yaml` 即可，无需重新编写。
Phoenix 接收 OpenTelemetry 调用链，显示调用步骤、耗时和错误。
它不代替 PostgreSQL，也不承担网关登录或 MCP 业务服务。

以下是本次 Release 的精简等价配置，仅省略宿主机 OTLP 端口映射。
需要自定义时先备份原文件，再保存为解压目录中的 `docker-compose.yaml`：

```yaml
name: mcpgateway-phoenix

services:
  phoenix:
    image: arizephoenix/phoenix:latest
    container_name: phoenix
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
    image: mcpgateway/mcpgateway:build-1168227-38372867939-1
    container_name: mcpgateway
    restart: unless-stopped
    env_file: .env
    depends_on:
      phoenix:
        condition: service_healthy
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      HOST: 0.0.0.0
      PORT: "4444"
      MCPGATEWAY_SKIP_MIGRATIONS: "false"
      DATABASE_URL: ${GATEWAY_DATABASE_URL:?Set GATEWAY_DATABASE_URL in .env}
      JWT_SECRET_KEY: ${JWT_SECRET_KEY:?Set JWT_SECRET_KEY in .env}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET:?Set AUTH_ENCRYPTION_SECRET in .env}
      PLATFORM_ADMIN_PASSWORD: ${PLATFORM_ADMIN_PASSWORD:?Set PLATFORM_ADMIN_PASSWORD in .env}
      DEFAULT_USER_PASSWORD: ${DEFAULT_USER_PASSWORD:?Set DEFAULT_USER_PASSWORD in .env}
      OTEL_ENABLE_OBSERVABILITY: "true"
      OTEL_TRACES_EXPORTER: otlp
      OTEL_EXPORTER_OTLP_ENDPOINT: http://phoenix:4317
      OTEL_EXPORTER_OTLP_PROTOCOL: grpc
      OTEL_EXPORTER_OTLP_INSECURE: "true"
      OTEL_SERVICE_NAME: mcp-gateway
      OTEL_RESOURCE_ATTRIBUTES: openinference.project.name=mcp-gateway,deployment.environment=docker
      OTEL_SQLALCHEMY_INSTRUMENTATION_ENABLED: "false"
    ports:
      - "${GATEWAY_PORT:-4444}:4444"

volumes:
  phoenix-data:
```

Phoenix 页面默认为 `http://服务器IP:6006`。
网关内部地址保持 `http://phoenix:4317`，不要改为 `localhost`。
后续版本使用该版本实际镜像标签。

## 7. 方案 B：仅运行网关

不需要 Phoenix 时，仍可下载完整包并导入镜像，只启动网关。
导入 Phoenix 镜像不会自动运行它。本方案仍使用现有 PostgreSQL。
创建 `compose.gateway-only.yaml`，与 `.env` 放在同一目录：

```yaml
name: mcpgateway-phoenix

services:
  gateway:
    image: mcpgateway/mcpgateway:build-1168227-38372867939-1
    container_name: mcpgateway
    restart: unless-stopped
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      HOST: 0.0.0.0
      PORT: "4444"
      MCPGATEWAY_SKIP_MIGRATIONS: "false"
      DATABASE_URL: ${GATEWAY_DATABASE_URL:?Set GATEWAY_DATABASE_URL in .env}
      JWT_SECRET_KEY: ${JWT_SECRET_KEY:?Set JWT_SECRET_KEY in .env}
      AUTH_ENCRYPTION_SECRET: ${AUTH_ENCRYPTION_SECRET:?Set AUTH_ENCRYPTION_SECRET in .env}
      PLATFORM_ADMIN_PASSWORD: ${PLATFORM_ADMIN_PASSWORD:?Set PLATFORM_ADMIN_PASSWORD in .env}
      DEFAULT_USER_PASSWORD: ${DEFAULT_USER_PASSWORD:?Set DEFAULT_USER_PASSWORD in .env}
      OTEL_ENABLE_OBSERVABILITY: "false"
      OTEL_TRACES_EXPORTER: none
      OTEL_SQLALCHEMY_INSTRUMENTATION_ENABLED: "false"
    ports:
      - "${GATEWAY_PORT:-4444}:4444"
```

此配置去掉 Phoenix 服务、依赖和数据卷，并关闭链路导出。
`.env` 中 Phoenix 端口可以保留，但本方案不使用它们。

全新部署执行：

```bash
docker compose -f compose.gateway-only.yaml config --quiet
docker compose -f compose.gateway-only.yaml up -d --pull never --wait --wait-timeout 300
docker compose -f compose.gateway-only.yaml ps
```

已有方案 A 时，先停止原方案，再启动方案 B，切换会短暂中断网关：

```bash
docker compose -f docker-compose.yaml down
docker compose -f compose.gateway-only.yaml up -d --pull never --wait --wait-timeout 300
```

保持相同数据库和密钥，不添加 `--volumes`。
以后查看日志、升级和停止服务时，继续指定 `-f compose.gateway-only.yaml`。
执行默认配置的 `up` 会重新启动方案 A。

## 8. 启动与验收

方案 A 在解压目录执行：

```bash
docker compose config --quiet
docker compose up -d --pull never --wait --wait-timeout 300
docker compose ps
curl -fsS http://localhost:4444/health
```

`--pull never` 禁止下载镜像，`--wait` 等待健康检查通过。
修改了 `GATEWAY_PORT` 时，健康检查 URL 使用实际宿主机端口。
方案 B 的 Compose 命令指定 `-f compose.gateway-only.yaml`。

| 检查项 | 通过条件 |
| --- | --- |
| 镜像 | 固定版本网关镜像存在，方案 A 同时有 Phoenix 镜像 |
| 配置 | `config --quiet` 成功 |
| 容器 | `ps` 显示所选方案服务健康 |
| 网关健康 | `/health` 成功，状态为 `healthy` |
| 管理页面 | `http://服务器IP:4444/admin/login` 能打开并登录 |
| 数据保存 | 使用正确数据库，页面保存配置后仍可读取 |
| MCP 业务 | 注册现场可访问的 MCP，完成发现和实际工具调用 |
| Phoenix，方案 A | 页面可打开，网关请求后可在 `mcp-gateway` 项目查看链路 |

新数据库使用 `.env` 中的管理员邮箱和生成密码登录；已有数据库使用原账号密码。
日常命令如下，方案 B 指定自己的 `-f` 文件，并略过 Phoenix 日志：

```bash
docker compose ps
docker compose logs --tail 100 gateway
docker compose logs --tail 100 phoenix
docker compose up -d --pull never
docker compose down
```

修改 `.env` 后执行 `up -d --pull never`，让容器按新配置重建。
`restart` 不会重新读取新的容器环境配置。

## 9. 常见问题

| 现象 | 检查或处理 |
| --- | --- |
| 数据库连接变量未设置 | 填写真实 `.env` 的 `GATEWAY_DATABASE_URL`，仅改 `.env.example` 不生效 |
| 密钥或密码无效 | 使用脚本生成值，已有数据库保留原密钥，避免示例占位值 |
| 找不到镜像且禁止拉取 | 核对导入输出与 Compose 的 `image:`，确认导入同一版本 |
| `exec format error` | 检查架构，本次包仅适用于 amd64 |
| 数据库拒绝或超时 | 检查地址、监听、访问规则、防火墙和容器出口网络 |
| 数据库认证失败 | 检查账号、密码、库名和 URL 编码 |
| schema 或迁移权限不足 | 由数据库管理员授予应用账号所需权限 |
| 登录后回到登录页 | HTTP 设置 `SECURE_COOKIES=false`，执行 `up` 使配置生效 |
| 改初始化密码却未重置账号 | 使用应用密码重置流程 |
| 宿主机端口被占用 | 修改 `.env` 的宿主机端口，保留容器内部端口 |
| 容器名冲突 | 核对已有部署，避免两个方案同时启动，不删除用途不明的容器 |
| Phoenix 不健康 | 查看日志、数据卷和资源；网关等待其健康，或选择第 7 节方案 |
| 仅网关方案仍启动 Phoenix | 明确指定 `-f compose.gateway-only.yaml` |

`down` 不删除外部 PostgreSQL。保留 Phoenix 历史数据时，不添加 `--volumes`。
先通过 `logs` 和 `ps` 定位故障，不执行全局容器或数据卷清理。

## 10. 源码和单独归档怎么用

### 10.1 工程源码

在完整包解压目录执行：

```bash
mkdir -p source
tar -xzf source.tar.gz -C source
```

源码来自本次构建提交，排除了真实 `.env` 和本地工作记录。
单独解压，避免覆盖部署文件。正常容器部署无需解压源码。
源码包不包含离线重建的完整工具链或依赖缓存。

### 10.2 单独镜像归档

```bash
IMAGE_BUNDLE='mcpgateway-build-1168227-38372867939-1-linux-amd64.tar.gz'
sha256sum -c "${IMAGE_BUNDLE}.sha256"
docker load -i "$IMAGE_BUNDLE"
```

沿用现有 `.env` 和 Compose，并按新标签更新镜像配置。
新部署缺少模板和生成脚本时，下载完整包。

### 10.3 单独文档归档

```bash
DOCS_BUNDLE='contextforge-deployment-docs-build-1168227-38372867939-1-linux-amd64.tar.gz'
sha256sum -c "${DOCS_BUNDLE}.sha256"
mkdir -p deployment-docs
tar -xzf "$DOCS_BUNDLE" -C deployment-docs
```

此归档供阅读和父页面集成，不含 Docker 镜像。
父页面开发人员阅读 `infra/portal-session-bridge/README.md`，使用相邻 `portal-client.js`。
麒麟、Nginx 和 iframe 配置见 `docs/docs/deployment/intranet-portal-gateway.md`。

## 11. 升级与回滚

升级前备份外部 PostgreSQL、原 `.env`、自定义 Compose 和 Phoenix 数据。
继续使用原 `AUTH_ENCRYPTION_SECRET`、`JWT_SECRET_KEY`、账号密码和数据库连接。
保留 Compose 项目名，避免 Phoenix 数据卷名称改变。

新包解压到新目录，先校验原始文件并导入镜像，再迁移配置。
先确定原项目名和运行方案，再执行启动命令。
默认项目名是 `mcpgateway-phoenix`。原部署使用 `-p` 时，沿用当时指定的项目名。
默认方案 A 使用新包的 `docker-compose.yaml`。
使用自定义配置或方案 B 时，先复制对应 Compose 到新目录，更新 `image:` 为新包导入标签。
同时迁移原端口和挂载配置；保持仅网关方案没有 Phoenix 依赖。
以下目录名是占位值，替换为实际路径：

```bash
cd /opt/contextforge/新版本解压目录
cp /opt/contextforge/旧版本解压目录/.env .env
chmod 600 .env

DEPLOY_PROJECT='mcpgateway-phoenix'
DEPLOY_FILE='docker-compose.yaml'
# 原部署有自定义项目名时，修改 DEPLOY_PROJECT。
# 原部署使用方案 B 时，改为已经准备好的 compose.gateway-only.yaml。
docker compose -p "$DEPLOY_PROJECT" -f "$DEPLOY_FILE" config --quiet
docker compose -p "$DEPLOY_PROJECT" -f "$DEPLOY_FILE" up -d --pull never --wait --wait-timeout 300
```

不要重新生成密钥。之后的管理命令继续使用相同的 `-p` 和 `-f` 参数。
随后执行第 8 节验收。

回滚保留旧镜像、旧 Compose 和升级前数据库备份。
数据库迁移可能改变结构，先确认旧镜像兼容，必要时由管理员恢复对应数据库备份。
仅切换旧镜像不能撤销数据库迁移。

## 12. 本文范围和版本关系

本文依据该 Release 的公开文件清单、Compose 和仓库配置编写。
数据库地址、密码、域名、端口和证书由现场替换。
新版本自动打包时，会把仓库中的本 README 放入完整部署包。
已经发布的旧归档不会因 README 更新而改变，本文的新详细说明以仓库文件为准。
真实现场数据库网络、业务 MCP 和麒麟验收需要在目标环境执行。
