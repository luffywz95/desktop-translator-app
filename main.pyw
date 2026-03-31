import os
import customtkinter as ctk
from tkinter import messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinterdnd2.TkinterDnD import _require as _require_tkdnd
from PIL import Image
import pytesseract
import keyboard
import time
import ctypes
import socket
import sys
from dotenv import dotenv_values, load_dotenv
import win32gui
import win32process
import win32api
import win32con
from components.loading_overlay import BusyOverlay

from app.services.speech_service import (
    get_installed_voices,
)
from app.controllers import bluetooth_picker_controller as bt_picker
from app.controllers import app_actions_controller as app_actions
from app.controllers import image_source_controller as image_actions
from app.controllers import settings_controller as settings_actions
from app.controllers import text_processing_controller as text_actions
from app.controllers import upload_bluetooth_controller as bt_upload_actions
from app.controllers import upload_remote_controller as remote_upload_actions
from app.controllers import web_crawler_controller as web_crawler_actions
from app.ui import build_main_ui, build_menu, build_settings_modal
from app.state.context import build_context
from app.state.transfer_settings import (
    get_port_or_default,
    normalized_receive_file,
    normalized_upload_file,
    persist_transfer_hub_atomic,
)

_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_APP_ROOT, ".env")
# Child-only: set by dev auto-reload on Windows so this process binds 55555 after the parent exits.
_RELOAD_STAGGER_ENV = "_DESKTOP_TRANSLATOR_RELOAD_STAGGER"

if os.environ.pop(_RELOAD_STAGGER_ENV, None) == "1":
    time.sleep(0.45)

context = build_context()
logger = context.logger

# Bind app to specific network port when it is running, e.g. 47382, same port number will not be allowed to run again
# Choose a random high port number
lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    lock_socket.bind(("127.0.0.1", 55555))
except socket.error:
    messagebox.showerror("Error", "App is already running!")
    logger.error("App is already running! Port 55555 is already in use.")
    sys.exit(1)

# Write the pid to a file, so that we can kill the app if it is already running
with open("app.pid", "w") as f:
    f.write(str(os.getpid()))

# --- 1. System & Engine Setup ---
ctypes.windll.shcore.SetProcessDpiAwareness(1)
load_dotenv(_ENV_PATH)

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

settings = context.settings
LANG_MAP = context.lang_map


