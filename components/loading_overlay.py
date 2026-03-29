"""Busy overlay with indeterminate progress (CustomTkinter).

Supports anchoring to the main window (full-app block) or to a frame (scoped region).
"""

from __future__ import annotations

import threading
import time
from tkinter import TclError
from typing import Any, Callable, Union

import customtkinter as ctk

__all__ = ["BusyOverlay", "run_blocking_task_with_busy_ui"]

_Anchor = Union[ctk.CTk, ctk.CTkFrame]

# Component-local visual tokens (parity with previous inline implementation)
_OVERLAY_FG_COLOR = ("#c8c8c8", "#2b2b2b")
_MESSAGE_FONT = ("Segoe UI", 14)
_MESSAGE_FONT_COMPACT = ("Segoe UI", 11)
_MESSAGE_TEXT_COLOR = ("gray10", "gray90")
_PROGRESS_WIDTH = 240
_PROGRESS_WIDTH_COMPACT = 160
_PROGRESS_COLOR = ("#3498db", "#3498db")

_POLL_SLEEP_S = 0.03


def _anchor_is_app_root(anchor: _Anchor) -> bool:
    """True when the anchor is the top-level CTk window (full-window overlay mode)."""
    return isinstance(anchor, ctk.CTk)


class BusyOverlay:
    """Dimmed layer with message + indeterminate bar, placed over an anchor widget.

    ``anchor`` may be the root ``CTk`` window (blocks the whole app) or a ``CTkFrame``
    that wraps a specific region (only that area is covered; the rest stays usable).
    """

    def __init__(self, anchor: _Anchor) -> None:
        self._anchor = anchor
        self._layer: ctk.CTkFrame | None = None
        self._msg: ctk.CTkLabel | None = None
        self._pb: ctk.CTkProgressBar | None = None

    def show(self, message: str) -> None:
        compact = not _anchor_is_app_root(self._anchor)
        msg_font = _MESSAGE_FONT_COMPACT if compact else _MESSAGE_FONT
        pb_width = _PROGRESS_WIDTH_COMPACT if compact else _PROGRESS_WIDTH

        if self._layer is None or not self._layer.winfo_exists():
            self._layer = ctk.CTkFrame(
                self._anchor,
                corner_radius=0,
                fg_color=_OVERLAY_FG_COLOR,
            )
            inner = ctk.CTkFrame(self._layer, fg_color="transparent")
            inner.place(relx=0.5, rely=0.5, anchor="center")
            self._msg = ctk.CTkLabel(
                inner,
                text="",
                font=msg_font,
                text_color=_MESSAGE_TEXT_COLOR,
                wraplength=pb_width + 40,
            )
            self._msg.pack(pady=(0, 8 if compact else 14))
            self._pb = ctk.CTkProgressBar(
                inner,
                width=pb_width,
                mode="indeterminate",
                progress_color=_PROGRESS_COLOR,
            )
            self._pb.pack()
        assert self._msg is not None and self._pb is not None
        self._msg.configure(text=message, font=msg_font, wraplength=pb_width + 40)
        self._pb.configure(width=pb_width)
        self._layer.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._layer.lift()
        self._pb.start()
        self._anchor.update_idletasks()
        if _anchor_is_app_root(self._anchor):
            self._anchor.update()

    def hide(self) -> None:
        if self._layer is None or not self._layer.winfo_exists():
            return
        try:
            if self._pb is not None:
                self._pb.stop()
        except (TclError, AttributeError):
            pass
        self._layer.place_forget()


def run_blocking_task_with_busy_ui(
    master: ctk.CTk,
    busy: BusyOverlay,
    message: str,
    fn: Callable[[], Any],
) -> Any:
    """Run ``fn`` in a worker thread while ``busy`` is shown and the UI keeps animating.

    ``busy`` should be anchored to ``master`` (full-window). The polling loop drives
    ``master.update()`` so the indeterminate bar keeps moving until the thread ends.
    """
    result: dict[str, Any] = {}
    err: list[BaseException] = []

    def target() -> None:
        try:
            result["v"] = fn()
        except BaseException as e:
            err.append(e)

    th = threading.Thread(target=target, daemon=True)
    busy.show(message)
    th.start()
    try:
        while th.is_alive():
            master.update_idletasks()
            master.update()
            time.sleep(_POLL_SLEEP_S)
    finally:
        busy.hide()
    if err:
        raise err[0]
    return result.get("v")
