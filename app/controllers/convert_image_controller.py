"""Handlers for the Convert Image tab (queue, browse, batch convert, progress)."""

from __future__ import annotations

import os
import threading
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from app.services import image_convert_service as ics


def _unique_dest_path(folder: str, base: str, ext: str) -> str:
    dest = os.path.join(folder, base + ext)
    if not os.path.exists(dest):
        return dest
    k = 1
    while True:
        cand = os.path.join(folder, f"{base}_{k}{ext}")
        if not os.path.exists(cand):
            return cand
        k += 1


def _update_input_summary(app: Any) -> None:
    var = getattr(app, "_convert_input_summary_var", None)
    if var is None:
        return
    q = app._convert_queue
    if not q:
        var.set("")
    elif len(q) == 1:
        var.set(os.path.basename(q[0]))
    else:
        var.set(f"{len(q)} files selected")


def update_convert_quality_percent_label(app: Any) -> None:
    lbl = getattr(app, "_convert_quality_pct_label", None)
    if lbl is None or not lbl.winfo_exists():
        return
    try:
        v = int(round(float(app._convert_quality_var.get())))
    except (TypeError, ValueError):
        v = 85
    lbl.configure(text=f"{v}%")


def _refresh_queue_list(app: Any) -> None:
    ff = getattr(app, "_convert_list_frame", None)
    if ff is None or not ff.winfo_exists():
        return
    for w in ff.winfo_children():
        w.destroy()
    app._convert_thumb_refs = []
    for i, path in enumerate(app._convert_queue):
        r = ctk.CTkFrame(ff, fg_color="transparent")
        r.pack(fill="x", pady=2)

        thumb_img = None
        try:
            im = Image.open(path)
            if getattr(im, "n_frames", 1) > 1:
                im.seek(0)
            im = im.copy()
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            im.thumbnail((44, 44), Image.Resampling.LANCZOS)
            thumb_img = ctk.CTkImage(
                light_image=im,
                dark_image=im,
                size=(44, 44),
            )
            app._convert_thumb_refs.append(thumb_img)
        except Exception:
            ph = ctk.CTkFrame(r, width=44, height=44, fg_color=("gray75", "gray30"))
            ph.pack(side="left", padx=(0, 8))
            ph.pack_propagate(False)
        else:
            ctk.CTkLabel(r, text="", image=thumb_img, width=44, height=44).pack(
                side="left", padx=(0, 8)
            )

        ctk.CTkLabel(
            r,
            text=os.path.basename(path),
            anchor="w",
            font=("Segoe UI", 11),
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            r,
            text="×",
            width=28,
            font=("Segoe UI", 12, "bold"),
            command=lambda idx=i: convert_tab_remove_at(app, idx),
        ).pack(side="right", padx=(4, 0))

    _update_input_summary(app)
    _sync_run_button(app)


def _sync_run_button(app: Any) -> None:
    btn = getattr(app, "_convert_run_btn", None)
    if btn is None or not btn.winfo_exists():
        return
    folder = getattr(app, "_convert_output_folder_var", None)
    folder_ok = bool(folder and folder.get().strip() and os.path.isdir(folder.get().strip()))
    btn.configure(
        state="normal" if app._convert_queue and folder_ok else "disabled"
    )


def convert_tab_remove_at(app: Any, index: int) -> None:
    if 0 <= index < len(app._convert_queue):
        app._convert_queue.pop(index)
        _refresh_queue_list(app)


def convert_tab_clear_queue(app: Any) -> None:
    app._convert_queue.clear()
    _refresh_queue_list(app)


def _add_paths_to_queue(app: Any, paths: list[str]) -> None:
    seen = set(app._convert_queue)
    for p in paths:
        p = os.path.normpath(p)
        if os.path.isfile(p) and p not in seen:
            app._convert_queue.append(p)
            seen.add(p)
    _refresh_queue_list(app)


def convert_tab_handle_drop(app: Any, event: Any) -> None:
    try:
        paths = list(app.tk.splitlist(event.data.strip()))
    except Exception:
        raw = (event.data or "").strip()
        paths = [raw.strip("{}").strip()] if raw else []
    _add_paths_to_queue(app, paths)


def convert_tab_browse(app: Any) -> None:
    paths = filedialog.askopenfilenames(
        parent=app,
        title="Add images to convert",
        filetypes=[
            (
                "Images",
                "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif *.ico",
            ),
            ("All files", "*.*"),
        ],
    )
    if paths:
        _add_paths_to_queue(app, list(paths))


def convert_tab_browse_output_folder(app: Any) -> None:
    d = filedialog.askdirectory(parent=app, title="Output folder")
    if d:
        app._convert_output_folder_var.set(d)
        _sync_run_button(app)


def convert_tab_on_output_folder_change(app: Any, *_args: Any) -> None:
    _sync_run_button(app)


def convert_tab_run(app: Any) -> None:
    if not app._convert_queue:
        return
    fmt = app._convert_format_var.get().strip().upper()
    if fmt not in ics.OUTPUT_FORMATS:
        messagebox.showerror("Convert", "Pick a valid output format.", parent=app)
        return
    folder = app._convert_output_folder_var.get().strip()
    if not folder or not os.path.isdir(folder):
        messagebox.showerror(
            "Convert",
            "Choose a valid output folder.",
            parent=app,
        )
        return

    quality = int(round(float(app._convert_quality_var.get())))
    ext = ics.default_extension(fmt)
    strip_meta = bool(app._convert_strip_metadata_var.get())
    cmyk = bool(app._convert_cmyk_to_rgb_var.get())

    queue_snapshot = list(app._convert_queue)
    n = len(queue_snapshot)
    if n == 0:
        return

    bar = getattr(app, "_convert_progress_bar", None)
    btn = getattr(app, "_convert_run_btn", None)
    if btn is not None:
        btn.configure(state="disabled")

    def set_progress(p: float) -> None:
        if bar is not None and bar.winfo_exists():
            bar.set(max(0.0, min(1.0, p)))

    set_progress(0.0)

    def work() -> None:
        errors: list[str] = []
        ok_count = 0
        for i, src in enumerate(queue_snapshot):
            base = os.path.splitext(os.path.basename(src))[0]
            dest = _unique_dest_path(folder, base, ext)
            try:
                ics.convert_file_to_path(
                    src,
                    dest,
                    fmt,
                    quality=quality,
                    strip_metadata=strip_meta,
                    cmyk_to_rgb=cmyk,
                )
                ok_count += 1
            except Exception as e:
                errors.append(f"{os.path.basename(src)}: {e}")
            done = i + 1
            app.after(0, lambda d=done, total=n: set_progress(d / total))

        def finish() -> None:
            if btn is not None and btn.winfo_exists():
                btn.configure(state="normal")
            if errors:
                messagebox.showwarning(
                    "Conversion finished with errors",
                    "\n".join(errors[:8]) + ("\n…" if len(errors) > 8 else ""),
                    parent=app,
                )
            elif ok_count:
                messagebox.showinfo(
                    "Convert",
                    f"Saved {ok_count} file(s) to:\n{folder}",
                    parent=app,
                )
            if ok_count == n and not errors:
                set_progress(1.0)
            elif ok_count > 0:
                set_progress(ok_count / n)
            else:
                set_progress(0.0)

        app.after(0, finish)

    threading.Thread(target=work, daemon=True).start()
