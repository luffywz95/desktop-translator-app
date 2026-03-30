from __future__ import annotations

import os
import threading
from logging import Logger
from tkinter import TclError, filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from components.loading_overlay import BusyOverlay
from app.services.bluetooth_doctor_service import (
    BluetoothDoctorSnapshot,
    collect_bluetooth_doctor_snapshot,
    doctor_add_fsquirt_sendto_shortcut,
    doctor_sendto_has_bluetooth_entry,
)
from utils.bluetooth_transfer import (
    BT_SEND_WATCHDOG_USER_MSG,
    bluetooth_send_ui_watchdog_timeout_sec,
)
from utils.upload_bluetooth_service import (
    bluetooth_runtime_available,
    is_ios_like_name,
    send_file_to_device,
)

_STALE_BT_DEVICE_MSG = "Could not open Bluetooth device."


def _norm_bt_path(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except OSError:
        return os.path.normcase(p)


def _merge_bluetooth_paths(existing: list[str], new_paths: list[str]) -> list[str]:
    """Append new paths; skip duplicates (same normalized path). Preserve order."""
    seen = {_norm_bt_path(x) for x in existing}
    out = list(existing)
    for p in new_paths:
        n = _norm_bt_path(p)
        if n not in seen:
            seen.add(n)
            out.append(p)
    return out


def _bt_scoped_busy_overlay(app: Any) -> BusyOverlay:
    host = getattr(app, "_upload_bluetooth_status_host", None)
    if host is None:
        raise RuntimeError("Bluetooth status host frame is missing.")
    o = getattr(app, "_bt_status_busy_overlay", None)
    if o is None:
        o = BusyOverlay(host)
        app._bt_status_busy_overlay = o
    return o


def _bt_hide_bluetooth_status_busy(app: Any) -> None:
    o = getattr(app, "_bt_status_busy_overlay", None)
    if o is None:
        return
    try:
        o.hide()
    except TclError:
        pass


def _bt_cancel_send_watchdog(app: Any) -> None:
    wid = getattr(app, "_bt_send_watchdog_after_id", None)
    if wid is not None:
        try:
            app.after_cancel(wid)
        except TclError:
            pass
    app._bt_send_watchdog_after_id = None


def _bt_show_bluetooth_send_dialog(
    app: Any,
    *,
    success: bool,
    failure_message: str,
    local_path: str,
) -> None:
    if not app.winfo_exists():
        return
    try:
        if success:
            paths = getattr(app, "_upload_bluetooth_paths", [])
            if len(paths) > 1:
                body = f"The transfer completed successfully.\n\n{len(paths)} files sent."
            else:
                body = (
                    "The file was sent successfully.\n\n"
                    f"{os.path.basename(local_path)}"
                )
            dev = (getattr(app, "_bt_target_name", None) or "").strip()
            if dev:
                body += f"\n\nDevice: {dev}"
            messagebox.showinfo("Bluetooth", body, parent=app)
        else:
            messagebox.showerror("Bluetooth", failure_message, parent=app)
    except TclError:
        pass


def _bt_finalize_bluetooth_send(
    app: Any,
    session: int,
    settings: Any,
    *,
    success: bool,
    user_message: str,
    local_path: str,
    cancel_watchdog: bool,
) -> None:
    if getattr(app, "_bt_send_session", 0) != session:
        return
    if getattr(app, "_bt_send_finished", False):
        return
    app._bt_send_finished = True
    if cancel_watchdog:
        _bt_cancel_send_watchdog(app)
    _bt_hide_bluetooth_status_busy(app)

    msg_for_ui = user_message
    if (
        not success
        and _STALE_BT_DEVICE_MSG in user_message
        and getattr(app, "_bt_target_device_id", "")
    ):
        clear_saved_bluetooth_upload_target(app, settings)
        msg_for_ui = (
            f"{user_message}\n\nThe saved device was cleared. "
            "Select your device again (Bluetooth → Select device)."
        )

    if not app.winfo_exists():
        return
    try:
        if app.upload_bluetooth_send_btn.winfo_exists():
            app.upload_bluetooth_send_btn.configure(state="normal")
        if app.upload_bluetooth_doctor_btn.winfo_exists():
            app.upload_bluetooth_doctor_btn.configure(state="normal")
        if app.upload_bluetooth_status.winfo_exists():
            app.upload_bluetooth_status.delete("1.0", "end")
            line = msg_for_ui if success else f"Failed: {msg_for_ui}"
            app.upload_bluetooth_status.insert("1.0", line)
    except TclError:
        pass

    _bt_show_bluetooth_send_dialog(
        app,
        success=success,
        failure_message=msg_for_ui,
        local_path=local_path,
    )


def clear_saved_bluetooth_upload_target(app: Any, settings: Any) -> None:
    app._bt_target_device_id = ""
    app._bt_target_name = ""
    settings["bluetooth_upload"] = {"device_id": "", "name": ""}
    if getattr(app, "upload_bt_device_label", None) is not None:
        try:
            if app.upload_bt_device_label.winfo_exists():
                app.upload_bt_device_label.configure(text="No device selected.")
        except Exception:
            pass


def upload_bluetooth_browse(app: Any) -> None:
    paths = filedialog.askopenfilenames(
        parent=app,
        title="Choose file(s) to send",
        filetypes=[("All files", "*.*")],
    )
    if paths:
        prior = list(getattr(app, "_upload_bluetooth_paths", []) or [])
        app._upload_bluetooth_paths = _merge_bluetooth_paths(prior, list(paths))
        app.upload_bluetooth_path_entry.delete(0, "end")
        n = len(app._upload_bluetooth_paths)
        if n == 1:
            app.upload_bluetooth_path_entry.insert(0, app._upload_bluetooth_paths[0])
        else:
            app.upload_bluetooth_path_entry.insert(0, f"{n} files selected")
        update_upload_bluetooth_preview(app)


def upload_bluetooth_handle_drop(app: Any, event: Any) -> None:
    # event.data might be a space-separated list of paths wrapped in curly braces if they contain spaces.
    raw_paths = app.tk.splitlist(event.data)
    if not raw_paths:
        return
    prior = list(getattr(app, "_upload_bluetooth_paths", []) or [])
    app._upload_bluetooth_paths = _merge_bluetooth_paths(prior, list(raw_paths))
    app.upload_bluetooth_path_entry.delete(0, "end")
    n = len(app._upload_bluetooth_paths)
    if n == 1:
        app.upload_bluetooth_path_entry.insert(0, app._upload_bluetooth_paths[0])
    else:
        app.upload_bluetooth_path_entry.insert(0, f"{n} files selected")
    update_upload_bluetooth_preview(app)

def _remove_bluetooth_file(app: Any, path_to_remove: str) -> None:
    if path_to_remove in app._upload_bluetooth_paths:
        app._upload_bluetooth_paths.remove(path_to_remove)
    
    app.upload_bluetooth_path_entry.delete(0, "end")
    if len(app._upload_bluetooth_paths) == 1:
        app.upload_bluetooth_path_entry.insert(0, app._upload_bluetooth_paths[0])
    elif len(app._upload_bluetooth_paths) > 1:
        app.upload_bluetooth_path_entry.insert(0, f"{len(app._upload_bluetooth_paths)} files selected")
    
    update_upload_bluetooth_preview(app)

def _bt_queue_thumb_size() -> int:
    return 36


def _bt_queue_icon_cell(app: Any, row: ctk.CTkFrame, path: str) -> None:
    """Left column: image thumbnail for raster images; plain text placeholder otherwise."""
    sz = _bt_queue_thumb_size()
    box = ctk.CTkFrame(row, width=sz, height=sz, fg_color="transparent")
    box.grid_propagate(False)
    box.grid(row=0, column=0, padx=(0, 6), sticky="nw")

    thumb_img = None
    try:
        im = Image.open(path)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        im = im.copy()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        im.thumbnail((sz, sz), Image.Resampling.LANCZOS)
        thumb_img = ctk.CTkImage(light_image=im, dark_image=im, size=(sz, sz))
        refs = getattr(app, "_upload_bluetooth_thumb_refs", None)
        if refs is not None:
            refs.append(thumb_img)
        ctk.CTkLabel(box, text="", image=thumb_img, width=sz, height=sz).place(
            relx=0.5, rely=0.5, anchor="center"
        )
    except Exception:
        ctk.CTkLabel(
            box,
            text="FILE",
            width=sz,
            height=sz,
            font=("Segoe UI", 9, "bold"),
            text_color=("gray40", "gray60"),
            fg_color=("gray85", "gray35"),
            corner_radius=4,
        ).place(relx=0.5, rely=0.5, anchor="center")


def update_upload_bluetooth_preview(app: Any) -> None:
    from components.hover_marquee_label import HoverMarqueeClipLabel

    host = getattr(app, "_upload_bluetooth_queue_inner", None)
    if host is None or not host.winfo_exists():
        return
    for widget in host.winfo_children():
        widget.destroy()
    app._upload_bluetooth_thumb_refs = []

    paths = getattr(app, "_upload_bluetooth_paths", [])
    if not paths:
        app.upload_bluetooth_empty_label = ctk.CTkLabel(
            host,
            text="No file(s) selected\n(Browse or drop to choose file(s))",
            text_color="gray",
        )
        app.upload_bluetooth_empty_label.pack(expand=True, fill="both", pady=40)
        return

    for p in paths:
        row = ctk.CTkFrame(host, fg_color="transparent")
        row.pack(fill="x", pady=2, padx=4)
        row.grid_columnconfigure(1, weight=1)  # Marquee gets remaining space
        row.grid_columnconfigure(2, weight=0)  # Close button gets fixed space

        _bt_queue_icon_cell(app, row, p)

        name_lbl = HoverMarqueeClipLabel(
            row, text=os.path.basename(p), font=("Segoe UI", 11)
        )
        name_lbl.grid(row=0, column=1, sticky="ew")

        close_btn = ctk.CTkButton(
            row,
            text="✕",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=("#d3d3d3", "#4d4d4d"),
            text_color=("gray10", "gray90"),
            command=lambda path=p: _remove_bluetooth_file(app, path),
        )
        close_btn.grid(row=0, column=2, padx=(6, 0), sticky="e")


def upload_bluetooth_send_bt(app: Any, *, logger: Logger, settings: Any) -> None:
    ok, hint = bluetooth_runtime_available()
    if not ok:
        messagebox.showwarning("Bluetooth", hint)
        return
    if not app._bt_target_device_id:
        messagebox.showwarning("Bluetooth", "Choose a Bluetooth device first.")
        return
    if is_ios_like_name(app._bt_target_name):
        logger.warning(
            "[Bluetooth] Blocked send to iOS-like target: %s (%s)",
            app._bt_target_name,
            app._bt_target_device_id,
        )
        messagebox.showwarning(
            "Bluetooth",
            "This target appears to be an iOS device. iOS generally blocks "
            "generic Bluetooth file transfer (OBEX) from Windows PCs.\n\n"
            "Please choose another device.",
        )
        return
    if not getattr(app, "_upload_bluetooth_paths", []):
        messagebox.showwarning("Bluetooth", "Choose a file first (Browse).")
        return

    paths = app._upload_bluetooth_paths
    total_files = len(paths)
    
    timeout_ms = 0
    for p in paths:
        try:
            fsize = os.path.getsize(p)
        except OSError:
            fsize = 0
        timeout_ms += int(1000 * bluetooth_send_ui_watchdog_timeout_sec(fsize))
        
    session = getattr(app, "_bt_send_session", 0) + 1
    app._bt_send_session = session
    app._bt_send_finished = False

    app.upload_bluetooth_send_btn.configure(state="disabled")
    app.upload_bluetooth_doctor_btn.configure(state="disabled")
    app.upload_bluetooth_status.delete("1.0", "end")
    try:
        _bt_scoped_busy_overlay(app).show("Sending over Bluetooth…")
    except (TclError, RuntimeError):
        app.upload_bluetooth_status.insert("1.0", "Sending over Bluetooth…")

    def watchdog() -> None:
        app._bt_send_watchdog_after_id = None
        logger.warning(
            "[Bluetooth] Send watchdog fired after %s ms (session=%s)",
            timeout_ms,
            session,
        )
        _bt_finalize_bluetooth_send(
            app,
            session,
            settings,
            success=False,
            user_message=BT_SEND_WATCHDOG_USER_MSG,
            local_path=f"{total_files} file(s)",
            cancel_watchdog=False,
        )

    app._bt_send_watchdog_after_id = app.after(timeout_ms, watchdog)

    def work() -> None:
        success, msg = False, "Bluetooth send did not complete."
        for i, path in enumerate(paths, 1):
            fname = os.path.basename(path)
            
            def update_status(current_file=fname, idx=i):
                if app.winfo_exists():
                    app.upload_bluetooth_status.delete("1.0", "end")
                    app.upload_bluetooth_status.insert("1.0", f"Sending {idx}/{total_files}: {current_file}...")
                    
            app.after(0, update_status)
            
            try:
                success, msg = send_file_to_device(app._bt_target_device_id, path)
                if not success:
                    msg = f"Failed on file {i}/{total_files} ({fname}): {msg}"
                    break
            except Exception as e:
                logger.exception(f"[Bluetooth] Send raised an exception on file {fname}")
                msg = f"Error on file {fname}: {type(e).__name__}: {e}"
                success = False
                break
                
        if success:
            msg = f"Successfully sent {total_files} file(s)."

        def done() -> None:
            if not app.winfo_exists():
                if getattr(app, "_bt_send_session", 0) == session:
                    app._bt_send_finished = True
                _bt_cancel_send_watchdog(app)
                _bt_hide_bluetooth_status_busy(app)
                return
            _bt_finalize_bluetooth_send(
                app,
                session,
                settings,
                success=success,
                user_message=msg,
                local_path=paths[0] if total_files == 1 else f"{total_files} file(s)",
                cancel_watchdog=True,
            )

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()


def _doctor_done_ui(
    app: Any,
    snap: BluetoothDoctorSnapshot,
    *,
    logger: Logger,
) -> None:
    if not app.winfo_exists():
        return
    app.upload_bluetooth_doctor_btn.configure(state="normal")
    app.upload_bluetooth_status.delete("1.0", "end")
    app.upload_bluetooth_status.insert("1.0", "\n".join(snap.report_lines))

    if snap.all_pass:
        logger.info("[Bluetooth Doctor] All checks passed")
        messagebox.showinfo(
            "Bluetooth Doctor",
            "All Bluetooth checks passed.\n\n"
            "Your PC appears ready for Bluetooth file transfer.",
        )
        return

    if snap.should_offer_fix:
        ask = messagebox.askyesno(
            "Bluetooth Doctor",
            "Bluetooth is available and fsquirt.exe is present, but 'Send to' "
            "does not contain a Bluetooth entry.\n\n"
            "Allow this app to add 'Bluetooth File Transfer' into shell:sendto?",
        )
        if ask:
            ok, msg = doctor_add_fsquirt_sendto_shortcut()
            logger.info(
                "[Bluetooth Doctor] Add SendTo shortcut result: ok=%s msg=%s",
                ok,
                msg,
            )
            recheck = doctor_sendto_has_bluetooth_entry(logger)
            app.upload_bluetooth_status.insert(
                "end",
                "\n\n[4] Auto-fix attempted: "
                + ("SUCCESS" if ok else "FAILED")
                + f"\n    Detail: {msg}\n    Re-check SendTo: {'YES' if recheck else 'NO'}",
            )
            if ok and recheck:
                messagebox.showinfo(
                    "Bluetooth Doctor",
                    "Added Bluetooth File Transfer to shell:sendto successfully.",
                )
            else:
                messagebox.showwarning(
                    "Bluetooth Doctor",
                    "Could not confirm the shortcut in SendTo. "
                    "You can add it manually via shell:sendto.",
                )
        else:
            logger.info("[Bluetooth Doctor] User declined SendTo auto-fix")
    else:
        app.upload_bluetooth_status.insert(
            "end",
            "\n\n[4] Auto-fix condition not met (requires [1]=OK, [2]=NO, [3]=OK).",
        )
        problems = []
        if not snap.supports_bt:
            problems.append("Bluetooth adapter/runtime is not ready")
        if not snap.fsquirt_ok:
            problems.append("fsquirt.exe is missing or not discoverable")
        if snap.supports_bt and snap.fsquirt_ok and snap.sendto_has_bt:
            problems.append("No actionable issue found for auto-fix")
        reason = "; ".join(problems) if problems else "Unknown reason"
        logger.warning(
            "[Bluetooth Doctor] Failure path (non-fsquirt-auto-fix): %s",
            reason,
        )
        messagebox.showwarning(
            "Bluetooth Doctor",
            "Bluetooth Doctor found issues that cannot be auto-fixed here.\n\n"
            f"Reason: {reason}",
        )


def upload_bluetooth_doctor(app: Any, *, logger: Logger) -> None:
    app.upload_bluetooth_doctor_btn.configure(state="disabled")
    app.upload_bluetooth_status.delete("1.0", "end")
    app.upload_bluetooth_status.insert("1.0", "Running Bluetooth Doctor...")
    logger.info("[Bluetooth Doctor] Started diagnostics")

    def work() -> None:
        snap = collect_bluetooth_doctor_snapshot(logger)

        def done() -> None:
            _doctor_done_ui(app, snap, logger=logger)

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()
