"""UI builder for the Web Crawler tab (mockup-aligned styling)."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.controllers.web_crawler_controller import web_crawler_sync_field_row_sizes
from components.tooltip import ToolTip

# Mockup: dark cards, blue accent for primary actions and key labels
_ACCENT = "#3399FF"
_ACCENT_HOVER = "#2B80D9"
_ACCENT_MUTED = "#2670C4"
_CARD_FG = ("#ebebeb", "#2b2b2b")
_CARD_BORDER = ("#c8c8c8", "#3d3d3d")
_CORNER = 10
_SECTION_TITLE = ("Segoe UI", 11, "bold")
_SECTION_TITLE_ULTRA = ("Segoe UI", 10, "bold")
_BODY = ("Segoe UI", 12)
_BODY_ULTRA = ("Segoe UI", 11)
_BTN_PRIMARY = ("Segoe UI", 12, "bold")
_BTN_SECONDARY = ("Segoe UI", 11, "bold")
_LOG_BG = ("#f0f0f0", "#1a1a1a")
_LOG_BORDER = ("#c8c8c8", "#404040")
_SMALL_LAYOUT_PX = 620
_ULTRA_SMALL_PX = 440
_LOG_H_NORMAL = 200
_LOG_H_ULTRA = 100


def _section(parent: ctk.CTkFrame, title: str) -> tuple[ctk.CTkFrame, ctk.CTkFrame, ctk.CTkLabel]:
    card = ctk.CTkFrame(
        parent,
        fg_color=_CARD_FG,
        corner_radius=_CORNER,
        border_width=1,
        border_color=_CARD_BORDER,
    )
    card.pack(fill="x", padx=6, pady=(0, 10))
    title_lbl = ctk.CTkLabel(
        card,
        text=title,
        font=_SECTION_TITLE,
        anchor="w",
        text_color=("gray10", "gray90"),
    )
    title_lbl.pack(fill="x", padx=12, pady=(10, 6))
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    return card, inner, title_lbl


def _primary_button(parent: Any, **kwargs: Any) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        fg_color=_ACCENT,
        hover_color=_ACCENT_HOVER,
        text_color=("white", "white"),
        corner_radius=8,
        height=36,
        font=_BTN_PRIMARY,
        **kwargs,
    )


def _secondary_button(parent: Any, **kwargs: Any) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        fg_color=_ACCENT,
        hover_color=_ACCENT_HOVER,
        text_color=("white", "white"),
        corner_radius=8,
        height=32,
        font=_BTN_SECONDARY,
        **kwargs,
    )


def _accent_checkbox(parent: Any, **kwargs: Any) -> ctk.CTkCheckBox:
    return ctk.CTkCheckBox(
        parent,
        font=_BODY,
        checkbox_width=20,
        checkbox_height=20,
        fg_color=_ACCENT,
        hover_color=_ACCENT_HOVER,
        border_color=_ACCENT_MUTED,
        **kwargs,
    )


def _accent_option_menu(
    parent: Any, variable: Any, values: list[str], **kwargs: Any
) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(
        parent,
        variable=variable,
        values=values,
        fg_color=_ACCENT,
        button_color=_ACCENT_MUTED,
        button_hover_color=_ACCENT_HOVER,
        dropdown_fg_color=_CARD_FG,
        font=_BODY,
        height=32,
        corner_radius=8,
        **kwargs,
    )


def _on_strategy_toggle(app: Any, mode: str) -> None:
    if mode == "static":
        app.web_crawler_static_var.set(True)
        app.web_crawler_js_var.set(False)
    else:
        app.web_crawler_js_var.set(True)
        app.web_crawler_static_var.set(False)


def _on_readiness_change(app: Any, choice: str) -> None:
    show = choice == "Wait for Element..."
    pady = (4, 0) if getattr(app, "_web_crawler_ultra", False) else (8, 0)
    if show:
        app.web_crawler_wait_selector_row.pack(fill="x", pady=pady)
    else:
        app.web_crawler_wait_selector_row.pack_forget()


def _wire_button_tooltips(app: Any) -> None:
    ToolTip(app.web_crawler_start_btn, "Start crawl with current strategy and settings.")
    ToolTip(app.web_crawler_browse_btn, "Choose output folder for crawl results.")
    ToolTip(app.web_crawler_add_field_btn, "Add a new extraction field mapping.")
    ToolTip(app.web_crawler_export_btn, "Show path of latest exported crawl file.")
    ToolTip(app.web_crawler_view_btn, "Preview extracted items from latest run.")


def _apply_compact_mode(app: Any, compact: bool) -> None:
    """Re-apply compact vs wide layout (no early return: ultra density can require re-pack)."""
    app._web_crawler_compact = compact

    if compact:
        app.web_crawler_start_btn.configure(text="🕸️", width=42)
        app.web_crawler_browse_btn.configure(text="📁", width=42)
        app.web_crawler_add_field_btn.configure(text="➕", width=42)
        app.web_crawler_export_btn.configure(text="📄", width=42)
        app.web_crawler_view_btn.configure(text="👁️", width=42)
    else:
        app.web_crawler_start_btn.configure(text="🕸️ START SPIDER", width=168)
        app.web_crawler_browse_btn.configure(text="📁 Browse", width=100)
        app.web_crawler_add_field_btn.configure(text="➕ ADD NEW FIELD", width=150)
        app.web_crawler_export_btn.configure(text="📄 EXPORT DATA", width=150)
        app.web_crawler_view_btn.configure(text="👁️ VIEW ITEMS (0)", width=168)
        count = int(getattr(app, "_web_crawler_last_count", 0) or 0)
        app.web_crawler_view_btn.configure(text=f"👁️ VIEW ITEMS ({count})")

    # Target row: stack button in compact mode.
    app.web_crawler_start_btn.grid_forget()
    p_start = (6, 0) if getattr(app, "_web_crawler_ultra", False) else (8, 0)
    if compact:
        app.web_crawler_start_btn.grid(row=1, column=0, sticky="e", pady=p_start)
    else:
        app.web_crawler_start_btn.grid(row=0, column=1, sticky="e")

    # Strategy checkboxes: row on wide, stack on compact.
    app.web_crawler_static_cb.pack_forget()
    app.web_crawler_js_cb.pack_forget()
    sp = 4 if getattr(app, "_web_crawler_ultra", False) else 6
    if compact:
        app.web_crawler_static_cb.pack(anchor="w")
        app.web_crawler_js_cb.pack(anchor="w", pady=(sp, 0))
    else:
        app.web_crawler_static_cb.pack(side="left")
        app.web_crawler_js_cb.pack(side="left", padx=(14, 0))

    # Politeness settings switches: row on wide, stack on compact.
    app.web_crawler_delay_cb.pack_forget()
    app.web_crawler_robots_cb.pack_forget()
    app.web_crawler_ignore_images_cb.pack_forget()
    if compact:
        app.web_crawler_delay_cb.pack(anchor="w")
        app.web_crawler_robots_cb.pack(anchor="w", pady=(sp, 0))
        app.web_crawler_ignore_images_cb.pack(anchor="w", pady=(sp, 0))
    else:
        app.web_crawler_delay_cb.pack(side="left")
        app.web_crawler_robots_cb.pack(side="left", padx=(10, 0))
        app.web_crawler_ignore_images_cb.pack(side="left", padx=(10, 0))

    # Footer alignment: keep one line even in compact mode.
    app.web_crawler_footer_left.pack_forget()
    app.web_crawler_footer_right.pack_forget()
    app.web_crawler_footer_left.pack(side="left")
    app.web_crawler_footer_right.pack(side="right")

    if compact:
        app.web_crawler_results_lbl.configure(text="Format:")
        try:
            app.web_crawler_fmt_menu.configure(width=90)
        except Exception:
            pass
        app.web_crawler_view_btn.pack_configure(padx=(6, 0))
    else:
        app.web_crawler_results_lbl.configure(text="Results Format:")
        try:
            app.web_crawler_fmt_menu.configure(width=110)
        except Exception:
            pass
        app.web_crawler_view_btn.pack_configure(padx=(8, 0))


def _apply_density_mode(app: Any, ultra: bool) -> None:
    if getattr(app, "_web_crawler_ultra", None) == ultra:
        return
    app._web_crawler_ultra = ultra
    app._web_crawler_field_entry_height = 28 if ultra else 32
    app._web_crawler_field_entry_font = _BODY_ULTRA if ultra else _BODY
    web_crawler_sync_field_row_sizes(app)

    card_padx = 4 if ultra else 6
    card_pady = (0, 6) if ultra else (0, 10)
    title_padx = 8 if ultra else 12
    title_pady = (6, 3) if ultra else (10, 6)
    inner_padx = 8 if ultra else 12
    inner_pady = (0, 6) if ultra else (0, 12)

    for card in getattr(app, "_web_crawler_density_cards", []):
        try:
            card.pack_configure(padx=card_padx, pady=card_pady)
        except Exception:
            pass
    for lbl in getattr(app, "_web_crawler_section_title_labels", []):
        try:
            lbl.pack_configure(padx=title_padx, pady=title_pady)
            lbl.configure(font=_SECTION_TITLE_ULTRA if ultra else _SECTION_TITLE)
        except Exception:
            pass
    for inner in getattr(app, "_web_crawler_section_inners", []):
        try:
            inner.pack_configure(padx=inner_padx, pady=inner_pady)
        except Exception:
            pass

    # Target block (custom card)
    try:
        app.web_crawler_top_title.pack_configure(padx=title_padx, pady=(title_pady[0], 2))
        app.web_crawler_top_title.configure(
            font=_SECTION_TITLE_ULTRA if ultra else _SECTION_TITLE
        )
        app.web_crawler_target_url_lbl.pack_configure(padx=title_padx, pady=(0, 2))
        app.web_crawler_target_url_lbl.configure(
            font=("Segoe UI", 10) if ultra else ("Segoe UI", 11)
        )
        top_ipady = (0, 6) if ultra else (0, 12)
        app.web_crawler_top_inner.pack_configure(padx=inner_padx, pady=top_ipady)
    except Exception:
        pass

    th = 30 if ultra else 36
    bh = 30 if ultra else 32
    try:
        app.web_crawler_target_entry.configure(height=th, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_start_btn.configure(height=th)
        app.web_crawler_project_name_entry.configure(height=bh, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_project_location_entry.configure(height=bh, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_browse_btn.configure(height=bh)
        app.web_crawler_wait_selector_entry.configure(height=bh, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_readiness_menu.configure(height=bh, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_fmt_menu.configure(height=bh, font=_BODY_ULTRA if ultra else _BODY)
    except Exception:
        pass

    try:
        app.web_crawler_readiness_lbl.configure(
            width=80 if ultra else 92,
            font=_BODY_ULTRA if ultra else _BODY,
        )
        app.web_crawler_wait_sel_lbl.configure(
            width=80 if ultra else 92,
            font=_BODY_ULTRA if ultra else _BODY,
        )
        app.web_crawler_name_lbl.configure(width=64 if ultra else 76, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_loc_lbl.configure(width=64 if ultra else 76, font=_BODY_ULTRA if ultra else _BODY)
        app.web_crawler_results_lbl.configure(font=_BODY_ULTRA if ultra else _BODY)
    except Exception:
        pass

    try:
        app.web_crawler_switches.grid_configure(pady=(6 if ultra else 10, 0))
        app.web_crawler_name_lbl.grid_configure(
            row=0, column=0, sticky="w", pady=(0, 4 if ultra else 8)
        )
    except Exception:
        pass

    try:
        app.web_crawler_log.configure(height=_LOG_H_ULTRA if ultra else _LOG_H_NORMAL)
    except Exception:
        pass

    try:
        app.web_crawler_fields_add_row.pack_configure(
            padx=inner_padx,
            pady=(0, 4 if ultra else 6),
        )
        app.web_crawler_fields_header.pack_configure(
            padx=inner_padx,
            pady=(0, 4 if ultra else 6),
        )
        app.web_crawler_fields_inner.pack_configure(
            padx=inner_padx,
            pady=(0, 6 if ultra else 12),
        )
        app.web_crawler_header_name.configure(
            width=120 if ultra else 148,
            font=("Segoe UI", 9, "bold") if ultra else ("Segoe UI", 10, "bold"),
        )
    except Exception:
        pass

    try:
        app.web_crawler_footer.pack_configure(
            padx=card_padx,
            pady=(2 if ultra else 4, 6 if ultra else 14),
        )
    except Exception:
        pass

    # Checkbox fonts scale down slightly in ultra
    try:
        cb_font = _BODY_ULTRA if ultra else _BODY
        cb_h = 18 if ultra else 20
        for cb in (
            app.web_crawler_static_cb,
            app.web_crawler_js_cb,
            app.web_crawler_delay_cb,
            app.web_crawler_robots_cb,
            app.web_crawler_ignore_images_cb,
        ):
            cb.configure(font=cb_font, checkbox_height=cb_h, checkbox_width=cb_h)
    except Exception:
        pass

    try:
        app.web_crawler_readiness.pack_configure(pady=(6 if ultra else 10, 0))
    except Exception:
        pass

    _on_readiness_change(app, app.web_crawler_readiness_var.get())


def _bind_responsive_layout(app: Any) -> None:
    def on_resize(_event: object | None = None) -> None:
        width = max(app.web_crawler_frame.winfo_width(), app.winfo_width())
        if width < 100:
            return
        compact = width <= _SMALL_LAYOUT_PX
        ultra = width <= _ULTRA_SMALL_PX
        _apply_density_mode(app, ultra)
        _apply_compact_mode(app, compact)

    app._web_crawler_apply_responsive = on_resize
    app.web_crawler_frame.bind("<Configure>", lambda e: on_resize(e), add="+")
    app.after(0, on_resize)


def build_web_crawler_tab_controls(app: Any, crawler_parent: ctk.CTkFrame) -> None:
    app.web_crawler_frame = crawler_parent
    app.web_crawler_frame.grid_rowconfigure(0, weight=1)
    app.web_crawler_frame.grid_columnconfigure(0, weight=1)

    app._web_crawler_ultra = False
    app._web_crawler_field_entry_height = 32
    app._web_crawler_field_entry_font = _BODY

    outer = ctk.CTkScrollableFrame(app.web_crawler_frame, fg_color="transparent")
    outer.grid(row=0, column=0, sticky="nsew")

    top_card = ctk.CTkFrame(
        outer,
        fg_color=_CARD_FG,
        corner_radius=_CORNER,
        border_width=1,
        border_color=_CARD_BORDER,
    )
    top_card.pack(fill="x", padx=6, pady=(0, 10))
    app.web_crawler_top_title = ctk.CTkLabel(
        top_card,
        text="Target",
        font=_SECTION_TITLE,
        anchor="w",
        text_color=("gray10", "gray90"),
    )
    app.web_crawler_top_title.pack(fill="x", padx=12, pady=(10, 4))
    app.web_crawler_target_url_lbl = ctk.CTkLabel(
        top_card,
        text="Target URL",
        font=("Segoe UI", 11),
        anchor="w",
        text_color=_ACCENT,
    )
    app.web_crawler_target_url_lbl.pack(fill="x", padx=12, pady=(0, 4))
    app.web_crawler_top_inner = ctk.CTkFrame(top_card, fg_color="transparent")
    app.web_crawler_top_inner.pack(fill="x", padx=12, pady=(0, 12))
    app.web_crawler_top_inner.grid_columnconfigure(0, weight=1)
    app.web_crawler_target_entry = ctk.CTkEntry(
        app.web_crawler_top_inner,
        placeholder_text="e.g. mysite.com",
        font=_BODY,
        height=36,
        corner_radius=8,
        border_width=1,
    )
    app.web_crawler_target_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    app.web_crawler_start_btn = _primary_button(
        app.web_crawler_top_inner,
        text="🕸️ START SPIDER",
        width=168,
        command=app._web_crawler_start,
    )
    app.web_crawler_start_btn.grid(row=0, column=1, sticky="e")

    strategy_card, strategy, strategy_title = _section(outer, "Crawl Strategy")
    app.web_crawler_static_var = ctk.BooleanVar(value=True)
    app.web_crawler_js_var = ctk.BooleanVar(value=False)
    strat_row = ctk.CTkFrame(strategy, fg_color="transparent")
    strat_row.pack(fill="x")
    app.web_crawler_static_cb = _accent_checkbox(
        strat_row,
        text="Static HTML (Fast)",
        variable=app.web_crawler_static_var,
        command=lambda: _on_strategy_toggle(app, "static"),
    )
    app.web_crawler_static_cb.pack(side="left")
    app.web_crawler_js_cb = _accent_checkbox(
        strat_row,
        text="JS-Rendered (Selenium) [Advanced]",
        variable=app.web_crawler_js_var,
        command=lambda: _on_strategy_toggle(app, "js"),
    )
    app.web_crawler_js_cb.pack(side="left", padx=(14, 0))

    app.web_crawler_readiness = ctk.CTkFrame(strategy, fg_color="transparent")
    app.web_crawler_readiness.pack(fill="x", pady=(10, 0))
    app.web_crawler_readiness_lbl = ctk.CTkLabel(
        app.web_crawler_readiness, text="Readiness:", width=92, anchor="w", font=_BODY
    )
    app.web_crawler_readiness_lbl.pack(side="left")
    app.web_crawler_readiness_var = ctk.StringVar(value="Smart Wait (Wait for Network)")
    app.web_crawler_readiness_menu = _accent_option_menu(
        app.web_crawler_readiness,
        app.web_crawler_readiness_var,
        [
            "Basic (HTML Only)",
            "Smart Wait (Wait for Network)",
            "Wait for Element...",
        ],
        command=lambda c: _on_readiness_change(app, c),
    )
    app.web_crawler_readiness_menu.pack(side="left", fill="x", expand=True)
    app.web_crawler_wait_selector_row = ctk.CTkFrame(strategy, fg_color="transparent")
    app.web_crawler_wait_sel_lbl = ctk.CTkLabel(
        app.web_crawler_wait_selector_row,
        text="Wait Selector:",
        width=92,
        anchor="w",
        font=_BODY,
    )
    app.web_crawler_wait_sel_lbl.pack(side="left")
    app.web_crawler_wait_selector_entry = ctk.CTkEntry(
        app.web_crawler_wait_selector_row,
        placeholder_text="e.g. div.product-card",
        font=_BODY,
        height=32,
        corner_radius=8,
    )
    app.web_crawler_wait_selector_entry.pack(side="left", fill="x", expand=True)
    _on_readiness_change(app, app.web_crawler_readiness_var.get())

    settings_card, settings, settings_title = _section(outer, "Project Settings (Scrapy)")
    settings.grid_columnconfigure(1, weight=1)
    app.web_crawler_name_lbl = ctk.CTkLabel(
        settings, text="Name:", width=76, anchor="w", font=_BODY
    )
    app.web_crawler_name_lbl.grid(row=0, column=0, sticky="w", pady=(0, 8))
    app.web_crawler_project_name_entry = ctk.CTkEntry(
        settings,
        font=_BODY,
        height=32,
        corner_radius=8,
    )
    app.web_crawler_project_name_entry.insert(0, "NewProject_01")
    app.web_crawler_project_name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))

    app.web_crawler_loc_lbl = ctk.CTkLabel(
        settings, text="Location:", width=76, anchor="w", font=_BODY
    )
    app.web_crawler_loc_lbl.grid(row=1, column=0, sticky="nw", pady=(4, 0))
    location_row = ctk.CTkFrame(settings, fg_color="transparent")
    location_row.grid(row=1, column=1, sticky="ew", pady=(0, 4))
    location_row.grid_columnconfigure(0, weight=1)
    app.web_crawler_project_location_entry = ctk.CTkEntry(
        location_row,
        font=_BODY,
        height=32,
        corner_radius=8,
    )
    app.web_crawler_project_location_entry.insert(0, "./crawls/")
    app.web_crawler_project_location_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    app.web_crawler_browse_btn = ctk.CTkButton(
        location_row,
        text="📁 Browse",
        width=100,
        height=32,
        command=app._web_crawler_browse_location,
        fg_color=_ACCENT,
        hover_color=_ACCENT_HOVER,
        font=_BTN_SECONDARY,
        corner_radius=8,
    )
    app.web_crawler_browse_btn.grid(row=0, column=1)

    app.web_crawler_switches = ctk.CTkFrame(settings, fg_color="transparent")
    app.web_crawler_switches.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
    app.web_crawler_delay_var = ctk.BooleanVar(value=True)
    app.web_crawler_robots_var = ctk.BooleanVar(value=True)
    app.web_crawler_ignore_images_var = ctk.BooleanVar(value=True)
    app.web_crawler_delay_cb = _accent_checkbox(
        app.web_crawler_switches,
        text="Download Delay (2s)",
        variable=app.web_crawler_delay_var,
    )
    app.web_crawler_delay_cb.pack(side="left")
    app.web_crawler_robots_cb = _accent_checkbox(
        app.web_crawler_switches,
        text="Respect robots.txt",
        variable=app.web_crawler_robots_var,
    )
    app.web_crawler_robots_cb.pack(side="left", padx=(10, 0))
    app.web_crawler_ignore_images_cb = _accent_checkbox(
        app.web_crawler_switches,
        text="Ignore Image URLs",
        variable=app.web_crawler_ignore_images_var,
    )
    app.web_crawler_ignore_images_cb.pack(side="left", padx=(10, 0))

    fields_outer = ctk.CTkFrame(
        outer,
        fg_color=_CARD_FG,
        corner_radius=_CORNER,
        border_width=1,
        border_color=_CARD_BORDER,
    )
    fields_outer.pack(fill="x", padx=6, pady=(0, 10))
    fields_title = ctk.CTkLabel(
        fields_outer,
        text="Item Field Definition",
        font=_SECTION_TITLE,
        anchor="w",
        text_color=("gray10", "gray90"),
    )
    fields_title.pack(fill="x", padx=12, pady=(10, 6))
    app.web_crawler_fields_add_row = ctk.CTkFrame(fields_outer, fg_color="transparent")
    app.web_crawler_fields_add_row.pack(fill="x", padx=12, pady=(0, 6))
    app.web_crawler_add_field_btn = _secondary_button(
        app.web_crawler_fields_add_row,
        text="➕ ADD NEW FIELD",
        command=app._web_crawler_add_field,
        width=150,
    )
    app.web_crawler_add_field_btn.pack(side="right")
    app.web_crawler_fields_header = ctk.CTkFrame(fields_outer, fg_color="transparent")
    app.web_crawler_fields_header.pack(fill="x", padx=12, pady=(0, 6))
    app.web_crawler_header_name = ctk.CTkLabel(
        app.web_crawler_fields_header,
        text="FIELD NAME",
        width=148,
        anchor="w",
        font=("Segoe UI", 10, "bold"),
        text_color=("gray30", "gray75"),
    )
    app.web_crawler_header_name.pack(side="left")
    ctk.CTkLabel(
        app.web_crawler_fields_header,
        text="CSS/XPath SELECTOR",
        anchor="w",
        font=("Segoe UI", 10, "bold"),
        text_color=("gray30", "gray75"),
    ).pack(side="left", fill="x", expand=True, padx=(10, 0))

    app.web_crawler_fields_inner = ctk.CTkFrame(fields_outer, fg_color="transparent")
    app.web_crawler_fields_inner.pack(fill="x", padx=12, pady=(0, 12))
    app.web_crawler_fields_wrap = ctk.CTkFrame(app.web_crawler_fields_inner, fg_color="transparent")
    app.web_crawler_fields_wrap.pack(fill="x")
    app._web_crawler_fields = []

    log_card = ctk.CTkFrame(
        outer,
        fg_color=_CARD_FG,
        corner_radius=_CORNER,
        border_width=1,
        border_color=_CARD_BORDER,
    )
    log_card.pack(fill="both", expand=True, padx=6, pady=(0, 10))
    log_title = ctk.CTkLabel(
        log_card,
        text="CRAWL LOG / QUEUE",
        font=_SECTION_TITLE,
        anchor="w",
        text_color=("gray10", "gray90"),
    )
    log_title.pack(fill="x", padx=12, pady=(10, 6))
    log_inner = ctk.CTkFrame(log_card, fg_color="transparent")
    log_inner.pack(fill="both", expand=True, padx=12, pady=(0, 12))
    app.web_crawler_log = ctk.CTkTextbox(
        log_inner,
        height=_LOG_H_NORMAL,
        font=("Consolas", 11),
        fg_color=_LOG_BG,
        border_width=1,
        border_color=_LOG_BORDER,
        corner_radius=8,
    )
    app.web_crawler_log.pack(fill="both", expand=True)
    app.web_crawler_log.insert("1.0", "[i] Ready to crawl.\n")

    app.web_crawler_footer = ctk.CTkFrame(outer, fg_color="transparent")
    app.web_crawler_footer.pack(fill="x", padx=6, pady=(4, 14))
    app.web_crawler_footer_left = ctk.CTkFrame(app.web_crawler_footer, fg_color="transparent")
    app.web_crawler_footer_left.pack(side="left")
    app.web_crawler_results_lbl = ctk.CTkLabel(
        app.web_crawler_footer_left, text="Results Format:", font=_BODY
    )
    app.web_crawler_results_lbl.pack(side="left")
    app.web_crawler_format_var = ctk.StringVar(value="CSV")
    app.web_crawler_fmt_menu = _accent_option_menu(
        app.web_crawler_footer_left,
        app.web_crawler_format_var,
        ["CSV", "JSON"],
    )
    app.web_crawler_fmt_menu.pack(side="left", padx=(10, 0))

    app.web_crawler_footer_right = ctk.CTkFrame(app.web_crawler_footer, fg_color="transparent")
    app.web_crawler_footer_right.pack(side="right")
    app.web_crawler_view_btn = _secondary_button(
        app.web_crawler_footer_right,
        text="👁️ VIEW ITEMS (0)",
        width=168,
        command=app._web_crawler_view_items,
    )
    app.web_crawler_view_btn.pack(side="right", padx=(8, 0))
    app.web_crawler_export_btn = _secondary_button(
        app.web_crawler_footer_right,
        text="📄 EXPORT DATA",
        width=150,
        command=app._web_crawler_export,
    )
    app.web_crawler_export_btn.pack(side="right")

    app._web_crawler_density_cards = [
        top_card,
        strategy_card,
        settings_card,
        fields_outer,
        log_card,
    ]
    app._web_crawler_section_title_labels = [
        strategy_title,
        settings_title,
        fields_title,
        log_title,
    ]
    app._web_crawler_section_inners = [strategy, settings]

    app._web_crawler_add_field("product_name", "h1.product-title::text")
    app._web_crawler_add_field("price", "span.price-current::text")
    app._web_crawler_add_field("description", "div#product-desc > p::text")
    _wire_button_tooltips(app)
    _bind_responsive_layout(app)
