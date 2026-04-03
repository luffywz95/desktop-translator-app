from __future__ import annotations

import base64
import io
import os
from typing import Any

import flet as ft
from PIL import Image

from app.controllers import convert_image_controller as convert_actions
from app.services.image_convert_service import LOSSY_FORMATS, OUTPUT_FORMATS
from app.ui_flet.adapters.ui_bridge import ButtonProxy, EntryProxy, TextProxy, VarProxy
from app.ui_flet.file_dialogs import schedule_get_directory_path, schedule_pick_files
from app.ui_flet.theme import (
    GLOBAL_RADIUS,
    PRIMARY,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    button_style,
    input_outline_kwargs,
)


class ProgressProxy:
    def __init__(self, control: ft.ProgressBar):
        self.control = control

    def set(self, value: float) -> None:
        self.control.value = max(0.0, min(1.0, float(value)))

    def winfo_exists(self) -> bool:
        return True


def build_convert_image_view(app: Any, page: ft.Page) -> ft.Control:
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

    output_dir_picker = ft.FilePicker()
    queue_picker = ft.FilePicker()

    app._convert_queue = []
    app._convert_thumb_refs = []
    app._convert_format_var = VarProxy(OUTPUT_FORMATS[0])
    app._convert_quality_var = VarProxy(85.0)
    app._convert_strip_metadata_var = VarProxy(False)
    app._convert_cmyk_to_rgb_var = VarProxy(False)
    app._convert_output_folder_var = VarProxy("")
    app._convert_input_summary_var = VarProxy("")

    queue_column = ft.Column([], spacing=6, scroll=ft.ScrollMode.AUTO)
    quality_label = ft.Text("85%")
    quality_slider = ft.Slider(
        min=1,
        max=100,
        value=85,
        tooltip="JPEG/WebP quality (only used for lossy output formats)",
    )

    def update_quality(_e: ft.ControlEvent | None = None) -> None:
        app._convert_quality_var.set(float(quality_slider.value))
        quality_label.value = f"{int(round(float(quality_slider.value)))}%"
        app._safe_page_update()

    quality_slider.on_change = update_quality

    format_dd = ft.Dropdown(
        label="Convert to",
        border_radius=GLOBAL_RADIUS,
        expand=True,
        options=[ft.dropdown.Option(v) for v in OUTPUT_FORMATS],
        value=OUTPUT_FORMATS[0],
        tooltip="Output image format for every file in the queue",
        **input_outline_kwargs(),
    )

    quality_block = ft.Column(
        [
            ft.Row([ft.Text("Quality"), quality_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            quality_slider,
        ],
        spacing=4,
        tight=True,
    )

    def on_format_change(e: ft.ControlEvent) -> None:
        value = (e.data or OUTPUT_FORMATS[0]).upper()
        app._convert_format_var.set(value)
        quality_block.visible = value in LOSSY_FORMATS
        app._safe_page_update()

    format_dd.on_change = on_format_change

    output_tf = ft.TextField(
        label="Output folder",
        border_radius=GLOBAL_RADIUS,
        read_only=True,
        filled=False,
        multiline=False,
        min_lines=1,
        max_lines=1,
        expand=True,
        **input_outline_kwargs(),
    )
    app._convert_output_entry = EntryProxy(output_tf)

    run_btn_control = ft.FilledButton(
        "START CONVERSION",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style("#1f6aa5"),
        disabled=True,
        tooltip="Convert all queued images into the selected format in the output folder",
        on_click=lambda _e: convert_actions.convert_tab_run(app),
    )
    progress_bar = ft.ProgressBar(value=0.0)

    convert_log_tf = ft.TextField(
        label="Log",
        multiline=True,
        min_lines=3,
        max_lines=5,
        read_only=True,
        filled=False,
        border_radius=GLOBAL_RADIUS,
        **input_outline_kwargs(),
    )
    convert_log_tf.value = "[i] Ready. Add files, choose output folder, then start conversion.\n"
    app._convert_log = TextProxy(convert_log_tf)

    app._convert_run_btn = ButtonProxy(run_btn_control)
    app._convert_progress_bar = ProgressProxy(progress_bar)

    def refresh_queue() -> None:
        paths = list(getattr(app, "_convert_queue", []))
        if not paths:
            queue_column.controls = [ft.Text("No file(s) selected (Browse to choose file(s))", color=ft.Colors.GREY_500)]
        else:
            rows = []
            for idx, path in enumerate(paths):
                b64 = _get_thumbnail_b64(path)
                img_control = (
                    ft.Image(src=b64, width=32, height=32, fit=ft.BoxFit.COVER, border_radius=4)
                    if b64 else ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=32, color=ft.Colors.GREY_500)
                )
                rows.append(
                    ft.Row(
                        [
                            img_control,
                            ft.Text(os.path.basename(path), expand=True),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                tooltip="Remove this file from the conversion queue",
                                on_click=lambda _e, i=idx: convert_actions.convert_tab_remove_at(app, i),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )
            queue_column.controls = rows
        app._convert_input_summary_var.set("" if not paths else (os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files selected"))
        out = app._convert_output_folder_var.get().strip()
        app._convert_run_btn.configure(state="normal" if paths and out and os.path.isdir(out) else "disabled")
        app._safe_page_update()

    app._flet_render_convert_queue = refresh_queue

    def on_queue_files(files: list[ft.FilePickerFile]) -> None:
        if not files:
            return
        convert_actions._add_paths_to_queue(app, [f.path for f in files if f.path])

    def on_output_dir(path: str | None) -> None:
        if not path:
            return
        app._convert_output_folder_var.set(path)
        app._convert_output_entry.delete(0, "end")
        app._convert_output_entry.insert(0, path)
        convert_actions.convert_tab_on_output_folder_change(app)
        refresh_queue()

    refresh_queue()

    browse_output_btn = ft.FilledButton(
        "Browse",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Choose the folder where converted files will be written",
        on_click=lambda _e: schedule_get_directory_path(
            page,
            output_dir_picker,
            on_output_dir,
            dialog_title="Output folder",
        ),
    )

    queue_section = ft.Column(
        [
            ft.Text("1. SELECT INPUT (QUEUE)", weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    ft.FilledButton(
                        "Add files...",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        style=button_style(PRIMARY),
                        tooltip="Add images to the batch conversion list",
                        on_click=lambda _e: schedule_pick_files(
                            page,
                            queue_picker,
                            on_queue_files,
                            allow_multiple=True,
                            dialog_title="Add images to convert",
                        ),
                    ),
                    ft.OutlinedButton(
                        "Clear queue",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        tooltip="Remove every file from the conversion list",
                        on_click=lambda _e: convert_actions.convert_tab_clear_queue(app),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=GLOBAL_RADIUS)),
                    ),
                ],
                spacing=8,
                wrap=True,
                run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=GLOBAL_RADIUS,
                padding=8,
                height=220,
                content=queue_column,
            ),
        ],
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    config_section = ft.Column(
        [
            ft.Text("2. CONFIGURE OUTPUT", weight=ft.FontWeight.BOLD),
            format_dd,
            quality_block,
            ft.Checkbox(
                label="Strip metadata",
                value=False,
                tooltip="Remove EXIF and other embedded metadata from outputs",
                on_change=lambda e: app._convert_strip_metadata_var.set(bool(e.control.value)),
            ),
            ft.Checkbox(
                label="Convert CMYK to RGB",
                value=False,
                tooltip="Convert print (CMYK) images to RGB before saving",
                on_change=lambda e: app._convert_cmyk_to_rgb_var.set(bool(e.control.value)),
            ),
        ],
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    output_folder_row = ft.Row(
        [
            ft.Container(
                expand=True,
                content=output_tf,
            ),
            browse_output_btn,
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    process_section = ft.Column(
        [
            ft.Text("3. PROCESS", weight=ft.FontWeight.BOLD),
            output_folder_row,
            convert_log_tf,
        ],
        spacing=10,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    scrollable_content = ft.Column(
        [
            queue_section,
            config_section,
            process_section,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=20,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    bottom_section = ft.Column(
        [
            run_btn_control,
            progress_bar,
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        tight=True,
    )

    body = ft.Column(
        [
            ft.Container(
                expand=True,
                content=scrollable_content,
            ),
            bottom_section,
        ],
        expand=True,
        spacing=16,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    return ft.Container(
        expand=True,
        content=body,
    )
