"""OCR feature service for the Image tab."""

from __future__ import annotations

from PIL import Image, ImageOps
import pytesseract


def extract_text(image: Image.Image, ocr_langs: str, psm: str = "--psm 6") -> str:
    """Run OCR and return extracted text."""
    processed = ImageOps.autocontrast(image.convert("L"))
    return pytesseract.image_to_string(processed, lang=ocr_langs, config=psm).strip()
