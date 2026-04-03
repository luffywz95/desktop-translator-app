from __future__ import annotations

from pathlib import Path

import flet as ft

_APP_DIR = Path(__file__).resolve().parent
_WINDOW_ICON = _APP_DIR / "assets" / "icon.ico"

from app.bootstrap import setup_application_environment
from app.state.context import build_context
from app.ui_flet import build_app_shell
from app.ui_flet.adapters import FletAppBridge
from app.ui_flet.theme import (
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    PRIMARY,
    build_theme,
    theme_mode_from_setting,
)
from app.ui_flet.win32_file_drop import schedule_win32_shell_file_drop, uninstall_win32_shell_file_drop


def _apply_flet_compat_shims() -> None:
    # Keep runtime stable across minor API differences.
    original_filled_button = ft.FilledButton
    original_outlined_button = ft.OutlinedButton
    original_tab = ft.Tab
    original_file_picker = ft.FilePicker
    original_dropdown = ft.Dropdown

    def filled_button_compat(*args, **kwargs):
        if "text" in kwargs and "content" not in kwargs:
            kwargs["content"] = kwargs.pop("text")
        return original_filled_button(*args, **kwargs)

    def outlined_button_compat(*args, **kwargs):
        if "text" in kwargs and "content" not in kwargs:
            kwargs["content"] = kwargs.pop("text")
        return original_outlined_button(*args, **kwargs)

    def tab_compat(*args, **kwargs):
        if "content" in kwargs:
            raise TypeError(
                "flet.Tab no longer accepts 'content'. Use app.ui_flet.material_tabs.material_tabs "
                "or compose ft.TabBar + ft.TabBarView."
            )
        if "text" in kwargs and "label" not in kwargs:
            kwargs["label"] = kwargs.pop("text")
        return original_tab(*args, **kwargs)

    def file_picker_compat(*args, **kwargs):
        # Legacy callback API removed in modern Flet; use file_dialogs.schedule_* + run_task.
        kwargs.pop("on_result", None)
        return original_file_picker(*args, **kwargs)

    def dropdown_compat(*args, **kwargs):
        on_change = kwargs.pop("on_change", None)
        control = original_dropdown(*args, **kwargs)
        if on_change is not None:
            if hasattr(control, "on_change"):
                control.on_change = on_change
            elif hasattr(control, "on_select"):
                control.on_select = on_change
        return control

    ft.FilledButton = filled_button_compat
    ft.OutlinedButton = outlined_button_compat
    ft.Tab = tab_compat
    ft.FilePicker = file_picker_compat
    ft.Dropdown = dropdown_compat


_apply_flet_compat_shims()


def _before_main(page: ft.Page) -> None:
    """Apply native window size and icon before `main()` so the first paint avoids defaults."""
    if getattr(page, "web", False):
        return
    if _WINDOW_ICON.is_file():
        page.window.icon = str(_WINDOW_ICON)
    page.window.min_width = MIN_WINDOW_WIDTH
    page.window.min_height = MIN_WINDOW_HEIGHT
    page.window.width = MIN_WINDOW_WIDTH
    page.window.height = MIN_WINDOW_HEIGHT


def main(page: ft.Page) -> None:
    context = build_context()
    page.title = "The Owl Nexus"
    page.theme_mode = theme_mode_from_setting(context.theme_mode)
    page.theme = build_theme(PRIMARY)
    page.padding = 0

    app = FletAppBridge(
        page,
        settings=context.settings,
        lang_map=context.lang_map,
        logger=context.logger,
    )
    shell = build_app_shell(app, page)
    page.add(shell)
    page.window.on_event = app._on_window_event
    page.on_keyboard_event = app._on_page_keyboard_event
    app._ensure_transfer_hub_running()

    def _on_shell_paths_dropped(paths: list[str]) -> None:
        if not paths:
            return
        if len(paths) == 1:
            app.load_image_path(paths[0])
            return
        from app.controllers import convert_image_controller as convert_actions

        convert_actions._add_paths_to_queue(app, paths)
        renderer = getattr(app, "_flet_render_convert_queue", None)
        if callable(renderer):
            renderer()

    schedule_win32_shell_file_drop(page, app, _on_shell_paths_dropped)

    def _on_session_end(_e: ft.ControlEvent | None = None) -> None:
        uninstall_win32_shell_file_drop()
        stop_cf = getattr(app, "_stop_cloudflare_quick_tunnel", None)
        if callable(stop_cf):
            try:
                stop_cf()
            except Exception:
                pass
        stop_recv = getattr(app, "_stop_receive_folder_watcher", None)
        if callable(stop_recv):
            try:
                stop_recv()
            except Exception:
                pass
        app._stop_transfer_hub_session()

    page.on_disconnect = _on_session_end
    page.on_close = _on_session_end


def run_flet_app() -> None:
    setup_application_environment()
    ft.run(main=main, before_main=_before_main)


if __name__ == "__main__":
    run_flet_app()
