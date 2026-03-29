"""Convert Image tab UI aligned with design mockups (wide + narrow / small screen).

Sections: 1. INPUT QUEUE, 2. CONFIGURE OUTPUT, 3. PROCESS — dashed drop zone, thumbnails,
output folder + batch conversion, progress bar, metadata/CMYK options.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk
from tkinter import BooleanVar, DoubleVar, StringVar

from app.controllers.convert_image_controller import (
    convert_tab_browse,
    convert_tab_browse_output_folder,
    convert_tab_clear_queue,
    convert_tab_handle_drop,
    convert_tab_on_output_folder_change,
    convert_tab_run,
    update_convert_quality_percent_label,
)
from app.services.image_convert_service import LOSSY_FORMATS, OUTPUT_FORMATS

REFLOW_WIDE_PX = 800

# Drop zone: compact target (esp. narrow / small screen); queue list gets remaining space.
DROP_ZONE_H_WIDE = 88
# Narrow: short band for section "1. INPUT QUEUE" (drop + list + toolbar row).
DROP_ZONE_H_NARROW = 120
DROP_ZONE_COL_MIN_NARROW = 120

# List height
LIST_H_WIDE = 200
LIST_H_NARROW = 80

# Small screen: queue panel height (title + padded inner + grid). Needs grid_propagate(False).
# ~ title + inner margins + max(drop, list + gap + toolbar).
PANEL_QUEUE_HEIGHT_NARROW = 80

_CARD_CORNER = 10
_CARD_BORDER = 1
_CARD_FG = ("#ebebeb", "#2b2b2b")
_CARD_BORDER_COLOR = ("#c8c8c8", "#3d3d3d")
_SECTION_FONT = ("Segoe UI", 11, "bold")


def _section_card(parent: ctk.CTkFrame, title: str, **kwargs: Any) -> ctk.CTkFrame:
    card = ctk.CTkFrame(
        parent,
        fg_color=_CARD_FG,
        corner_radius=_CARD_CORNER,
        border_width=_CARD_BORDER,
        border_color=_CARD_BORDER_COLOR,
        **kwargs,
    )
    ctk.CTkLabel(
        card,
        text=title,
        font=_SECTION_FONT,
        anchor="w",
        text_color=("gray10", "gray90"),
    ).pack(fill="x", padx=10, pady=3)

    inner = ctk.CTkScrollableFrame(card, fg_color="transparent")
    inner._scrollbar.configure(height=0)
    inner.pack(fill="both", expand=True, padx=8, pady=(0, 10))
    # Card must be placed on the parent; otherwise the whole section stays unmapped.
    card.pack(fill="both", expand=True)
    return inner


def _build_queue_section_card(app: Any, panel: ctk.CTkFrame) -> ctk.CTkFrame:
    """Card shell for '1. INPUT QUEUE' with refs so narrow vs wide padding/font can be applied."""
    card = ctk.CTkFrame(
        panel,
        fg_color=_CARD_FG,
        corner_radius=_CARD_CORNER,
        border_width=_CARD_BORDER,
        border_color=_CARD_BORDER_COLOR,
    )
    app._convert_queue_section_label = ctk.CTkLabel(
        card,
        text="1. SELECT INPUT (QUEUE)",
        font=_SECTION_FONT,
        anchor="w",
        text_color=("gray10", "gray90"),
    )
    app._convert_queue_section_label.pack(fill="x", padx=10, pady=(10, 6))
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=8, pady=(0, 10))
    card.pack(fill="both", expand=True)
    return inner


def _apply_queue_section_chrome(app: Any, wide: bool) -> None:
    """Tighter title + inner padding on narrow so the first section stays short."""
    lbl = getattr(app, "_convert_queue_section_label", None)
    inner = getattr(app, "_convert_queue_inner", None)
    if lbl is None or inner is None:
        return
    if wide:
        lbl.pack_configure(padx=10, pady=(10, 6))
        lbl.configure(font=_SECTION_FONT)
        inner.pack_configure(padx=8, pady=(0, 10))
    else:
        lbl.pack_configure(padx=8, pady=(6, 3))
        lbl.configure(font=("Segoe UI", 10, "bold"))
        inner.pack_configure(padx=6, pady=(0, 6))


def _canvas_bg_fg() -> tuple[str, str]:
    mode = ctk.get_appearance_mode()
    if mode == "Dark":
        return "#2b2b2b", "#c8c8c8"
    return "#ebebeb", "#505050"


def _build_dashed_drop_canvas(
    parent: ctk.CTkFrame, app: Any, dnd_files: str, height: int, width: int
) -> tk.Canvas:
    bg, fg = _canvas_bg_fg()
    canvas = tk.Canvas(
        parent,
        height=height,
        width=width,
        highlightthickness=0,
        bg=bg,
        cursor="hand2",
    )

    def redraw(_event: object | None = None) -> None:
        canvas.delete("all")
        w = max(canvas.winfo_width(), 2)
        h = max(canvas.winfo_height(), 2)
        b, fgc = _canvas_bg_fg()
        canvas.configure(bg=b)
        outline = "#666666" if ctk.get_appearance_mode() == "Dark" else "#888888"
        compact = getattr(app, "_convert_drop_compact", False)
        pad = 5 if compact else 8
        font = ("Segoe UI", 10) if compact else ("Segoe UI", 11)
        canvas.create_rectangle(
            pad,
            pad,
            w - pad,
            h - pad,
            dash=(6, 4),
            outline=outline,
            width=2,
            fill=b,
        )
        canvas.create_text(
            w // 2,
            h // 2,
            text="Drag & Drop",
            font=font,
            fill=fgc,
        )

    canvas.bind("<Configure>", lambda e: redraw(e))
    canvas.drop_target_register(dnd_files)
    canvas.dnd_bind("<<Drop>>", lambda e: convert_tab_handle_drop(app, e))
    app._convert_drop_redraw = redraw
    return canvas


def _repack_drop_canvas(app: Any) -> None:
    """Keep the drop target short; do not stretch it to fill extra vertical space."""
    c = app._convert_drop_canvas
    c.pack_forget()
    c.pack(fill="x", expand=False)


def _apply_convert_queue_inner_layout(app: Any, wide: bool) -> None:
    inner = app._convert_queue_inner
    drop_wrap = app._convert_drop_wrap
    lst = app._convert_list_frame
    tb_wide = app._convert_queue_toolbar_wide
    tb_narrow = app._convert_queue_toolbar_narrow

    for w in (drop_wrap, lst, tb_wide, tb_narrow):
        w.grid_forget()

    app._convert_drop_compact = not wide

    if wide:
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(1, weight=1)
        drop_wrap.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        lst.grid(row=1, column=0, sticky="nsew")
        lst._scrollbar.configure(height=0)
        tb_wide.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        app._convert_drop_canvas.configure(height=DROP_ZONE_H_WIDE)
    else:
        inner.grid_columnconfigure(0, weight=0, minsize=DROP_ZONE_COL_MIN_NARROW)
        inner.grid_columnconfigure(1, weight=1)
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_rowconfigure(1, weight=0)
        # Top-aligned compact layout: drop zone and toolbar side-by-side; hide list on narrow.
        drop_wrap.grid(row=0, column=0, rowspan=2, sticky="new", padx=(0, 8))
        lst.grid(row=0, column=1, sticky="nsew")
        lst._scrollbar.configure(height=LIST_H_NARROW)
        tb_narrow.grid(row=1, column=1, sticky="ew", pady=(2, 0))
        app._convert_drop_canvas.configure(height=DROP_ZONE_H_NARROW)

    _repack_drop_canvas(app)
    dr = getattr(app, "_convert_drop_redraw", None)
    if callable(dr):
        app.after_idle(dr)


def build_convert_image_tab_controls(
    app: Any, shell: ctk.CTkFrame, dnd_files: str
) -> None:
    app._convert_queue = []
    app._convert_thumb_refs = []
    app._convert_layout_wide: bool | None = None
    app._convert_reflow_after: str | None = None

    app._convert_format_var = StringVar(value=OUTPUT_FORMATS[0])
    app._convert_quality_var = DoubleVar(value=85.0)
    app._convert_strip_metadata_var = BooleanVar(value=False)
    app._convert_cmyk_to_rgb_var = BooleanVar(value=False)
    app._convert_output_folder_var = StringVar(value="")
    app._convert_input_summary_var = StringVar(value="")

    shell.grid_columnconfigure(0, weight=1)
    shell.grid_rowconfigure(0, weight=1)

    outer = ctk.CTkFrame(shell, fg_color="transparent")
    outer.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
    app._convert_outer = outer
    app._convert_shell = shell

    # Panels
    # Queue panel
    panel_q = ctk.CTkFrame(outer, fg_color="transparent")
    # Options panel
    panel_o = ctk.CTkFrame(outer, fg_color="transparent")
    # Execution panel
    panel_e = ctk.CTkFrame(outer, fg_color="transparent")
    app._convert_panel_queue = panel_q
    app._convert_panel_options = panel_o
    app._convert_panel_execution = panel_e

    _build_queue_panel(app, panel_q, dnd_files)
    _build_options_panel(app, panel_o)
    _build_execution_panel(app, panel_e)

    app._convert_output_folder_var.trace_add(
        "write",
        lambda *_a: convert_tab_on_output_folder_change(app),
    )
    app._convert_quality_var.trace_add(
        "write",
        lambda *_a: update_convert_quality_percent_label(app),
    )
    update_convert_quality_percent_label(app)

    def schedule_reflow(_event: object | None = None) -> None:
        aid = getattr(app, "_convert_reflow_after", None)
        if aid is not None:
            try:
                app.after_cancel(aid)
            except Exception:
                pass
        app._convert_reflow_after = app.after(80, apply_reflow)

    def apply_reflow() -> None:
        app._convert_reflow_after = None
        w = shell.winfo_width()
        if w < 50:
            app._convert_reflow_after = app.after(120, apply_reflow)
            return
        wide = w >= REFLOW_WIDE_PX
        if app._convert_layout_wide is wide:
            return
        app._convert_layout_wide = wide
        for p in (panel_q, panel_o, panel_e):
            p.grid_forget()

        _apply_convert_queue_inner_layout(app, wide)

        if wide:
            outer.grid_columnconfigure(0, weight=2, minsize=160)
            outer.grid_columnconfigure(1, weight=1, minsize=180)
            outer.grid_columnconfigure(2, weight=1, minsize=200)
            outer.grid_rowconfigure(0, weight=1)
            panel_q.grid_propagate(True)
            panel_q.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
            panel_o.grid(row=0, column=1, sticky="nsew", padx=4, pady=0)
            panel_e.grid(row=0, column=2, sticky="nsew", padx=(8, 0), pady=0)
        else:
            outer.grid_columnconfigure(0, weight=1, minsize=0)
            outer.grid_columnconfigure(1, weight=1, minsize=0)
            outer.grid_columnconfigure(2, weight=1, minsize=0)
            # Row 0: queue band — fixed height; rows 1–2 take remaining space.
            outer.grid_rowconfigure(0, weight=1)
            outer.grid_rowconfigure(1, weight=1)
            outer.grid_rowconfigure(2, weight=1)
            panel_q.configure(height=PANEL_QUEUE_HEIGHT_NARROW)
            panel_q.grid_propagate(False)
            panel_q.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
            panel_o.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
            panel_e.grid(row=2, column=0, sticky="nsew", pady=0)

        _apply_queue_section_chrome(app, wide)

    shell.bind("<Configure>", schedule_reflow, add="+")
    app.after_idle(schedule_reflow)


def _build_queue_panel(app: Any, panel: ctk.CTkFrame, dnd_files: str) -> None:
    app._convert_queue_inner = _build_queue_section_card(app, panel)
    inner = app._convert_queue_inner
    inner.grid_columnconfigure(0, weight=1)
    inner.grid_rowconfigure(0, weight=1)

    app._convert_drop_wrap = ctk.CTkFrame(inner, fg_color="transparent")
    app._convert_drop_wrap.grid_columnconfigure(0, weight=1)
    app._convert_drop_wrap.grid_rowconfigure(0, weight=1)
    drop_wrap = app._convert_drop_wrap
    app._convert_drop_canvas = _build_dashed_drop_canvas(
        drop_wrap,
        app,
        dnd_files,
        height=DROP_ZONE_H_NARROW,
        width=DROP_ZONE_COL_MIN_NARROW,
    )
    app._convert_drop_canvas.grid(row=0, column=0, sticky="nsew")
    _repack_drop_canvas(app)

    app._convert_list_frame = ctk.CTkScrollableFrame(
        inner, height=LIST_H_NARROW, fg_color="transparent"
    )
    app._convert_list_frame._scrollbar.configure(height=0)

    app._convert_queue_toolbar_wide = ctk.CTkFrame(inner, fg_color="transparent")
    tw = app._convert_queue_toolbar_wide
    tw.grid_columnconfigure(0, weight=1)
    tw.grid_columnconfigure(1, weight=0)
    ctk.CTkButton(
        tw,
        text="Add files…",
        width=110,
        font=("Segoe UI", 12, "bold"),
        corner_radius=8,
        command=lambda: convert_tab_browse(app),
    ).grid(row=0, column=0, sticky="w")
    ctk.CTkButton(
        tw,
        text="Clear queue",
        width=104,
        font=("Segoe UI", 11),
        corner_radius=8,
        command=lambda: convert_tab_clear_queue(app),
    ).grid(row=0, column=1, sticky="e")

    app._convert_queue_toolbar_narrow = ctk.CTkFrame(inner, fg_color="transparent")
    tn = app._convert_queue_toolbar_narrow
    tn.grid_columnconfigure(0, weight=1)
    ctk.CTkEntry(
        tn,
        textvariable=app._convert_input_summary_var,
        placeholder_text="Drop files or browse…",
        font=("Segoe UI", 11),
        state="readonly",
        corner_radius=6,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ctk.CTkButton(
        tn,
        text="📁",
        width=40,
        font=("Segoe UI", 14),
        corner_radius=8,
        command=lambda: convert_tab_browse(app),
    ).grid(row=0, column=1, sticky="e")

    _apply_convert_queue_inner_layout(app, False)
    _apply_queue_section_chrome(app, False)


def _sync_quality_visibility(app: Any, _value: str | None = None) -> None:
    fmt = app._convert_format_var.get().strip().upper()
    lossy = fmt in LOSSY_FORMATS
    cb_row = app._convert_options_cb_row
    if lossy:
        app._convert_quality_block.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        cb_row.grid(row=3, column=0, sticky="w", pady=(14, 0))
        if fmt == "JPEG":
            app._convert_quality_title.configure(text="JPEG Quality")
        else:
            app._convert_quality_title.configure(text="WebP quality")
    else:
        app._convert_quality_block.grid_remove()
        cb_row.grid(row=2, column=0, sticky="w", pady=(14, 0))
    update_convert_quality_percent_label(app)


def _build_options_panel(app: Any, panel: ctk.CTkFrame) -> None:
    inner = _section_card(panel, "2. CONFIGURE OUTPUT")
    inner.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(inner, text="Convert to:", font=("Segoe UI", 11)).grid(
        row=0, column=0, sticky="w", pady=(0, 4)
    )
    ctk.CTkOptionMenu(
        inner,
        values=list(OUTPUT_FORMATS),
        variable=app._convert_format_var,
        command=lambda v: _sync_quality_visibility(app, v),
        font=("Segoe UI", 12),
        corner_radius=8,
    ).grid(row=1, column=0, sticky="ew", pady=(0, 0))

    app._convert_quality_block = ctk.CTkFrame(inner, fg_color="transparent")
    app._convert_quality_block.grid_columnconfigure(0, weight=1)
    qh = ctk.CTkFrame(app._convert_quality_block, fg_color="transparent")
    qh.grid_columnconfigure(0, weight=1)
    qh.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    app._convert_quality_title = ctk.CTkLabel(
        qh, text="JPEG Quality", font=("Segoe UI", 11)
    )
    app._convert_quality_title.grid(row=0, column=0, sticky="w")
    app._convert_quality_pct_label = ctk.CTkLabel(
        qh, text="85%", font=("Segoe UI", 11), text_color=("gray30", "gray70")
    )
    app._convert_quality_pct_label.grid(row=0, column=1, sticky="e")
    ctk.CTkSlider(
        app._convert_quality_block,
        from_=1,
        to=100,
        number_of_steps=99,
        variable=app._convert_quality_var,
    ).grid(row=1, column=0, sticky="ew")

    cb_row = ctk.CTkFrame(inner, fg_color="transparent")
    app._convert_options_cb_row = cb_row
    cb_row.grid(row=3, column=0, sticky="w", pady=(14, 0))
    ctk.CTkCheckBox(
        cb_row,
        text="Strip metadata",
        variable=app._convert_strip_metadata_var,
        font=("Segoe UI", 11),
    ).pack(anchor="w", pady=2)
    ctk.CTkCheckBox(
        cb_row,
        text="Convert CMYK to RGB",
        variable=app._convert_cmyk_to_rgb_var,
        font=("Segoe UI", 11),
    ).pack(anchor="w", pady=2)

    _sync_quality_visibility(app)


def _build_execution_panel(app: Any, panel: ctk.CTkFrame) -> None:
    inner = _section_card(panel, "3. PROCESS")
    inner.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(inner, text="Output folder", font=("Segoe UI", 11)).grid(
        row=0, column=0, sticky="w", pady=(0, 4)
    )
    out_row = ctk.CTkFrame(inner, fg_color="transparent")
    out_row.grid_columnconfigure(0, weight=1)
    out_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
    ctk.CTkEntry(
        out_row,
        textvariable=app._convert_output_folder_var,
        placeholder_text="Select destination folder…",
        font=("Segoe UI", 11),
        corner_radius=6,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ctk.CTkButton(
        out_row,
        text="📁",
        width=40,
        font=("Segoe UI", 14),
        corner_radius=8,
        command=lambda: convert_tab_browse_output_folder(app),
    ).grid(row=0, column=1, sticky="e")

    app._convert_run_btn = ctk.CTkButton(
        inner,
        text="START CONVERSION",
        state="disabled",
        font=("Segoe UI", 13, "bold"),
        command=lambda: convert_tab_run(app),
        fg_color="#1f6aa5",
        hover_color="#144870",
        corner_radius=8,
        height=40,
    )
    app._convert_run_btn.grid(row=2, column=0, sticky="ew", pady=(0, 10))

    app._convert_progress_bar = ctk.CTkProgressBar(
        inner,
        mode="determinate",
        height=16,
        corner_radius=4,
    )
    app._convert_progress_bar.grid(row=3, column=0, sticky="ew")
    app._convert_progress_bar.set(0)
