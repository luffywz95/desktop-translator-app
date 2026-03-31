"""Helpers for CustomTkinter CTkScrollableFrame: hide scrollbar when content does not overflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import customtkinter as ctk


def sync_scrollbar_visibility(scrollable: "ctk.CTkScrollableFrame") -> None:
    """Show the CTk scrollbar only when vertical content exceeds the canvas viewport."""
    try:
        canvas = scrollable._parent_canvas
        scrollbar = scrollable._scrollbar
    except AttributeError:
        return

    canvas.update_idletasks()
    bbox = canvas.bbox("all")
    ch = max(canvas.winfo_height(), 1)
    if bbox is None:
        content_h = 0
    else:
        content_h = bbox[3] - bbox[1]

    needs_scroll = content_h > (ch + 1)

    sb = scrollbar
    if needs_scroll:
        if not sb.winfo_ismapped():
            gi = getattr(scrollable, "_scrollbar_restore_grid", None)
            if gi:
                sb.grid(**gi)
            else:
                sb.grid()
        return

    if sb.winfo_ismapped():
        if not getattr(scrollable, "_scrollbar_restore_grid", None):
            info = sb.grid_info()
            scrollable._scrollbar_restore_grid = {
                k: info[k]
                for k in (
                    "row",
                    "column",
                    "rowspan",
                    "columnspan",
                    "sticky",
                    "padx",
                    "pady",
                )
                if k in info
            }
        sb.grid_remove()


def attach_scrollbar_auto_hide(
    scrollable: "ctk.CTkScrollableFrame", *extra_configure_watch: Any
) -> None:
    """Bind resize/layout events so scrollbar visibility stays in sync.

    Pass extra widgets (e.g. parent modal) whose <Configure> should trigger a re-check.
    """
    root = scrollable.winfo_toplevel()

    def schedule() -> None:
        prev = getattr(scrollable, "_scrollbar_sync_after", None)
        if prev is not None:
            try:
                root.after_cancel(prev)
            except Exception:
                pass

        def run() -> None:
            setattr(scrollable, "_scrollbar_sync_after", None)
            sync_scrollbar_visibility(scrollable)

        setattr(scrollable, "_scrollbar_sync_after", root.after(20, run))

    scrollable.bind("<Configure>", lambda _e: schedule(), add="+")
    try:
        scrollable._parent_frame.bind("<Configure>", lambda _e: schedule(), add="+")
        scrollable._parent_canvas.bind("<Configure>", lambda _e: schedule(), add="+")
    except AttributeError:
        pass
    for w in extra_configure_watch:
        try:
            w.bind("<Configure>", lambda _e: schedule(), add="+")
        except Exception:
            pass
    root.after_idle(schedule)
