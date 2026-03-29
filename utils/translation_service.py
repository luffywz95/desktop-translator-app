"""Text translation feature service for the Text tab."""

from __future__ import annotations

from deep_translator import GoogleTranslator


def translate_text(text: str, target_code: str) -> str:
    """Translate plain text into target language code."""
    return GoogleTranslator(source="auto", target=target_code).translate(text)