class App(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        _require_tkdnd(self)

        # set an icon from the assets folder
        self.iconbitmap(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))

        # set app desktop icon
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "com.samleung.ocrtool"
        )

        # load the icons
        self.copy_icon = self._load_icon(
            os.path.join(os.path.dirname(__file__), "assets", "copy-lm.png"),
            os.path.join(os.path.dirname(__file__), "assets", "copy-dm.png"),
        )

        self.title("The Owl Nexus (By Sam·D·Leung)")
        self.geometry("420x700")
        self.minsize(420, 700)
        ctk.set_appearance_mode("system")

        self._hotkey_handle_capture = None
        self.mask_layer = None
        self._busy_overlay = BusyOverlay(self)

        self._setup_menu()
        self._setup_main_ui()
        self._setup_settings_modal()

        self._bind_global_hotkey()
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        # Initialize TTS Engine
        self.is_speaking = False

    def withdraw(self):
        """Hide window and stop Transfer Hub — no background upload server when UI is hidden."""
        from utils.transfer_hub_runner import stop_transfer_hub_server

        stop_transfer_hub_server()
        super().withdraw()

    def deiconify(self):
        """Show window and start Transfer Hub only while the user can see the app."""
        super().deiconify()
        from utils.transfer_hub_runner import start_transfer_hub_server

        allow_lan, port = self._receive_listen_params()
        start_transfer_hub_server(allow_lan=allow_lan, port=port)

    def _load_icon(self, light_path, dark_path, size=(20, 20)):
        return ctk.CTkImage(
            light_image=Image.open(light_path),
            dark_image=Image.open(dark_path),
            size=size,
        )

    def show_app(self):
        self.deiconify()

        hwnd = self.winfo_id()

        # 1. Get the thread ID of the current foreground window
        curr_foreground_thread = win32process.GetWindowThreadProcessId(
            win32gui.GetForegroundWindow()
        )[0]
        # 2. Get the thread ID of your own app
        this_thread = win32api.GetCurrentThreadId()

        try:
            # 3. Attach your thread to the foreground thread to "borrow" permission
            if curr_foreground_thread != this_thread:
                win32process.AttachThreadInput(
                    this_thread, curr_foreground_thread, True
                )

                # 4. Perform the focus shift
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwnd)

                # 5. Detach now that we're done
                win32process.AttachThreadInput(
                    this_thread, curr_foreground_thread, False
                )
        except Exception:
            # Fallback if the thread trick fails (e.g., trying to over-ride a system window)
            self.attributes("-topmost", True)
            self.after(10, lambda: self.attributes("-topmost", False))

        self.focus_force()
        self.attributes("-alpha", 1.0)

    def _setup_menu(self):
        build_menu(self)

    def _restart_transfer_hub_if_visible(self):
        if not self.winfo_viewable():
            return
        from utils.transfer_hub_runner import restart_transfer_hub_server

        allow_lan, port = self._receive_listen_params()
        restart_transfer_hub_server(allow_lan=allow_lan, port=port)

    def _get_port_or_default(self, raw: str, default: int = 5000) -> int:
        return get_port_or_default(raw, default)

    def _normalized_receive_file(self) -> dict:
        return normalized_receive_file(settings)

    def _normalized_upload_file(self) -> dict:
        return normalized_upload_file(settings)

    def _receive_listen_params(self) -> tuple[bool, int]:
        r = self._normalized_receive_file()
        return bool(r["enable"]), int(r["port"])

    def _persist_transfer_hub_atomic(self, receive: dict, upload: dict) -> None:
        """Assign whole dicts so LiveState flushes to LMDB (nested mutation does not)."""
        persist_transfer_hub_atomic(settings, receive, upload)

    def _maybe_show_file_transfer_firewall_notice_on_enable(self) -> None:
        """Once per settings panel visit, when any file-transfer switch turns on."""
        if getattr(self, "_file_transfer_fw_notice_shown_this_visit", False):
            return
        self._file_transfer_fw_notice_shown_this_visit = True
        messagebox.showinfo(
            "File transfer",
            "When you save settings, this app may check Windows Firewall and add or change "
            "TCP rules for the ports you configure. That can take a moment and may show a "
            "Windows administrator prompt.",
        )

    def _on_receive_file_toggle(self):
        want = self.receive_file_var.get()
        port = self._get_port_or_default(self.receive_file_port_var.get(), 5000)
        self.receive_file_port_var.set(str(port))
        if want and not getattr(self, "_settings_edge_receive_enable", False):
            self._maybe_show_file_transfer_firewall_notice_on_enable()
        self._settings_edge_receive_enable = bool(want)

    def _on_upload_file_toggle(self):
        want = self.upload_file_var.get()
        port = self._get_port_or_default(self.upload_file_port_var.get(), 5000)
        self.upload_file_port_var.set(str(port))
        if want and not getattr(self, "_settings_edge_upload_enable", False):
            self._maybe_show_file_transfer_firewall_notice_on_enable()
        self._settings_edge_upload_enable = bool(want)

    def _setup_main_ui(self):
        build_main_ui(self, LANG_MAP, settings, DND_FILES)

    def _setup_settings_modal(self):
        build_settings_modal(self, settings)

    # --- Logic ---
    def toggle_pin(self):
        settings["is_pinned"] = not settings["is_pinned"]
        self.attributes("-topmost", settings["is_pinned"])
        self.pin_btn.configure(
            fg_color="#3498db" if settings["is_pinned"] else "transparent"
        )

    def open_settings(self):
        settings["settings_open"] = True

        self.mask_layer = ctk.CTkFrame(
            self, fg_color="transparent", bg_color="transparent", corner_radius=0
        )
        self.mask_layer.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.settings_modal.place(
            relx=0.5, rely=0.5, anchor="center", relwidth=0.8, relheight=0.6
        )
        self.settings_modal.lift()

        self.application_invoke_hotkey_row.key_input.delete(0, "end")
        self.application_invoke_hotkey_row.key_input.insert(
            0,
            settings["hotkey_settings"]["application_invoke_hotkey"]["hotkey"][
                -1
            ].upper(),
        )

        self.background_process_hotkey_row.enabled_var.set(
            settings["hotkey_settings"]["background_process_hotkey"]["enable"]
        )
        self.background_process_hotkey_row.key_input.delete(0, "end")
        self.background_process_hotkey_row.key_input.insert(
            0,
            settings["hotkey_settings"]["background_process_hotkey"]["hotkey"][
                -1
            ].upper(),
        )

        self.dim_var.set(settings["enable_focus_dim"])
        self.opacity_val.set(settings["idle_opacity"])
        _r = self._normalized_receive_file()
        _u = self._normalized_upload_file()
        self.receive_file_var.set(_r["enable"])
        self.receive_file_port_var.set(str(_r["port"]))
        self.upload_file_var.set(_u["enable"])
        self.upload_file_port_var.set(str(_u["port"]))
        self._settings_edge_receive_enable = bool(_r["enable"])
        self._settings_edge_upload_enable = bool(_u["enable"])
        self._file_transfer_fw_notice_shown_this_visit = False
        if hasattr(self, "upload_tab_url_entry"):
            self.upload_tab_url_entry.delete(0, "end")
            self.upload_tab_url_entry.insert(0, _u["remote_url"])
            self.upload_tab_token_entry.delete(0, "end")
            self.upload_tab_token_entry.insert(0, _u["remote_token"])

    def close_settings(self, save=False):
        settings["settings_open"] = False

        if save:
            settings_actions.save_settings_from_modal(
                self,
                settings=settings,
                show_app_request=show_app_request,
            )

        if self.mask_layer:
            self.mask_layer.destroy()
        if self.settings_modal:
            self.settings_modal.place_forget()
        self.attributes("-alpha", 1.0)

    def _on_focus_in(self, event=None):
        self.attributes("-alpha", 1.0)

    def _on_focus_out(self, event=None):
        if not settings["is_pinned"]:
            return
        if settings["enable_focus_dim"] and not settings["settings_open"]:
            self.attributes("-alpha", settings["idle_opacity"])

    def _sync_trans_state(self):
        settings["enable_translation"] = self.trans_cb_main.get()
        if settings["current_img"]:
            self.process_image()

    def _sync_lang_state(self, choice):
        settings["target_lang"] = choice
        if settings["enable_translation"] and settings["current_img"]:
            self.process_image()

        self.selected_voices_dict = {
            voice.id: f"{voice.name} ({voice.gender}, {voice.age})"
            for voice in filter(
                lambda x: [
                    x.languages.__contains__(v)
                    for v in LANG_MAP[settings["target_lang"]]["tts_lang"]
                ].__contains__(True),
                self.current_voices,
            )
        }

        self.voice_menu_main.configure(
            values=list(self.selected_voices_dict.values()),
        )
        self.voice_var_main.set(
            self.selected_voices_dict[0].value,
        )

    def _bind_global_hotkey(self):
        if self._hotkey_handle_capture:
            keyboard.remove_hotkey(self._hotkey_handle_capture)

        # Process the image via hotkey
        if settings["hotkey_settings"]["background_process_hotkey"]["enable"]:
            self._hotkey_handle_capture = keyboard.add_hotkey(
                settings["hotkey_settings"]["background_process_hotkey"]["hotkey"],
                lambda: self.after(0, self.handle_paste),
            )

    def clear_all(self):
        settings["current_img"] = None
        # First detach any existing image from the label, then drop the reference.
        # Using a blank image string is safest for Tk's image handling.
        self.img_zone.configure(image="", text=self.placeholder_text)
        self.display_img = None
        self.result_box.delete("1.0", "end")
        self.process_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self._hide_url_entry()
        self._clear_choose_fail()
        if hasattr(self, "url_entry"):
            self.url_entry.delete(0, "end")

    def _clear_choose_fail(self):
        if hasattr(self, "choose_fail_label"):
            self.choose_fail_label.configure(text="")
            if self.choose_fail_label.winfo_ismapped():
                self.choose_fail_label.grid_remove()

    def _show_choose_fail(self, message: str):
        if not hasattr(self, "choose_fail_label"):
            return
        short = (message or "").strip()
        if len(short) > 160:
            short = short[:157] + "..."
        self.choose_fail_label.configure(text=short)
        if self.choose_fail_label.winfo_ismapped():
            return
        self.choose_fail_label.grid(row=0, column=0, sticky="nw", padx=10, pady=6)
        self.choose_fail_label.lift(self.img_zone)

    def _hide_url_entry(self):
        if not getattr(self, "_choose_url_visible", False):
            return
        self._choose_url_visible = False
        self.url_row.grid_remove()

    def _show_url_entry(self):
        if self._choose_url_visible:
            return
        self._choose_url_visible = True
        self.url_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.after(50, lambda: self.url_entry.focus_set())

    def _load_image_path(self, path: str) -> None:
        image_actions.load_image_path(self, path, settings=settings, logger=logger)

    def _choose_from_device(self) -> None:
        image_actions.choose_from_device(self, settings=settings, logger=logger)

    def _choose_from_cloud(self, name: str) -> None:
        image_actions.choose_from_cloud(self, name, settings=settings, logger=logger)

    def _choose_from_url_menu(self):
        self._show_url_entry()

    def _load_image_from_url_async(self) -> None:
        image_actions.load_image_from_url_async(self, settings=settings, logger=logger)

    def _choose_from_clipboard(self) -> None:
        image_actions.choose_from_clipboard(self, settings=settings)

    def handle_drop(self, event) -> None:
        image_actions.handle_drop(self, event, settings=settings, logger=logger)

    def handle_paste(self, event=None) -> None:
        image_actions.handle_paste(self, event, settings=settings)

    # --- OCR Logic ---
    def process_image(self):
        text_actions.process_image(self, settings=settings, lang_map=LANG_MAP)

    # --- Translation Logic ---
    def translate_text(self):
        text_actions.translate_text(
            self,
            settings=settings,
            lang_map=LANG_MAP,
            logger=logger,
        )

    # --- New Voice Logic ---
    def toggle_speech(self):
        text_actions.toggle_speech(self, settings=settings, logger=logger)

    # --- Update results ---
    def _update_results(self, text):
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text if text else "No text found.")
        self.process_btn.configure(state="normal")
        self.copy_btn.configure(state="normal" if text else "disabled")
        self.voice_btn.configure(state="normal" if text else "disabled")

    def _upload_bt_close_picker(self) -> None:
        bt_picker.upload_bt_close_picker(self)

    def _upload_bt_refresh_picker_list(self) -> None:
        bt_picker.upload_bt_refresh_picker_list(self)

    def _upload_bt_open_picker(self) -> None:
        bt_picker.upload_bt_open_picker(self, logger=logger, settings=settings)

    def _upload_bt_selected_info(self):
        return bt_picker.upload_bt_selected_info(self)

    def _upload_bt_pair_selected(self) -> None:
        bt_picker.upload_bt_pair_selected(self)

    def _upload_bt_use_selected(self) -> None:
        bt_picker.upload_bt_use_selected(self, logger=logger, settings=settings)

    def _upload_bluetooth_browse(self) -> None:
        bt_upload_actions.upload_bluetooth_browse(self)

    def _upload_bluetooth_handle_drop(self, event) -> None:
        bt_upload_actions.upload_bluetooth_handle_drop(self, event)

    def _update_upload_bluetooth_preview(self) -> None:
        bt_upload_actions.update_upload_bluetooth_preview(self)

    def _upload_bluetooth_send_bt(self) -> None:
        bt_upload_actions.upload_bluetooth_send_bt(self, logger=logger, settings=settings)

    def _upload_bluetooth_doctor(self) -> None:
        bt_upload_actions.upload_bluetooth_doctor(self, logger=logger)

    def _upload_tab_browse(self) -> None:
        remote_upload_actions.upload_tab_browse(self)

    def _upload_tab_send(self) -> None:
        remote_upload_actions.run_upload_tab_send(self)

    def _web_crawler_browse_location(self) -> None:
        web_crawler_actions.web_crawler_browse_location(self)

    def _web_crawler_add_field(
        self,
        field_name: str = "",
        selector: str = "",
    ) -> None:
        web_crawler_actions.web_crawler_add_field(
            self,
            field_name=field_name,
            selector=selector,
        )

    def _web_crawler_start(self) -> None:
        web_crawler_actions.web_crawler_start(self, logger=logger)

    def _web_crawler_export(self) -> None:
        web_crawler_actions.web_crawler_export_last(self)

    def _web_crawler_view_items(self) -> None:
        web_crawler_actions.web_crawler_view_items(self)

    def copy_result(self):
        app_actions.copy_result(self)

    # --- Install New Voice ---
    def _install_voice_ui(self):
        app_actions.open_windows_voice_settings()

    def _get_voice_list(self):
        """Utility to get a list of installed voice names for the settings UI."""
        return get_installed_voices(logger)


