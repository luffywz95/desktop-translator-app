"""Start/stop Transfer Hub (Flask) as a subprocess while the main window is visible."""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time

from components.logger import Logger

logger = Logger().get()

_proc: subprocess.Popen | None = None


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def start_transfer_hub_server(allow_lan: bool = False, port: int = 5000) -> None:
    """Run utils/server.py if not already running."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return

    root = _project_root()
    script = os.path.join(root, "utils", "server.py")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    env = os.environ.copy()
    env["TRANSFER_HUB_HOST"] = "0.0.0.0" if allow_lan else "127.0.0.1"
    env["TRANSFER_HUB_PORT"] = str(int(port))

    _proc = subprocess.Popen(
        [sys.executable, "-u", script],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    logger.info(
        "Transfer Hub server started (pid %s) host=%s port=%s — window is visible",
        _proc.pid,
        env["TRANSFER_HUB_HOST"],
        env["TRANSFER_HUB_PORT"],
    )

    time.sleep(0.15)
    if _proc.poll() is not None:
        logger.error(
            "Transfer Hub server exited immediately (e.g. selected port in use). "
            "Check logs or stop the other process using that port."
        )


def stop_transfer_hub_server() -> None:
    """Terminate the Flask child process if it is running."""
    global _proc
    if _proc is None:
        return
    if _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
            _proc.wait(timeout=2)
        logger.info("Transfer Hub server stopped (window hidden or app exit)")
    _proc = None


def restart_transfer_hub_server(allow_lan: bool = False, port: int = 5000) -> None:
    """Stop and start the child so bind address / env changes apply."""
    stop_transfer_hub_server()
    start_transfer_hub_server(allow_lan=allow_lan, port=port)


atexit.register(stop_transfer_hub_server)
