from __future__ import annotations

import os
import threading
from logging import Logger
from typing import Any

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


def _norm_bt_path(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except OSError:
        return os.path.normcase(p)


def _merge_bluetooth_paths(existing: list[str], new_paths: list[str]) -> list[str]:
    seen = {_norm_bt_path(x) for x in existing}
    out = list(existing)
    for p in new_paths:
        n = _norm_bt_path(p)
        if n not in seen:
            seen.add(n)
            out.append(p)
    return out


def _bt_cancel_send_watchdog(app: Any) -> None:
    wid = getattr(app, "_bt_send_watchdog_after_id", None)
    if wid is not None:
        try:
            app.after_cancel(wid)
        except Exception:
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
            _showinfo(app, "Bluetooth", body)
        else:
            _showerror(app, "Bluetooth", failure_message)
    except Exception:
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
        app.upload_bluetooth_send_btn.configure(state="normal")
        app.upload_bluetooth_doctor_btn.configure(state="normal")
        app.upload_bluetooth_status.delete("1.0", "end")
        line = msg_for_ui if success else f"Failed: {msg_for_ui}"
        app.upload_bluetooth_status.insert("1.0", line)
    except Exception:
        pass

    _bt_show_bluetooth_send_dialog(
        app,
        success=success,
        failure_message=msg_for_ui,
        local_path=local_path,
    )
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()


def clear_saved_bluetooth_upload_target(app: Any, settings: Any) -> None:
    app._bt_target_device_id = ""
    app._bt_target_name = ""
    settings["bluetooth_upload"] = {"device_id": "", "name": ""}
    if getattr(app, "upload_bt_device_label", None) is not None:
        try:
            app.upload_bt_device_label.configure(text="No device selected.")
        except Exception:
            pass


def upload_bluetooth_browse(app: Any) -> None:
    pick_many = getattr(app, "pick_multiple_files", None)
    if not callable(pick_many):
        raise RuntimeError("pick_multiple_files is required for Bluetooth file pick")
    paths = tuple(pick_many("Choose file(s) to send"))
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
    splitter = getattr(app, "split_drop_paths", None)
    if not callable(splitter):
        return
    raw_paths = splitter(getattr(event, "data", ""))
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


def update_upload_bluetooth_preview(app: Any) -> None:
    renderer = getattr(app, "_flet_render_bt_queue", None)
    if not callable(renderer):
        raise RuntimeError("_flet_render_bt_queue is required")
    renderer()


def upload_bluetooth_send_bt(app: Any, *, logger: Logger, settings: Any) -> None:
    ok, hint = bluetooth_runtime_available()
    if not ok:
        _showwarning(app, "Bluetooth", hint)
        return
    if not app._bt_target_device_id:
        _showwarning(app, "Bluetooth", "Choose a Bluetooth device first.")
        return
    if is_ios_like_name(app._bt_target_name):
        logger.warning(
            "[Bluetooth] Blocked send to iOS-like target: %s (%s)",
            app._bt_target_name,
            app._bt_target_device_id,
        )
        _showwarning(
            app,
            "Bluetooth",
            "This target appears to be an iOS device. iOS generally blocks "
            "generic Bluetooth file transfer (OBEX) from Windows PCs.\n\n"
            "Please choose another device.",
        )
        return
    if not getattr(app, "_upload_bluetooth_paths", []):
        _showwarning(app, "Bluetooth", "Choose a file first (Browse).")
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
    app.upload_bluetooth_status.insert("1.0", "Sending over Bluetooth…")
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()

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
                    app.upload_bluetooth_status.insert(
                        "1.0", f"Sending {idx}/{total_files}: {current_file}..."
                    )
                    if hasattr(app, "_safe_page_update"):
                        app._safe_page_update()

            app.after(0, update_status)

            try:
                success, msg = send_file_to_device(app._bt_target_device_id, path)
                if not success:
                    msg = f"Failed on file {i}/{total_files} ({fname}): {msg}"
                    break
            except Exception as e:
                logger.exception("[Bluetooth] Send raised an exception on file %s", fname)
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


def _bluetooth_doctor_apply_sendto_fix(app: Any, *, logger: Logger) -> None:
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
        _showinfo(
            app,
            "Bluetooth Doctor",
            "Added Bluetooth File Transfer to shell:sendto successfully.",
        )
    else:
        _showwarning(
            app,
            "Bluetooth Doctor",
            "Could not confirm the shortcut in SendTo. "
            "You can add it manually via shell:sendto.",
        )
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()


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
        _showinfo(
            app,
            "Bluetooth Doctor",
            "All Bluetooth checks passed.\n\n"
            "Your PC appears ready for Bluetooth file transfer.",
        )
        return

    if snap.should_offer_fix:
        offer_msg = (
            "Bluetooth is available and fsquirt.exe is present, but 'Send to' "
            "does not contain a Bluetooth entry.\n\n"
            "Allow this app to add 'Bluetooth File Transfer' into shell:sendto?"
        )
        schedule = getattr(app, "schedule_confirm_dialog", None)
        if not callable(schedule):
            _showwarning(app, "Bluetooth Doctor", offer_msg)
            return

        def on_yes() -> None:
            _bluetooth_doctor_apply_sendto_fix(app, logger=logger)

        def on_no() -> None:
            logger.info("[Bluetooth Doctor] User declined SendTo auto-fix")

        schedule("Bluetooth Doctor", offer_msg, on_yes=on_yes, on_no=on_no)
        return

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
    _showwarning(
        app,
        "Bluetooth Doctor",
        "Bluetooth Doctor found issues that cannot be auto-fixed here.\n\n"
        f"Reason: {reason}",
    )


def upload_bluetooth_doctor(app: Any, *, logger: Logger) -> None:
    app.upload_bluetooth_doctor_btn.configure(state="disabled")
    app.upload_bluetooth_status.delete("1.0", "end")
    app.upload_bluetooth_status.insert("1.0", "Running Bluetooth Doctor...")
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()
    logger.info("[Bluetooth Doctor] Started diagnostics")

    def work() -> None:
        snap = collect_bluetooth_doctor_snapshot(logger)

        def done() -> None:
            _doctor_done_ui(app, snap, logger=logger)

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()
