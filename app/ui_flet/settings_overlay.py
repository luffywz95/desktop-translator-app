from __future__ import annotations

import sys
from typing import Any

import flet as ft

from app.ui_flet.firewall_save_flow import start_flet_firewall_then_save
from app.ui_flet.theme import (
    GLOBAL_RADIUS,
    SUCCESS,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    button_style,
    input_outline_kwargs,
    normalize_theme_mode_setting,
    theme_mode_from_setting,
)


def build_settings_overlay(app: Any) -> tuple[ft.Container, callable, callable]:
    recv_cfg = app._normalized_receive_file()
    upload_cfg = app._normalized_upload_file()

    receive_switch = ft.Switch(
        label="Receive file",
        value=bool(recv_cfg["enable"]),
        tooltip="Run the local Transfer Hub HTTP listener to receive files from your phone",
    )
    receive_port = ft.TextField(
        label="Receive port",
        value=str(recv_cfg["port"]),
        width=140,
        border_radius=GLOBAL_RADIUS,
        tooltip="TCP port for the receive server (must match the phone app)",
        **input_outline_kwargs(),
    )
    upload_switch = ft.Switch(
        label="Upload file",
        value=bool(upload_cfg["enable"]),
        tooltip="Allow this PC to accept upload-related Transfer Hub features on the upload port",
    )
    upload_port = ft.TextField(
        label="Upload port",
        value=str(upload_cfg["port"]),
        width=140,
        border_radius=GLOBAL_RADIUS,
        tooltip="TCP port used for upload-side Transfer Hub integration",
        **input_outline_kwargs(),
    )

    loading_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

    theme_dd = ft.Dropdown(
        label="Theme",
        width=240,
        value=app.theme_mode,
        tooltip="Light, dark, or match your system setting",
        options=[
            ft.dropdown.Option(key="dark", text="Dark"),
            ft.dropdown.Option(key="light", text="Light"),
            ft.dropdown.Option(key="system", text="Follow system"),
        ],
        border_radius=GLOBAL_RADIUS,
        **input_outline_kwargs(),
    )

    def on_theme_select(e: ft.ControlEvent) -> None:
        # Material Dropdown fires `on_select`, not `on_change` (compat only maps ctor kwargs).
        ctrl = getattr(e, "control", None)
        raw = getattr(ctrl, "value", None) if ctrl is not None else None
        if raw is None:
            raw = getattr(e, "data", None)
        key = normalize_theme_mode_setting(raw)
        app.theme_mode = key
        app.page.theme_mode = theme_mode_from_setting(key)
        app.settings["theme_mode"] = key
        app.page.update()

    theme_dd.on_select = on_theme_select

    overlay = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
        alignment=ft.Alignment(0, 0),
        expand=True,
        content=ft.Container(
            width=560,
            bgcolor=ft.Colors.SURFACE,
            border_radius=20,
            border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
            shadow=ft.BoxShadow(
                spread_radius=2,
                blur_radius=15,
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
                offset=ft.Offset(0, 4)
            ),
            padding=16,
            content=ft.Column(
                [
                    ft.Text("Application Settings", size=20, weight=ft.FontWeight.BOLD),
                    ft.Divider(height=1, color=ft.Colors.GREY_800),
                    ft.Column(
                        [
                            theme_dd,
                            ft.Row([receive_switch, receive_port], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Row([upload_switch, upload_port], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ],
                        spacing=10,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    ft.Divider(height=1, color=ft.Colors.GREY_800),
                    ft.Row(
                        [
                            loading_ring,
                            ft.FilledButton(
                                "Save",
                                height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                                style=button_style(SUCCESS),
                                tooltip="Save Transfer Hub and UI options",
                            ),
                            ft.OutlinedButton(
                                "Close",
                                height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=GLOBAL_RADIUS)),
                                tooltip="Hide settings without writing changes to disk",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=16,
                tight=True,
            ),
        ),
    )

    save_btn = overlay.content.content.controls[-1].controls[1]
    close_btn = overlay.content.content.controls[-1].controls[2]

    def set_loading(loading: bool) -> None:
        loading_ring.visible = loading
        overlay.content.content.disabled = loading
        app.settings["settings_is_loading"] = loading
        if hasattr(app, "_safe_page_update"):
            app._safe_page_update()
        else:
            app.page.update()

    def close_settings(force: bool = False) -> None:
        if app.settings.get("settings_is_loading"):
            return
        if not force:
            recv_cfg = app._normalized_receive_file()
            upload_cfg = app._normalized_upload_file()
            
            changed = False
            if bool(receive_switch.value) != bool(recv_cfg["enable"]): changed = True
            if str(receive_port.value) != str(recv_cfg["port"]): changed = True
            if bool(upload_switch.value) != bool(upload_cfg["enable"]): changed = True
            if str(upload_port.value) != str(upload_cfg["port"]): changed = True
            
            if changed:
                if hasattr(app, "schedule_confirm_dialog"):
                    app.schedule_confirm_dialog(
                        "Unsaved Changes",
                        "There are change(s) not saved yet, continue to close?",
                        on_yes=lambda: close_settings(force=True)
                    )
                return

        overlay.visible = False
        app.settings["settings_open"] = False
        app.page.update()

    def save_settings() -> None:
        receive_port_num = app._get_port_or_default(receive_port.value, 5000)
        upload_port_num = app._get_port_or_default(upload_port.value, 5000)
        new_rcv = bool(receive_switch.value)
        new_up = bool(upload_switch.value)
        old_receive = app._normalized_receive_file()
        old_upload = app._normalized_upload_file()

        def finalize(
            final_rcv: bool,
            final_up: bool,
            firewall_summary: str | None = None,
        ) -> None:
            set_loading(False)
            receive_switch.value = final_rcv
            upload_switch.value = final_up
            tm = normalize_theme_mode_setting(theme_dd.value)
            app.theme_mode = tm
            app.page.theme_mode = theme_mode_from_setting(tm)
            app.settings.begin_batch()
            try:
                app.settings["theme_mode"] = tm
                app._persist_transfer_hub_atomic(
                    {"enable": final_rcv, "port": receive_port_num},
                    {
                        "enable": final_up,
                        "port": upload_port_num,
                        "remote_url": old_upload.get("remote_url", ""),
                        "remote_token": old_upload.get("remote_token", ""),
                    },
                )
            finally:
                app.settings.commit()
            if hasattr(app, "_safe_page_update"):
                app._safe_page_update()
            else:
                app.page.update()
            app._restart_transfer_hub_if_visible()

            body = "Settings saved successfully."
            if firewall_summary is not None:
                extra = firewall_summary.strip()
                if extra:
                    body = f"{body}\n\n{extra}"
            # SnackBar sits under the full-screen settings overlay; use a dialog so the user sees it.
            if hasattr(app, "schedule_info_dialog"):
                app.schedule_info_dialog("Settings", body, on_ok=None)
            elif hasattr(app, "showinfo"):
                app.showinfo("Settings", body)

        if sys.platform == "win32" and (new_rcv or new_up):
            set_loading(True)
            start_flet_firewall_then_save(
                app,
                old_receive=old_receive,
                old_upload=old_upload,
                receive_port=receive_port_num,
                upload_port=upload_port_num,
                new_receive_enabled=new_rcv,
                new_upload_enabled=new_up,
                receive_switch=receive_switch,
                upload_switch=upload_switch,
                on_done=finalize,
            )
            return

        finalize(new_rcv, new_up)

    close_btn.on_click = lambda _e: close_settings()
    save_btn.on_click = lambda _e: save_settings()

    def open_settings() -> None:
        recv_cfg = app._normalized_receive_file()
        upload_cfg = app._normalized_upload_file()
        receive_switch.value = bool(recv_cfg["enable"])
        receive_port.value = str(recv_cfg["port"])
        upload_switch.value = bool(upload_cfg["enable"])
        upload_port.value = str(upload_cfg["port"])
        app.theme_mode = normalize_theme_mode_setting(app.settings.get("theme_mode"))
        theme_dd.value = app.theme_mode

        overlay.visible = True
        app.settings["settings_open"] = True
        app.page.update()

    return overlay, open_settings, close_settings
