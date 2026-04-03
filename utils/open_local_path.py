"""Open a file with the OS default application (desktop)."""

from __future__ import annotations

import os
import subprocess
import sys


def open_local_path(path: str) -> None:
    path = os.path.normpath(path)
    if not path or not os.path.isfile(path):
        return
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)
