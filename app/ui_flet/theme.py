from __future__ import annotations

from typing import Any

import flet as ft

from utils.persistence import normalize_theme_mode_setting

PRIMARY = "#3498db"
SUCCESS = "#2ecc71"
ACCENT = "#9b59b6"
BUTTON_HOVER = "#1f6aa5"
GLOBAL_RADIUS = 10
FONT_FAMILY = "Segoe UI"

# Desktop window floor — matches a comfortable Translation layout; prevents Convert tab overlap.
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 660

# Translation tab: OCR / translate output height (fixed; input area takes remaining vertical space).
TRANSLATION_RESULT_VISIBLE_LINES = 5

# Height for Choose file split, Process, Reset, Translate, Speak, Load (keeps rows visually aligned).
TRANSLATION_ACTION_BUTTON_HEIGHT = 40.0

# Unfocused inputs in M3 can look borderless; very light blue outline (matches PRIMARY family).
INPUT_OUTLINE_COLOR = "#ddeef6"
INPUT_OUTLINE_WIDTH = 1.0
INPUT_FOCUSED_OUTLINE_WIDTH = 1.5


def input_outline_kwargs(*, focused_color: str | None = None) -> dict[str, Any]:
    """Border styling for TextField, Dropdown, and similar form controls."""
    return {
        "border": ft.InputBorder.OUTLINE,
        "border_width": INPUT_OUTLINE_WIDTH,
        "border_color": INPUT_OUTLINE_COLOR,
        "focused_border_width": INPUT_FOCUSED_OUTLINE_WIDTH,
        "focused_border_color": focused_color or PRIMARY,
    }


# Translation result (OCR) box — neutral light gray frame, distinct from input fields.
RESULT_BOX_BORDER_COLOR = "#cfd4da"


def result_box_outline_kwargs() -> dict[str, Any]:
    return {
        "border": ft.InputBorder.OUTLINE,
        "border_width": 1.0,
        "border_color": RESULT_BOX_BORDER_COLOR,
        "focused_border_width": INPUT_FOCUSED_OUTLINE_WIDTH,
        "focused_border_color": PRIMARY,
    }


def theme_mode_from_setting(value: object) -> ft.ThemeMode:
    return ft.ThemeMode(normalize_theme_mode_setting(value))


def build_theme(seed: str = PRIMARY) -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=seed,
        font_family=FONT_FAMILY,
    )


def button_style(bgcolor: str = PRIMARY) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={
            ft.ControlState.DEFAULT: bgcolor,
            ft.ControlState.DISABLED: ft.Colors.GREY_800,
        },
        color={
            ft.ControlState.DEFAULT: ft.Colors.WHITE,
            ft.ControlState.DISABLED: ft.Colors.GREY_500,
        },
        shape=ft.RoundedRectangleBorder(radius=GLOBAL_RADIUS),
    )
