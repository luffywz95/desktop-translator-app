from __future__ import annotations

import threading
from logging import Logger
from tkinter import Listbox, Scrollbar, messagebox
from typing import Any, Mapping

import customtkinter as ctk

from utils.upload_bluetooth_service import is_ios_like_name


def upload_bt_close_picker(app: Any) -> None:
    if app._bt_picker_win is not None and app._bt_picker_win.winfo_exists():
        app._bt_picker_win.destroy()
    app._bt_picker_win = None


def upload_bt_refresh_picker_list(app: Any) -> None:
    from utils import bluetooth_transfer as bt

    if app._bt_picker_win is None or not app._bt_picker_win.winfo_exists():
        return
    app._bt_picker_status.configure(text="Scanning…")

    def work() -> None:
        err = ""
        try:
            devs = bt.run_coroutine(bt.list_devices_async())
        except Exception as e:
            devs = []
            err = str(e)

        def done() -> None:
            if app._bt_picker_win is None or not app._bt_picker_win.winfo_exists():
                return
            app._bt_picker_devices = devs
            app._bt_listbox.delete(0, "end")
            for d in devs:
                tag = "paired" if d.is_paired else "nearby"
                app._bt_listbox.insert("end", f"{d.name}  ({tag})")
            if devs:
                app._bt_picker_status.configure(text=f"{len(devs)} device(s)")
            elif err:
                app._bt_picker_status.configure(text=err[:120])
            else:
                app._bt_picker_status.configure(text="No devices found")

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()


def upload_bt_selected_info(app: Any) -> Any:
    lb = getattr(app, "_bt_listbox", None)
    if lb is None or not app._bt_picker_devices:
        return None
    sel = lb.curselection()
    if not sel:
        return None
    i = int(sel[0])
    if i < 0 or i >= len(app._bt_picker_devices):
        return None
    return app._bt_picker_devices[i]


def upload_bt_pair_selected(app: Any) -> None:
    from utils import bluetooth_transfer as bt

    dev = upload_bt_selected_info(app)
    if dev is None:
        messagebox.showinfo("Bluetooth", "Select a device in the list.")
        return
    if dev.is_paired:
        messagebox.showinfo("Bluetooth", "This device is already paired.")
        return
    if not dev.can_pair:
        messagebox.showwarning(
            "Bluetooth",
            "Pairing is not available for this entry. Use Windows Settings → Bluetooth.",
        )
        return

    app._bt_picker_status.configure(text="Pairing…")

    def work() -> None:
        ok, msg = bt.run_coroutine(bt.pair_device_async(dev.device_id))

        def done() -> None:
            if app._bt_picker_win and app._bt_picker_win.winfo_exists():
                app._bt_picker_status.configure(text=msg[:120])
            if ok:
                upload_bt_refresh_picker_list(app)
            elif not ok:
                messagebox.showwarning("Bluetooth", msg)

        app.after(0, done)

    threading.Thread(target=work, daemon=True).start()


def upload_bt_use_selected(
    app: Any, *, logger: Logger, settings: Mapping[str, Any]
) -> None:
    dev = upload_bt_selected_info(app)
    if dev is None:
        messagebox.showinfo("Bluetooth", "Select a device in the list.")
        return
    if is_ios_like_name(dev.name):
        logger.info(
            "[Bluetooth] iOS-like device selected: %s (%s)",
            dev.name,
            dev.device_id,
        )
        messagebox.showwarning(
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
    from utils import bluetooth_transfer as bt

    ok, msg = bt.bluetooth_transfer_available()
    if not ok:
        messagebox.showwarning("Bluetooth", msg)
        return

    if app._bt_picker_win is not None and app._bt_picker_win.winfo_exists():
        app._bt_picker_win.lift()
        upload_bt_refresh_picker_list(app)
        return

    app._bt_picker_win = ctk.CTkToplevel(app)
    app._bt_picker_win.title("Bluetooth devices")
    app._bt_picker_win.geometry("380x420")
    app._bt_picker_win.transient(app)

    topbar = ctk.CTkFrame(app._bt_picker_win, fg_color="transparent")
    topbar.pack(fill="x", padx=10, pady=(10, 6))

    ctk.CTkButton(
        topbar,
        text="↻",
        width=36,
        command=lambda: upload_bt_refresh_picker_list(app),
        font=("Segoe UI", 18),
    ).pack(side="left")
    app._bt_picker_status = ctk.CTkLabel(topbar, text="", font=("Segoe UI", 11))
    app._bt_picker_status.pack(side="left", padx=(8, 0), expand=True, anchor="w")
    ctk.CTkButton(
        topbar,
        text="✕",
        width=36,
        command=lambda: upload_bt_close_picker(app),
        font=("Segoe UI", 14),
    ).pack(side="right")

    list_fr = ctk.CTkFrame(app._bt_picker_win, fg_color="transparent")
    list_fr.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    sb = Scrollbar(list_fr)
    app._bt_listbox = Listbox(
        list_fr,
        height=14,
        yscrollcommand=sb.set,
        font=("Segoe UI", 11),
        bg="#2b2b2b",
        fg="#e7edf5",
        selectbackground="#1f538d",
        selectforeground="white",
        highlightthickness=0,
        bd=0,
    )
    app._bt_listbox.pack(side="left", fill="both", expand=True)
    sb.config(command=app._bt_listbox.yview)
    sb.pack(side="right", fill="y")
    app._bt_listbox.bind(
        "<Double-1>",
        lambda _e: upload_bt_use_selected(app, logger=logger, settings=settings),
    )

    btn_row = ctk.CTkFrame(app._bt_picker_win, fg_color="transparent")
    btn_row.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkButton(
        btn_row,
        text="Pair selected",
        command=lambda: upload_bt_pair_selected(app),
    ).pack(side="left", padx=(0, 6))
    ctk.CTkButton(
        btn_row,
        text="Use selected device",
        fg_color="#2ecc71",
        hover_color="#27ae60",
        command=lambda: upload_bt_use_selected(app, logger=logger, settings=settings),
    ).pack(side="left")

    app._bt_picker_win.protocol(
        "WM_DELETE_WINDOW",
        lambda: upload_bt_close_picker(app),
    )
    upload_bt_refresh_picker_list(app)
