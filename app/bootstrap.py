"""Process-wide startup before Flet UI (single instance, env, OCR paths)."""

from __future__ import annotations

import os
import socket
import sys
import time

import ctypes
from dotenv import load_dotenv

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_PATH = os.path.join(_APP_ROOT, ".env")
_RELOAD_STAGGER_ENV = "_DESKTOP_TRANSLATOR_RELOAD_STAGGER"


def app_root() -> str:
    return _APP_ROOT


def setup_application_environment() -> None:
    """Initialize process environment. Exits on duplicate instance or fatal setup error."""
    if os.environ.pop(_RELOAD_STAGGER_ENV, None) == "1":
        time.sleep(0.45)

    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind(("127.0.0.1", 55555))
    except socket.error:
        _duplicate_instance_message()
        sys.exit(1)

    try:
        with open(os.path.join(_APP_ROOT, "app.pid"), "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    load_dotenv(_ENV_PATH)

    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = os.getenv(
        "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


def _duplicate_instance_message() -> None:
    title = "Error"
    body = "App is already running!"
    if sys.platform == "win32":
        MB_OK = 0x00000000
        MB_ICONERROR = 0x00000010
        ctypes.windll.user32.MessageBoxW(0, body, title, MB_OK | MB_ICONERROR)
    else:
        print(f"{title}: {body}", file=sys.stderr)
