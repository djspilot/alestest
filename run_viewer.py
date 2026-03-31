#!/usr/bin/env python3

from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parent
VIEWER_DIR = ROOT_DIR / "viewer"

API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8000"))
VIEWER_HOST = os.environ.get("VIEWER_HOST", "127.0.0.1")
VIEWER_PORT = int(os.environ.get("VIEWER_PORT", "5173"))
API_PORT_FALLBACK_RANGE = int(os.environ.get("API_PORT_FALLBACK_RANGE", "20"))
VIEWER_PORT_FALLBACK_RANGE = int(os.environ.get("VIEWER_PORT_FALLBACK_RANGE", "20"))

API_URL = f"http://{API_HOST}:{API_PORT}"
VIEWER_URL = f"http://{VIEWER_HOST}:{VIEWER_PORT}"

PROCESSES: list[subprocess.Popen] = []


def require_command(name: str) -> str:
    command = shutil.which(name)
    if not command:
        raise SystemExit(f"Missing required command: {name}")
    return command


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def find_free_port(host: str, requested_port: int, fallback_range: int, label: str) -> int:
    for offset in range(fallback_range + 1):
        candidate = requested_port + offset
        if not port_in_use(host, candidate):
            if candidate != requested_port:
                print(f"{label} port {requested_port} is in use, falling back to {candidate}.", file=sys.stderr)
            return candidate
    raise SystemExit(
        f"No free {label.lower()} port found in range {requested_port}-{requested_port + fallback_range}."
    )


def wait_for_http(url: str, label: str, attempts: int = 40) -> None:
    for _ in range(attempts):
        try:
            with urlopen(url, timeout=1.5) as response:
                if 200 <= response.status < 500:
                    print(f"{label} ready at {url}")
                    return
        except URLError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"{label} did not become ready: {url}")


def terminate_processes() -> None:
    for process in reversed(PROCESSES):
        if process.poll() is not None:
            continue
        process.terminate()

    deadline = time.time() + 5
    for process in reversed(PROCESSES):
        if process.poll() is not None:
            continue
        remaining = max(deadline - time.time(), 0)
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()


def handle_signal(signum, _frame) -> None:
    terminate_processes()
    raise SystemExit(128 + signum)


def spawn_process(command: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(command, cwd=cwd, creationflags=creationflags, env=env)
    PROCESSES.append(process)
    return process


def main() -> int:
    global API_PORT, VIEWER_PORT, API_URL, VIEWER_URL

    python_executable = sys.executable
    npm_command = require_command("npm.cmd" if os.name == "nt" else "npm")

    # Ensure viewer dependencies are installed (vite etc.)
    node_modules = VIEWER_DIR / "node_modules"
    if not node_modules.exists():
        print("Viewer dependencies not found. Running npm install...")
        subprocess.run([npm_command, "install"], cwd=VIEWER_DIR, check=True)
        print("Viewer dependencies installed.")

    API_PORT = find_free_port(API_HOST, API_PORT, API_PORT_FALLBACK_RANGE, "API")
    VIEWER_PORT = find_free_port(VIEWER_HOST, VIEWER_PORT, VIEWER_PORT_FALLBACK_RANGE, "Viewer")
    API_URL = f"http://{API_HOST}:{API_PORT}"
    VIEWER_URL = f"http://{VIEWER_HOST}:{VIEWER_PORT}"

    atexit.register(terminate_processes)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    spawn_process(
        [
            python_executable,
            "-m",
            "uvicorn",
            "manufacturing_pipeline.api.app:app",
            "--host",
            API_HOST,
            "--port",
            str(API_PORT),
        ],
        ROOT_DIR,
    )
    wait_for_http(f"{API_URL}/api/v1/health", "API")

    spawn_process(
        [
            npm_command,
            "run",
            "dev",
            "--",
            "--host",
            VIEWER_HOST,
            "--port",
            str(VIEWER_PORT),
        ],
        VIEWER_DIR,
        extra_env={"VITE_PIPELINE_API_BASE_URL": API_URL},
    )
    wait_for_http(VIEWER_URL, "Viewer")

    print(
        "\nALES STEP Viewer is running.\n"
        f"Viewer: {VIEWER_URL}\n"
        f"API:    {API_URL}\n\n"
        "Press Ctrl+C to stop both processes."
    )

    exit_codes = [process.wait() for process in PROCESSES]
    return next((code for code in exit_codes if code), 0)


if __name__ == "__main__":
    raise SystemExit(main())
