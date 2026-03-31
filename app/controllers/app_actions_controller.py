from __future__ import annotations

import subprocess
from typing import Any

import pyperclip


def copy_result(app: Any) -> None:
    content = app.result_box.get("1.0", "end-1c")
    if content:
        pyperclip.copy(content)


def open_windows_voice_settings() -> None:
    # Opens "Add a voice" / speech settings on Windows.
    subprocess.Popen("start ms-settings:speech", shell=True)
