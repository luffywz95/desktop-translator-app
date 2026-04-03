"""Start a Cloudflare quick tunnel (trycloudflare.com) to a local HTTP URL via the cloudflared CLI."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from typing import IO

_TRYCF_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com/?", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def cloudflared_executable() -> str | None:
    return shutil.which("cloudflared")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _scan_line_for_url(line: str) -> str | None:
    m = _TRYCF_RE.search(_strip_ansi(line))
    if not m:
        return None
    u = m.group(0).rstrip("/")
    return u + "/"


def _read_stream_for_url(stream: IO[str], out: list[str | None], stop: threading.Event) -> None:
    try:
        while not stop.is_set():
            line = stream.readline()
            if not line:
                break
            url = _scan_line_for_url(line)
            if url:
                out[0] = url
                stop.set()
                return
    except Exception:
        pass


def start_quick_tunnel(local_http_url: str, *, timeout_s: float = 90.0) -> tuple[str, subprocess.Popen[str]]:
    """Run ``cloudflared tunnel --url <local_http_url>`` and return (public_https_url, process).

    Caller must terminate *process* when done. Raises FileNotFoundError if cloudflared is not on PATH,
    RuntimeError on timeout or early process exit without a URL.
    """
    exe = cloudflared_executable()
    if not exe:
        raise FileNotFoundError("cloudflared executable not found in PATH")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        [exe, "tunnel", "--url", local_http_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )

    url_box: list[str | None] = [None]
    stop = threading.Event()
    assert proc.stdout is not None and proc.stderr is not None
    t_out = threading.Thread(target=_read_stream_for_url, args=(proc.stdout, url_box, stop), daemon=True)
    t_err = threading.Thread(target=_read_stream_for_url, args=(proc.stderr, url_box, stop), daemon=True)
    t_out.start()
    t_err.start()

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if url_box[0]:
            return url_box[0], proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    stop.set()
    for t in (t_out, t_err):
        t.join(timeout=1.0)
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    if url_box[0]:
        return url_box[0], proc

    raise RuntimeError(
        "Timed out or cloudflared exited before printing a trycloudflare.com URL. "
        "Install cloudflared and ensure it is on PATH, or check your network."
    )
