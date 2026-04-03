from __future__ import annotations

from typing import Any

import flet as ft

from app.ui_flet.material_tabs import material_tabs
from app.ui_flet.settings_overlay import build_settings_overlay
from app.ui_flet.convert_image_view import build_convert_image_view
from app.ui_flet.translation_view import build_translation_view
from app.ui_flet.receive_view import build_receive_view
from app.ui_flet.upload_view import build_upload_view
from app.ui_flet.web_crawler_view import build_web_crawler_view
from app.ui_flet.theme import PRIMARY


def build_app_shell(app: Any, page: ft.Page) -> ft.Control:
    translation_view = build_translation_view(app, page)
    upload_view = build_upload_view(app, page)
    receive_view = build_receive_view(app, page)
    convert_view = build_convert_image_view(app, page)
    crawler_view = build_web_crawler_view(app, page)
    settings_overlay, open_settings, _close_settings = build_settings_overlay(app)
    app.open_settings = open_settings
    app.close_settings = _close_settings

    settings_btn = ft.IconButton(
        icon=ft.Icons.SETTINGS,
        icon_color=PRIMARY,
        tooltip="Application settings: Transfer Hub",
        on_click=lambda _e: app.open_settings(),
    )

    pin_btn = ft.IconButton(
        icon=ft.Icons.PUSH_PIN_OUTLINED,
        icon_color=ft.Colors.GREY_600,
        tooltip="Pin window on top of other apps",
    )

    def on_pin_click(_e: ft.ControlEvent) -> None:
        if getattr(page, "web", False):
            return
        page.window.always_on_top = not bool(page.window.always_on_top)
        on = page.window.always_on_top
        pin_btn.icon = ft.Icons.PUSH_PIN if on else ft.Icons.PUSH_PIN_OUTLINED
        pin_btn.icon_color = PRIMARY if on else ft.Colors.GREY_600
        pin_btn.tooltip = "Unpin window (normal stacking)" if on else "Pin window on top of other apps"
        page.update()

    pin_btn.on_click = on_pin_click

    header_trailing: list[ft.Control] = [settings_btn]
    if not getattr(page, "web", False):
        header_trailing.append(pin_btn)

    header = ft.Row(
        [
            ft.Text("The Owl Nexus", size=20, weight=ft.FontWeight.BOLD),
            ft.Row(header_trailing, spacing=4),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    main_tabs = material_tabs(
        labels=["Translation", "Upload", "Receive", "Convert Image", "Web Crawler"],
        panels=[
            ft.Container(expand=True, content=translation_view),
            ft.Container(padding=10, alignment=ft.Alignment(-1, -1), expand=True, content=upload_view),
            ft.Container(padding=10, alignment=ft.Alignment(-1, -1), expand=True, content=receive_view),
            ft.Container(padding=10, alignment=ft.Alignment(-1, -1), expand=True, content=convert_view),
            ft.Container(padding=10, alignment=ft.Alignment(-1, -1), expand=True, content=crawler_view),
        ],
        expand=1,
    )

    return ft.Stack(
        [
            ft.Container(
                expand=True,
                padding=16,
                content=ft.Column(
                    [
                        header,
                        main_tabs,
                    ],
                    expand=True,
                ),
            ),
            settings_overlay,
        ],
        expand=True,
    )
