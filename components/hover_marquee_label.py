"""Clipped single-line label with slow horizontal marquee on pointer hover (overflow only)."""

from __future__ import annotations

import time
from tkinter import font as tkfont
from typing import Any

import customtkinter as ctk
from customtkinter import ThemeManager

__all__ = ["HoverMarqueeClipLabel"]


class HoverMarqueeClipLabel(ctk.CTkFrame):
    """Transparent frame + canvas; text scrolls left while pointer is over and text overflows."""

    _PAD_X = 2
    _SCROLL_STEP_PX = 1
    _SCROLL_INTERVAL_MS = 52
    _PAUSE_AT_END_MS = 650

    def __init__(
        self,
        master: Any,
        *,
        text: str = "",
        font: tuple[str, int] | tuple[str, int, str] = ("Segoe UI", 11),
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._font_tuple = font
        self._tk_font = tkfont.Font(root=self, family=font[0], size=font[1])
        self._text = text
        self._scroll_x = 0
        self._pause_until_ms = 0.0
        self._after_id: str | None = None
        self._hover = False
        self._overflow = False
        self._text_item: int | None = None
        self._last_canvas_w = 1
        self._text_fill_resolved = "#000000"

        line_h = max(22, self._tk_font.metrics("linespace") + 4)
        self._canvas = ctk.CTkCanvas(
            self,
            highlightthickness=0,
            bd=0,
            height=line_h,
        )
        self._canvas.pack(fill="x", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        self.bind("<Destroy>", self._on_destroy)

        self._sync_draw()

    def _appearance_index(self) -> int:
        return 1 if str(ctk.get_appearance_mode()).lower() == "dark" else 0

    def configure(self, **kwargs: Any) -> None:
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            self._scroll_x = 0
            self._pause_until_ms = 0.0
            self._overflow = self._has_overflow()
            if not self._overflow:
                self._cancel_after()
            self._sync_draw()
        if kwargs:
            super().configure(**kwargs)

    def cget(self, key: str) -> Any:
        if key == "text":
            return self._text
        return super().cget(key)

    def _on_destroy(self, _event: Any) -> None:
        self._cancel_after()

    def _cancel_after(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _text_width(self) -> int:
        if not self._text:
            return 0
        return int(self._tk_font.measure(self._text))

    def _visible_inner_w(self) -> int:
        w = self._last_canvas_w - 2 * self._PAD_X
        return max(0, w)

    def _has_overflow(self) -> bool:
        vw = self._visible_inner_w()
        if vw < 4:
            return False
        return self._text_width() > vw

    def _max_scroll(self) -> int:
        vw = self._visible_inner_w()
        tw = self._text_width()
        return max(0, tw - vw)

    def _on_canvas_configure(self, _event: Any) -> None:
        nw = self._canvas.winfo_width()
        if nw < 2:
            return
        self._last_canvas_w = nw
        self._overflow = self._has_overflow()
        self._sync_draw()
        if self._hover and self._overflow:
            self._start_marquee_if_needed()
        else:
            self._cancel_after()

    def _sync_draw(self) -> None:
        if not self.winfo_exists():
            return
        idx = self._appearance_index()
        fill = ThemeManager.theme["CTkLabel"]["text_color"][idx]
        self._text_fill_resolved = fill
        bg = ThemeManager.theme["CTk"]["fg_color"][idx]
        try:
            self._canvas.configure(bg=bg)
        except Exception:
            pass

        self._canvas.delete("all")
        self._text_item = None
        h = self._canvas.winfo_height()
        if h < 4:
            h = int(self._canvas.cget("height"))
        cy = max(h // 2, 1)
        sx = self._scroll_x if (self._hover and self._overflow) else 0
        x0 = self._PAD_X - sx
        self._text_item = self._canvas.create_text(
            x0,
            cy,
            text=self._text,
            anchor="w",
            font=self._font_tuple,
            fill=fill,
        )

    def _draw_scroll_position(self) -> None:
        if self._text_item is None:
            self._sync_draw()
            return
        fill = self._text_fill_resolved
        h = self._canvas.winfo_height()
        if h < 4:
            h = int(self._canvas.cget("height"))
        cy = max(h // 2, 1)
        sx = self._scroll_x if (self._hover and self._overflow) else 0
        x0 = self._PAD_X - sx
        try:
            self._canvas.coords(self._text_item, x0, cy)
            self._canvas.itemconfigure(self._text_item, fill=fill)
        except Exception:
            self._sync_draw()

    def _on_enter(self, _event: Any) -> None:
        self._hover = True
        self._overflow = self._has_overflow()
        if self._overflow:
            self._start_marquee_if_needed()

    def _on_leave(self, _event: Any) -> None:
        self._hover = False
        self._cancel_after()
        self._scroll_x = 0
        self._pause_until_ms = 0.0
        self._draw_scroll_position()

    def _start_marquee_if_needed(self) -> None:
        if not self._overflow or not self._hover:
            return
        self._cancel_after()
        self._after_id = self.after(self._SCROLL_INTERVAL_MS, self._tick)

    def _tick(self) -> None:
        self._after_id = None
        if not self.winfo_exists():
            return
        if not self._hover:
            return
        self._overflow = self._has_overflow()
        if not self._overflow:
            self._scroll_x = 0
            self._draw_scroll_position()
            return

        now = time.monotonic() * 1000.0
        if now < self._pause_until_ms:
            self._after_id = self.after(self._SCROLL_INTERVAL_MS, self._tick)
            return

        max_s = self._max_scroll()
        if max_s <= 0:
            self._sync_draw()
            return

        self._scroll_x += self._SCROLL_STEP_PX
        if self._scroll_x >= max_s:
            self._scroll_x = 0
            self._pause_until_ms = now + self._PAUSE_AT_END_MS

        self._draw_scroll_position()
        self._after_id = self.after(self._SCROLL_INTERVAL_MS, self._tick)
