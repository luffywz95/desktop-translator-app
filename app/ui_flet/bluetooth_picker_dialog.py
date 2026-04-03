from __future__ import annotations

from typing import Any

import flet as ft

from app.controllers import bluetooth_picker_controller as bt_picker
from app.ui_flet.theme import (
    GLOBAL_RADIUS,
    PRIMARY,
    SUCCESS,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    button_style,
)


def build_bluetooth_picker_dialog(app: Any) -> ft.AlertDialog:
    status_text = ft.Text("", size=12)
    devices_column = ft.Column([], spacing=4, scroll=ft.ScrollMode.AUTO, height=260)

    def render_devices() -> None:
        devices = list(getattr(app, "_bt_picker_devices", []) or [])
        selected = int(getattr(app, "_bt_picker_selected_idx", -1))
        status_text.value = getattr(app, "_bt_picker_status_value", "") or ""
        rows: list[ft.Control] = []
        for idx, dev in enumerate(devices):
            tag = "paired" if getattr(dev, "is_paired", False) else "nearby"
            label = f"{dev.name} ({tag})"
            rows.append(
                ft.Container(
                    border_radius=GLOBAL_RADIUS,
                    bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE) if idx == selected else None,
                    content=ft.ListTile(
                        dense=True,
                        title=ft.Text(label),
                        on_click=lambda _e, i=idx: _select(i),
                    ),
                    padding=4,
                )
            )
        devices_column.controls = rows or [ft.Text("No devices found.")]
        app._safe_page_update()

    def _select(index: int) -> None:
        app._bt_picker_selected_idx = index
        render_devices()

    def open_dialog() -> None:
        dialog.open = True
        render_devices()
        app._safe_page_update()

    def close_dialog() -> None:
        dialog.open = False
        app._safe_page_update()

    def refresh_dialog() -> None:
        render_devices()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Bluetooth devices"),
        content=ft.Container(
            width=460,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                icon_color=PRIMARY,
                                tooltip="Scan again for paired and nearby Bluetooth devices",
                                on_click=lambda _e: bt_picker.upload_bt_refresh_picker_list(app),
                            ),
                            status_text,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    devices_column,
                ],
                tight=True,
            ),
        ),
        actions=[
            ft.FilledButton(
                "Pair selected",
                height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                style=button_style(PRIMARY),
                tooltip="Start pairing with the highlighted device (if supported)",
                on_click=lambda _e: bt_picker.upload_bt_pair_selected(app),
            ),
            ft.FilledButton(
                "Use selected device",
                height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                style=button_style(SUCCESS),
                tooltip="Set the highlighted device as the Bluetooth upload target",
                on_click=lambda _e: bt_picker.upload_bt_use_selected(
                    app,
                    logger=app.logger,
                    settings=app.settings,
                ),
            ),
            ft.OutlinedButton(
                "Close",
                height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                tooltip="Close the device picker without changing the current target",
                on_click=lambda _e: bt_picker.upload_bt_close_picker(app),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=GLOBAL_RADIUS)),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    app.open_bluetooth_picker_dialog = open_dialog
    app.close_bluetooth_picker_dialog = close_dialog
    app.refresh_bluetooth_picker_dialog = refresh_dialog
    app._bt_picker_status_value = ""
    return dialog
