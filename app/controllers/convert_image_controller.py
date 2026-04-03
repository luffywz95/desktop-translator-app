"""Handlers for the Convert Image tab (queue, browse, batch convert, progress)."""

from __future__ import annotations

import os
import threading
from typing import Any

from app.services import image_convert_service as ics


def _showinfo(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showinfo", None)
    if callable(h):
        h(title, message)


def _showwarning(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showwarning", None)
    if callable(h):
        h(title, message)


def _showerror(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showerror", None)
    if callable(h):
        h(title, message)


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
    if lbl is None:
        return
    if hasattr(lbl, "winfo_exists") and not lbl.winfo_exists():
        return
    try:
        v = int(round(float(app._convert_quality_var.get())))
    except (TypeError, ValueError):
        v = 85
    lbl.configure(text=f"{v}%")


def _refresh_queue_list(app: Any) -> None:
    flet_renderer = getattr(app, "_flet_render_convert_queue", None)
    if not callable(flet_renderer):
        raise RuntimeError("_flet_render_convert_queue is required")
    flet_renderer()
    _update_input_summary(app)
    _sync_run_button(app)


def _convert_log_append(app: Any, line: str) -> None:
    lg = getattr(app, "_convert_log", None)
    if lg is None:
        return
    we = getattr(lg, "winfo_exists", None)
    if callable(we) and not we():
        return
    lg.insert("end", line if line.endswith("\n") else line + "\n")
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()


def _sync_run_button(app: Any) -> None:
    btn = getattr(app, "_convert_run_btn", None)
    if btn is None:
        return
    if hasattr(btn, "winfo_exists") and not btn.winfo_exists():
        return
    folder = getattr(app, "_convert_output_folder_var", None)
    folder_ok = bool(
        folder and folder.get().strip() and os.path.isdir(folder.get().strip())
    )
    btn.configure(state="normal" if app._convert_queue and folder_ok else "disabled")


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
    splitter = getattr(app, "split_drop_paths", None)
    if not callable(splitter):
        return
    paths = list(splitter(getattr(event, "data", "")))
    _add_paths_to_queue(app, paths)


def convert_tab_browse(app: Any) -> None:
    pick_many = getattr(app, "pick_multiple_files", None)
    if not callable(pick_many):
        raise RuntimeError("pick_multiple_files is required")
    paths = tuple(pick_many("Add images to convert"))
    if paths:
        _add_paths_to_queue(app, list(paths))


def convert_tab_browse_output_folder(app: Any) -> None:
    pick_dir = getattr(app, "pick_directory", None)
    if not callable(pick_dir):
        raise RuntimeError("pick_directory is required")
    d = pick_dir("Output folder")
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
        _showerror(app, "Convert", "Pick a valid output format.")
        return
    folder = app._convert_output_folder_var.get().strip()
    if not folder or not os.path.isdir(folder):
        _showerror(app, "Convert", "Choose a valid output folder.")
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
    log = getattr(app, "_convert_log", None)
    if log is not None:
        le = getattr(log, "winfo_exists", None)
        if not callable(le) or le():
            log.delete()
    if btn is not None:
        btn.configure(state="disabled")

    def set_progress(p: float) -> None:
        if bar is not None:
            we = getattr(bar, "winfo_exists", None)
            if callable(we) and not we():
                return
            bar.set(max(0.0, min(1.0, p)))

    set_progress(0.0)

    def work() -> None:
        app.after(
            0,
            lambda: _convert_log_append(
                app, f"[i] Converting {n} file(s) to {fmt} → {folder}"
            ),
        )
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
                bn = os.path.basename(src)
                app.after(0, lambda b=bn, d=dest: _convert_log_append(app, f"[ok] {b} → {d}"))
            except Exception as e:
                errors.append(f"{os.path.basename(src)}: {e}")
                bn = os.path.basename(src)
                app.after(0, lambda b=bn, err=e: _convert_log_append(app, f"[err] {b}: {err}"))
            done = i + 1
            app.after(0, lambda d=done, total=n: set_progress(d / total))

        def finish() -> None:
            if btn is not None:
                be = getattr(btn, "winfo_exists", None)
                if not callable(be) or be():
                    btn.configure(state="normal")
            _convert_log_append(
                app,
                f"[i] Finished: {ok_count}/{n} file(s) ok, {len(errors)} error(s).",
            )
            if errors:
                _showwarning(
                    app,
                    "Conversion finished with errors",
                    "\n".join(errors[:8]) + ("\n…" if len(errors) > 8 else ""),
                )
            elif ok_count:
                _showinfo(app, "Convert", f"Saved {ok_count} file(s) to:\n{folder}")
            if ok_count == n and not errors:
                set_progress(1.0)
            elif ok_count > 0:
                set_progress(ok_count / n)
            else:
                set_progress(0.0)
            if hasattr(app, "_safe_page_update"):
                app._safe_page_update()

        app.after(0, finish)

    threading.Thread(target=work, daemon=True).start()
