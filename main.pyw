import os
import customtkinter as ctk
from io import BytesIO
from tkinter import Menu, filedialog, messagebox
import urllib.error
import urllib.request
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinterdnd2.TkinterDnD import _require as _require_tkdnd
from PIL import ImageGrab, Image, ImageOps, ImageTk
import pytesseract
import keyboard
import pyperclip
import threading
import ctypes
import socket
import sys
from dotenv import load_dotenv
import pyttsx3
import win32gui
import win32process
import win32api
import win32con

from components.tooltip import ToolTip
from components.hot_key_settings_row import HotkeySettingRow
from components.logger import Logger

from utils.persistence import (
    StorageEngine,
    default_settings,
    default_lang_map,
)

# Bind app to specific network port when it is running, e.g. 47382, same port number will not be allowed to run again
# Choose a random high port number
lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    lock_socket.bind(("127.0.0.1", 55555))
except socket.error:
    messagebox.showerror("Error", "App is already running!")
    sys.exit(1)

# Write the pid to a file, so that we can kill the app if it is already running
with open("app.pid", "w") as f:
    f.write(str(os.getpid()))

# --- 1. System & Engine Setup ---
ctypes.windll.shcore.SetProcessDpiAwareness(1)
load_dotenv()

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

settings = None
LANG_MAP = None

state_helper = StorageEngine()
settings = state_helper.bind("settings", default_settings)
LANG_MAP = state_helper.bind("lang_map", default_lang_map)

