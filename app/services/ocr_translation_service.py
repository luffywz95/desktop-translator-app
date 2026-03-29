from __future__ import annotations

from typing import Any

from utils.ocr_service import extract_text
from utils.translation_service import translate_text as translate_text_service


def run_ocr_then_translate(
    image: Any,
    ocr_langs: str,
    enable_translation: bool,
    target_code: str,
) -> str:
    text = extract_text(image, ocr_langs)
    if text and enable_translation:
        return translate_text_service(text, target_code)
    return text


def run_translate_text(text: str, target_code: str) -> str:
    return translate_text_service(text, target_code)
