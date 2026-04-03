"""Windows desktop: accept Explorer file drops on the Flet top-level window (WM_DROPFILES).

Flet's DragTarget is in-app only; this hooks the native HWND after the window appears.
"""

from __future__ import annotations

import asyncio
import ctypes
import sys
from ctypes import wintypes
from typing import Any, Callable

import flet as ft

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL

_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int

_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int

_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_void_p

_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
_user32.SetWindowLongPtrW.restype = ctypes.c_void_p

_user32.CallWindowProcW.argtypes = [
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.CallWindowProcW.restype = ctypes.c_void_p

_shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
_shell32.DragAcceptFiles.restype = None

_shell32.DragQueryFileW.argtypes = [
    wintypes.WPARAM,
    wintypes.UINT,
    wintypes.LPWSTR,
    wintypes.UINT,
]
_shell32.DragQueryFileW.restype = wintypes.UINT

_shell32.DragFinish.argtypes = [wintypes.WPARAM]
_shell32.DragFinish.restype = None

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_void_p,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]


class _ShellDropBinding:
    __slots__ = ("hwnd", "old_proc", "py_wndproc")

    def __init__(self, hwnd: int, old_proc: int, py_wndproc: Any):
        self.hwnd = hwnd
        self.old_proc = old_proc
        self.py_wndproc = py_wndproc

    def release(self) -> None:
        try:
            _shell32.DragAcceptFiles(self.hwnd, False)
        except Exception:
            pass
        try:
            _user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, ctypes.c_void_p(self.old_proc))
        except Exception:
            pass
        self.py_wndproc = None


_active: _ShellDropBinding | None = None


def uninstall_win32_shell_file_drop() -> None:
    global _active
    if _active is not None:
        try:
            _active.release()
        finally:
            _active = None


def _find_visible_hwnd_exact_title(title: str) -> int | None:
    matches: list[int] = []

    @EnumWindowsProc
    def enum_cb(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        n = _user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value == title:
            matches.append(int(hwnd))
        return True

    _user32.EnumWindows(enum_cb, 0)
    return matches[0] if matches else None


def _paths_from_hdrop(hdrop: wintypes.WPARAM) -> list[str]:
    n = _shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
    out: list[str] = []
    for i in range(int(n)):
        buf = ctypes.create_unicode_buffer(4096)
        _shell32.DragQueryFileW(hdrop, i, buf, len(buf))
        if buf.value:
            out.append(buf.value)
    return out


def _try_bind(hwnd: int, app: Any, on_paths: Callable[[list[str]], None]) -> bool:
    global _active
    if _active is not None:
        return True

    old = _user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    old_int = ctypes.cast(old, ctypes.c_void_p).value or 0
    if not old_int:
        return False

    ctx: dict[str, Any] = {"app": app, "on_paths": on_paths}

    @WNDPROC
    def wndproc(hwnd_, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                paths = _paths_from_hdrop(wparam)
                _shell32.DragFinish(wparam)
                if paths:
                    a = ctx["app"]
                    op = ctx["on_paths"]

                    def work() -> None:
                        try:
                            op(paths)
                        except Exception:
                            a.logger.exception("Shell file drop handler failed")

                    a.run_on_ui(work)
            except Exception:
                try:
                    _shell32.DragFinish(wparam)
                except Exception:
                    pass
            return 0
        return _user32.CallWindowProcW(
            ctypes.c_void_p(old_int),
            hwnd_,
            msg,
            wparam,
            lparam,
        )

    py_proc = wndproc
    ctypes.windll.kernel32.SetLastError(0)
    prev = _user32.SetWindowLongPtrW(
        hwnd,
        GWLP_WNDPROC,
        ctypes.cast(py_proc, ctypes.c_void_p),
    )
    err = ctypes.get_last_error()
    if (prev is None or ctypes.cast(prev, ctypes.c_void_p).value == 0) and err != 0:
        return False

    try:
        _shell32.DragAcceptFiles(hwnd, True)
    except Exception:
        _user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.c_void_p(old_int))
        return False

    _active = _ShellDropBinding(hwnd, old_int, py_proc)
    return True


def schedule_win32_shell_file_drop(
    page: ft.Page,
    app: Any,
    on_paths: Callable[[list[str]], None],
    *,
    window_title: str | None = None,
) -> None:
    if sys.platform != "win32":
        return
    if getattr(page, "web", False):
        return
    title = (window_title or page.title or "").strip()
    if not title:
        return

    async def _poll_and_bind() -> None:
        for _ in range(80):
            hwnd = _find_visible_hwnd_exact_title(title)
            if hwnd and _try_bind(hwnd, app, on_paths):
                app.logger.debug("Win32 shell file drop enabled (hwnd=%s)", hwnd)
                return
            await asyncio.sleep(0.1)
        app.logger.debug("Win32 shell file drop: no HWND matched title %r", title)

    try:
        page.run_task(_poll_and_bind)
    except Exception:
        app.logger.debug("Win32 shell file drop: run_task failed", exc_info=True)
