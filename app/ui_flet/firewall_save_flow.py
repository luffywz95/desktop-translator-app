"""Non-blocking Windows Firewall wizard when saving settings in Flet."""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable, Literal

from utils.windows_firewall import (
    TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME,
    TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME,
)
from utils.windows_firewall_settings_flow import gather_transfer_firewall_state

WorkKind = Literal["add", "enable", "replace"]

# on_done(rcv, up, firewall_summary) — firewall_summary is None if user skipped firewall check (intro No).
FirewallDone = Callable[[bool, bool, str | None], None]


def start_flet_firewall_then_save(
    app: Any,
    *,
    old_receive: dict[str, Any],
    old_upload: dict[str, Any],
    receive_port: int,
    upload_port: int,
    new_receive_enabled: bool,
    new_upload_enabled: bool,
    receive_switch: Any,
    upload_switch: Any,
    on_done: FirewallDone,
) -> None:
    _ = receive_switch, upload_switch
    if sys.platform != "win32":
        on_done(new_receive_enabled, new_upload_enabled, None)
        return
    if not (new_receive_enabled or new_upload_enabled):
        on_done(new_receive_enabled, new_upload_enabled, None)
        return

    intro = (
        "At least one file transfer port is enabled. Do you want this app to "
        "check Windows Firewall and add or update TCP rules for those ports "
        "if needed?\n\n"
        "This can take a moment and may show a Windows administrator prompt.\n\n"
        "Choose No to save without checking or changing firewall rules."
    )

    def on_intro_no() -> None:
        on_done(new_receive_enabled, new_upload_enabled, None)

    def on_intro_yes() -> None:
        app.showinfo("Windows Firewall", "Checking Windows Firewall…")

        outcome_lines: list[str] = []

        def flush_done(rcv: bool, up: bool) -> None:
            text = "\n".join(outcome_lines).strip()
            on_done(rcv, up, text or "Firewall: Operation finished.")

        def work() -> dict[str, Any] | None:
            try:
                return gather_transfer_firewall_state(
                    new_receive_enabled=new_receive_enabled,
                    new_upload_enabled=new_upload_enabled,
                    old_receive=old_receive,
                    old_upload=old_upload,
                    receive_port=receive_port,
                    upload_port=upload_port,
                )
            except Exception:
                app.logger.exception("gather_transfer_firewall_state failed")
                return None

        def thread_main() -> None:
            state = work()
            app.run_on_ui(lambda: after_gather(state, outcome_lines, flush_done))

        threading.Thread(target=thread_main, daemon=True).start()

    app.schedule_confirm_dialog(
        "Windows Firewall",
        intro,
        on_yes=on_intro_yes,
        on_no=on_intro_no,
    )

    def after_gather(
        state: dict[str, Any] | None,
        outcome_lines: list[str],
        flush_done: Callable[[bool, bool], None],
    ) -> None:
        if state is None:
            outcome_lines.append(
                "Firewall: Failed — could not read Windows Firewall (inspect error)."
            )
            app.showerror("Windows Firewall", "Could not check Windows Firewall.")
            flush_done(new_receive_enabled, new_upload_enabled)
            return

        from utils.windows_firewall import (
            apply_inbound_rule_enable_elevated,
            apply_inbound_transfer_rule_add_elevated,
            apply_inbound_transfer_rule_elevated,
            apply_outbound_rule_enable_elevated,
            apply_outbound_transfer_rule_add_elevated,
            apply_outbound_transfer_rule_elevated,
            transfer_hub_inbound_rule_ready,
            transfer_hub_outbound_rule_ready,
            try_enable_net_firewall_rule_non_elevated,
            wait_for_transfer_hub_inbound_ready,
            wait_for_transfer_hub_outbound_ready,
        )

        nr = new_receive_enabled
        nu = new_upload_enabled
        recv = state.get("recv")
        upload = state.get("upload")

        if recv and recv["state"] == "error":
            outcome_lines.append(
                "Receive (firewall): Failed to inspect rules — skipped; no rule was added."
            )
        if upload and upload["state"] == "error":
            outcome_lines.append(
                "Upload (firewall): Failed to inspect rules — skipped; no rule was added."
            )

        def resolve_work(
            info: dict[str, Any] | None,
            *,
            user_confirmed_replace: bool,
        ) -> tuple[bool, WorkKind | None, str | None]:
            if info is None:
                return False, None, None
            st = info["state"]
            if st == "error":
                return False, None, None
            if st == "noop":
                return False, None, None
            if st == "add":
                return True, "add", None
            if st == "enable":
                name = info.get("enable_name") or ""
                return True, "enable", name or None
            if st == "confirm_replace":
                if user_confirmed_replace:
                    return True, "replace", None
                return False, None, None
            return False, None, None

        user_recv_replace = True
        user_upload_replace = True

        def proceed_after_confirms() -> None:
            recv_elev, recv_kind, recv_en = resolve_work(recv, user_confirmed_replace=user_recv_replace)
            up_elev, up_kind, up_en = resolve_work(upload, user_confirmed_replace=user_upload_replace)

            recv_enable = recv_en or TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME
            upload_enable = up_en or TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME

            any_work = recv_elev or up_elev
            if not any_work:
                skipped_replace = (
                    (recv and recv["state"] == "confirm_replace" and not user_recv_replace)
                    or (
                        upload
                        and upload["state"] == "confirm_replace"
                        and not user_upload_replace
                    )
                )
                clean_noop = (recv is None or recv["state"] == "noop") and (
                    upload is None or upload["state"] == "noop"
                )
                if clean_noop and not skipped_replace:
                    outcome_lines.append(
                        "Firewall: Success — rules already match your enabled ports (receive/upload)."
                    )
                elif skipped_replace and clean_noop:
                    outcome_lines.append(
                        "Firewall: No changes applied — you declined replacing existing rule(s)."
                    )
                else:
                    outcome_lines.append(
                        "Firewall: No changes applied — rules already match or changes were skipped."
                    )
                dlg_msg = (
                    "Windows Firewall already has the correct rules for your enabled ports."
                    if clean_noop and not skipped_replace
                    else (
                        "No firewall changes will be applied (rules already match your ports, "
                        "or you chose not to replace existing rules)."
                    )
                )
                app.schedule_info_dialog(
                    "Windows Firewall",
                    dlg_msg,
                    on_ok=lambda: flush_done(nr, nu),
                )
                return

            def manual_enable_dialog_receive_then_finish(
                nrr: bool,
                nuu: bool,
                display_name: str,
            ) -> None:
                outcome_lines.append(
                    f"Receive (firewall): Partial — enable rule \"{display_name}\" manually "
                    "in Windows Defender Firewall → Advanced settings → Inbound rules."
                )

                def on_ok() -> None:
                    finish_upload_side(nrr, nuu)

                app.schedule_info_dialog(
                    "Firewall (Receive)",
                    f"The rule \"{display_name}\" exists and includes your port, but it could not "
                    "be enabled automatically (permission denied or UAC cancelled).\n\n"
                    "Please enable it manually in Windows Defender Firewall.",
                    on_ok=on_ok,
                )

            def manual_enable_dialog_upload_then_done(nrr: bool, nuu: bool, display_name: str) -> None:
                outcome_lines.append(
                    f"Upload (firewall): Partial — enable rule \"{display_name}\" manually "
                    "in Windows Defender Firewall → Advanced settings → Outbound rules."
                )

                def on_ok() -> None:
                    flush_done(nrr, nuu)

                app.schedule_info_dialog(
                    "Firewall (Upload)",
                    f"The rule \"{display_name}\" exists and includes your port, but it could not "
                    "be enabled automatically (permission denied or UAC cancelled).\n\n"
                    "Please enable it manually in Windows Defender Firewall.",
                    on_ok=on_ok,
                )

            def finish_upload_side(nrr: bool, nuu: bool) -> None:
                if not up_elev or up_kind is None:
                    flush_done(nrr, nuu)
                    return
                launched = False
                if up_kind == "add":
                    launched = apply_outbound_transfer_rule_add_elevated(int(upload_port))
                elif up_kind == "enable":
                    try_enable_net_firewall_rule_non_elevated(upload_enable)
                    time.sleep(0.35)
                    if transfer_hub_outbound_rule_ready(int(upload_port)):
                        outcome_lines.append(
                            "Upload (firewall): Success — Transfer Hub outbound rule enabled without "
                            "administrator prompt (correct remote port)."
                        )
                        flush_done(nrr, nuu)
                        return
                    launched = apply_outbound_rule_enable_elevated(upload_enable)
                elif up_kind == "replace":
                    launched = apply_outbound_transfer_rule_elevated(
                        int(old_upload["port"]),
                        int(upload_port),
                    )
                if not launched:
                    outcome_lines.append(
                        "Upload (firewall): Failed — could not start administrator prompt for outbound rule."
                    )
                    app.showerror(
                        "Firewall",
                        "Could not start the firewall rule setup.",
                    )
                    flush_done(nrr, nuu)
                    return

                def verify_out() -> None:
                    ok = wait_for_transfer_hub_outbound_ready(int(upload_port))

                    def ui_out() -> None:
                        if up_kind == "enable":
                            if ok and transfer_hub_outbound_rule_ready(int(upload_port)):
                                outcome_lines.append(
                                    "Upload (firewall): Success — Transfer Hub outbound rule enabled "
                                    "and verified (correct remote port)."
                                )
                                flush_done(nrr, nuu)
                            else:
                                manual_enable_dialog_upload_then_done(
                                    nrr, nuu, upload_enable
                                )
                            return
                        if ok:
                            outcome_lines.append(
                                "Upload (firewall): Success — Transfer Hub outbound rule verified "
                                "(correct remote port)."
                            )
                            flush_done(nrr, nuu)
                            return

                        msg_retry_u = (
                            "Could not confirm that the Transfer Hub outbound rule exists, is enabled, "
                            f"and allows remote TCP port {upload_port}. This can happen if a Windows "
                            "administrator prompt timed out, was declined, or the firewall took longer "
                            "than expected to update.\n\n"
                            "Try again? A Windows administrator prompt may appear to add or update the rule."
                        )

                        def on_no_retry_u() -> None:
                            outcome_lines.append(
                                "Upload (firewall): Uncertain — could not verify Transfer Hub outbound rule "
                                "(timeout, UAC cancelled, or rule/port mismatch)."
                            )
                            flush_done(nrr, nuu)

                        def on_yes_retry_u() -> None:
                            launched_r = False
                            if up_kind == "add":
                                launched_r = apply_outbound_transfer_rule_add_elevated(
                                    int(upload_port)
                                )
                            elif up_kind == "replace":
                                launched_r = apply_outbound_transfer_rule_elevated(
                                    int(old_upload["port"]),
                                    int(upload_port),
                                )
                            if not launched_r:
                                outcome_lines.append(
                                    "Upload (firewall): Uncertain — retry skipped; could not start "
                                    "administrator prompt for outbound rule."
                                )
                                flush_done(nrr, nuu)
                                return

                            def verify_out_retry() -> None:
                                ok_r = wait_for_transfer_hub_outbound_ready(int(upload_port))

                                def ui_out_r() -> None:
                                    if ok_r:
                                        outcome_lines.append(
                                            "Upload (firewall): Success — Transfer Hub outbound rule "
                                            "verified (correct remote port) after retry."
                                        )
                                    else:
                                        outcome_lines.append(
                                            "Upload (firewall): Uncertain — still could not verify "
                                            "Transfer Hub outbound rule after retry."
                                        )
                                    flush_done(nrr, nuu)

                                app.run_on_ui(ui_out_r)

                            threading.Thread(target=verify_out_retry, daemon=True).start()

                        app.schedule_confirm_dialog(
                            "Firewall (Upload)",
                            msg_retry_u,
                            on_yes=on_yes_retry_u,
                            on_no=on_no_retry_u,
                        )

                    app.run_on_ui(ui_out)

                threading.Thread(target=verify_out, daemon=True).start()

            def apply_and_verify() -> None:
                if not recv_elev or recv_kind is None:
                    finish_upload_side(nr, nu)
                    return

                if recv_kind == "add":
                    launched_in = apply_inbound_transfer_rule_add_elevated(int(receive_port))
                    if not launched_in:
                        outcome_lines.append(
                            "Receive (firewall): Failed — could not start administrator prompt to add inbound rule."
                        )
                        app.showerror(
                            "Firewall",
                            "Could not start the firewall rule setup.",
                        )
                        finish_upload_side(nr, nu)
                        return

                    def verify_add_in() -> None:
                        ok = wait_for_transfer_hub_inbound_ready(int(receive_port))

                        def ui_add() -> None:
                            if ok:
                                outcome_lines.append(
                                    "Receive (firewall): Success — Transfer Hub inbound rule added "
                                    "and verified (correct local port)."
                                )
                                finish_upload_side(nr, nu)
                                return

                            msg_retry_in_add = (
                                "Could not confirm that the Transfer Hub inbound rule exists, is enabled, "
                                f"and allows local TCP port {receive_port}. This can happen if a Windows "
                                "administrator prompt timed out, was declined, or the firewall took longer "
                                "than expected to update.\n\n"
                                "Try again? A Windows administrator prompt may appear to add the rule."
                            )

                            def on_no_retry_in_add() -> None:
                                outcome_lines.append(
                                    "Receive (firewall): Uncertain — could not verify Transfer Hub inbound rule "
                                    "after add (timeout, UAC cancelled, or rule/port mismatch)."
                                )
                                finish_upload_side(nr, nu)

                            def on_yes_retry_in_add() -> None:
                                launched_r = apply_inbound_transfer_rule_add_elevated(
                                    int(receive_port)
                                )
                                if not launched_r:
                                    outcome_lines.append(
                                        "Receive (firewall): Uncertain — retry skipped; could not start "
                                        "administrator prompt to add inbound rule."
                                    )
                                    finish_upload_side(nr, nu)
                                    return

                                def verify_add_retry() -> None:
                                    ok_r = wait_for_transfer_hub_inbound_ready(int(receive_port))

                                    def ui_add_r() -> None:
                                        if ok_r:
                                            outcome_lines.append(
                                                "Receive (firewall): Success — Transfer Hub inbound rule added "
                                                "and verified (correct local port) after retry."
                                            )
                                        else:
                                            outcome_lines.append(
                                                "Receive (firewall): Uncertain — still could not verify "
                                                "Transfer Hub inbound rule after add retry."
                                            )
                                        finish_upload_side(nr, nu)

                                    app.run_on_ui(ui_add_r)

                                threading.Thread(target=verify_add_retry, daemon=True).start()

                            app.schedule_confirm_dialog(
                                "Firewall (Receive)",
                                msg_retry_in_add,
                                on_yes=on_yes_retry_in_add,
                                on_no=on_no_retry_in_add,
                            )

                        app.run_on_ui(ui_add)

                    threading.Thread(target=verify_add_in, daemon=True).start()
                    return

                if recv_kind == "enable":
                    try_enable_net_firewall_rule_non_elevated(recv_enable)
                    time.sleep(0.35)
                    if transfer_hub_inbound_rule_ready(int(receive_port)):
                        outcome_lines.append(
                            "Receive (firewall): Success — Transfer Hub inbound rule enabled without "
                            "administrator prompt (correct local port)."
                        )
                        finish_upload_side(nr, nu)
                        return
                    launched_in = apply_inbound_rule_enable_elevated(recv_enable)
                    if not launched_in:
                        manual_enable_dialog_receive_then_finish(nr, nu, recv_enable)
                        return

                    def verify_en_in() -> None:
                        ok = wait_for_transfer_hub_inbound_ready(int(receive_port))

                        def ui_en() -> None:
                            if ok and transfer_hub_inbound_rule_ready(int(receive_port)):
                                outcome_lines.append(
                                    "Receive (firewall): Success — Transfer Hub inbound rule enabled "
                                    "and verified (correct local port)."
                                )
                                finish_upload_side(nr, nu)
                            else:
                                manual_enable_dialog_receive_then_finish(nr, nu, recv_enable)

                        app.run_on_ui(ui_en)

                    threading.Thread(target=verify_en_in, daemon=True).start()
                    return

                if recv_kind == "replace":
                    launched_in = apply_inbound_transfer_rule_elevated(
                        int(old_receive["port"]),
                        int(receive_port),
                    )
                    if not launched_in:
                        outcome_lines.append(
                            "Receive (firewall): Failed — could not start administrator prompt to replace inbound rule."
                        )
                        app.showerror(
                            "Firewall",
                            "Could not start the firewall rule setup.",
                        )
                        finish_upload_side(nr, nu)
                        return

                    def verify_rep_in() -> None:
                        ok = wait_for_transfer_hub_inbound_ready(int(receive_port))

                        def ui_rep() -> None:
                            if ok:
                                outcome_lines.append(
                                    "Receive (firewall): Success — Transfer Hub inbound rule replaced "
                                    "and verified (correct local port)."
                                )
                                finish_upload_side(nr, nu)
                                return

                            msg_retry_in_rep = (
                                "Could not confirm that the Transfer Hub inbound rule exists, is enabled, "
                                f"and allows local TCP port {receive_port} after replacing the rule. This can "
                                "happen if a Windows administrator prompt timed out, was declined, or the "
                                "firewall took longer than expected to update.\n\n"
                                "Try again? A Windows administrator prompt may appear to update the rule."
                            )

                            def on_no_retry_in_rep() -> None:
                                outcome_lines.append(
                                    "Receive (firewall): Uncertain — could not verify Transfer Hub inbound rule "
                                    "after replace (timeout, UAC cancelled, or rule/port mismatch)."
                                )
                                finish_upload_side(nr, nu)

                            def on_yes_retry_in_rep() -> None:
                                launched_r = apply_inbound_transfer_rule_elevated(
                                    int(old_receive["port"]),
                                    int(receive_port),
                                )
                                if not launched_r:
                                    outcome_lines.append(
                                        "Receive (firewall): Uncertain — retry skipped; could not start "
                                        "administrator prompt to replace inbound rule."
                                    )
                                    finish_upload_side(nr, nu)
                                    return

                                def verify_rep_retry() -> None:
                                    ok_r = wait_for_transfer_hub_inbound_ready(int(receive_port))

                                    def ui_rep_r() -> None:
                                        if ok_r:
                                            outcome_lines.append(
                                                "Receive (firewall): Success — Transfer Hub inbound rule "
                                                "replaced and verified (correct local port) after retry."
                                            )
                                        else:
                                            outcome_lines.append(
                                                "Receive (firewall): Uncertain — still could not verify "
                                                "Transfer Hub inbound rule after replace retry."
                                            )
                                        finish_upload_side(nr, nu)

                                    app.run_on_ui(ui_rep_r)

                                threading.Thread(target=verify_rep_retry, daemon=True).start()

                            app.schedule_confirm_dialog(
                                "Firewall (Receive)",
                                msg_retry_in_rep,
                                on_yes=on_yes_retry_in_rep,
                                on_no=on_no_retry_in_rep,
                            )

                        app.run_on_ui(ui_rep)

                    threading.Thread(target=verify_rep_in, daemon=True).start()

            app.schedule_info_dialog(
                "Firewall",
                "If a Windows administrator prompt appears, approve it to "
                "add, enable, or update rules.\n\n"
                "Click OK when ready.",
                on_ok=apply_and_verify,
            )

        def ask_upload_replace() -> None:
            if not upload or upload["state"] != "confirm_replace":
                proceed_after_confirms()
                return
            names = "\n".join(f"  • {n}" for n in upload["remove_names"])
            msg = (
                "A Windows Firewall rule exists for upload (outbound) but TCP remote port "
                f"{upload_port} is not included, or the rule must be replaced.\n\n"
                f"Rule(s):\n{names}\n\n"
                "Remove the listed rule(s) and add a new outbound rule for this port?"
            )

            def on_yes() -> None:
                nonlocal user_upload_replace
                user_upload_replace = True
                proceed_after_confirms()

            def on_no() -> None:
                nonlocal user_upload_replace
                user_upload_replace = False
                proceed_after_confirms()

            app.schedule_confirm_dialog(
                "Windows Firewall (Upload)",
                msg,
                on_yes=on_yes,
                on_no=on_no,
            )

        def ask_recv_replace() -> None:
            if not recv or recv["state"] != "confirm_replace":
                ask_upload_replace()
                return
            names = "\n".join(f"  • {n}" for n in recv["remove_names"])
            msg = (
                "A Windows Firewall rule exists for receiving files but TCP local port "
                f"{receive_port} is not included, or the rule must be replaced.\n\n"
                f"Rule(s):\n{names}\n\n"
                "Remove the listed rule(s) and add a new inbound rule for this port?"
            )

            def on_yes() -> None:
                nonlocal user_recv_replace
                user_recv_replace = True
                ask_upload_replace()

            def on_no() -> None:
                nonlocal user_recv_replace
                user_recv_replace = False
                ask_upload_replace()

            app.schedule_confirm_dialog(
                "Windows Firewall (Receive)",
                msg,
                on_yes=on_yes,
                on_no=on_no,
            )

        ask_recv_replace()