logger = Logger().get()


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

        self.title("The Owl - Translator (Sam·D·Leung)")
        self.geometry("400x600")
        self.minsize(400, 650)
        ctk.set_appearance_mode("system")

        self._hotkey_handle_capture = None
        self.mask_layer = None

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

        start_transfer_hub_server(
            allow_lan=settings.get("transfer_hub_allow_lan", False),
        )

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
        self.menu_bar = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.menu_bar.pack(fill="x", side="top")

        # Requirement 1: Pin Button (Icon Only)
        self.pin_btn = ctk.CTkButton(
            self.menu_bar,
            text="📌",
            width=40,
            height=30,
            fg_color="transparent",
            hover_color="#3d3d3d",
            command=self.toggle_pin,
        )
        self.pin_btn.pack(side="right", padx=(0, 5))

        self.settings_btn = ctk.CTkButton(
            self.menu_bar,
            text="⚙️",
            width=40,
            height=30,
            command=self.open_settings,
            fg_color="transparent",
            font=("Arial", 16),
        )
        self.settings_btn.pack(side="right", padx=10)

    def _restart_transfer_hub_if_visible(self):
        if not self.winfo_viewable():
            return
        from utils.transfer_hub_runner import restart_transfer_hub_server

        restart_transfer_hub_server(
            allow_lan=settings.get("transfer_hub_allow_lan", False),
        )

    def _on_transfer_hub_lan_toggle(self):
        want = self.transfer_hub_lan_var.get()
        if want:
            if sys.platform == "win32":
                from utils.windows_firewall import (
                    add_transfer_hub_rule_elevated,
                    inbound_tcp_port_allowed,
                    wait_for_inbound_tcp_allowed,
                )

                if not inbound_tcp_port_allowed(5000):
                    if not messagebox.askyesno(
                        "Windows Firewall",
                        "To receive uploads from phones and other PCs on your network, "
                        "Windows Firewall needs an inbound rule that allows TCP port 5000.\n\n"
                        "Allow this app to add that rule? (Windows will ask for administrator "
                        "approval on the next step.)",
                    ):
                        self.transfer_hub_lan_var.set(False)
                        return
                    if not add_transfer_hub_rule_elevated(5000):
                        messagebox.showerror(
                            "Firewall",
                            "Could not start the firewall rule setup.",
                        )
                        self.transfer_hub_lan_var.set(False)
                        return
                    messagebox.showinfo(
                        "Firewall",
                        "If a Windows administrator prompt appeared, approve it to add the rule.\n\n"
                        "Click OK when done so we can verify the connection.",
                    )
                    if not wait_for_inbound_tcp_allowed(5000):
                        messagebox.showwarning(
                            "Firewall",
                            "Could not confirm an inbound allow rule for TCP port 5000. "
                            "If you cancelled the administrator prompt, try again. "
                            "Otherwise add the rule manually in Windows Defender Firewall.",
                        )
                        self.transfer_hub_lan_var.set(False)
                        return
            settings["transfer_hub_allow_lan"] = True
        else:
            settings["transfer_hub_allow_lan"] = False
        self._restart_transfer_hub_if_visible()

    def _setup_main_ui(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Create tabs with two tabs: OCR and Text Editor for translation (tab button on the bottom of the tab frame)
        # corner_radius=0, border_width=0 so tab content aligns with main_frame width like trans_opt / result below
        # (default tabview inset uses max(corner_radius, border_width) as inner padx/pady on tab bodies).
        self.tab_frame = ctk.CTkTabview(
            self.main_frame,
            height=260,
            corner_radius=0,
            border_width=0,
        )
        self.tab_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.tab_frame.add("Image")
        self.tab_frame.add("Text")

        # region OCR Tab — grid: preview expands (row 0); button bar pinned to bottom of ocr_frame (row 1)
        self.ocr_frame = self.tab_frame.tab("Image")
        self.ocr_frame.grid_rowconfigure(0, weight=1)
        self.ocr_frame.grid_columnconfigure(0, weight=1)
        self.ocr_frame.grid_rowconfigure(1, weight=0)
        self.placeholder_text = "Drag & Drop Image Here\nor press Ctrl+V to paste"

        self.choose_fail_label = ctk.CTkLabel(
            self.ocr_frame,
            text="",
            font=("Segoe UI", 10),
            text_color="#e74c3c",
            wraplength=320,
            anchor="nw",
            justify="left",
            fg_color="transparent",
        )

        self.img_zone = ctk.CTkLabel(
            self.ocr_frame,
            text=self.placeholder_text,
            fg_color=("#ebebeb", "#2b2b2b"),
            corner_radius=15,
            text_color="gray",
        )
        self.img_zone.pack(fill="both", expand=True)
        self.img_zone.drop_target_register(DND_FILES)
        self.img_zone.dnd_bind("<<Drop>>", self.handle_drop)
        self.bind("<Control-v>", self.handle_paste)

        self.ocr_bottom = ctk.CTkFrame(self.ocr_frame, fg_color="transparent")
        self.ocr_bottom.grid_columnconfigure(0, weight=1)
        self.ocr_bottom.grid_columnconfigure(1, weight=0)
        self.ocr_bottom.grid_rowconfigure(0, weight=0)

        self.url_row = ctk.CTkFrame(self.ocr_bottom, fg_color="transparent")
        self.url_entry = ctk.CTkEntry(
            self.url_row,
            placeholder_text="http://www.example.com/examplefile.pdf",
            placeholder_text_color=("#4A90E2", "#6AB0FF"),
            font=("Segoe UI", 12),
            corner_radius=6,
            border_width=1,
        )
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<Return>", lambda e: self._load_image_from_url_async())
        self.url_load_btn = ctk.CTkButton(
            self.url_row,
            text="Load",
            width=64,
            corner_radius=8,
            font=("Segoe UI", 12, "bold"),
            command=self._load_image_from_url_async,
        )
        self.url_load_btn.pack(side="left", padx=(8, 0))

        self.choose_split_outer = ctk.CTkFrame(
            self.ocr_bottom,
            fg_color="transparent",
        )
        self.choose_file_main_btn = ctk.CTkButton(
            self.choose_split_outer,
            text="📄 Choose file",
            width=120,
            corner_radius=8,
            border_width=0,
            font=("Segoe UI", 13, "bold"),
            command=self._choose_from_device,
            fg_color=("#3b8ed0", "#1f538d"),
            hover_color=("#36719f", "#144870"),
            text_color=("white", "white"),
        )
        self.choose_file_main_btn.pack(side="left")

        self.choose_file_drop_btn = ctk.CTkButton(
            self.choose_split_outer,
            text="▾",
            width=36,
            corner_radius=8,
            font=("Segoe UI", 13, "bold"),
            fg_color=("#6d6d6d", "#3d3d3d"),
            hover_color=("#5c5c5c", "#4d4d4d"),
            text_color=("white", "white"),
            command=self._popup_choose_menu,
        )
        self.choose_file_drop_btn.pack(side="left")

        self.btn_frame = ctk.CTkFrame(self.ocr_bottom, fg_color="transparent")
        self.process_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔄 Process",
            width=80,
            command=self.process_image,
            state="disabled",
        )
        self.process_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
        self.process_btn.pack(side="right", fill="x")
        ToolTip(self.process_btn, "Process the image")

        self.reset_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔃 Reset",
            width=80,
            command=self.clear_all,
            fg_color="#e74c3c",
            hover_color="#c0392b",
        )
        self.reset_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
        self.reset_btn.pack(side="right", fill="x", padx=(0, 5))
        ToolTip(self.reset_btn, "Reset the image and the result")

        self._choose_url_visible = False
        self.choose_split_outer.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.btn_frame.grid(row=1, column=1, sticky="e", padx=(16, 0), pady=(2, 0))

        self.img_zone.grid(row=0, column=0, sticky="nsew")
        # Keep the OCR button bar pinned close to the bottom border (with a bit of spacing).
        self.ocr_bottom.grid(row=1, column=0, sticky="ew", padx=(4, 4), pady=(4, 4))

        self._choose_menu = Menu(self, tearoff=0)
        self._choose_menu.add_command(
            label="From device", command=self._choose_from_device
        )
        self._choose_menu.add_command(
            label="From Dropbox",
            command=lambda: self._choose_from_cloud("Dropbox"),
        )
        self._choose_menu.add_command(
            label="From Google Drive",
            command=lambda: self._choose_from_cloud("Google Drive"),
        )
        self._choose_menu.add_command(
            label="From OneDrive",
            command=lambda: self._choose_from_cloud("OneDrive"),
        )
        self._choose_menu.add_command(
            label="From URL", command=self._choose_from_url_menu
        )
        self._choose_menu.add_command(
            label="From Clipboard", command=self._choose_from_clipboard
        )
        ToolTip(self.choose_file_main_btn, "Pick a file from this PC (or use the menu)")
        ToolTip(self.choose_file_drop_btn, "More sources")
        # endregion

        # region Translation Tab (same relheight=0.8 main area as Image tab)
        self.trans_frame = self.tab_frame.tab("Text")

        self.trans_text_editor = ctk.CTkTextbox(
            self.trans_frame,
            font=("Segoe UI", 13),
            undo=True,  # <--- CRITICAL: Enable the undo stack
            autoseparators=True,  # <--- Automatically creates a "checkpoint" on space/enter
        )
        self.trans_text_editor.place(anchor="nw", relheight=0.8, relwidth=1)
        self.trans_text_editor.bind("<Control-v>", self.handle_paste)

        self.btn_frame_2 = ctk.CTkFrame(self.trans_frame, fg_color="transparent")
        self.btn_frame_2.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=-5)

        self.translate_btn = ctk.CTkButton(
            self.btn_frame_2,
            text="🌐 Translate",
            command=self.translate_text,
            width=80,
        )
        self.translate_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
        self.translate_btn.pack(side="right", fill="x")
        ToolTip(self.translate_btn, "Translate the text in the text editor")
        # endregion

        # region Translation Options
        self.trans_opt_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.trans_opt_frame.pack(fill="x", pady=10)

        self.trans_cb_main = ctk.CTkCheckBox(
            self.trans_opt_frame, text="Translate to:", command=self._sync_trans_state
        )
        self.trans_cb_main.pack(side="left", padx=(0, 10))

        self.lang_menu_main = ctk.CTkOptionMenu(
            self.trans_opt_frame,
            values=list(LANG_MAP.keys()),
            command=self._sync_lang_state,
        )
        self.lang_menu_main.pack(side="left", fill="x", expand=True)
        # endregion

        # region Result Section
        self.result_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(self.result_frame, text="Result:").pack(anchor="w")
        self.result_box = ctk.CTkTextbox(
            self.result_frame, height=100, font=("Segoe UI", 13)
        )
        self.result_box.pack(fill="both", expand=True)

        self.copy_btn = ctk.CTkButton(
            self.result_box,
            image=self.copy_icon,
            width=30,
            height=30,
            command=self.copy_result,
            state="disabled",
            fg_color=("#dbdbdb", "#3d3d3d"),
            hover_color=("#cfcfcf", "#4d4d4d"),
            text_color=("#000000", "#ffffff"),
            text="",
            corner_radius=8,
        )
        self.copy_btn.place(relx=0.98, rely=0.95, anchor="se")
        ToolTip(self.copy_btn, "Copy the result to the clipboard")
        # endregion

        # region Voice Section
        self.voice_opt_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.voice_opt_frame.pack(fill="x", pady=10)

        # Display current voices (Optional: informative only)
        self.current_voices = self._get_voice_list()

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

        self.voice_var_main = ctk.StringVar(
            value=list(self.selected_voices_dict.values())[0],
        )
        self.voice_menu_main = ctk.CTkOptionMenu(
            self.voice_opt_frame,
            values=list(self.selected_voices_dict.values()),
            dynamic_resizing=False,
            variable=self.voice_var_main,
            # command=self._sync_voice_state,
        )
        self.voice_menu_main.pack(side="left", fill="x", expand=True)

        # Show the current voice selected
        self.voice_tooltip = ToolTip(
            self.voice_menu_main, f"Current voice: {self.voice_var_main.get()}"
        )

        self.voice_var_main.trace_add(
            "write",
            lambda value: self.voice_tooltip.update_tip_text(
                text=f"Current voice: {value}"
            ),
        )

        self.voice_btn = ctk.CTkButton(
            self.voice_opt_frame,
            text="🔊 Speak",
            command=self.toggle_speech,
            state="disabled",
            width=80,
            fg_color="#9b59b6",
            hover_color="#8e44ad",
        )
        self.voice_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
        self.voice_btn.pack(side="left", fill="x", padx=(5, 0))
        # endregion

    def _setup_settings_modal(self):
        self.settings_modal = ctk.CTkFrame(
            self, corner_radius=20, border_width=2, fg_color=("#ffffff", "#2b2b2b")
        )
        self.settings_modal.place_forget()

        self.settings_panel = ctk.CTkScrollableFrame(
            self.settings_modal,
            fg_color="transparent",
            corner_radius=0,
            orientation="vertical",  # default is "vertical"
            label_text="Application Settings",
            label_font=("Arial", 18, "bold"),
        )
        # Pack it with a top pady so it respects the modal's top rounded corners
        self.settings_panel.pack(fill="both", expand=True, pady=(10, 0), padx=10)
        # Use grid_configure because the internal structure uses grid
        self.settings_panel._label.grid_configure(pady=(5, 5), padx=20)

        # region Hotkey Settings
        # Application Invoke Hotkey
        self.application_invoke_hotkey_row = HotkeySettingRow(
            self.settings_panel,
            label_text="The Hotkey for Application Invoke:",
            default_key=settings["hotkey_settings"]["application_invoke_hotkey"][
                "hotkey"
            ][-1].upper(),
            is_enabled=settings["hotkey_settings"]["application_invoke_hotkey"][
                "enable"
            ],
            always_enabled=True,
            tooltip_text=None,
            # is_enabled_var_trace=lambda enabled_var_value: settings.__setitem__(
            #     "hotkey_settings",
            #     "application_invoke_hotkey",
            #     "enable",
            #     enabled_var_value,
            # ),
        )
        self.application_invoke_hotkey_row.pack(pady=(10, 0), padx=30, fill="x")

        # Background Process Hotkey
        self.background_process_hotkey_row = HotkeySettingRow(
            self.settings_panel,
            label_text="Enable Hotkey for Background Process:",
            default_key=settings["hotkey_settings"]["background_process_hotkey"][
                "hotkey"
            ][-1].upper(),
            is_enabled=settings["hotkey_settings"]["background_process_hotkey"][
                "enable"
            ],
            always_enabled=False,
            tooltip_text="Instant process the recently captured image, the result will be copied to the clipboard",
        )
        self.background_process_hotkey_row.pack(pady=(10, 10), padx=30, fill="x")
        # endregion

        ctk.CTkFrame(
            self.settings_panel,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        ).pack(fill="x", padx=15, pady=10)

        # region Transfer Hub
        self.transfer_hub_lan_var = ctk.BooleanVar(
            value=settings.get("transfer_hub_allow_lan", False),
        )
        th_row = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        th_row.pack(fill="x", padx=30, pady=(0, 8))
        ctk.CTkLabel(
            th_row,
            text="Enable Transfer Hub",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        self.transfer_hub_lan_switch = ctk.CTkSwitch(
            th_row,
            text="",
            width=44,
            variable=self.transfer_hub_lan_var,
            command=self._on_transfer_hub_lan_toggle,
        )
        self.transfer_hub_lan_switch.pack(side="right", padx=(8, 0))
        ToolTip(
            self.transfer_hub_lan_switch,
            "When on, Transfer Hub listens on your network (TCP 5000). "
            "Windows Firewall must allow inbound traffic on this port.",
        )
        # endregion

        ctk.CTkFrame(
            self.settings_panel,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        ).pack(fill="x", padx=15, pady=10)

        # region Opacity Toggles
        self.dim_var = ctk.BooleanVar(value=settings["enable_focus_dim"])
        ctk.CTkCheckBox(
            self.settings_panel, text="Auto-dim on Focus Lost", variable=self.dim_var
        ).pack(pady=(10, 0), padx=30, anchor="w")

        ctk.CTkLabel(self.settings_panel, text="Focus-out Opacity Level:").pack(
            pady=(10, 0), padx=30, anchor="w"
        )

        self.opacity_val = ctk.DoubleVar(value=settings["idle_opacity"])
        self.opacity_slider = ctk.CTkSlider(
            self.settings_panel, from_=0.1, to=1.0, variable=self.opacity_val
        )
        self.opacity_slider.set(settings["idle_opacity"])
        self.opacity_slider.pack(pady=10, padx=30, fill="x")
        # endregion

        ctk.CTkFrame(
            self.settings_panel,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        ).pack(fill="x", padx=15, pady=10)

        # region Voice Management Section
        # Button to trigger Windows installation
        install_btn = ctk.CTkButton(
            self.settings_panel,
            text="➕ Install New Voices",
            fg_color="#3498db",
            command=self._install_voice_ui,
            height=30,
        )
        install_btn.pack(pady=10, padx=30)
        # endregion

        ctk.CTkFrame(
            self.settings_modal,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        ).pack(fill="x", padx=15, pady=(5, 0))

        self.save_btn = ctk.CTkButton(
            self.settings_modal,
            text="Save & Close",
            corner_radius=12,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=lambda: self.close_settings(save=True),
        )
        self.save_btn.pack(fill="x", padx=25, pady=(10, 20))

        # Close the settings panel via Escape key
        self.bind("<Escape>", lambda event: self.close_settings())

    def _install_voice_ui(self):
        self.voice_management_frame = ctk.CTkFrame(
            self.settings_panel, fg_color="transparent"
        )
        self.voice_management_frame.pack(pady=10, padx=30)

        ctk.CTkLabel(
            self.voice_management_frame,
            text="Voice Management",
            font=("Arial", 16, "bold"),
        ).pack(pady=(20, 5))

        voice_row = ctk.CTkFrame(self.voice_management_frame, fg_color="transparent")
        voice_row.pack(pady=5, padx=30, fill="x")

        # Button to trigger Windows installation
        install_btn = ctk.CTkButton(
            voice_row,
            text="➕ Install New Voices",
            fg_color="#3498db",
            command=self._install_voice_ui,
            height=30,
        )
        install_btn.pack(side="left", expand=True, padx=5)
        ToolTip(
            install_btn, "Opens Windows Settings to download Cantonese, Putonghua, etc."
        )

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
        self.transfer_hub_lan_var.set(settings.get("transfer_hub_allow_lan", False))

    def close_settings(self, save=False):
        settings["settings_open"] = False

        if save:
            settings.begin_batch()
            try:
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
                settings["transfer_hub_allow_lan"] = self.transfer_hub_lan_var.get()
            finally:
                settings.commit()

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

    def _popup_choose_menu(self):
        self.update_idletasks()
        try:
            self._choose_menu.tk_popup(
                self.choose_file_drop_btn.winfo_rootx(),
                self.choose_file_drop_btn.winfo_rooty()
                + self.choose_file_drop_btn.winfo_height(),
            )
        finally:
            try:
                self._choose_menu.grab_release()
            except Exception:
                pass

    def _cloud_folder_candidates(self, name: str):
        home = os.path.expanduser("~")
        if name == "Dropbox":
            return [os.path.join(home, "Dropbox")]
        if name == "Google Drive":
            return [
                os.path.join(home, "Google Drive"),
                os.path.join(home, "My Drive"),
            ]
        if name == "OneDrive":
            return [os.path.join(home, "OneDrive")]
        return []

    def _load_image_path(self, path: str):
        try:
            settings["current_img"] = Image.open(path)
            self._clear_choose_fail()
            self.process_image()
        except Exception as e:
            logger.error(f"Open file failed: {e}")
            self._show_choose_fail(f"Could not open file: {e}")

    def _choose_from_device(self):
        self._hide_url_entry()
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose image or file",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._load_image_path(path)

    def _choose_from_cloud(self, name: str):
        self._hide_url_entry()
        for d in self._cloud_folder_candidates(name):
            if os.path.isdir(d):
                path = filedialog.askopenfilename(
                    parent=self,
                    title=f"Choose from {name}",
                    initialdir=d,
                    filetypes=[
                        (
                            "Images",
                            "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif",
                        ),
                        ("All files", "*.*"),
                    ],
                )
                if path:
                    self._load_image_path(path)
                return
        self._show_choose_fail(
            f"{name} folder not found. Install sync or use From device."
        )

    def _choose_from_url_menu(self):
        self._show_url_entry()

    def _fetch_url_as_image(self, url: str) -> Image.Image:
        u = url.strip()
        if not u.startswith(("http://", "https://")):
            u = "https://" + u
        req = urllib.request.Request(
            u,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TheOwlTranslator/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if len(data) > 25 * 1024 * 1024:
            raise ValueError("Download too large (max 25 MB).")
        bio = BytesIO(data)
        img = Image.open(bio)
        img.load()
        return img

    def _load_image_from_url_async(self):
        if not hasattr(self, "url_entry"):
            return
        url = self.url_entry.get().strip()
        if not url:
            self._show_choose_fail("Enter a URL.")
            return

        self.url_load_btn.configure(state="disabled")

        def work():
            try:
                img = self._fetch_url_as_image(url)

                def ok():
                    self.url_load_btn.configure(state="normal")
                    settings["current_img"] = img
                    self._clear_choose_fail()
                    self.process_image()

                self.after(0, ok)
            except (urllib.error.URLError, OSError, ValueError) as e:
                logger.error(f"URL image load failed: {e}")
                err_msg = str(e)

                def fail():
                    self.url_load_btn.configure(state="normal")
                    self._show_choose_fail(err_msg)

                self.after(0, fail)
            except Exception as e:
                logger.error(f"URL image load failed: {e}")

                def fail2():
                    self.url_load_btn.configure(state="normal")
                    self._show_choose_fail(
                        "Could not load image from URL (unsupported format or error)."
                    )

                self.after(0, fail2)

        threading.Thread(target=work, daemon=True).start()

    def _choose_from_clipboard(self):
        self._hide_url_entry()
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            settings["current_img"] = img
            self._clear_choose_fail()
            self.process_image()
        else:
            self._show_choose_fail("No image in clipboard.")

    def handle_drop(self, event):
        try:
            settings["current_img"] = Image.open(event.data.strip("{}"))
            self.process_image()
        except Exception as e:
            logger.error(f"Error handling drop: {e}")
            pass

    def handle_paste(self, event=None):
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            settings["current_img"] = img
            self.process_image()
            # Check if app is in the foreground
            if (
                settings["hotkey_settings"]["background_process_hotkey"]["enable"]
                and self.state() != "normal"
            ):
                self.copy_result()

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
            img = ImageOps.autocontrast(settings["current_img"].convert("L"))
            text = pytesseract.image_to_string(
                img, lang=settings["ocr_langs"], config="--psm 6"
            ).strip()
            if text and settings["enable_translation"]:
                from deep_translator import GoogleTranslator

                text = GoogleTranslator(
                    source="auto",
                    target=LANG_MAP[settings["target_lang"]]["trans_lang"],
                ).translate(text)
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
            from deep_translator import GoogleTranslator

            target_lang = settings["target_lang"]
            target_code = LANG_MAP[target_lang]["trans_lang"]

            translation_result = GoogleTranslator(
                source="auto", target=target_code
            ).translate(text)

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

        threading.Thread(target=self._speech_worker, args=(text,), daemon=True).start()

    def _speech_worker(self, text):
        engine = None
        try:
            self.is_speaking = True
            self.after(
                0,
                lambda: self.voice_btn.configure(
                    text="🛑 Speaking...", state="disabled"
                ),
            )

            # Re-initialize engine inside thread for stability
            engine = pyttsx3.init()

            # Optional: Set speed
            engine.setProperty("rate", 150)

            # --- Voice Selection Logic ---
            selected_voice_id = next(
                k
                for k, v in self.selected_voices_dict.items()
                if v == self.voice_var_main.get()
            )

            if selected_voice_id:
                engine.setProperty("voice", selected_voice_id)
            else:
                # TODO: Pop up a message to the user to install a new voice
                messagebox.showerror(
                    "No voice found",
                    f'No voice found for "{settings["target_lang"]}". Please install a new voice from the settings.',
                )
                return

            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"Speech error: {e}")
        finally:
            # 4. Cleanup engine to free the driver
            if engine:
                try:
                    engine.stop()
                except Exception as e:
                    logger.error(f"Error stopping engine: {e}")
                    pass  # the "pass" keyword: do nothing

            self.is_speaking = False
            # Re-enable the button on the main thread
            self.after(
                0, lambda: self.voice_btn.configure(text="🔊 Speak", state="normal")
            )

    def _get_voice_id(self, voices, langs):
        for voice in voices:
            if any(lang in voice.languages for lang in langs):
                return voice.id
        return None

    # --- Update results ---
    def _update_results(self, text):
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text if text else "No text found.")
        self.process_btn.configure(state="normal")
        self.copy_btn.configure(state="normal" if text else "disabled")
        self.voice_btn.configure(state="normal" if text else "disabled")

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
        try:
            temp_engine = pyttsx3.init()
            voices = temp_engine.getProperty("voices")
            return voices
        except Exception as e:
            logger.error(f"Error getting voice list: {e}")
            return ["No voices found"]


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

    # Check if we are debugging, if so, we can set the app to be visible
    if "pydevd" in sys.modules or sys.gettrace() is not None:
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