def show_app_request():
    """Triggered by hotkey: Safely tells the existing app to show itself."""
    if "app" in globals() and app.winfo_exists():
        # Use .after() to ensure the command runs in the GUI's own thread context
        app.after(0, app.show_app)
    else:
        logger.error("App instance not found or destroyed.")


if __name__ == "__main__":
    # 1. Initialize the app on the MAIN thread
    app = App()

    is_debugging = "pydevd" in sys.modules or sys.gettrace() is not None

    is_watching = dotenv_values(_ENV_PATH).get("WATCH_RELOAD") == "1"

    # Check if we are debugging, if so, we can set the app to be visible
    if is_debugging or is_watching:
        app.deiconify()
    else:
        # 2. Hide it immediately so it stays 'resident' in the background
        app.withdraw()

    # 3. Register the hotkey to just 'deiconify' (unhide) the app
    # We don't need a separate thread here because the app is already 'alive'
    app._hotkey_handle_application_invoke = keyboard.add_hotkey(
        settings["hotkey_settings"]["application_invoke_hotkey"]["hotkey"],
        show_app_request,
    )

    logger.info("Background OCR Tool Active (Resident Mode)...")

    # 4. Start the mainloop on the main thread
    # This keeps the script alive and listening
    try:
        app.mainloop()
    except KeyboardInterrupt:
        from utils.transfer_hub_runner import stop_transfer_hub_server

        stop_transfer_hub_server()
        sys.exit(0)

# Run this command to automatically restart the app when files change:
# watchmedo auto-restart --patterns="*.py;*.pyw" --recursive -- python main.pyw
# Run this command to automatically restart the app when files change and kill the previous instance:
# $env:WATCH_RELOAD="1"; watchmedo auto-restart --patterns="*.py;*.pyw" --recursive --kill-after 1 -- python main.pyw
