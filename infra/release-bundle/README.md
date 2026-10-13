# ContextForge 离线 Release 部署包

从 GitHub Releases 下载对应架构的 `contextforge-<版本>-linux-<架构>.tar.gz` 和 `.sha256` 文件。
`x86_64` 使用 amd64；`aarch64` 使用 arm64。Docker Engine、Compose v2、Bash、OpenSSL 和 sha256sum 由运维提前安装。

总包包含以下文件：

- `images.tar.gz`：ContextForge、Phoenix 两个镜像，包含应用依赖、前端资源和编译后的中文翻译。
- `docker-compose.yaml`：固定包内两个镜像标签的启动配置，连接现有 PostgreSQL。
- `.env.example`、`init-env.sh`：配置模板和首次部署的密钥生成脚本。
- `source.tar.gz`：本次构建提交的工程文件，排除真实 `.env` 和本地工作记录。
- `VERSION.json`：源码提交、架构、构建地址和镜像 ID。
- `SHA256SUMS`：包内文件校验清单。
- `DEPLOY-INTRANET.md`、`docs/`、`infra/portal-session-bridge/`：内网部署和父页面集成文档。

## 首次部署

先准备可从网关容器访问的现有 PostgreSQL，并创建数据库和账号。数据库准备步骤见 `DEPLOY-INTRANET.md` 第 3 节。
在下载目录执行外层校验，再解压总包。以下名称需要替换为实际文件名：

```bash
sha256sum -c contextforge-实际版本-linux-amd64.tar.gz.sha256
tar -xzf contextforge-实际版本-linux-amd64.tar.gz
cd contextforge-实际版本-linux-amd64
sha256sum -c SHA256SUMS
docker load -i images.tar.gz
bash init-env.sh
```

编辑 `.env`，填写现有数据库的连接字符串。密码中的特殊字符需要 URL 编码：

```dotenv
GATEWAY_DATABASE_URL='postgresql+psycopg://数据库用户:URL编码后的密码@数据库地址:5432/数据库名'
```

数据库地址必须能从容器访问。数据库运行在 Docker 宿主机时，可使用 `host.docker.internal`。
填写后启动服务；连接字符串为空时，Compose 拒绝启动：

```bash
docker compose config --quiet
docker compose up -d --pull never --wait --wait-timeout 300
curl -fsS http://localhost:4444/health
```

生成的 `.env` 权限为仅当前用户可读写。按需修改管理员邮箱和端口，再启动服务。
使用 `.env` 中的 `PLATFORM_ADMIN_EMAIL` 和 `PLATFORM_ADMIN_PASSWORD` 登录 `http://服务器地址:4444/admin/login`。
Phoenix 界面位于 `http://服务器地址:6006`；只向可信管理网段开放 Phoenix 端口。
`--pull never` 禁止启动时下载镜像。Phoenix 数据保存在 Docker 数据卷中；现有 PostgreSQL 由数据库管理员维护。

Phoenix 接收网关发送的 OpenTelemetry 调用链，用于查看调用步骤、耗时和错误，便于排查慢请求。
它是可选的监控服务。本包保留 Phoenix；只部署网关时，使用下面的独立网关配置。

## 工程文件和现有数据库

先创建 `source/` 目录，再用 `tar -xzf source.tar.gz -C source` 解压工程。
源码用于审查和重新构建；离线部署直接使用包内镜像。
源码包没有离线构建工具链。宿主机部署应用时无需安装 Python、Node 或项目依赖。

复用现有 PostgreSQL、现有 Nginx或父页面 iframe 时，按 `docs/docs/deployment/intranet-portal-gateway.md` 创建独立网关配置。
父页面开发人员阅读 `infra/portal-session-bridge/README.md`，并使用相邻的 `portal-client.js`。
默认 Compose 启动网关和 Phoenix，连接 `.env` 中指定的现有 PostgreSQL。

## 升级和回滚

升级前备份数据库和 `.env`。保留 `AUTH_ENCRYPTION_SECRET`、`JWT_SECRET_KEY`、密码、Compose 项目名和数据卷。
解压新版本到新目录，校验文件并导入镜像。复制原 `.env`，使用相同项目名启动新版本。
已有 `.env` 时，`init-env.sh` 拒绝覆盖。不要重新生成加密密钥。

数据库迁移随网关启动执行。回滚时同时评估旧镜像和数据库兼容性；必要时恢复对应备份。
用 `docker compose down` 停止服务。保留数据时不要添加 `--volumes`。
