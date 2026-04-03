from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any

from utils.logger import Logger as LoggerFactory
from utils.persistence import (
    DEFAULT_TARGET_LANG,
    StorageEngine,
    default_lang_map,
    default_settings,
    normalize_theme_mode_setting,
)


@dataclass(slots=True)
class AppContext:
    settings: Any
    lang_map: dict[str, dict[str, Any]]
    logger: Logger
    theme_mode: str


def build_context() -> AppContext:
    state_helper = StorageEngine()
    settings = state_helper.bind("settings", default_settings)
    lang_map = state_helper.bind("lang_map", default_lang_map)
    logger = LoggerFactory().get()
    # Repair bad persisted values (e.g. "current_img" from an earlier lang_map bug).
    tl = settings.get("target_lang")
    if not isinstance(tl, str) or tl not in lang_map:
        settings["target_lang"] = DEFAULT_TARGET_LANG
    tm = normalize_theme_mode_setting(settings.get("theme_mode"))
    if settings.get("theme_mode") != tm:
        settings["theme_mode"] = tm
    return AppContext(settings=settings, lang_map=lang_map, logger=logger, theme_mode=tm)
