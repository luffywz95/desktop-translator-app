"""Flet 0.84+ FilePicker: async API wired with page.run_task (do not put FilePicker in page.overlay)."""

from __future__ import annotations

from typing import Any, Callable

import flet as ft


def schedule_pick_files(
    page: ft.Page,
    picker: ft.FilePicker,
    on_files: Callable[[list[ft.FilePickerFile]], None],
    **kwargs: Any,
) -> None:
    async def _run() -> None:
        files = await picker.pick_files(**kwargs)
        on_files(files or [])

    page.run_task(_run)


def schedule_get_directory_path(
    page: ft.Page,
    picker: ft.FilePicker,
    on_path: Callable[[str | None], None],
    *,
    dialog_title: str | None = None,
) -> None:
    async def _run() -> None:
        path = await picker.get_directory_path(dialog_title=dialog_title)
        on_path(path)

    page.run_task(_run)
