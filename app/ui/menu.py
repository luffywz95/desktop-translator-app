from __future__ import annotations

import customtkinter as ctk


def build_menu(app) -> None:
    app.menu_bar = ctk.CTkFrame(app, height=50, corner_radius=0)
    app.menu_bar.pack(fill="x", side="top")

    app.pin_btn = ctk.CTkButton(
        app.menu_bar,
        text="📌",
        width=40,
        height=30,
        fg_color="transparent",
        hover_color="#3d3d3d",
        command=app.toggle_pin,
    )
    app.pin_btn.pack(side="right", padx=(0, 5))

    app.settings_btn = ctk.CTkButton(
        app.menu_bar,
        text="⚙️",
        width=40,
        height=30,
        command=app.open_settings,
        fg_color="transparent",
        font=("Arial", 16),
    )
    app.settings_btn.pack(side="right", padx=10)
