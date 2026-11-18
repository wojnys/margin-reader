"""Start the application processes and contract watcher; stop only processes owned by this launcher."""

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    os.chdir(ROOT)
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm was not found. Activate Node.js 24 LTS and try again.")
    for port in [8017, 5187]:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(
                    f"Port {port} is occupied. Stop the existing Margin process before restarting."
                )
    if not Path("frontend/node_modules").exists():
        subprocess.run([npm, "ci"], cwd="frontend", check=True)
    subprocess.run([npm, "run", "api:generate"], cwd="frontend", check=True)
    # Compose needs no private application configuration. Wait for PostgreSQL before
    # Alembic/API startup, without implicitly loading the private dotenv file.
    subprocess.run(["docker", "compose", "--env-file", "/dev/null", "up", "-d", "--wait"], check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    # Wait for the persistent workflow service to become reachable after a fresh container start.
    from backend.app.core.config import settings

    host, port_text = settings().temporal_address.rsplit(":", 1)
    for _ in range(40):
        try:
            with socket.create_connection((host, int(port_text)), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        raise SystemExit("Temporal did not start. Inspect docker compose logs temporal.")
    children = []

    def stop(*_: object) -> None:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        commands = [
            (
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.app.main:create_app",
                    "--factory",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8017",
                    "--reload",
                ],
                ROOT,
            ),
            ([sys.executable, "-m", "backend.app.temporal.worker"], ROOT),
            ([sys.executable, "-m", "backend.app.temporal.knowledge_worker"], ROOT),
            ([npm, "run", "dev"], ROOT / "frontend"),
            ([npm, "run", "api:watch"], ROOT / "frontend"),
        ]
        for command, directory in commands:
            children.append(
                subprocess.Popen(
                    command,
                    cwd=directory,
                    start_new_session=True,
                    env={**os.environ, "PYDANTIC_AI_NO_BANNER": "1"},
                )
            )
        print(
            "\nMargin: http://localhost:5187\nAPI: http://localhost:8017/docs\nTemporal: http://localhost:8323\n",
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
    finally:
        stop()
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    main()
