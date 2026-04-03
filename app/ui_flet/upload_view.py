from __future__ import annotations

import base64
import io
import os
from typing import Any

import flet as ft
from PIL import Image

from app.controllers import bluetooth_picker_controller as bt_picker
from app.controllers import upload_bluetooth_controller as bt_upload_actions
from app.controllers import upload_remote_controller as remote_upload_actions
from app.ui_flet.adapters.ui_bridge import ButtonProxy, EntryProxy, LabelProxy, TextProxy
from app.ui_flet.bluetooth_picker_dialog import build_bluetooth_picker_dialog
from app.ui_flet.file_dialogs import schedule_pick_files
from app.ui_flet.theme import (
    GLOBAL_RADIUS,
    PRIMARY,
    SUCCESS,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    button_style,
    input_outline_kwargs,
)


def build_upload_view(app: Any, page: ft.Page) -> ft.Control:
    def _get_thumbnail_b64(path: str) -> str | None:
        try:
            with Image.open(path) as img:
                img.thumbnail((64, 64))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                return f"data:image/png;base64,{b64_str}"
        except Exception:
            return None

    upload_filepicker = ft.FilePicker()
    bt_filepicker = ft.FilePicker()

    app._upload_local_path = ""
    app._upload_bluetooth_paths = []
    app._bt_target_device_id = ""
    app._bt_target_name = ""
    app._bt_picker_devices = []
    app._bt_picker_selected_idx = -1
    app._flet_bt_picker = True

    # Remote panel controls
    remote_cfg = app._normalized_upload_file()
    url_tf = ft.TextField(
        label="Remote URL",
        value=remote_cfg["remote_url"],
        border_radius=GLOBAL_RADIUS,
        filled=False,
        tooltip="HTTP(S) endpoint that accepts the file upload (e.g. REST API)",
        **input_outline_kwargs(),
    )
    token_tf = ft.TextField(
        label="Bearer token (optional)",
        value=remote_cfg["remote_token"],
        border_radius=GLOBAL_RADIUS,
        filled=False,
        password=True,
        can_reveal_password=True,
        tooltip="If the server expects Authorization: Bearer …, paste the secret here",
        **input_outline_kwargs(),
    )
    path_tf = ft.TextField(
        label="Local file",
        read_only=True,
        filled=False,
        multiline=False,
        min_lines=1,
        max_lines=1,
        border_radius=GLOBAL_RADIUS,
        tooltip="Path of the file that will be uploaded when you click Upload file",
        **input_outline_kwargs(),
    )
    remote_status_tf = ft.TextField(
        multiline=True,
        min_lines=3,
        max_lines=5,
        read_only=True,
        filled=False,
        border_radius=GLOBAL_RADIUS,
        tooltip="Log output and status messages from the last remote upload",
        **input_outline_kwargs(),
    )
    remote_send_btn = ft.FilledButton(
        "Upload file",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(SUCCESS),
        tooltip="POST the chosen file to the remote URL (optional Bearer token)",
        on_click=lambda _e: remote_upload_actions.run_upload_tab_send(app),
    )

    app.upload_tab_url_entry = EntryProxy(url_tf)
    app.upload_tab_token_entry = EntryProxy(token_tf)
    app.upload_tab_path_entry = EntryProxy(path_tf)
    app.upload_tab_status = TextProxy(remote_status_tf)
    app.upload_tab_send_btn = ButtonProxy(remote_send_btn)

    def on_remote_files(files: list[ft.FilePickerFile]) -> None:
        if not files:
            return
        path = files[0].path
        if not path:
            return
        app._upload_local_path = path
        app.upload_tab_path_entry.delete(0, "end")
        app.upload_tab_path_entry.insert(0, path)
        app._safe_page_update()

    remote_scrollable = ft.Column(
        [
            ft.Text("Upload files from this PC to a remote URL.", weight=ft.FontWeight.BOLD),
            url_tf,
            token_tf,
            ft.Row(
                [
                    ft.Container(expand=True, content=path_tf),
                    ft.FilledButton(
                        "Browse",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        style=button_style(PRIMARY),
                        on_click=lambda _e: schedule_pick_files(
                            page,
                            upload_filepicker,
                            on_remote_files,
                            allow_multiple=False,
                            dialog_title="Choose file to upload",
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    remote_bottom = ft.Column(
        [
            remote_send_btn,
            remote_status_tf,
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    remote_panel = ft.Column(
        [
            ft.Container(expand=True, content=remote_scrollable),
            remote_bottom,
        ],
        expand=True,
        spacing=16,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # Bluetooth panel controls
    bt_device_label = ft.Text("No device selected.")
    bt_paths_tf = ft.TextField(
        read_only=True,
        filled=False,
        multiline=False,
        min_lines=1,
        max_lines=1,
        border_radius=GLOBAL_RADIUS,
        tooltip="Summary of files queued for Bluetooth send",
        **input_outline_kwargs(),
    )
    bt_status_tf = ft.TextField(
        multiline=True,
        min_lines=3,
        max_lines=5,
        read_only=True,
        filled=False,
        border_radius=GLOBAL_RADIUS,
        tooltip="Bluetooth pairing, send progress, and error messages",
        **input_outline_kwargs(),
    )
    bt_send_btn = ft.FilledButton(
        "Upload file(s) to device",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(SUCCESS),
        tooltip="Send the queued file(s) to the selected Bluetooth device (RFCOMM)",
        on_click=lambda _e: bt_upload_actions.upload_bluetooth_send_bt(
            app,
            logger=app.logger,
            settings=app.settings,
        ),
    )
    bt_doctor_btn = ft.FilledButton(
        "Doctor",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Diagnose Bluetooth / pairing issues and suggest fixes",
        on_click=lambda _e: bt_upload_actions.upload_bluetooth_doctor(app, logger=app.logger),
    )

    queue_list = ft.Column([], spacing=6, scroll=ft.ScrollMode.AUTO)

    app.upload_bt_device_label = LabelProxy(bt_device_label)
    app.upload_bluetooth_path_entry = EntryProxy(bt_paths_tf)
    app.upload_bluetooth_status = TextProxy(bt_status_tf)
    app.upload_bluetooth_send_btn = ButtonProxy(bt_send_btn)
    app.upload_bluetooth_doctor_btn = ButtonProxy(bt_doctor_btn)

    def render_bt_queue() -> None:
        paths = list(getattr(app, "_upload_bluetooth_paths", []) or [])
        app.upload_bluetooth_path_entry.delete(0, "end")
        if not paths:
            app.upload_bluetooth_path_entry.insert(0, "No file(s) selected")
            queue_list.controls = [ft.Text("No file(s) selected (Browse to choose file(s))", color=ft.Colors.GREY_500)]
        elif len(paths) == 1:
            app.upload_bluetooth_path_entry.insert(0, paths[0])
        else:
            app.upload_bluetooth_path_entry.insert(0, f"{len(paths)} files selected")
        if paths:
            rows = []
            for path in paths:
                b64 = _get_thumbnail_b64(path)
                img_control = (
                    ft.Image(src=b64, width=32, height=32, fit=ft.BoxFit.COVER, border_radius=4)
                    if b64 else ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=32, color=ft.Colors.GREY_500)
                )
                rows.append(
                    ft.Row(
                        [
                            img_control,
                            ft.Text(os.path.basename(path), expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                tooltip="Remove this file from the send queue",
                                on_click=lambda _e, p=path: _remove_bt_path(p),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )
            queue_list.controls = rows
        app._safe_page_update()

    def _remove_bt_path(path: str) -> None:
        app._upload_bluetooth_paths = [p for p in app._upload_bluetooth_paths if p != path]
        render_bt_queue()

    def on_bt_files(files: list[ft.FilePickerFile]) -> None:
        if not files:
            return
        add_paths = [f.path for f in files if f.path]
        app._upload_bluetooth_paths = bt_upload_actions._merge_bluetooth_paths(
            list(getattr(app, "_upload_bluetooth_paths", []) or []),
            add_paths,
        )
        render_bt_queue()
    app._flet_render_bt_queue = render_bt_queue

    bt_picker_dialog = build_bluetooth_picker_dialog(app)
    page.overlay.append(bt_picker_dialog)

    bt_scrollable = ft.Column(
        [
            ft.Row(
                [
                    bt_device_label,
                    ft.FilledButton(
                        "Select device",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        style=button_style(PRIMARY),
                        tooltip="Open the Bluetooth device list to pair or pick a target",
                        on_click=lambda _e: bt_picker.upload_bt_open_picker(
                            app,
                            logger=app.logger,
                            settings=app.settings,
                        ),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=GLOBAL_RADIUS,
                padding=8,
                height=170,
                content=queue_list,
            ),
            ft.Row(
                [
                    ft.Container(expand=True, content=bt_paths_tf),
                    ft.FilledButton(
                        "Browse",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        style=button_style(PRIMARY),
                        on_click=lambda _e: schedule_pick_files(
                            page,
                            bt_filepicker,
                            on_bt_files,
                            allow_multiple=True,
                            dialog_title="Choose file(s) to send",
                        ),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    bt_bottom = ft.Column(
        [
            ft.Row(
                [bt_send_btn, bt_doctor_btn],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bt_status_tf,
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    bluetooth_panel = ft.Column(
        [
            ft.Container(expand=True, content=bt_scrollable),
            bt_bottom,
        ],
        expand=True,
        spacing=16,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    selected = {"name": "remote"}
    content_container = ft.Container(expand=True, content=remote_panel)

    def show_panel(name: str) -> None:
        selected["name"] = name
        content_container.content = remote_panel if name == "remote" else bluetooth_panel
        nav_remote.style = button_style(PRIMARY if name == "remote" else "#6d6d6d")
        nav_bt.style = button_style(PRIMARY if name == "bluetooth" else "#6d6d6d")
        app._safe_page_update()

    nav_remote = ft.FilledButton(
        "Remote",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Upload to a server over HTTP(S)",
        on_click=lambda _e: show_panel("remote"),
    )
    nav_bt = ft.FilledButton(
        "Bluetooth",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style("#6d6d6d"),
        tooltip="Send files to a phone or device over Bluetooth",
        on_click=lambda _e: show_panel("bluetooth"),
    )

    show_panel("remote")
    render_bt_queue()

    upload_body = ft.Row(
        [
            ft.Container(
                width=120,
                content=ft.Column(
                    [nav_remote, nav_bt],
                    spacing=8,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            ft.VerticalDivider(width=1),
            content_container,
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START,
        expand=True,
    )
    return ft.Container(
        expand=True,
        content=upload_body,
    )
