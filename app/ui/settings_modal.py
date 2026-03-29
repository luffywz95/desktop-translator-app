from __future__ import annotations

import customtkinter as ctk

from components.hot_key_settings_row import HotkeySettingRow
from components.tooltip import ToolTip


def build_settings_modal(app, settings: dict) -> None:
    app.settings_modal = ctk.CTkFrame(
        app, corner_radius=20, border_width=2, fg_color=("#ffffff", "#2b2b2b")
    )
    app.settings_modal.place_forget()

    app.settings_panel = ctk.CTkScrollableFrame(
        app.settings_modal,
        fg_color="transparent",
        corner_radius=0,
        orientation="vertical",
        label_text="Application Settings",
        label_font=("Arial", 18, "bold"),
    )
    app.settings_panel.pack(fill="both", expand=True, pady=(10, 0), padx=10)
    app.settings_panel._label.grid_configure(pady=(5, 5), padx=20)

    app.application_invoke_hotkey_row = HotkeySettingRow(
        app.settings_panel,
        label_text="The Hotkey for Application Invoke:",
        default_key=settings["hotkey_settings"]["application_invoke_hotkey"]["hotkey"][
            -1
        ].upper(),
        is_enabled=settings["hotkey_settings"]["application_invoke_hotkey"]["enable"],
        always_enabled=True,
        tooltip_text=None,
    )
    app.application_invoke_hotkey_row.pack(pady=(10, 0), padx=30, fill="x")

    app.background_process_hotkey_row = HotkeySettingRow(
        app.settings_panel,
        label_text="Enable Hotkey for Background Process:",
        default_key=settings["hotkey_settings"]["background_process_hotkey"]["hotkey"][
            -1
        ].upper(),
        is_enabled=settings["hotkey_settings"]["background_process_hotkey"]["enable"],
        always_enabled=False,
        tooltip_text="Instant process the recently captured image, the result will be copied to the clipboard",
    )
    app.background_process_hotkey_row.pack(pady=(10, 10), padx=30, fill="x")

    ctk.CTkFrame(
        app.settings_panel,
        height=2,
        fg_color=("#dbdbdb", "#3d3d3d"),
        border_width=0,
    ).pack(fill="x", padx=15, pady=10)

    _r0 = app._normalized_receive_file()
    _u0 = app._normalized_upload_file()

    ctk.CTkLabel(
        app.settings_panel,
        text="Enable File Transfer Ports",
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", padx=30, pady=(0, 4))

    app.receive_file_var = ctk.BooleanVar(value=bool(_r0["enable"]))
    app.receive_file_port_var = ctk.StringVar(value=str(_r0["port"]))
    receive_row = ctk.CTkFrame(app.settings_panel, fg_color="transparent")
    receive_row.pack(fill="x", padx=30, pady=(0, 6))
    ctk.CTkLabel(
        receive_row,
        text="Receive file",
        font=("Segoe UI", 13, "bold"),
    ).pack(side="left")
    app.receive_file_port_entry = ctk.CTkEntry(
        receive_row,
        width=76,
        textvariable=app.receive_file_port_var,
        justify="center",
    )
    app.receive_file_port_entry.pack(side="right", padx=(8, 0))
    app.receive_file_switch = ctk.CTkSwitch(
        receive_row,
        text="",
        width=44,
        variable=app.receive_file_var,
        command=app._on_receive_file_toggle,
    )
    app.receive_file_switch.pack(side="right", padx=(8, 0))
    ToolTip(
        app.receive_file_switch,
        "Receive: listen on LAN for uploads to this PC. Saving settings may add or update an "
        "inbound Windows Firewall rule for the port.",
    )

    app.upload_file_var = ctk.BooleanVar(value=bool(_u0["enable"]))
    app.upload_file_port_var = ctk.StringVar(value=str(_u0["port"]))
    upload_row = ctk.CTkFrame(app.settings_panel, fg_color="transparent")
    upload_row.pack(fill="x", padx=30, pady=(0, 8))
    ctk.CTkLabel(
        upload_row,
        text="Upload file",
        font=("Segoe UI", 13, "bold"),
    ).pack(side="left")
    app.upload_file_port_entry = ctk.CTkEntry(
        upload_row,
        width=76,
        textvariable=app.upload_file_port_var,
        justify="center",
    )
    app.upload_file_port_entry.pack(side="right", padx=(8, 0))
    app.upload_file_switch = ctk.CTkSwitch(
        upload_row,
        text="",
        width=44,
        variable=app.upload_file_var,
        command=app._on_upload_file_toggle,
    )
    app.upload_file_switch.pack(side="right", padx=(8, 0))
    ToolTip(
        app.upload_file_switch,
        "Upload: allow outbound connections on this TCP port. Saving settings may add or update "
        "an outbound Windows Firewall rule.",
    )

    ctk.CTkFrame(
        app.settings_panel,
        height=2,
        fg_color=("#dbdbdb", "#3d3d3d"),
        border_width=0,
    ).pack(fill="x", padx=15, pady=10)

    app.dim_var = ctk.BooleanVar(value=settings["enable_focus_dim"])
    ctk.CTkCheckBox(
        app.settings_panel, text="Auto-dim on Focus Lost", variable=app.dim_var
    ).pack(pady=(10, 0), padx=30, anchor="w")

    ctk.CTkLabel(app.settings_panel, text="Focus-out Opacity Level:").pack(
        pady=(10, 0), padx=30, anchor="w"
    )

    app.opacity_val = ctk.DoubleVar(value=settings["idle_opacity"])
    app.opacity_slider = ctk.CTkSlider(
        app.settings_panel, from_=0.1, to=1.0, variable=app.opacity_val
    )
    app.opacity_slider.set(settings["idle_opacity"])
    app.opacity_slider.pack(pady=10, padx=30, fill="x")

    ctk.CTkFrame(
        app.settings_panel,
        height=2,
        fg_color=("#dbdbdb", "#3d3d3d"),
        border_width=0,
    ).pack(fill="x", padx=15, pady=10)

    install_btn = ctk.CTkButton(
        app.settings_panel,
        text="➕ Install New Voices",
        fg_color="#3498db",
        command=app._install_voice_ui,
        height=30,
    )
    install_btn.pack(pady=10, padx=30)

    ctk.CTkFrame(
        app.settings_modal,
        height=2,
        fg_color=("#dbdbdb", "#3d3d3d"),
        border_width=0,
    ).pack(fill="x", padx=15, pady=(5, 0))

    app.save_btn = ctk.CTkButton(
        app.settings_modal,
        text="Save & Close",
        corner_radius=12,
        fg_color="#2ecc71",
        hover_color="#27ae60",
        command=lambda: app.close_settings(save=True),
    )
    app.save_btn.pack(fill="x", padx=25, pady=(10, 20))

    app.bind("<Escape>", lambda event: app.close_settings())
