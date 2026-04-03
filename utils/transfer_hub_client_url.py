"""Build the HTTP URL clients (e.g. phone browser) should use for the Transfer Hub."""

from __future__ import annotations

import socket


def primary_lan_ipv4() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def build_transfer_hub_http_url(*, allow_lan: bool, port: int) -> str:
    host = primary_lan_ipv4() if allow_lan else "127.0.0.1"
    return f"http://{host}:{int(port)}/"
