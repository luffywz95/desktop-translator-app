from __future__ import annotations

from typing import Any

import flet as ft

from app.ui_flet.adapters.ui_bridge import (
    ButtonProxy,
    EntryProxy,
    HotkeyRowProxy,
    LabelProxy,
    TextProxy,
    VarProxy,
)
from app.controllers import image_source_controller as image_actions
from app.ui_flet.file_dialogs import schedule_pick_files
from app.ui_flet.material_tabs import material_tabs
from app.ui_flet.theme import (
    ACCENT,
    GLOBAL_RADIUS,
    PRIMARY,
    TRANSLATION_ACTION_BUTTON_HEIGHT,
    TRANSLATION_RESULT_VISIBLE_LINES,
    button_style,
    input_outline_kwargs,
    result_box_outline_kwargs,
)


def build_translation_view(app: Any, page: ft.Page) -> ft.Control:
    app.trans_cb_main = ft.Checkbox(
        label="Translate to:",
        value=bool(app.settings["enable_translation"]),
        tooltip="After OCR, translate extracted text into the language selected below",
        on_change=app._sync_trans_state,
    )

    app.lang_menu_main = ft.Dropdown(
        value=app.settings["target_lang"],
        options=[ft.dropdown.Option(k) for k in app.lang_map.keys()],
        border_radius=GLOBAL_RADIUS,
        expand=True,
        tooltip="Target language for translation and for picking a matching TTS voice",
        on_focus=app._disarm_paste_image_shortcut,
        **input_outline_kwargs(),
    )
    app.lang_menu_main.on_select = app._sync_lang_state

    image_status_text = ft.Text("", color=ft.Colors.RED_400, visible=False)
    app.choose_fail_label = LabelProxy(image_status_text)

    app.img_zone = ft.Container(
        content=ft.Text(app.placeholder_text, color=ft.Colors.GREY_500),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.BLUE_GREY),
        border_radius=15,
        alignment=ft.Alignment(0, 0),
        expand=True,
        padding=10,
    )
    img_zone_gesture = ft.GestureDetector(
        content=app.img_zone,
        expand=True,
        on_tap=app._arm_paste_image_shortcut,
        mouse_cursor=ft.MouseCursor.CLICK,
        tooltip=(
            "Click here, then paste an image (Ctrl+V). "
            "On Windows desktop, drag files from File Explorer onto the window."
        ),
    )

    file_picker = ft.FilePicker()

    def on_picked_files(files: list[ft.FilePickerFile]) -> None:
        if not files:
            return
        path = files[0].path
        if path:
            app.load_image_path(path)
        app._safe_page_update()

    url_entry = ft.TextField(
        hint_text="https://example.com/image.png",
        border_radius=GLOBAL_RADIUS,
        expand=True,
        on_focus=app._disarm_paste_image_shortcut,
        **input_outline_kwargs(),
    )
    app.url_entry = EntryProxy(url_entry)
    load_btn = ft.FilledButton(
        "Load",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Load image from the URL above",
    )
    def open_image_from_local(_e: ft.ControlEvent | None = None) -> None:
        schedule_pick_files(
            page,
            file_picker,
            on_picked_files,
            allow_multiple=False,
            dialog_title="Choose image or file",
        )

    def on_from_clipboard(_e: ft.ControlEvent | None) -> None:
        image_actions.choose_from_clipboard(app, settings=app.settings)
        app._safe_page_update()

    _split_rl = ft.BorderRadius.only(
        top_left=GLOBAL_RADIUS,
        bottom_left=GLOBAL_RADIUS,
        top_right=0,
        bottom_right=0,
    )
    _split_rr = ft.BorderRadius.only(
        top_left=0,
        bottom_left=0,
        top_right=GLOBAL_RADIUS,
        bottom_right=GLOBAL_RADIUS,
    )
    choose_main_btn = ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.NOTE_ADD, color=ft.Colors.WHITE, size=20),
                ft.Text("Choose file", color=ft.Colors.WHITE),
            ],
            spacing=8,
            tight=True,
        ),
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=ft.ButtonStyle(
            bgcolor=PRIMARY,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=_split_rl),
            padding=ft.padding.symmetric(horizontal=14, vertical=8),
        ),
        tooltip="Pick an image or document file from disk (same as From Local)",
        on_click=lambda _e: open_image_from_local(_e),
    )
    image_source_menu = ft.PopupMenuButton(
        icon=ft.Icons.ARROW_DROP_DOWN,
        icon_size=20,
        icon_color=ft.Colors.WHITE,
        bgcolor=PRIMARY,
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        padding=0,
        style=ft.ButtonStyle(
            bgcolor=PRIMARY,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=_split_rr),
            padding=ft.padding.symmetric(horizontal=4, vertical=8),
        ),
        menu_position=ft.PopupMenuPosition.UNDER,
        tooltip="Other ways to load an image",
        items=[
            ft.PopupMenuItem(
                content="From Local",
                on_click=lambda _e: open_image_from_local(_e),
            ),
            ft.PopupMenuItem(
                content="From Clipboard",
                on_click=lambda _e: on_from_clipboard(_e),
            ),
            ft.PopupMenuItem(
                content="From URL",
                on_click=lambda _e: app._show_url_entry(),
            ),
        ],
    )
    choose_split_row = ft.Row(
        [choose_main_btn, image_source_menu],
        spacing=0,
        tight=True,
    )

    app.url_load_btn = ButtonProxy(load_btn)
    app.url_row = ft.Row(
        [url_entry, load_btn],
        visible=False,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    process_btn_control = ft.FilledButton(
        "Process",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Run OCR on the loaded image",
        on_click=lambda _e: app.process_image(),
        disabled=True,
    )
    app.process_btn = ButtonProxy(process_btn_control)

    reset_btn_control = ft.FilledButton(
        "Reset",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style("#e74c3c"),
        tooltip="Clear image, URL row, and OCR results",
        on_click=lambda _e: app.clear_all(),
    )

    _res_lines = TRANSLATION_RESULT_VISIBLE_LINES
    result_tf = ft.TextField(
        multiline=True,
        min_lines=_res_lines,
        max_lines=_res_lines,
        border_radius=GLOBAL_RADIUS,
        expand=True,
        tooltip="OCR result from the loaded image; use Copy to place it on the clipboard",
        on_focus=app._disarm_paste_image_shortcut,
        **result_box_outline_kwargs(),
    )
    app.result_box = TextProxy(result_tf)

    copy_btn_control = ft.IconButton(
        icon=ft.Icons.CONTENT_COPY,
        tooltip="Copy result",
        on_click=lambda _e: app.copy_result(),
        disabled=True,
    )
    app.copy_btn = ButtonProxy(copy_btn_control)

    app.voice_menu_main = ft.Dropdown(
        border_radius=GLOBAL_RADIUS,
        expand=True,
        tooltip="Text-to-speech voice used when you click Speak",
        on_focus=app._disarm_paste_image_shortcut,
        **input_outline_kwargs(),
    )
    app.voice_var_main = VarProxy("")
    app._refresh_voice_choices()

    voice_btn_control = ft.FilledButton(
        "Speak",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(ACCENT),
        tooltip="Read OCR text aloud with the selected voice",
        on_click=lambda _e: app.toggle_speech(),
        disabled=True,
    )
    app.voice_btn = ButtonProxy(voice_btn_control)

    text_editor_tf = ft.TextField(
        multiline=True,
        min_lines=4,
        max_lines=None,
        border_radius=GLOBAL_RADIUS,
        expand=True,
        fit_parent_size=True,
        collapsed=True,
        tooltip="Edit or paste text here, then use Translate for the target language",
        on_focus=app._disarm_paste_image_shortcut,
        **input_outline_kwargs(),
    )
    app.trans_text_editor = TextProxy(text_editor_tf)

    translate_btn = ft.FilledButton(
        "Translate",
        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
        style=button_style(PRIMARY),
        tooltip="Translate the text in the editor using the target language above",
        on_click=lambda _e: app.translate_text(),
    )

    load_btn.on_click = lambda _e: app._load_image_from_url_async()

    image_panel = ft.Container(
        padding=10,
        alignment=ft.Alignment(-1, -1),
        expand=True,
        content=ft.Column(
            [
                image_status_text,
                img_zone_gesture,
                app.url_row,
                ft.Row(
                    [
                        choose_split_row,
                        ft.Container(expand=True),
                        ft.Row(
                            [process_btn_control, reset_btn_control],
                            spacing=8,
                            tight=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            expand=True,
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )
    # Keep Translate outside any scroll: editor expands and scrolls inside the field; button stays visible.
    text_panel = ft.Container(
        padding=10,
        alignment=ft.Alignment(-1, -1),
        expand=True,
        content=ft.Column(
            [
                text_editor_tf,
                ft.Row(
                    [translate_btn],
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                ),
            ],
            expand=True,
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )

    nested_tabs = material_tabs(
        labels=["Image", "Text"],
        panels=[image_panel, text_panel],
        expand=1,
        animation_duration=ft.Duration(milliseconds=200),
    )

    app.voice_var_main.trace_add(
        "write",
        lambda _a, _b, _c: None,
    )

    # Settings controller compatibility placeholders for Phase 1.
    app.application_invoke_hotkey_row = HotkeyRowProxy(
        key_input=EntryProxy(ft.TextField(value="q", border_radius=GLOBAL_RADIUS, **input_outline_kwargs())),
        enabled_var=VarProxy(True),
    )
    app.background_process_hotkey_row = HotkeyRowProxy(
        key_input=EntryProxy(ft.TextField(value="x", border_radius=GLOBAL_RADIUS, **input_outline_kwargs())),
        enabled_var=VarProxy(bool(app.settings["hotkey_settings"]["background_process_hotkey"]["enable"])),
    )
    app.dim_var = VarProxy(bool(app.settings["enable_focus_dim"]))
    app.opacity_val = VarProxy(float(app.settings["idle_opacity"]))
    app.receive_file_var = VarProxy(bool(app._normalized_receive_file()["enable"]))
    app.upload_file_var = VarProxy(bool(app._normalized_upload_file()["enable"]))
    app.receive_file_port_var = VarProxy(str(app._normalized_receive_file()["port"]))
    app.upload_file_port_var = VarProxy(str(app._normalized_upload_file()["port"]))
    app.upload_tab_url_entry = EntryProxy(
        ft.TextField(
            value=app._normalized_upload_file()["remote_url"],
            border_radius=GLOBAL_RADIUS,
            **input_outline_kwargs(),
        )
    )
    app.upload_tab_token_entry = EntryProxy(
        ft.TextField(
            value=app._normalized_upload_file()["remote_token"],
            border_radius=GLOBAL_RADIUS,
            **input_outline_kwargs(),
        )
    )

    # Top (tabs + Image/Text + translate row) grows; result stays above voice; voice row at bottom.
    translate_options_row = ft.Row(
        [app.trans_cb_main, app.lang_menu_main],
        alignment=ft.MainAxisAlignment.START,
    )
    # Do not expand this row vertically: only the block above (tabs + input) should grow.
    result_row = ft.Row(
        [result_tf, copy_btn_control],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    voice_row = ft.Row(
        [app.voice_menu_main, voice_btn_control],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return ft.Column(
        [
            ft.Container(
                expand=True,
                content=ft.Column(
                    [nested_tabs, translate_options_row],
                    expand=True,
                    spacing=10,
                    alignment=ft.MainAxisAlignment.START,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            result_row,
            voice_row,
        ],
        expand=True,
        spacing=10,
        alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
