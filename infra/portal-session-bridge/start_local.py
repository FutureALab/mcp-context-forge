"""Start the local parent page and gateway on ports 5173 and 4445."""

import argparse
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
PAGE_URL = "http://localhost:5173/infra/portal-session-bridge/local-test.html"
GATEWAY_URL = "http://localhost:4445"
DEMO_EMAIL = "demo@example.com"
DEMO_SERVER_ID = "portal-demo-public"


def port_open(port: int) -> bool:
    """Return whether a local TCP service accepts connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def start_process(arguments: list[str], name: str, environment: dict[str, str]) -> subprocess.Popen:
    """Start a hidden local service and save its output in temporary files."""
    log_dir = Path(tempfile.gettempdir())
    with (log_dir / f"mcp-portal-{name}.out.log").open("w", encoding="utf-8") as output, (log_dir / f"mcp-portal-{name}.err.log").open("w", encoding="utf-8") as error:
        return subprocess.Popen(arguments, cwd=ROOT, env=environment, stdout=output, stderr=error, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def require_database() -> None:
    """Report an unavailable PostgreSQL server before waiting for gateway startup."""
    from dotenv import dotenv_values
    from sqlalchemy.engine import make_url

    database_url = os.environ.get("DATABASE_URL") or dotenv_values(ROOT / ".env").get("DATABASE_URL")
    if not database_url:
        return
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return
    host, port = url.host or "localhost", url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError as exc:
        raise SystemExit(f"PostgreSQL {host}:{port} 未启动或无法连接。请先启动数据库；只需本机演示时给启动命令加上 --demo-db。") from exc


async def seed_demo_user() -> None:
    """Create an isolated portal account and public MCP for the local demo."""
    from sqlalchemy import select

    from mcpgateway.db import EmailTeam, EmailUser, Server, SessionLocal
    from mcpgateway.services.email_auth_service import EmailAuthService

    with SessionLocal() as db:
        user = db.execute(select(EmailUser).where(EmailUser.email == DEMO_EMAIL)).scalar_one_or_none()
        if user is None:
            user = await EmailAuthService(db).create_user(DEMO_EMAIL, "", full_name="Demo User", auth_provider="portal", skip_password_validation=True)
        team = db.execute(select(EmailTeam).where(EmailTeam.created_by == user.email, EmailTeam.is_personal.is_(True))).scalar_one_or_none()
        if db.get(Server, DEMO_SERVER_ID) is None:
            db.add(Server(id=DEMO_SERVER_ID, name="本机演示 MCP", owner_email=user.email, team_id=team.id if team else None, visibility="public", enabled=True))
            db.commit()


def main() -> None:
    """Launch missing services and report their local URLs."""
    parser = argparse.ArgumentParser(description="Start the local parent page and gateway")
    parser.add_argument("--demo-db", action="store_true", help="Use an isolated SQLite database with a demo account")
    args = parser.parse_args()
    if port_open(4445):
        raise SystemExit("4445 端口已被占用，请先关闭该端口的服务。")
    if not args.demo_db:
        require_database()
    page = None
    if not port_open(5173):
        page = start_process([sys.executable, "-m", "http.server", "5173", "--bind", "localhost"], "page", os.environ.copy())

    environment = os.environ.copy()
    environment.update(
        HOST="127.0.0.1",
        PORT="4445",
        PORTAL_SSO_ENABLED="true",
        PORTAL_SSO_PARENT_ORIGIN="http://localhost:5173",
        ALLOWED_ORIGINS='["http://localhost:5173","http://localhost:4445"]',
        X_FRAME_OPTIONS="none",
        SECURE_COOKIES="false",
        RATE_LIMITING_ENABLED="false",
        PYTHONIOENCODING="utf-8",
    )
    if args.demo_db:
        demo_db = Path(tempfile.gettempdir()) / f"mcp-portal-demo-{os.getpid()}.db"
        environment.update(DATABASE_URL=f"sqlite:///{demo_db.as_posix()}", SELF_SERVICE_API_KEYS_ENABLED="true", MCPGATEWAY_UI_ENABLED="true", MCPGATEWAY_ADMIN_API_ENABLED="true")
    gateway = None
    try:
        gateway = start_process([sys.executable, "-m", "mcpgateway"], "gateway", environment)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if gateway.poll() is not None:
                raise SystemExit(f"网关启动失败，请查看 {Path(tempfile.gettempdir()) / 'mcp-portal-gateway.err.log'}")
            try:
                with urlopen(f"{GATEWAY_URL}/health", timeout=2) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                pass
            time.sleep(1)
        else:
            raise SystemExit(f"网关未在 60 秒内就绪，请查看 {Path(tempfile.gettempdir()) / 'mcp-portal-gateway.err.log'}")

        if args.demo_db:
            os.environ.update(environment)
            asyncio.run(seed_demo_user())

        with urlopen(PAGE_URL, timeout=3) as response:
            if response.status != 200 or b"MCP Gateway" not in response.read():
                raise SystemExit("5173 端口不是本项目演示页。")
    except BaseException:
        if gateway is not None and gateway.poll() is None:
            gateway.terminate()
        if page is not None and page.poll() is None:
            page.terminate()
        raise

    print(f"Demo page: {PAGE_URL}")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Gateway PID: {gateway.pid}")
    if args.demo_db:
        print(f"Demo account: Demo User / {DEMO_EMAIL}")
        print(f"Demo database: {demo_db}")


if __name__ == "__main__":
    main()
