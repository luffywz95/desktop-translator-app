from __future__ import annotations

import threading
from logging import Logger
from typing import Any, Mapping

from utils.upload_bluetooth_service import is_ios_like_name


def _showinfo(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showinfo", None)
    if callable(h):
        h(title, message)


def _showwarning(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showwarning", None)
    if callable(h):
        h(title, message)


def upload_bt_close_picker(app: Any) -> None:
    close_dialog = getattr(app, "close_bluetooth_picker_dialog", None)
    if callable(close_dialog):
        close_dialog()


def upload_bt_refresh_picker_list(app: Any) -> None:
    from utils import bluetooth_transfer as bt

    app._bt_picker_status_value = "Scanning..."
    if hasattr(app, "_safe_page_update"):
        app._safe_page_update()

    def work() -> None:
        err = ""
        try:
            devs = bt.run_coroutine(bt.list_devices_async())
        except Exception as e:
            devs = []
            err = str(e)

        def done() -> None:
            app._bt_picker_devices = devs
            if devs:
                app._bt_picker_status_value = f"{len(devs)} device(s)"
            elif err:
                app._bt_picker_status_value = err[:120]
            else:
                app._bt_picker_status_value = "No devices found"
            app.refresh_bluetooth_picker_dialog()

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()


def upload_bt_selected_info(app: Any) -> Any:
    idx = int(getattr(app, "_bt_picker_selected_idx", -1))
    if idx < 0 or idx >= len(getattr(app, "_bt_picker_devices", [])):
        return None
    return app._bt_picker_devices[idx]


def upload_bt_pair_selected(app: Any) -> None:
    from utils import bluetooth_transfer as bt

    dev = upload_bt_selected_info(app)
    if dev is None:
        _showinfo(app, "Bluetooth", "Select a device in the list.")
        return
    if dev.is_paired:
        _showinfo(app, "Bluetooth", "This device is already paired.")
        return
    if not dev.can_pair:
        _showwarning(
            app,
            "Bluetooth",
            "Pairing is not available for this entry. Use Windows Settings → Bluetooth.",
        )
        return

    app._bt_picker_status_value = "Pairing..."
    app.refresh_bluetooth_picker_dialog()

    def work() -> None:
        ok, msg = bt.run_coroutine(bt.pair_device_async(dev.device_id))

        def done() -> None:
            app._bt_picker_status_value = msg[:120]
            app.refresh_bluetooth_picker_dialog()
            if ok:
                upload_bt_refresh_picker_list(app)
            elif not ok:
                _showwarning(app, "Bluetooth", msg)

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()


def upload_bt_use_selected(
    app: Any, *, logger: Logger, settings: Mapping[str, Any]
) -> None:
    dev = upload_bt_selected_info(app)
    if dev is None:
        _showinfo(app, "Bluetooth", "Select a device in the list.")
        return
    if is_ios_like_name(dev.name):
        logger.info(
            "[Bluetooth] iOS-like device selected: %s (%s)",
            dev.name,
            dev.device_id,
        )
        _showwarning(
            app,
            "Bluetooth",
            "This looks like an iOS device. iOS generally does not support "
            "generic Bluetooth file transfer (OBEX) from Windows.\n\n"
            "Please choose another device, or use another transfer method.",
        )
        settings["bluetooth_upload"] = {"device_id": "", "name": ""}
    else:
        settings["bluetooth_upload"] = {
            "device_id": dev.device_id,
            "name": dev.name,
        }
    app._bt_target_device_id = dev.device_id
    app._bt_target_name = dev.name
    app.upload_bt_device_label.configure(text=f"Device: {dev.name}")
    upload_bt_close_picker(app)


def upload_bt_open_picker(app: Any, *, logger: Logger, settings: Mapping[str, Any]) -> None:
    _ = (logger, settings)
    from utils import bluetooth_transfer as bt

    ok, msg = bt.bluetooth_transfer_available()
    if not ok:
        _showwarning(app, "Bluetooth", msg)
        return

    open_dialog = getattr(app, "open_bluetooth_picker_dialog", None)
    if not callable(open_dialog):
        raise RuntimeError("open_bluetooth_picker_dialog is required")
    app._flet_bt_picker = True
    app._bt_picker_selected_idx = -1
    app._bt_picker_status_value = ""
    open_dialog()
    upload_bt_refresh_picker_list(app)
