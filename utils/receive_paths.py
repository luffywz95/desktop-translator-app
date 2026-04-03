"""Paths under `received/` used by Transfer Hub (utils/server.py) and the Receive tab."""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

RECEIVED_IMAGES_DIR = _PROJECT_ROOT / "received" / "images"
RECEIVED_FILES_DIR = _PROJECT_ROOT / "received" / "files"

IMAGE_EXTENSIONS = frozenset(
    ".jpg .jpeg .png .gif .webp .bmp .tif .tiff .heic .heif .ico .avif".split()
)


def ensure_received_dirs() -> None:
    RECEIVED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    RECEIVED_FILES_DIR.mkdir(parents=True, exist_ok=True)


def list_received_entries() -> list[tuple[str, str, str, float]]:
    """Return rows: (folder_key, filename, full_path, mtime) newest first."""
    ensure_received_dirs()
    rows: list[tuple[str, str, str, float]] = []
    for folder_key, base in (("images", RECEIVED_IMAGES_DIR), ("files", RECEIVED_FILES_DIR)):
        if not base.is_dir():
            continue
        for name in os.listdir(base):
            p = base / name
            if p.is_file():
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                rows.append((folder_key, name, str(p.resolve()), mt))
    rows.sort(key=lambda r: -r[3])
    return rows
