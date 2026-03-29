from __future__ import annotations

import os
import urllib.request
from io import BytesIO

from PIL import Image


def cloud_folder_candidates(name: str) -> list[str]:
    home = os.path.expanduser("~")
    if name == "Dropbox":
        return [os.path.join(home, "Dropbox")]
    if name == "Google Drive":
        return [
            os.path.join(home, "Google Drive"),
            os.path.join(home, "My Drive"),
        ]
    if name == "OneDrive":
        return [os.path.join(home, "OneDrive")]
    return []


def fetch_url_as_image(url: str) -> Image.Image:
    normalized = url.strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized

    request = urllib.request.Request(
        normalized,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TheOwlTranslator/1.0)"},
    )

    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()

    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Download too large (max 25 MB).")

    image = Image.open(BytesIO(data))
    image.load()
    return image
