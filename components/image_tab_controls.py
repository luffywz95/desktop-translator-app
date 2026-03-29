"""UI builder for Image tab controls."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import Menu

from components.tooltip import ToolTip


def popup_choose_menu(app) -> None:
    """Show choose-source popup anchored to the split button."""
    app.update_idletasks()
    try:
        app._choose_menu.tk_popup(
            app.choose_file_drop_btn.winfo_rootx(),
            app.choose_file_drop_btn.winfo_rooty() + app.choose_file_drop_btn.winfo_height(),
        )
    finally:
        try:
            app._choose_menu.grab_release()
        except Exception:
            pass


def build_image_tab_controls(app, tab_frame, dnd_files: str) -> None:
    """Populate Image tab widgets and bind callbacks onto the app instance."""
    app.ocr_frame = tab_frame.tab("Image")
    app.ocr_frame.grid_rowconfigure(0, weight=1)
    app.ocr_frame.grid_columnconfigure(0, weight=1)
    app.ocr_frame.grid_rowconfigure(1, weight=0)
    app.placeholder_text = "Drag & Drop Image Here\nor press Ctrl+V to paste"

    app.choose_fail_label = ctk.CTkLabel(
        app.ocr_frame,
        text="",
        font=("Segoe UI", 10),
        text_color="#e74c3c",
        wraplength=320,
        anchor="nw",
        justify="left",
        fg_color="transparent",
    )

    app.img_zone = ctk.CTkLabel(
        app.ocr_frame,
        text=app.placeholder_text,
        fg_color=("#ebebeb", "#2b2b2b"),
        corner_radius=15,
        text_color="gray",
    )
    app.img_zone.pack(fill="both", expand=True)
    app.img_zone.drop_target_register(dnd_files)
    app.img_zone.dnd_bind("<<Drop>>", app.handle_drop)
    app.bind("<Control-v>", app.handle_paste)

    app.ocr_bottom = ctk.CTkFrame(app.ocr_frame, fg_color="transparent")
    app.ocr_bottom.grid_columnconfigure(0, weight=1)
    app.ocr_bottom.grid_columnconfigure(1, weight=0)
    app.ocr_bottom.grid_rowconfigure(0, weight=0)

    app.url_row = ctk.CTkFrame(app.ocr_bottom, fg_color="transparent")
    app.url_entry = ctk.CTkEntry(
        app.url_row,
        placeholder_text="http://www.example.com/examplefile.pdf",
        placeholder_text_color=("#4A90E2", "#6AB0FF"),
        font=("Segoe UI", 12),
        corner_radius=6,
        border_width=1,
    )
    app.url_entry.pack(side="left", fill="x", expand=True)
    app.url_entry.bind("<Return>", lambda e: app._load_image_from_url_async())
    app.url_load_btn = ctk.CTkButton(
        app.url_row,
        text="Load",
        width=64,
        corner_radius=8,
        font=("Segoe UI", 12, "bold"),
        command=app._load_image_from_url_async,
    )
    app.url_load_btn.pack(side="left", padx=(8, 0))

    app.choose_split_outer = ctk.CTkFrame(app.ocr_bottom, fg_color="transparent")
    app.choose_file_main_btn = ctk.CTkButton(
        app.choose_split_outer,
        text="📄 Choose file",
        width=120,
        corner_radius=8,
        border_width=0,
        font=("Segoe UI", 13, "bold"),
        command=app._choose_from_device,
        fg_color=("#3b8ed0", "#1f538d"),
        hover_color=("#36719f", "#144870"),
        text_color=("white", "white"),
    )
    app.choose_file_main_btn.pack(side="left")

    app.choose_file_drop_btn = ctk.CTkButton(
        app.choose_split_outer,
        text="▾",
        width=36,
        corner_radius=8,
        font=("Segoe UI", 13, "bold"),
        fg_color=("#6d6d6d", "#3d3d3d"),
        hover_color=("#5c5c5c", "#4d4d4d"),
        text_color=("white", "white"),
        command=lambda: popup_choose_menu(app),
    )
    app.choose_file_drop_btn.pack(side="left")

    app.btn_frame = ctk.CTkFrame(app.ocr_bottom, fg_color="transparent")
    app.process_btn = ctk.CTkButton(
        app.btn_frame,
        text="🔄 Process",
        width=80,
        command=app.process_image,
        state="disabled",
    )
    app.process_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
    app.process_btn.pack(side="right", fill="x")
    ToolTip(app.process_btn, "Process the image")

    app.reset_btn = ctk.CTkButton(
        app.btn_frame,
        text="🔃 Reset",
        width=80,
        command=app.clear_all,
        fg_color="#e74c3c",
        hover_color="#c0392b",
    )
    app.reset_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
    app.reset_btn.pack(side="right", fill="x", padx=(0, 5))
    ToolTip(app.reset_btn, "Reset the image and the result")

    app._choose_url_visible = False
    app.choose_split_outer.grid(row=1, column=0, sticky="w", pady=(2, 0))
    app.btn_frame.grid(row=1, column=1, sticky="e", padx=(16, 0), pady=(2, 0))

    app.img_zone.grid(row=0, column=0, sticky="nsew")
    app.ocr_bottom.grid(row=1, column=0, sticky="ew", padx=(4, 4), pady=(4, 4))

    app._choose_menu = Menu(app, tearoff=0)
    app._choose_menu.add_command(label="From device", command=app._choose_from_device)
    app._choose_menu.add_command(
        label="From Dropbox",
        command=lambda: app._choose_from_cloud("Dropbox"),
    )
    app._choose_menu.add_command(
        label="From Google Drive",
        command=lambda: app._choose_from_cloud("Google Drive"),
    )
    app._choose_menu.add_command(
        label="From OneDrive",
        command=lambda: app._choose_from_cloud("OneDrive"),
    )
    app._choose_menu.add_command(label="From URL", command=app._choose_from_url_menu)
    app._choose_menu.add_command(
        label="From Clipboard", command=app._choose_from_clipboard
    )
    ToolTip(app.choose_file_main_btn, "Pick a file from this PC (or use the menu)")
    ToolTip(app.choose_file_drop_btn, "More sources")
