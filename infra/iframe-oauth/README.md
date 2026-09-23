# 同站不同端口的 iframe OAuth 演示

父平台只登录一次，MCP iframe 自动完成自己的 OAuth2 / OIDC 授权码流程。
演示复用 ContextForge 的通用 OIDC 登录，不修改核心认证代码，也不使用邮箱请求头免密登录。
企业内网落地与父页面改造见 [内网部署方案](INTRANET-ROLLOUT.md)。

## 启动

在仓库根目录运行 PowerShell：

```powershell
./infra/iframe-oauth/start.ps1
```

打开 <http://localhost:18080>，点击“登录内网平台”。
使用 `infra/iframe-oauth/.runtime/account.txt` 中的测试账号。
登录后，父页面自动加载 MCP，并显示两个应用的实际登录身份。
点击父页面的“领取 API Key”，在 iframe 中点击“检测账号并查询所属 Team”。
选择测试账号的 Team 和“AIOps 演示 MCP”，再点击“生成 API Key”。
页面只展示一次新 Key；请在关闭页面前复制。演示 MCP 没有预置工具。
点击“MCP 工作区”可返回管理界面。
刷新父页面无需再次输入密码。“退出演示”清除本浏览器的父平台、身份服务和 MCP 登录 Cookie。

启动脚本默认使用本机 `I:\anaconda\envs\py312\python.exe` 中已有的项目依赖。
其他 Python 路径可显式指定：

```powershell
./infra/iframe-oauth/start.ps1 -Python 'C:\path\to\venv\Scripts\python.exe'
```

需要 Docker Desktop、现有的 `nginx:stable-alpine` 和 `base-node:24-bookworm` 镜像。
Compose 使用 `pull_policy: never`，不会下载镜像或安装依赖。
若使用其他已导入的 Node 22+ 镜像，修改 `compose.yaml` 的 `identity.image`。

停止演示，保留测试数据库和账号：

```powershell
./infra/iframe-oauth/stop.ps1
```

## 访问路径

| 浏览器地址 | 用途 |
| --- | --- |
| `http://localhost:18080/` | 父平台页面，由 Nginx 提供 |
| `http://localhost:18080/portal/*` | 父平台登录和会话接口 |
| `http://localhost:18080/oidc/*` | 本地测试 OIDC 服务 |
| `http://localhost:18081/embed/start.html` | iframe 自动发起 SSO |
| `http://localhost:18081/admin/` | 真实 ContextForge 管理页面 |
| `http://localhost:18081/admin/api-key` | 演示账号自助领取 API Key |
| `http://localhost:18081/embed/session` | 只读会话检查，Nginx 将 HttpOnly Cookie 转为后端 Bearer Header |

两个浏览器端口来自同一个 Nginx 容器。
Nginx 将 MCP 请求转发到本机隔离网关 `host.docker.internal:4446`。
启动脚本只管理自己的进程和 Compose 项目，不停止其他容器。

## 登录过程

1. 父平台使用 `portal-demo` 客户端发起授权码登录。
2. 用户在测试身份服务输入账号，建立身份服务会话。
3. 父平台后端兑换授权码，验证签名、issuer、audience、nonce 和过期时间。
4. 父页面加载另一端口的 `/embed/start.html`。
5. iframe 调用 ContextForge 原有 `/auth/sso/login/intranet-demo`。
6. 身份服务识别已有 Cookie，为 `contextforge-demo` 签发新的授权码，无需再次输入密码。
7. ContextForge 校验授权码、PKCE、state、nonce 和 ID Token，创建自己的 HttpOnly 登录 Cookie。
8. iframe 进入 MCP 管理页面。

父页面不传邮箱作为登录凭证，也不接收 MCP Token。
测试用户只获得 `platform_viewer` 角色，不授予平台管理员权限。
演示网关启用自助领取，并准备一个公开的虚拟 MCP。测试账号登录后使用自己的 Team 领取该 MCP 的 Key。

## 浏览器和部署约束

- 同协议、同主机、不同端口属于同站、不同源。Cookie 不按端口隔离。
- 因此演示中的应用使用不同 Cookie 名称；同一主机下的应用必须互相信任。
- `X_FRAME_OPTIONS=SAMEORIGIN` 会阻止不同端口嵌入。本演示关闭该响应头，并由 Nginx 精确设置 `frame-ancestors`。
- 父页面只允许框架访问身份服务和 MCP 两个来源；CORS 只允许父平台和 MCP 来源。
- `SameSite=Lax` 支持本例的 HTTP 同站演示，不需要 `SameSite=None`。
- HTTP 和模拟身份服务仅用于本地验证。正式接入使用 HTTPS 和企业 OIDC 服务。
- 实际企业 IdP 可能禁止 iframe 授权。此时在顶层窗口完成授权，再返回父页面加载 iframe。
- 浏览器入口默认只绑定 `127.0.0.1`。网关 `4446` 绑定所有接口供 Docker 访问，应由防火墙限制直连。
- 修改为内网域名时，同步修改 `.runtime/config.json` 中两个 Origin、Compose 的 `DEMO_HOST` 和端口绑定。
- 域名必须能由浏览器和网关解析。修改配置后停止并重新启动演示。

`.runtime/` 保存独立 SQLite 数据库、随机凭据和日志，已被 Git 忽略。
不读取或修改仓库根目录 `.env`，也不使用原有 `mcp.db`。
测试身份服务使用内存会话，重启后需要重新登录；签名密钥编号随重启变化。
退出只清除本浏览器会话，不实现生产环境的全局 Token 撤销。

## 验证与排错

```powershell
node --test infra/iframe-oauth/server.test.mjs
I:/anaconda/envs/py312/python.exe infra/iframe-oauth/verify_live.py
docker compose -f infra/iframe-oauth/compose.yaml exec -T nginx nginx -t
docker compose -f infra/iframe-oauth/compose.yaml logs --tail 30
```

`verify_live.py` 需要先启动演示。
它验证真实网关的两次授权码登录、普通用户权限、Key 领取、Key 的 MCP 初始化、Cookie、CORS、iframe 响应头和退出。
脚本使用临时虚拟 MCP 和临时 Key，验证后删除，不消耗页面上演示 MCP 的首次领取机会。
浏览器还需确认 iframe 能显示 MCP 页面、切换到 Key 页面，并能领取演示 MCP 的 Key。

启动失败查看 `.runtime/gateway.stderr.log`。
网关启动器仅对自身进程设置本地地址的 `NO_PROXY`，防止系统代理截获 Token 兑换请求。
测试身份服务日志仅记录 HTTP 方法、路径和状态码，不记录查询参数或请求体。

## 文件说明

- `compose.yaml`、`nginx.conf.template`：两个端口和反向代理配置。
- `public/`：父页面、状态检查和 iframe 自动登录入口。
- `server.mjs`：测试 OIDC 服务和父平台后端，无第三方 Node 依赖。
- `run_gateway.py`：随机凭据、隔离数据库和网关 SSO 配置。
- `start.ps1`、`stop.ps1`：启动、健康检查和清理。
- `server.test.mjs`、`verify_live.py`：拒绝路径和真实网关集成测试。
