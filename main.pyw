from logging import Logger
import os
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinterdnd2.TkinterDnD import _require as _require_tkdnd
from PIL import Image, ImageTk
import pytesseract
import keyboard
import pyperclip
import threading
import time
import ctypes
import socket
import sys
from dotenv import dotenv_values, load_dotenv
import win32gui
import win32process
import win32api
import win32con
from typing import Any

from components.loading_overlay import BusyOverlay, run_blocking_task_with_busy_ui

from app.services.image_source_service import fetch_url_as_image
from app.services.ocr_translation_service import (
    run_ocr_then_translate,
    run_translate_text,
)
from app.services.speech_service import (
    get_installed_voices,
    speech_worker,
    voice_id_for_languages,
)
from app.controllers import bluetooth_picker_controller as bt_picker
from app.controllers import image_source_controller as image_actions
from app.controllers.upload_bluetooth_controller import (
    update_upload_bluetooth_preview,
    upload_bluetooth_browse,
    upload_bluetooth_doctor,
    upload_bluetooth_send_bt,
)
from app.controllers.upload_remote_controller import run_upload_tab_send
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
        self.geometry("400x600")
        self.minsize(400, 650)
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
            settings.begin_batch()
            try:
                old_receive = normalized_receive_file(settings)
                old_upload = normalized_upload_file(settings)

                application_invoke_hotkey = (
                    self.application_invoke_hotkey_row.key_input.get().lower()
                )
                if application_invoke_hotkey:
                    settings["hotkey_settings"]["application_invoke_hotkey"][
                        "hotkey"
                    ] = "ctrl+shift+" + application_invoke_hotkey
                    if self._hotkey_handle_application_invoke:
                        keyboard.remove_hotkey(self._hotkey_handle_application_invoke)
                    self._hotkey_handle_application_invoke = keyboard.add_hotkey(
                        settings["hotkey_settings"]["application_invoke_hotkey"][
                            "hotkey"
                        ],
                        lambda: self.after(0, show_app_request),
                    )

                settings["hotkey_settings"]["background_process_hotkey"]["enable"] = (
                    self.background_process_hotkey_row.enabled_var.get()
                )

                background_process_hotkey = (
                    self.background_process_hotkey_row.key_input.get().lower()
                )
                if background_process_hotkey:
                    settings["hotkey_settings"]["background_process_hotkey"][
                        "hotkey"
                    ] = "ctrl+shift+" + background_process_hotkey

                settings["enable_focus_dim"] = self.dim_var.get()
                settings["idle_opacity"] = self.opacity_val.get()
                _rp = self._get_port_or_default(self.receive_file_port_var.get(), 5000)
                _up = self._get_port_or_default(self.upload_file_port_var.get(), 5000)
                self.receive_file_port_var.set(str(_rp))
                self.upload_file_port_var.set(str(_up))

                new_r_en = bool(self.receive_file_var.get())
                new_u_en = bool(self.upload_file_var.get())

                if sys.platform == "win32":
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
                    if new_r_en or new_u_en:
                        user_wants_fw_check = messagebox.askyesno(
                            "Windows Firewall",
                            "At least one file transfer port is enabled. Do you want this app to "
                            "check Windows Firewall and add or update TCP rules for those ports "
                            "if needed?\n\n"
                            "This can take a moment and may show a Windows administrator prompt.\n\n"
                            "Choose No to save without checking or changing firewall rules.",
                        )

                    if user_wants_fw_check:

                        def _fw_gather() -> dict[str, Any]:
                            need_apply_receive = False
                            if new_r_en:
                                if _rp != old_receive["port"]:
                                    need_apply_receive = True
                                else:
                                    need_apply_receive = not inbound_tcp_port_allowed(_rp)

                            need_apply_upload = False
                            if new_u_en:
                                if _up != old_upload["port"]:
                                    need_apply_upload = True
                                else:
                                    need_apply_upload = not outbound_tcp_port_allowed(_up)

                            recv_action, recv_remove_names = ("noop", [])
                            if need_apply_receive:
                                recv_action, recv_remove_names = (
                                    preview_inbound_transfer_firewall_action(int(_rp))
                                )

                            upload_action, upload_remove_names = ("noop", [])
                            if need_apply_upload:
                                upload_action, upload_remove_names = (
                                    preview_outbound_transfer_firewall_action(int(_up))
                                )
                            return {
                                "need_apply_receive": need_apply_receive,
                                "need_apply_upload": need_apply_upload,
                                "recv_action": recv_action,
                                "recv_remove_names": recv_remove_names,
                                "upload_action": upload_action,
                                "upload_remove_names": upload_remove_names,
                            }

                        st = run_blocking_task_with_busy_ui(
                            self,
                            self._busy_overlay,
                            "Checking Windows Firewall…",
                            _fw_gather,
                        )
                        need_apply_receive = st["need_apply_receive"]
                        need_apply_upload = st["need_apply_upload"]
                        recv_action = st["recv_action"]
                        recv_remove_names = st["recv_remove_names"]
                        upload_action = st["upload_action"]
                        upload_remove_names = st["upload_remove_names"]

                        will_elevate_receive = need_apply_receive and recv_action != "noop"
                        will_elevate_upload = need_apply_upload and upload_action != "noop"

                        if not need_apply_receive and not need_apply_upload:
                            messagebox.showinfo(
                                "Windows Firewall",
                                "No changes were needed; the TCP ports you selected are already "
                                "allowed.",
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
                            for n in rules_to_remove:
                                if n not in seen_rm:
                                    seen_rm.add(n)
                                    deduped_remove.append(n)

                            if deduped_remove:
                                listed = "\n".join(f"  • {n}" for n in deduped_remove)
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
                                        int(old_receive["port"]), int(_rp)
                                    ):
                                        messagebox.showerror(
                                            "Firewall",
                                            "Could not start the firewall rule setup.",
                                        )
                                        new_r_en = False
                                        self.receive_file_var.set(False)
                                    elif not run_blocking_task_with_busy_ui(
                                        self,
                                        self._busy_overlay,
                                        "Verifying Windows Firewall…",
                                        lambda: wait_for_inbound_tcp_allowed(_rp),
                                    ):
                                        messagebox.showwarning(
                                            "Firewall",
                                            "Could not confirm the firewall rules. If you cancelled an "
                                            "administrator prompt, try again. You can also adjust "
                                            "rules manually in Windows Defender Firewall.",
                                        )
                                        new_r_en = False
                                        self.receive_file_var.set(False)
                                if will_elevate_upload:
                                    if not apply_outbound_transfer_rule_elevated(
                                        int(old_upload["port"]), int(_up)
                                    ):
                                        messagebox.showerror(
                                            "Firewall",
                                            "Could not start the firewall rule setup.",
                                        )
                                        new_u_en = False
                                        self.upload_file_var.set(False)
                                    elif not run_blocking_task_with_busy_ui(
                                        self,
                                        self._busy_overlay,
                                        "Verifying Windows Firewall…",
                                        lambda: wait_for_outbound_tcp_allowed(_up),
                                    ):
                                        messagebox.showwarning(
                                            "Firewall",
                                            "Could not confirm the firewall rules. If you cancelled an "
                                            "administrator prompt, try again. You can also adjust "
                                            "rules manually in Windows Defender Firewall.",
                                        )
                                        new_u_en = False
                                        self.upload_file_var.set(False)

                self._persist_transfer_hub_atomic(
                    {"enable": new_r_en, "port": _rp},
                    {
                        "enable": new_u_en,
                        "port": _up,
                        "remote_url": self.upload_tab_url_entry.get().strip(),
                        "remote_token": self.upload_tab_token_entry.get(),
                    },
                )
            finally:
                settings.commit()
            self._restart_transfer_hub_if_visible()

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

    def _fetch_url_as_image(self, url: str) -> Image.Image:
        return fetch_url_as_image(url)

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
        if settings["current_img"]:
            self.result_box.delete("1.0", "end")
            self.result_box.insert("1.0", "⚙️ Processing...")
            thumb = settings["current_img"].copy()
            thumb.thumbnail((500, 220))
            # Use a Tk PhotoImage and store it as an instance attribute
            # to prevent garbage collection issues across multiple updates.
            self.display_img = ImageTk.PhotoImage(thumb)
            self.img_zone.configure(image=self.display_img, text="")

            threading.Thread(target=self._ocr_worker, daemon=True).start()

    def _ocr_worker(self):
        try:
            text = run_ocr_then_translate(
                image=settings["current_img"],
                ocr_langs=settings["ocr_langs"],
                enable_translation=bool(settings["enable_translation"]),
                target_code=LANG_MAP[settings["target_lang"]]["trans_lang"],
            )
            self.after(0, lambda: self._update_results(text))
        except Exception as e:
            self.after(
                0, lambda msg=str(e): self.result_box.insert("end", f"\nError: {msg}")
            )

    # --- Translation Logic ---
    def translate_text(self):
        try:
            text = self.trans_text_editor.get("1.0", "end")
            if not text:
                return

            if not settings["enable_translation"]:
                return self.after(0, lambda: self._update_results(text))

            # 2. Immediate UI Feedback
            self.result_box.delete("1.0", "end")
            self.result_box.insert("1.0", "🌐 Translating...")

            threading.Thread(
                target=self._translation_worker, args=(text,), daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Translation Setup Error: {e}")

    def _translation_worker(self, text):
        try:
            target_lang = settings["target_lang"]
            target_code = LANG_MAP[target_lang]["trans_lang"]
            translation_result = run_translate_text(text, target_code)

            self.after(0, lambda: self._update_results(translation_result))
        except Exception as e:
            logger.error(f"Translation Error: {e}")
            self.after(
                0, lambda msg=str(e): self._update_results(f"Translation Error: {msg}")
            )

    # --- New Voice Logic ---
    def toggle_speech(self):
        text = self.result_box.get("1.0", "end-1c").strip()
        if not text or self.is_speaking:
            # If already speaking, we could add stop logic here,
            # but pyttsx3.stop() is notoriously unstable across threads.
            return

        threading.Thread(
            target=speech_worker,
            args=(self, text),
            kwargs={"settings": settings, "logger": logger},
            daemon=True,
        ).start()

    def _get_voice_id(self, voices, langs):
        return voice_id_for_languages(voices, langs)

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
        upload_bluetooth_browse(self)

    def _update_upload_bluetooth_preview(self, path: str) -> None:
        update_upload_bluetooth_preview(self, path)

    def _upload_bluetooth_send_bt(self) -> None:
        upload_bluetooth_send_bt(self, logger=logger, settings=settings)

    def _upload_bluetooth_doctor(self) -> None:
        upload_bluetooth_doctor(self, logger=logger)

    def _upload_tab_browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose file to upload",
            filetypes=[("All files", "*.*")],
        )
        if path:
            self._upload_local_path = path
            self.upload_tab_path_entry.delete(0, "end")
            self.upload_tab_path_entry.insert(0, path)

    def _upload_tab_send(self) -> None:
        run_upload_tab_send(self)

    def copy_result(self):
        content = self.result_box.get("1.0", "end-1c")
        if content:
            pyperclip.copy(content)

    # --- Install New Voice ---
    def _install_voice_ui(self):
        """Opens Windows Settings directly to the Speech/Voice installation page."""
        import subprocess

        # This URI opens the 'Add a Voice' or Speech settings page directly on Windows 10/11
        subprocess.Popen("start ms-settings:speech", shell=True)

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
