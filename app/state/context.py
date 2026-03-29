from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from typing import Any

from utils.logger import Logger as LoggerFactory
from utils.persistence import StorageEngine, default_lang_map, default_settings


@dataclass(slots=True)
class AppContext:
    settings: Any
    lang_map: dict[str, dict[str, Any]]
    logger: Logger


def build_context() -> AppContext:
    state_helper = StorageEngine()
    settings = state_helper.bind("settings", default_settings)
    lang_map = state_helper.bind("lang_map", default_lang_map)
    logger = LoggerFactory().get()
    return AppContext(settings=settings, lang_map=lang_map, logger=logger)
