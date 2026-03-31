from __future__ import annotations

import threading
from logging import Logger
from typing import Any, Mapping

from PIL import ImageTk

from app.services.ocr_translation_service import run_ocr_then_translate, run_translate_text
from app.services.speech_service import speech_worker


def process_image(
    app: Any,
    *,
    settings: Mapping[str, Any],
    lang_map: Mapping[str, Any],
) -> None:
    if not settings["current_img"]:
        return
    app.result_box.delete("1.0", "end")
    app.result_box.insert("1.0", "⚙️ Processing...")
    thumb = settings["current_img"].copy()
    thumb.thumbnail((500, 220))
    # Keep a strong reference to avoid Tk image GC glitches.
    app.display_img = ImageTk.PhotoImage(thumb)
    app.img_zone.configure(image=app.display_img, text="")
    threading.Thread(
        target=lambda: ocr_worker(app, settings=settings, lang_map=lang_map),
        daemon=True,
    ).start()


def ocr_worker(app: Any, *, settings: Mapping[str, Any], lang_map: Mapping[str, Any]) -> None:
    try:
        text = run_ocr_then_translate(
            image=settings["current_img"],
            ocr_langs=settings["ocr_langs"],
            enable_translation=bool(settings["enable_translation"]),
            target_code=lang_map[settings["target_lang"]]["trans_lang"],
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
        logger.error(f"Translation Setup Error: {e}")


def translation_worker(
    app: Any,
    text: str,
    *,
    settings: Mapping[str, Any],
    lang_map: Mapping[str, Any],
    logger: Logger,
) -> None:
    try:
        target_lang = settings["target_lang"]
        target_code = lang_map[target_lang]["trans_lang"]
        translation_result = run_translate_text(text, target_code)
        app.after(0, lambda: app._update_results(translation_result))
    except Exception as e:
        logger.error(f"Translation Error: {e}")
        app.after(0, lambda msg=str(e): app._update_results(f"Translation Error: {msg}"))


def toggle_speech(app: Any, *, settings: Mapping[str, Any], logger: Logger) -> None:
    text = app.result_box.get("1.0", "end-1c").strip()
    if not text or app.is_speaking:
        # Stop behavior is intentionally unchanged.
        return

    threading.Thread(
        target=speech_worker,
        args=(app, text),
        kwargs={"settings": settings, "logger": logger},
        daemon=True,
    ).start()
