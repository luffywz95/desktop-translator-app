from __future__ import annotations

import sys
from tkinter import messagebox
from typing import Any, Callable

import keyboard

from app.state.transfer_settings import normalized_receive_file, normalized_upload_file
from components.loading_overlay import run_blocking_task_with_busy_ui


def save_settings_from_modal(
    app: Any,
    *,
    settings: dict[str, Any],
    show_app_request: Callable[[], None],
) -> None:
    settings.begin_batch()
    try:
        old_receive = normalized_receive_file(settings)
        old_upload = normalized_upload_file(settings)

        application_invoke_hotkey = app.application_invoke_hotkey_row.key_input.get().lower()
        if application_invoke_hotkey:
            settings["hotkey_settings"]["application_invoke_hotkey"]["hotkey"] = (
                "ctrl+shift+" + application_invoke_hotkey
            )
            if app._hotkey_handle_application_invoke:
                keyboard.remove_hotkey(app._hotkey_handle_application_invoke)
            app._hotkey_handle_application_invoke = keyboard.add_hotkey(
                settings["hotkey_settings"]["application_invoke_hotkey"]["hotkey"],
                lambda: app.after(0, show_app_request),
            )

        settings["hotkey_settings"]["background_process_hotkey"]["enable"] = (
            app.background_process_hotkey_row.enabled_var.get()
        )

        background_process_hotkey = app.background_process_hotkey_row.key_input.get().lower()
        if background_process_hotkey:
            settings["hotkey_settings"]["background_process_hotkey"]["hotkey"] = (
                "ctrl+shift+" + background_process_hotkey
            )

        settings["enable_focus_dim"] = app.dim_var.get()
        settings["idle_opacity"] = app.opacity_val.get()
        receive_port = app._get_port_or_default(app.receive_file_port_var.get(), 5000)
        upload_port = app._get_port_or_default(app.upload_file_port_var.get(), 5000)
        app.receive_file_port_var.set(str(receive_port))
        app.upload_file_port_var.set(str(upload_port))

        new_receive_enabled = bool(app.receive_file_var.get())
        new_upload_enabled = bool(app.upload_file_var.get())

        if sys.platform == "win32":
            new_receive_enabled, new_upload_enabled = _maybe_apply_windows_firewall(
                app=app,
                old_receive=old_receive,
                old_upload=old_upload,
                receive_port=receive_port,
                upload_port=upload_port,
                new_receive_enabled=new_receive_enabled,
                new_upload_enabled=new_upload_enabled,
            )

        app._persist_transfer_hub_atomic(
            {"enable": new_receive_enabled, "port": receive_port},
            {
                "enable": new_upload_enabled,
                "port": upload_port,
                "remote_url": app.upload_tab_url_entry.get().strip(),
                "remote_token": app.upload_tab_token_entry.get(),
            },
        )
    finally:
        settings.commit()
    app._restart_transfer_hub_if_visible()


