from __future__ import annotations

import os
import threading
import urllib.error
from logging import Logger
from tkinter import filedialog
from typing import Any

from PIL import Image, ImageGrab

from app.services.image_source_service import cloud_folder_candidates, fetch_url_as_image


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
        logger.error(f"Open file failed: {e}")
        app._show_choose_fail(f"Could not open file: {e}")


def choose_from_device(
    app: Any,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    app._hide_url_entry()
    path = filedialog.askopenfilename(
        parent=app,
        title="Choose image or file",
        filetypes=[
            ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif"),
            ("All files", "*.*"),
        ],
    )
    if path:
        load_image_path(app, path, settings=settings, logger=logger)


def choose_from_cloud(
    app: Any,
    name: str,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    app._hide_url_entry()
    for d in cloud_folder_candidates(name):
        if os.path.isdir(d):
            path = filedialog.askopenfilename(
                parent=app,
                title=f"Choose from {name}",
                initialdir=d,
                filetypes=[
                    (
                        "Images",
                        "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif",
                    ),
                    ("All files", "*.*"),
                ],
            )
            if path:
                load_image_path(app, path, settings=settings, logger=logger)
            return
    app._show_choose_fail(
        f"{name} folder not found. Install sync or use From device."
    )


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
            logger.error(f"URL image load failed: {e}")
            err_msg = str(e)

            def fail() -> None:
                app.url_load_btn.configure(state="normal")
                app._show_choose_fail(err_msg)

            app.after(0, fail)
        except Exception as e:
            logger.error(f"URL image load failed: {e}")

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


def handle_drop(
    app: Any,
    event: Any,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    try:
        settings["current_img"] = Image.open(event.data.strip("{}"))
        app.process_image()
    except Exception as e:
        logger.error(f"Error handling drop: {e}")
        pass


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
