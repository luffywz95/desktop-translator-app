from __future__ import annotations

import threading
from logging import Logger
from typing import Any, Mapping

from app.services.ocr_translation_service import run_ocr_then_translate, run_translate_text
from app.services.speech_service import speech_worker
from utils.persistence import DEFAULT_TARGET_LANG


def _resolved_target_lang(settings: Mapping[str, Any], lang_map: Mapping[str, Any]) -> str:
    tl = settings.get("target_lang")
    if isinstance(tl, str) and tl in lang_map:
        return tl
    return DEFAULT_TARGET_LANG


def ocr_worker(app: Any, *, settings: Mapping[str, Any], lang_map: Mapping[str, Any]) -> None:
    try:
        target_lang = _resolved_target_lang(settings, lang_map)
        text = run_ocr_then_translate(
            image=settings["current_img"],
            ocr_langs=settings["ocr_langs"],
            enable_translation=bool(settings["enable_translation"]),
            target_code=lang_map[target_lang]["trans_lang"],
        )
        app.after(0, lambda: app._update_results(text))
    except Exception as e:
        app.after(0, lambda msg=str(e): app.result_box.insert("end", f"\nError: {msg}"))


def translate_text(
    app: Any,
    *,
    settings: Mapping[str, Any],
    lang_map: Mapping[str, Any],
    logger: Logger,
) -> None:
    try:
        text = app.trans_text_editor.get("1.0", "end")
        if not text:
            return

        if not settings["enable_translation"]:
            app.after(0, lambda: app._update_results(text))
            return

        app.result_box.delete("1.0", "end")
        app.result_box.insert("1.0", "🌐 Translating...")

        threading.Thread(
            target=lambda: translation_worker(
                app,
                text,
                settings=settings,
                lang_map=lang_map,
                logger=logger,
            ),
            daemon=True,
        ).start()
    except Exception as e:
        logger.error("Translation Setup Error: %s", e)


def translation_worker(
    app: Any,
    text: str,
    *,
    settings: Mapping[str, Any],
    lang_map: Mapping[str, Any],
    logger: Logger,
) -> None:
    try:
        target_lang = _resolved_target_lang(settings, lang_map)
        target_code = lang_map[target_lang]["trans_lang"]
        translation_result = run_translate_text(text, target_code)
        app.after(0, lambda: app._update_results(translation_result))
    except Exception as e:
        logger.error("Translation Error: %s", e)
        app.after(0, lambda msg=str(e): app._update_results(f"Translation Error: {msg}"))


def toggle_speech(app: Any, *, settings: Mapping[str, Any], logger: Logger) -> None:
    text = app.result_box.get("1.0", "end-1c").strip()
    if not text or app.is_speaking:
        return

    threading.Thread(
        target=speech_worker,
        args=(app, text),
        kwargs={"settings": settings, "logger": logger},
        daemon=True,
    ).start()