def _maybe_apply_windows_firewall(
    *,
    app: Any,
    old_receive: dict[str, Any],
    old_upload: dict[str, Any],
    receive_port: int,
    upload_port: int,
    new_receive_enabled: bool,
    new_upload_enabled: bool,
) -> tuple[bool, bool]:
    from utils.windows_firewall import (
        apply_inbound_transfer_rule_elevated,
        apply_outbound_transfer_rule_elevated,
        inbound_tcp_port_allowed,
        outbound_tcp_port_allowed,
        preview_inbound_transfer_firewall_action,
        preview_outbound_transfer_firewall_action,
        wait_for_inbound_tcp_allowed,
        wait_for_outbound_tcp_allowed,
    )

    user_wants_fw_check = False
    if new_receive_enabled or new_upload_enabled:
        user_wants_fw_check = messagebox.askyesno(
            "Windows Firewall",
            "At least one file transfer port is enabled. Do you want this app to "
            "check Windows Firewall and add or update TCP rules for those ports "
            "if needed?\n\n"
            "This can take a moment and may show a Windows administrator prompt.\n\n"
            "Choose No to save without checking or changing firewall rules.",
        )

    if not user_wants_fw_check:
        return new_receive_enabled, new_upload_enabled

    def _fw_gather() -> dict[str, Any]:
        need_apply_receive = False
        if new_receive_enabled:
            if receive_port != old_receive["port"]:
                need_apply_receive = True
            else:
                need_apply_receive = not inbound_tcp_port_allowed(receive_port)

        need_apply_upload = False
        if new_upload_enabled:
            if upload_port != old_upload["port"]:
                need_apply_upload = True
            else:
                need_apply_upload = not outbound_tcp_port_allowed(upload_port)

        recv_action, recv_remove_names = ("noop", [])
        if need_apply_receive:
            recv_action, recv_remove_names = preview_inbound_transfer_firewall_action(
                int(receive_port)
            )

        upload_action, upload_remove_names = ("noop", [])
        if need_apply_upload:
            upload_action, upload_remove_names = preview_outbound_transfer_firewall_action(
                int(upload_port)
            )
        return {
            "need_apply_receive": need_apply_receive,
            "need_apply_upload": need_apply_upload,
            "recv_action": recv_action,
            "recv_remove_names": recv_remove_names,
            "upload_action": upload_action,
            "upload_remove_names": upload_remove_names,
        }

    state = run_blocking_task_with_busy_ui(
        app,
        app._busy_overlay,
        "Checking Windows Firewall…",
        _fw_gather,
    )
    need_apply_receive = state["need_apply_receive"]
    need_apply_upload = state["need_apply_upload"]
    recv_action = state["recv_action"]
    recv_remove_names = state["recv_remove_names"]
    upload_action = state["upload_action"]
    upload_remove_names = state["upload_remove_names"]

    will_elevate_receive = need_apply_receive and recv_action != "noop"
    will_elevate_upload = need_apply_upload and upload_action != "noop"

    if not need_apply_receive and not need_apply_upload:
        messagebox.showinfo(
            "Windows Firewall",
            "No changes were needed; the TCP ports you selected are already allowed.",
        )
    elif not will_elevate_receive and not will_elevate_upload:
        messagebox.showinfo(
            "Windows Firewall",
            "No changes were needed for this app's firewall rules.",
        )
    else:
        rules_to_remove: list[str] = []
        if recv_action == "replace" and recv_remove_names:
            rules_to_remove.extend(recv_remove_names)
        if upload_action == "replace" and upload_remove_names:
            rules_to_remove.extend(upload_remove_names)
        seen_rm: set[str] = set()
        deduped_remove = []
        for name in rules_to_remove:
            if name not in seen_rm:
                seen_rm.add(name)
                deduped_remove.append(name)

        if deduped_remove:
            listed = "\n".join(f"  • {name}" for name in deduped_remove)
            if not messagebox.askyesno(
                "Windows Firewall",
                "The following existing firewall rules for this app will be "
                f"removed:\n{listed}\n\n"
                "New rules will be added for the TCP ports you enabled. "
                "Continue?",
            ):
                if recv_action == "replace":
                    will_elevate_receive = False
                if upload_action == "replace":
                    will_elevate_upload = False

        if will_elevate_receive or will_elevate_upload:
            messagebox.showinfo(
                "Firewall",
                "If a Windows administrator prompt appears, approve it to "
                "add or update rules.\n\n"
                "Click OK when done so we can verify the changes.",
            )
            if will_elevate_receive:
                if not apply_inbound_transfer_rule_elevated(
                    int(old_receive["port"]),
                    int(receive_port),
                ):
                    messagebox.showerror(
                        "Firewall",
                        "Could not start the firewall rule setup.",
                    )
                    new_receive_enabled = False
                    app.receive_file_var.set(False)
                elif not run_blocking_task_with_busy_ui(
                    app,
                    app._busy_overlay,
                    "Verifying Windows Firewall…",
                    lambda: wait_for_inbound_tcp_allowed(receive_port),
                ):
                    messagebox.showwarning(
                        "Firewall",
                        "Could not confirm the firewall rules. If you cancelled an "
                        "administrator prompt, try again. You can also adjust "
                        "rules manually in Windows Defender Firewall.",
                    )
                    new_receive_enabled = False
                    app.receive_file_var.set(False)
            if will_elevate_upload:
                if not apply_outbound_transfer_rule_elevated(
                    int(old_upload["port"]),
                    int(upload_port),
                ):
                    messagebox.showerror(
                        "Firewall",
                        "Could not start the firewall rule setup.",
                    )
                    new_upload_enabled = False
                    app.upload_file_var.set(False)
                elif not run_blocking_task_with_busy_ui(
                    app,
                    app._busy_overlay,
                    "Verifying Windows Firewall…",
                    lambda: wait_for_outbound_tcp_allowed(upload_port),
                ):
                    messagebox.showwarning(
                        "Firewall",
                        "Could not confirm the firewall rules. If you cancelled an "
                        "administrator prompt, try again. You can also adjust "
                        "rules manually in Windows Defender Firewall.",
                    )
                    new_upload_enabled = False
                    app.upload_file_var.set(False)

    return new_receive_enabled, new_upload_enabled
