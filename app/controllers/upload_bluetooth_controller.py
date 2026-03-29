from __future__ import annotations

import os
import threading
from logging import Logger
from tkinter import TclError, filedialog, messagebox
from typing import Any

from PIL import Image, ImageTk

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
    path = filedialog.askopenfilename(
        parent=app,
        title="Choose file to send",
        filetypes=[("All files", "*.*")],
    )
    if path:
        app._upload_bluetooth_path = path
        app.upload_bluetooth_path_entry.delete(0, "end")
        app.upload_bluetooth_path_entry.insert(0, path)
        update_upload_bluetooth_preview(app, path)


def update_upload_bluetooth_preview(app: Any, path: str) -> None:
    app._upload_bluetooth_preview_img = None
    try:
        img = Image.open(path)
        img.thumbnail((360, 240))
        app._upload_bluetooth_preview_img = ImageTk.PhotoImage(img)
        app.upload_bluetooth_preview.configure(
            image=app._upload_bluetooth_preview_img,
            text="",
        )
    except Exception:
        base = os.path.basename(path)
        app.upload_bluetooth_preview.configure(
            image=None,
            text=f"(No image preview)\n{base}",
        )


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
    if not getattr(app, "_upload_bluetooth_path", ""):
        messagebox.showwarning("Bluetooth", "Choose a file first (Browse).")
        return

    local_path = app._upload_bluetooth_path
    try:
        fsize = os.path.getsize(local_path)
    except OSError:
        fsize = 0
    timeout_ms = int(1000 * bluetooth_send_ui_watchdog_timeout_sec(fsize))
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
            local_path=local_path,
            cancel_watchdog=False,
        )

    app._bt_send_watchdog_after_id = app.after(timeout_ms, watchdog)

    def work() -> None:
        success, msg = False, "Bluetooth send did not complete."
        try:
            success, msg = send_file_to_device(app._bt_target_device_id, local_path)
        except Exception as e:
            logger.exception("[Bluetooth] Send raised an exception")
            msg = f"{type(e).__name__}: {e}"
            success = False
        finally:

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
                    local_path=local_path,
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
