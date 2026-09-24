"""Start the local parent page and gateway on ports 5173 and 4445."""

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


def main() -> None:
    """Launch missing services and report their local URLs."""
    if port_open(4445):
        raise SystemExit("4445 端口已被占用，请先关闭该端口的服务。")
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


if __name__ == "__main__":
    main()
