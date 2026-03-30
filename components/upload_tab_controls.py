"""UI builder for Upload tab controls (Remote + Bluetooth)."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Mapping

import customtkinter as ctk

from components.hover_marquee_label import HoverMarqueeClipLabel
from components.info_button import InfoButton
from components.tooltip import ToolTip
from utils.upload_bluetooth_service import is_ios_like_name


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
        pad = 8
        font = ("Segoe UI", 11)
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
            text="Drag & Drop File(s)",
            font=font,
            fill=fgc,
        )

    canvas.bind("<Configure>", lambda e: redraw(e))
    canvas.drop_target_register(dnd_files)
    canvas.dnd_bind("<<Drop>>", lambda e: app._upload_bluetooth_handle_drop(e))
    app._upload_bluetooth_drop_redraw = redraw
    return canvas


def show_upload_subtab(app, name: str) -> None:
    name = (name or "").strip().lower()
    sel = "bluetooth" if name == "bluetooth" else "remote"

    # Toggle panels
    if sel == "bluetooth":
        app.upload_remote_panel.grid_remove()
        app._upload_bluetooth_panel.grid(row=0, column=1, sticky="nsew")
    else:
        app._upload_bluetooth_panel.grid_remove()
        app.upload_remote_panel.grid(row=0, column=1, sticky="nsew")

    on = ("#3b8ed0", "#1f538d")
    off = ("gray70", "gray40")

    # The width is now managed by the .pack(fill="x") in the build function
    app._upload_nav_remote.configure(
        fg_color=on if sel == "remote" else off,
        font=("Segoe UI", 12, "bold") if sel == "remote" else ("Segoe UI", 12),
    )

    app._upload_nav_bluetooth.configure(
        fg_color=on if sel == "bluetooth" else off,
        font=("Segoe UI", 12, "bold") if sel == "bluetooth" else ("Segoe UI", 12),
    )


def build_upload_tab_controls(
    app: Any, upload_parent: ctk.CTkFrame, settings: Mapping[str, Any], dnd_files: str
) -> None:
    """Populate Upload section widgets on ``upload_parent`` (top-level Upload tab)."""
    app.upload_frame = upload_parent
    app.upload_frame.grid_rowconfigure(0, weight=1)
    app.upload_frame.grid_columnconfigure(1, weight=1)
    app.upload_frame.grid_propagate(False)

    app._upload_nav = ctk.CTkFrame(app.upload_frame, width=90, fg_color="#242424")
    app._upload_nav.grid(row=0, column=0, sticky="ns", padx=3, pady=(0, 6))
    app._upload_nav.grid_propagate(False)  # This locks the frame at 120px
    app._upload_nav.grid_columnconfigure(0, weight=1)

    app._upload_nav_remote = ctk.CTkButton(
        app._upload_nav,
        text="Remote",
        width=80,
        command=lambda: show_upload_subtab(app, "remote"),
    )
    app._upload_nav_remote.grid(row=0, column=0, pady=8)

    app._upload_nav_bluetooth = ctk.CTkButton(
        app._upload_nav,
        text="Bluetooth",
        width=80,
        command=lambda: show_upload_subtab(app, "bluetooth"),
    )
    app._upload_nav_bluetooth.grid(row=1, column=0, pady=(0, 8))

    app.upload_remote_panel = ctk.CTkFrame(app.upload_frame, fg_color="transparent")
    app.upload_remote_panel.grid_columnconfigure(0, weight=1)
    app.upload_remote_panel.grid_rowconfigure(8, weight=1)
    app.upload_remote_panel.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

    app._upload_bluetooth_panel = ctk.CTkFrame(app.upload_frame, fg_color="transparent")
    app._upload_bluetooth_panel.grid_columnconfigure(0, weight=1)
    # Row 1 = preview: no weight — otherwise it eats all height and hides Browse / Upload / Doctor.
    app._upload_bluetooth_panel.grid_rowconfigure(1, weight=0)
    app._upload_bluetooth_panel.grid_rowconfigure(6, weight=1)
    app._upload_bluetooth_panel.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

    build_remote_panel(app, app.upload_remote_panel)
    build_bluetooth_panel(app, app._upload_bluetooth_panel, settings, dnd_files)


def build_remote_panel(app, upload_remote_panel: ctk.CTkFrame) -> None:
    _uu = app._normalized_upload_file()
    ctk.CTkLabel(
        upload_remote_panel,
        text="Upload files from this PC to a remote URL.",
        font=("Segoe UI", 12, "bold"),
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))

    label_group = ctk.CTkFrame(upload_remote_panel, fg_color="transparent")
    label_group.grid(row=1, column=0, sticky="w")
    ctk.CTkLabel(
        label_group,
        text="Remote URL:",
        font=("Segoe UI", 11),
    ).pack(side="left")
    InfoButton(
        label_group,
        tooltip_text='POST multipart/form-data, field name "file"',
    ).pack(side="left", padx=(0, 2))

    app.upload_tab_url_entry = ctk.CTkEntry(
        upload_remote_panel,
        placeholder_text="https://your-server.example/upload/file",
        font=("Segoe UI", 12),
    )
    if _uu["remote_url"]:
        app.upload_tab_url_entry.insert(0, _uu["remote_url"])
    app.upload_tab_url_entry.grid(row=2, column=0, sticky="ew", pady=(2, 6))
    ctk.CTkLabel(
        upload_remote_panel,
        text="Bearer token (optional):",
        font=("Segoe UI", 11),
    ).grid(row=3, column=0, sticky="w")
    app.upload_tab_token_entry = ctk.CTkEntry(
        upload_remote_panel,
        show="*",
        font=("Segoe UI", 12),
    )
    if _uu["remote_token"]:
        app.upload_tab_token_entry.insert(0, _uu["remote_token"])
    app.upload_tab_token_entry.grid(row=4, column=0, sticky="ew", pady=(2, 6))

    path_row = ctk.CTkFrame(upload_remote_panel, fg_color="transparent")
    path_row.grid(row=5, column=0, sticky="ew", pady=(0, 6))
    path_row.grid_columnconfigure(0, weight=1)
    app.upload_tab_path_entry = ctk.CTkEntry(
        path_row,
        placeholder_text="No file selected",
        font=("Segoe UI", 12),
    )
    app.upload_tab_path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ctk.CTkButton(
        path_row,
        text="Browse",
        width=80,
        command=app._upload_tab_browse,
    ).grid(row=0, column=1)
    app._upload_local_path = ""

    up_btn_row = ctk.CTkFrame(upload_remote_panel, fg_color="transparent")
    up_btn_row.grid(row=6, column=0, sticky="w")
    app.upload_tab_send_btn = ctk.CTkButton(
        up_btn_row,
        text="Upload file",
        width=120,
        fg_color="#2ecc71",
        hover_color="#27ae60",
        font=("Segoe UI", 13, "bold"),
        command=app._upload_tab_send,
    )
    app.upload_tab_send_btn.pack(side="left")

    app.upload_tab_status = ctk.CTkTextbox(
        upload_remote_panel,
        height=100,
        font=("Consolas", 11),
    )
    app.upload_tab_status.grid(row=8, column=0, sticky="nsew", pady=(8, 0))


def build_bluetooth_panel(
    app: Any,
    upload_bluetooth_panel: ctk.CTkFrame,
    settings: Mapping[str, Any],
    dnd_files: str,
) -> None:
    app._bt_target_device_id = ""
    app._bt_target_name = ""
    app._upload_bluetooth_paths = []
    app._upload_bluetooth_preview_img = None
    app._upload_bluetooth_thumb_refs = []
    app._bt_picker_win = None
    app._bt_picker_devices = []

    bluetooth_top = ctk.CTkFrame(upload_bluetooth_panel, fg_color="transparent")
    bluetooth_top.grid(row=0, column=0, sticky="ew")
    bluetooth_top.grid_columnconfigure(0, weight=1)
    app.upload_bt_device_label = HoverMarqueeClipLabel(
        bluetooth_top,
        text="No device selected.",
        font=("Segoe UI", 11),
    )
    app.upload_bt_device_label.grid(row=0, column=0, sticky="ew")
    ctk.CTkButton(
        bluetooth_top,
        text="Select device",
        command=app._upload_bt_open_picker,
    ).grid(row=0, column=1, sticky="e", padx=(8, 0))

    # Queue List (scrollable). Content lives in _upload_bluetooth_queue_inner so we never
    # destroy CTkScrollableFrame internal widgets when refreshing rows.
    app.upload_bluetooth_list_frame = ctk.CTkScrollableFrame(
        upload_bluetooth_panel,
        height=120,
        fg_color=("#ebebeb", "#2b2b2b"),
        corner_radius=8,
    )
    app.upload_bluetooth_list_frame._scrollbar.configure(height=120)
    app.upload_bluetooth_list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
    app._upload_bluetooth_queue_inner = ctk.CTkFrame(
        app.upload_bluetooth_list_frame, fg_color="transparent"
    )
    app._upload_bluetooth_queue_inner.pack(fill="both", expand=True)

    app.upload_bluetooth_empty_label = ctk.CTkLabel(
        app._upload_bluetooth_queue_inner,
        text="No file(s) selected\n(Browse or drop to choose file(s))",
        text_color="gray",
    )
    app.upload_bluetooth_empty_label.pack(expand=True, fill="both", pady=40)

    # Drag & Drop Zone
    app.upload_bluetooth_drop_wrap = ctk.CTkFrame(
        upload_bluetooth_panel, fg_color="transparent"
    )
    app.upload_bluetooth_drop_wrap.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    app.upload_bluetooth_drop_canvas = _build_dashed_drop_canvas(
        app.upload_bluetooth_drop_wrap,
        app,
        dnd_files,
        height=60,
        width=120,
    )
    app.upload_bluetooth_drop_canvas.pack(fill="x", expand=False)

    # region Action Control Group
    bluetooth_path_row = ctk.CTkFrame(upload_bluetooth_panel, fg_color="transparent")
    bluetooth_path_row.grid(row=3, column=0, sticky="ew", pady=(0, 6))
    bluetooth_path_row.grid_columnconfigure(0, weight=1)

    app.upload_bluetooth_path_entry = ctk.CTkEntry(
        bluetooth_path_row,
        placeholder_text="No file(s) selected",
        font=("Segoe UI", 12),
    )
    app.upload_bluetooth_path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    app.upload_bluetooth_browse_btn = ctk.CTkButton(
        bluetooth_path_row,
        text="Browse",
        width=80,
        command=app._upload_bluetooth_browse,
    )
    app.upload_bluetooth_browse_btn.grid(row=0, column=1)

    bluetooth_action_row = ctk.CTkFrame(upload_bluetooth_panel, fg_color="transparent")
    bluetooth_action_row.grid(row=4, column=0, sticky="ew", pady=(0, 6))

    app.upload_bluetooth_send_btn = ctk.CTkButton(
        bluetooth_action_row,
        text="Upload file(s) to device",
        width=170,
        fg_color="#2ecc71",
        hover_color="#27ae60",
        font=("Segoe UI", 13, "bold"),
        command=app._upload_bluetooth_send_bt,
    )
    app.upload_bluetooth_send_btn.pack(side="left", fill="x")

    app.upload_bluetooth_doctor_btn = ctk.CTkButton(
        bluetooth_action_row,
        text="Doctor",
        width=80,
        fg_color="#3498db",
        hover_color="#1f538d",
        font=("Segoe UI", 13, "bold"),
        command=app._upload_bluetooth_doctor,
    )
    app.upload_bluetooth_doctor_btn.pack(side="left", padx=(8, 0))
    ToolTip(
        app.upload_bluetooth_doctor_btn,
        "Analyze the status of the Bluetooth transfer.",
    )
    # endregion

    # region Status Display
    ctk.CTkLabel(
        upload_bluetooth_panel,
        text="Status:",
        font=("Segoe UI", 11),
    ).grid(row=5, column=0, sticky="w", pady=(0))

    app._upload_bluetooth_status_host = ctk.CTkFrame(
        upload_bluetooth_panel,
        fg_color="transparent",
    )
    app._upload_bluetooth_status_host.grid(row=6, column=0, sticky="nsew", pady=(4, 0))

    app.upload_bluetooth_status = ctk.CTkTextbox(
        app._upload_bluetooth_status_host,
        font=("Consolas", 10),
    )
    app.upload_bluetooth_status.pack(fill="both", expand=True)
    # endregion

    _apply_saved_bluetooth_upload_target(app, settings)

    show_upload_subtab(app, "remote")


def _apply_saved_bluetooth_upload_target(app: Any, settings: Mapping[str, Any]) -> None:
    raw = settings.get("bluetooth_upload")
    if not isinstance(raw, dict):
        return
    device_id = (raw.get("device_id") or "").strip()
    name = (raw.get("name") or "").strip()
    if not device_id:
        return
    if is_ios_like_name(name):
        settings["bluetooth_upload"] = {"device_id": "", "name": ""}
        return
    app._bt_target_device_id = device_id
    app._bt_target_name = name or device_id
    app.upload_bt_device_label.configure(text=f"Device: {app._bt_target_name}")
