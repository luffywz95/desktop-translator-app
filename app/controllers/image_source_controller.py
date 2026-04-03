from __future__ import annotations

import threading
import urllib.error
from logging import Logger
from typing import Any

from PIL import Image, ImageGrab

from app.services.image_source_service import fetch_url_as_image


def load_image_path(
    app: Any,
    path: str,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    try:
        settings["current_img"] = Image.open(path)
        app._clear_choose_fail()
        app.process_image()
    except Exception as e:
        logger.error("Open file failed: %s", e)
        app._show_choose_fail(f"Could not open file: {e}")


def load_image_from_url_async(
    app: Any,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    if not hasattr(app, "url_entry"):
        return
    url = app.url_entry.get().strip()
    if not url:
        app._show_choose_fail("Enter a URL.")
        return

    app.url_load_btn.configure(state="disabled")

    def work() -> None:
        try:
            img = fetch_url_as_image(url)

            def ok() -> None:
                app.url_load_btn.configure(state="normal")
                settings["current_img"] = img
                app._clear_choose_fail()
                app.process_image()

            app.after(0, ok)
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.error("URL image load failed: %s", e)
            err_msg = str(e)

            def fail() -> None:
                app.url_load_btn.configure(state="normal")
                app._show_choose_fail(err_msg)

            app.after(0, fail)
        except Exception as e:
            logger.error("URL image load failed: %s", e)

            def fail2() -> None:
                app.url_load_btn.configure(state="normal")
                app._show_choose_fail(
                    "Could not load image from URL (unsupported format or error)."
                )

            app.after(0, fail2)

    threading.Thread(target=work, daemon=True).start()


def choose_from_clipboard(
    app: Any,
    *,
    settings: dict[str, Any],
) -> None:
    app._hide_url_entry()
    img = ImageGrab.grabclipboard()
    if isinstance(img, Image.Image):
        settings["current_img"] = img
        app._clear_choose_fail()
        app.process_image()
    else:
        app._show_choose_fail("No image in clipboard.")


def handle_paste(
    app: Any,
    event: Any | None = None,
    *,
    settings: dict[str, Any],
) -> None:
    img = ImageGrab.grabclipboard()
    if isinstance(img, Image.Image):
        settings["current_img"] = img
        app.process_image()
        if (
            settings["hotkey_settings"]["background_process_hotkey"]["enable"]
            and app.state() != "normal"
        ):
            app.copy_result()
