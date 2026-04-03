"""Flet 0.84+ tabs: TabBar labels + TabBarView panels (legacy Tab(text=, content=) removed)."""

from __future__ import annotations

from typing import Any

import flet as ft


def material_tabs(
    *,
    labels: list[str],
    panels: list[ft.Control],
    expand: int | bool | None = 1,
    animation_duration: ft.Duration | None = None,
    **tabs_kwargs: Any,
) -> ft.Tabs:
    if len(labels) != len(panels):
        raise ValueError("labels and panels must have the same length")
    n = len(labels)
    col = ft.Column(
        [
            ft.TabBar(tabs=[ft.Tab(label=lb) for lb in labels]),
            ft.TabBarView(expand=1, controls=panels),
        ],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    kw: dict[str, Any] = {"length": n, "content": col, "expand": expand, **tabs_kwargs}
    if animation_duration is not None:
        kw["animation_duration"] = animation_duration
    return ft.Tabs(**kw)
