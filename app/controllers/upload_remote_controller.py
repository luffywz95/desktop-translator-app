from __future__ import annotations

import threading
from tkinter import messagebox
from typing import Any

from dataclasses import dataclass

from utils.upload_remote_service import upload_file as upload_remote_file


@dataclass(slots=True)
class UploadRemoteResult:
    code: int
    body: str


def send_remote_file(url: str, local_path: str, token: str | None = None) -> UploadRemoteResult:
    code, body = upload_remote_file(url, local_path, token)
    return UploadRemoteResult(code=code, body=body)


def run_upload_tab_send(app: Any) -> None:
    url = app.upload_tab_url_entry.get().strip()
    if not url:
        messagebox.showwarning("Upload", "Enter a remote URL.")
        return
    if not getattr(app, "_upload_local_path", ""):
        messagebox.showwarning("Upload", "Choose a file first (Browse).")
        return
    token = app.upload_tab_token_entry.get().strip()

    app.upload_tab_send_btn.configure(state="disabled")
    app.upload_tab_status.delete("1.0", "end")
    app.upload_tab_status.insert("1.0", "Uploading...")

    local_path = app._upload_local_path

    def work() -> None:
        result = send_remote_file(url, local_path, token or None)
        code = result.code
        body = result.body

        def done() -> None:
            app.upload_tab_send_btn.configure(state="normal")
            app.upload_tab_status.delete("1.0", "end")
            if 200 <= code < 300:
                app.upload_tab_status.insert(
                    "1.0",
                    f"Success HTTP {code}\n\n{(body or '')[:4000]}",
                )
                up = app._normalized_upload_file()
                up["remote_url"] = app.upload_tab_url_entry.get().strip()
                up["remote_token"] = app.upload_tab_token_entry.get()
                app._persist_transfer_hub_atomic(
                    app._normalized_receive_file(),
                    up,
                )
            elif code == 0:
                app.upload_tab_status.insert("1.0", body or "Request failed.")
            else:
                app.upload_tab_status.insert(
                    "1.0",
                    f"HTTP {code}\n\n{(body or '')[:4000]}",
                )

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()
