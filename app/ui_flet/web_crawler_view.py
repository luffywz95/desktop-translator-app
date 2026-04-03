from __future__ import annotations

from typing import Any

import flet as ft

from app.controllers import web_crawler_controller as crawler_actions
from app.ui_flet.adapters.ui_bridge import ButtonProxy, EntryProxy, TextProxy, VarProxy
from app.ui_flet.file_dialogs import schedule_get_directory_path
from app.ui_flet.theme import (
    GLOBAL_RADIUS,
    PRIMARY,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    button_style,
    input_outline_kwargs,
)


def build_web_crawler_view(app: Any, page: ft.Page) -> ft.Control:
    folder_picker = ft.FilePicker()

    app._web_crawler_fields = []
    app._web_crawler_proc = None
    app._web_crawler_last_output = ""
    app._web_crawler_last_count = 0
    app._web_crawler_compact = False

    target_tf = ft.TextField(
        label="Target URL",
        hint_text="e.g. mysite.com",
        border_radius=GLOBAL_RADIUS,
        expand=True,
        tooltip="Starting page for the crawl (domain/path Scrapy will begin from)",
        **input_outline_kwargs(),
    )
    start_btn = ft.FilledButton(
        "START SPIDER",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Begin crawling with the current strategy, fields, and project folder",
        on_click=lambda _e: crawler_actions.web_crawler_start(app, app.logger),
    )

    app.web_crawler_target_entry = EntryProxy(target_tf)
    app.web_crawler_start_btn = ButtonProxy(start_btn)

    app.web_crawler_static_var = VarProxy(True)
    app.web_crawler_js_var = VarProxy(False)
    app.web_crawler_delay_var = VarProxy(True)
    app.web_crawler_robots_var = VarProxy(True)
    app.web_crawler_ignore_images_var = VarProxy(True)
    app.web_crawler_readiness_var = VarProxy("Smart Wait (Wait for Network)")
    app.web_crawler_format_var = VarProxy("CSV")

    wait_selector_tf = ft.TextField(
        label="Wait Selector",
        border_radius=GLOBAL_RADIUS,
        tooltip="CSS selector to wait for when readiness is “Wait for Element…”",
        **input_outline_kwargs(),
    )
    app.web_crawler_wait_selector_entry = EntryProxy(wait_selector_tf)

    project_name_tf = ft.TextField(
        label="Project name",
        value="NewProject_01",
        border_radius=GLOBAL_RADIUS,
        tooltip="Subfolder name under Location for this crawl’s files",
        **input_outline_kwargs(),
    )
    project_location_tf = ft.TextField(
        label="Location",
        value="./crawls/",
        border_radius=GLOBAL_RADIUS,
        expand=True,
        tooltip="Base directory for crawl output (Browse to change)",
        **input_outline_kwargs(),
    )
    app.web_crawler_project_name_entry = EntryProxy(project_name_tf)
    app.web_crawler_project_location_entry = EntryProxy(project_location_tf)

    def on_dir_chosen(path: str | None) -> None:
        if not path:
            return
        app.web_crawler_project_location_entry.delete(0, "end")
        app.web_crawler_project_location_entry.insert(0, path)
        app._safe_page_update()

    browse_btn = ft.FilledButton(
        "Browse",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Pick the folder where crawl logs and extracted data are stored",
        on_click=lambda _e: schedule_get_directory_path(
            page,
            folder_picker,
            on_dir_chosen,
            dialog_title="Choose crawler output folder",
        ),
    )
    app.web_crawler_browse_btn = ButtonProxy(browse_btn)

    fields_column = ft.Column([], spacing=6)

    def render_fields() -> None:
        rows: list[ft.Control] = []
        for row in app._web_crawler_fields:
            rows.append(
                ft.Row(
                    [
                        row["name_entry"].control,
                        row["selector_entry"].control,
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="Remove this extract field from the item schema",
                            on_click=lambda _e, r=row: crawler_actions.web_crawler_remove_field(app, r),
                        ),
                    ]
                )
            )
        fields_column.controls = rows
        app._safe_page_update()

    app._flet_render_web_fields = render_fields

    log_tf = ft.TextField(
        multiline=True,
        min_lines=5,
        max_lines=8,
        read_only=True,
        border_radius=GLOBAL_RADIUS,
        **input_outline_kwargs(),
    )
    log_tf.value = "[i] Ready to crawl.\n"
    app.web_crawler_log = TextProxy(log_tf)

    log_box = ft.Column(
        [
            ft.Text("Process Log", weight=ft.FontWeight.BOLD),
            log_tf,
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    export_btn = ft.FilledButton(
        "EXPORT DATA",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Write the last crawl results to CSV or JSON on disk",
        on_click=lambda _e: crawler_actions.web_crawler_export_last(app),
    )
    view_btn = ft.FilledButton(
        "VIEW ITEMS (0)",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Open a scrollable preview of extracted records from the last crawl",
        on_click=lambda _e: crawler_actions.web_crawler_view_items(app),
    )
    app.web_crawler_export_btn = ButtonProxy(export_btn)
    app.web_crawler_view_btn = ButtonProxy(view_btn)

    readiness_dd = ft.Dropdown(
        label="Readiness",
        border_radius=GLOBAL_RADIUS,
        value=app.web_crawler_readiness_var.get(),
        tooltip="How long Playwright waits before scraping each page (HTML-only vs JS vs custom selector)",
        options=[
            ft.dropdown.Option("Basic (HTML Only)"),
            ft.dropdown.Option("Smart Wait (Wait for Network)"),
            ft.dropdown.Option("Wait for Element..."),
        ],
        **input_outline_kwargs(),
    )
    readiness_dd.on_change = lambda e: app.web_crawler_readiness_var.set(e.data)

    format_dd = ft.Dropdown(
        label="Results format",
        border_radius=GLOBAL_RADIUS,
        value="CSV",
        tooltip="File format used when you export or view crawl results",
        options=[ft.dropdown.Option("CSV"), ft.dropdown.Option("JSON")],
        **input_outline_kwargs(),
    )
    format_dd.on_change = lambda e: app.web_crawler_format_var.set(e.data)

    crawler_actions.web_crawler_add_field(app, "product_name", "h1.product-title::text")
    crawler_actions.web_crawler_add_field(app, "price", "span.price-current::text")
    crawler_actions.web_crawler_add_field(app, "description", "div#product-desc > p::text")

    top_bar = ft.Row(
        [target_tf, start_btn],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    scrollable_content = ft.Column(
        [
            ft.Container(
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=GLOBAL_RADIUS,
                padding=10,
                content=ft.Column(
                    [
                        ft.Text("Crawl Strategy", weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Checkbox(
                                    label="Static HTML (Fast)",
                                    value=True,
                                    tooltip="Fetch pages without a full browser (faster; no JavaScript execution)",
                                    on_change=lambda e: (app.web_crawler_static_var.set(bool(e.control.value)), app.web_crawler_js_var.set(not bool(e.control.value))),
                                ),
                                ft.Checkbox(
                                    label="JS-Rendered",
                                    value=False,
                                    tooltip="Use Playwright so pages that need JavaScript can render before scrape",
                                    on_change=lambda e: (app.web_crawler_js_var.set(bool(e.control.value)), app.web_crawler_static_var.set(not bool(e.control.value))),
                                ),
                            ]
                        ),
                        readiness_dd,
                        wait_selector_tf,
                    ]
                ),
            ),
            ft.Container(
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=GLOBAL_RADIUS,
                padding=10,
                content=ft.Column(
                    [
                        ft.Text("Project Settings", weight=ft.FontWeight.BOLD),
                        project_name_tf,
                        ft.Row(
                            [project_location_tf, browse_btn],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                ft.Checkbox(
                                    label="Download Delay (2s)",
                                    value=True,
                                    tooltip="Pause ~2 seconds between requests to reduce load on the target site",
                                    on_change=lambda e: app.web_crawler_delay_var.set(bool(e.control.value)),
                                ),
                                ft.Checkbox(
                                    label="Respect robots.txt",
                                    value=True,
                                    tooltip="Follow robots.txt rules when discovering URLs",
                                    on_change=lambda e: app.web_crawler_robots_var.set(bool(e.control.value)),
                                ),
                                ft.Checkbox(
                                    label="Ignore Image URLs",
                                    value=True,
                                    tooltip="Do not enqueue .jpg/.png/etc. links as crawl targets",
                                    on_change=lambda e: app.web_crawler_ignore_images_var.set(bool(e.control.value)),
                                ),
                            ],
                            wrap=True,
                        ),
                    ]
                ),
            ),
            ft.Container(
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=GLOBAL_RADIUS,
                padding=10,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Item Field Definition", weight=ft.FontWeight.BOLD),
                                ft.FilledButton(
                                    "ADD NEW FIELD",
                                    style=button_style(PRIMARY),
                                    tooltip="Add another name + CSS selector pair for extracted item data",
                                    on_click=lambda _e: crawler_actions.web_crawler_add_field(app, "", ""),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        fields_column,
                    ]
                ),
            ),
            log_box,
            ft.Row(
                [
                    format_dd,
                    export_btn,
                    view_btn,
                ],
                alignment=ft.MainAxisAlignment.END,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=10,
    )

    return ft.Column(
        [
            top_bar,
            scrollable_content,
        ],
        expand=True,
        spacing=10,
    )
