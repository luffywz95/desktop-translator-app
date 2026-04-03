"""Put absolute file paths on the Windows clipboard as CF_HDROP (Explorer copy / cut)."""

from __future__ import annotations

import ctypes
import os
import struct
import sys
from ctypes import wintypes

GMEM_MOVEABLE = 0x0002
CF_HDROP = 15
# winuser.h
DROPEFFECT_MOVE = 2
DROPEFFECT_COPY = 1

_preferred_drop_effect_fmt: int | None = None


def _preferred_drop_effect_format() -> int:
    global _preferred_drop_effect_fmt
    if _preferred_drop_effect_fmt is None:
        user32 = ctypes.windll.user32
        user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterClipboardFormatW.restype = wintypes.UINT
        _preferred_drop_effect_fmt = int(user32.RegisterClipboardFormatW("Preferred DropEffect"))
    return _preferred_drop_effect_fmt


def _build_dropfiles_blob(paths: list[str]) -> bytes:
    norm = [os.path.normpath(os.path.abspath(p)) for p in paths if p]
    wide = ("\0".join(norm) + "\0\0").encode("utf-16-le")
    # DROPFILES: pFiles, pt, fNC, fWide
    header = struct.pack("<LllLL", 20, 0, 0, 0, 1)
    return header + wide


def set_clipboard_file_paths(paths: list[str], *, move: bool = False) -> bool:
    """Return True if CF_HDROP (and optional cut effect) was placed on the clipboard."""
    if sys.platform != "win32":
        return False
    paths = [os.path.normpath(os.path.abspath(p)) for p in paths if p]
    if not paths:
        return False

    payload = _build_dropfiles_blob(paths)
    size = len(payload)

    k32 = ctypes.windll.kernel32
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.restype = wintypes.BOOL
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    k32.GlobalFree.restype = wintypes.HGLOBAL

    hglob = k32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not hglob:
        return False
    ptr = k32.GlobalLock(hglob)
    if not ptr:
        k32.GlobalFree(hglob)
        return False
    try:
        ctypes.memmove(ptr, payload, size)
    finally:
        k32.GlobalUnlock(hglob)

    u32 = ctypes.windll.user32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.CloseClipboard.restype = wintypes.BOOL
    u32.EmptyClipboard.restype = wintypes.BOOL
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE

    if not u32.OpenClipboard(None):
        k32.GlobalFree(hglob)
        return False

    try:
        u32.EmptyClipboard()
        if not u32.SetClipboardData(CF_HDROP, hglob):
            k32.GlobalFree(hglob)
            return False
        hglob = None

        effect_val = DROPEFFECT_MOVE if move else DROPEFFECT_COPY
        effect_bytes = struct.pack("I", effect_val)
        sz = len(effect_bytes)
        h_eff = k32.GlobalAlloc(GMEM_MOVEABLE, sz)
        if h_eff:
            p2 = k32.GlobalLock(h_eff)
            if not p2:
                k32.GlobalFree(h_eff)
            else:
                try:
                    ctypes.memmove(p2, effect_bytes, sz)
                finally:
                    k32.GlobalUnlock(h_eff)
                fmt = _preferred_drop_effect_format()
                if not u32.SetClipboardData(fmt, h_eff):
                    k32.GlobalFree(h_eff)
    finally:
        u32.CloseClipboard()
        if hglob is not None:
            k32.GlobalFree(hglob)

    return True
