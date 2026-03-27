"""Outbound multipart file upload via urllib (no extra dependencies)."""

from __future__ import annotations

import mimetypes
import os
import uuid
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _read_response_body(resp) -> str:
    try:
        data = resp.read()
        if not data:
            return ""
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def post_file_multipart(
    url: str,
    file_path: str,
    field_name: str = "file",
    bearer_token: Optional[str] = None,
    timeout: float = 120.0,
    extra_headers: Optional[dict[str, str]] = None,
) -> tuple[int, str]:
    """
    POST file as multipart/form-data (one part: field_name).

    Returns (status_code, body_or_error_text).
    """
    url = (url or "").strip()
    if not url:
        return 0, "No URL provided."

    path = os.path.abspath(os.path.expanduser(file_path))
    if not os.path.isfile(path):
        return 0, f"File not found: {path}"

    filename = os.path.basename(path)
    mime, _ = mimetypes.guess_type(filename)
    if not mime:
        mime = "application/octet-stream"

    boundary = f"----TheOwlBoundary{uuid.uuid4().hex}"

    with open(path, "rb") as f:
        file_bytes = f.read()

    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n"
        "\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("ascii")
    body = head + file_bytes + tail

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "TheOwl-TransferHub/1.0",
    }
    if bearer_token and bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token.strip()}"
    if extra_headers:
        for k, v in extra_headers.items():
            if k and v is not None:
                headers[str(k)] = str(v)

    req = Request(url, data=body, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            text = _read_response_body(resp)
            return int(code), text[:8000] if text else ""
    except HTTPError as e:
        try:
            body_txt = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_txt = str(e)
        return int(e.code), (body_txt or str(e))[:8000]
    except URLError as e:
        return 0, f"Network error: {e.reason!s}" if e.reason else f"Network error: {e}"
    except OSError as e:
        return 0, f"Request failed: {e}"
