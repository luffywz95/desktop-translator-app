import os
import customtkinter as ctk
from tkinter import messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinterdnd2.TkinterDnD import _require as _require_tkdnd
from PIL import ImageGrab, Image, ImageOps, ImageTk
import pytesseract
import keyboard
import pyperclip
import threading
import ctypes
import sys
from dotenv import load_dotenv
import pyttsx3
import win32gui
import win32process
import win32api
import win32con
import lmdb
import json

from components.tooltip import ToolTip
from components.hot_key_settings_row import HotkeySettingRow
from components.logger import Logger

# --- 1. System & Engine Setup ---
ctypes.windll.shcore.SetProcessDpiAwareness(1)
load_dotenv()

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

state = {
    "settings_open": False,
    "is_pinned": False,
    "enable_translation": False,
    "target_lang": "English",
    "hotkey_settings": {
        "background_process_hotkey": {
            "enable": True,
            "hotkey": "ctrl+shift+x",
        },
        "application_invoke_hotkey": {
            "enable": True,
            "hotkey": "ctrl+shift+q",
        },
    },
    "enable_focus_dim": True,
    "idle_opacity": 1,
    "current_img": None,
    "ocr_langs": "chi_sim+chi_sim_vert+chi_tra+chi_tra_vert+eng+kor+jpn+vie",
}

LANG_MAP = {
    "English": {"trans_lang": "en", "tts_lang": ["en-US"]},
    "Chinese (Simplified)": {"trans_lang": "zh-CN", "tts_lang": ["zh-CN", "zh-Hans"]},
    "Chinese (Traditional)": {"trans_lang": "zh-TW", "tts_lang": ["zh-TW", "zh-HK"]},
    "Japanese": {"trans_lang": "ja", "tts_lang": ["ja-JP"]},
    "Korean": {"trans_lang": "ko", "tts_lang": ["ko-KR"]},
}

logger = Logger().get()

# 1. Initialize the Environment
# map_size is the maximum disk space allocated (e.g., 10MB)
env = lmdb.open("./storage", map_size=10 * 1024 * 1024)


def save_state(key, value):
    # Data must be bytes. We serialize the value to JSON.
    serialized_value = json.dumps(value).encode("utf-8")

    with env.begin(write=True) as txn:
        txn.put(key.encode("utf-8"), serialized_value)


def get_state(key, default=None):
    with env.begin() as txn:
        raw_data = txn.get(key.encode("utf-8"))
        if raw_data is None:
            return default
        return json.loads(raw_data.decode("utf-8"))


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

    def _setup_main_ui(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Create tabs with two tabs: OCR and Text Editor for translation (tab button on the bottom of the tab frame)
        self.tab_frame = ctk.CTkTabview(self.main_frame)
        self.tab_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.tab_frame.add("Image")
        self.tab_frame.add("Text")

        # region OCR Tab
        self.ocr_frame = self.tab_frame.tab("Image")
        self.ocr_frame.configure(height=220)
        self.placeholder_text = "Drag & Drop Image Here\nor press Ctrl+V to paste"
        self.img_zone = ctk.CTkLabel(
            self.ocr_frame,
            text=self.placeholder_text,
            fg_color=("#ebebeb", "#2b2b2b"),
            corner_radius=15,
            text_color="gray",
        )
        self.img_zone.drop_target_register(DND_FILES)
        self.img_zone.dnd_bind("<<Drop>>", self.handle_drop)
        self.img_zone.place(anchor="nw", relheight=0.8, relwidth=1)
        self.bind("<Control-v>", self.handle_paste)

        # Button Frame at the bottom right corner of the OCR frame
        self.btn_frame = ctk.CTkFrame(self.ocr_frame, fg_color="transparent")
        # relx/rely = 1.0 means 100% of the width/height (far right, far bottom)
        # anchor="se" ensures the corner of the frame itself is the attachment point
        self.btn_frame.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=-5)

        self.process_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔄 Process",
            width=100,
            command=self.process_image,
            state="disabled",
        )
        self.process_btn.pack(side="right", fill="x")
        ToolTip(self.process_btn, "Process the image")

        self.clear_btn = ctk.CTkButton(
            self.btn_frame,
            text="🗑️ Clear",
            width=100,
            command=self.clear_all,
            fg_color="#e74c3c",
            hover_color="#c0392b",
        )
        self.clear_btn.pack(side="right", fill="x", padx=(0, 5))
        ToolTip(self.clear_btn, "Clear the image and the result")
        # endregion

        # region Translation Tab
        self.trans_frame = self.tab_frame.tab("Text")
        self.trans_frame.configure(height=220)

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
            width=100,
        )
        ToolTip(self.translate_btn, "Translate the text in the text editor")
        self.translate_btn.pack(side="right", fill="x")
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

        # region Voice Section
        self.voice_opt_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.voice_opt_frame.pack(fill="x", pady=10)

        # Display current voices (Optional: informative only)
        current_voices = self._get_voice_list()
        self.voice_var_main = ctk.StringVar(value=current_voices[0])

        self.voice_menu_main = ctk.CTkOptionMenu(
            self.voice_opt_frame,
            values=current_voices,
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
            lambda *args: self.voice_tooltip.update_tip_text(
                text=f"Current voice: {self.voice_var_main.get()}"
            ),
        )

        self.voice_btn = ctk.CTkButton(
            self.voice_opt_frame,
            text="🔊 Speak",
            command=self.toggle_speech,
            state="disabled",
            width=100,
            fg_color="#9b59b6",
            hover_color="#8e44ad",
        )
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
        def application_invoke_hotkey_event_handler(event=None):
            state["hotkey_settings"]["application_invoke_hotkey"]["hotkey"] = (
                "ctrl+shift+" + event.widget.get().lower()
            )
            if self._hotkey_handle_application_invoke:
                keyboard.remove_hotkey(self._hotkey_handle_application_invoke)
            self._hotkey_handle_application_invoke = keyboard.add_hotkey(
                state["hotkey_settings"]["application_invoke_hotkey"]["hotkey"],
                lambda: self.after(0, show_app_request),
            )

        HotkeySettingRow(
            self.settings_panel,
            label_text="The Hotkey for Application Invoke:",
            default_key="Q",
            is_enabled=state["hotkey_settings"]["application_invoke_hotkey"]["enable"],
            always_enabled=True,
            tooltip_text=None,
            hotkey_event_handler=application_invoke_hotkey_event_handler,
            is_enabled_var_trace=lambda enabled_var_value: state.__setitem__(
                "hotkey_settings",
                "application_invoke_hotkey",
                "enable",
                enabled_var_value,
            ),
        ).pack(pady=(10, 0), padx=30, fill="x")

        # Background Process Hotkey
        HotkeySettingRow(
            self.settings_panel,
            label_text="Enable Hotkey for Background Process:",
            default_key="X",
            is_enabled=state["hotkey_settings"]["background_process_hotkey"]["enable"],
            always_enabled=False,
            tooltip_text="Instant process the recently captured image, the result will be copied to the clipboard",
            hotkey_event_handler=None,
        ).pack(pady=(10, 10), padx=30, fill="x")
        # endregion

        ctk.CTkFrame(
            self.settings_panel,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        ).pack(fill="x", padx=15, pady=10)

        # region Opacity Toggles
        self.dim_var = ctk.BooleanVar(value=state["enable_focus_dim"])
        # Add this "trace" to link the variable back to the dictionary
        self.dim_var.trace_add(
            "write",
            lambda *args: state.__setitem__("enable_focus_dim", self.dim_var.get()),
        )
        ctk.CTkCheckBox(
            self.settings_panel, text="Auto-dim on Focus Lost", variable=self.dim_var
        ).pack(pady=(10, 0), padx=30, anchor="w")

        ctk.CTkLabel(self.settings_panel, text="Focus-out Opacity Level:").pack(
            pady=(10, 0), padx=30, anchor="w"
        )
        self.opacity_slider = ctk.CTkSlider(
            self.settings_panel, from_=0.1, to=1.0, command=self._update_opacity_val
        )
        self.opacity_slider.set(state["idle_opacity"])
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
            command=self.close_settings,
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
        state["is_pinned"] = not state["is_pinned"]
        self.attributes("-topmost", state["is_pinned"])
        self.pin_btn.configure(
            fg_color="#3498db" if state["is_pinned"] else "transparent"
        )

    def open_settings(self):
        state["settings_open"] = True
        self.mask_layer = ctk.CTkFrame(
            self, fg_color="transparent", bg_color="transparent", corner_radius=0
        )
        self.mask_layer.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.settings_modal.place(
            relx=0.5, rely=0.5, anchor="center", relwidth=0.8, relheight=0.6
        )
        self.settings_modal.lift()

    def close_settings(self):
        state["settings_open"] = False
        if self.mask_layer:
            self.mask_layer.destroy()
        if self.settings_modal:
            self.settings_modal.place_forget()
        self.attributes("-alpha", 1.0)

    def _update_opacity_val(self, val):
        state["idle_opacity"] = float(val)

    def _on_focus_in(self, event=None):
        self.attributes("-alpha", 1.0)

    def _on_focus_out(self, event=None):
        if not state["is_pinned"]:
            return
        if state["enable_focus_dim"] and not state["settings_open"]:
            self.attributes("-alpha", state["idle_opacity"])

    def _sync_trans_state(self):
        state["enable_translation"] = self.trans_cb_main.get()
        if state["current_img"]:
            self.process_image()

    def _sync_lang_state(self, choice):
        state["target_lang"] = choice
        if state["enable_translation"] and state["current_img"]:
            self.process_image()

    def _bind_global_hotkey(self):
        if self._hotkey_handle_capture:
            keyboard.remove_hotkey(self._hotkey_handle_capture)

        # Process the image via hotkey
        if state["hotkey_settings"]["background_process_hotkey"]["enable"]:
            self._hotkey_handle_capture = keyboard.add_hotkey(
                state["hotkey_settings"]["background_process_hotkey"]["hotkey"],
                lambda: self.after(0, self.handle_paste),
            )

    def clear_all(self):
        state["current_img"] = None
        # First detach any existing image from the label, then drop the reference.
        # Using a blank image string is safest for Tk's image handling.
        self.img_zone.configure(image="", text=self.placeholder_text)
        self.display_img = None
        self.result_box.delete("1.0", "end")
        self.process_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")

    def handle_drop(self, event):
        try:
            state["current_img"] = Image.open(event.data.strip("{}"))
            self.process_image()
        except Exception as e:
            logger.error(f"Error handling drop: {e}")
            pass

    def handle_paste(self, event=None):
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            state["current_img"] = img
            self.process_image()
            # Check if app is in the foreground
            if (
                state["hotkey_settings"]["background_process_hotkey"]["enable"]
                and self.state() != "normal"
            ):
                self.copy_result()

    # --- OCR Logic ---
    def process_image(self):
        if state["current_img"]:
            self.result_box.delete("1.0", "end")
            self.result_box.insert("1.0", "⚙️ Processing...")
            thumb = state["current_img"].copy()
            thumb.thumbnail((500, 220))
            # Use a Tk PhotoImage and store it as an instance attribute
            # to prevent garbage collection issues across multiple updates.
            self.display_img = ImageTk.PhotoImage(thumb)
            self.img_zone.configure(image=self.display_img, text="")

            threading.Thread(target=self._ocr_worker, daemon=True).start()

    def _ocr_worker(self):
        try:
            img = ImageOps.autocontrast(state["current_img"].convert("L"))
            text = pytesseract.image_to_string(
                img, lang=state["ocr_langs"], config="--psm 6"
            ).strip()
            if text and state["enable_translation"]:
                from deep_translator import GoogleTranslator

                text = GoogleTranslator(
                    source="auto", target=LANG_MAP[state["target_lang"]]["trans_lang"]
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

            if not state["enable_translation"]:
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

            target_lang = state["target_lang"]
            target_code = LANG_MAP[target_lang]["trans_lang"]

            translation_result = GoogleTranslator(
                source="auto", target=target_code
            ).translate(text)

            state["current_lang_choice"] = target_lang

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
            voices = engine.getProperty("voices")
            target_lang = state["current_lang_choice"]
            selected_voice = self._get_voice_id(
                voices, LANG_MAP[target_lang]["tts_lang"]
            )

            if selected_voice:
                engine.setProperty("voice", selected_voice)
            else:
                # TODO: Pop up a message to the user to install a new voice
                messagebox.showerror(
                    "No voice found",
                    f'No voice found for "{target_lang}". Please install a new voice from the settings.',
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
            return [v.name for v in voices]
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
        state["hotkey_settings"]["application_invoke_hotkey"]["hotkey"],
        show_app_request,
    )

    logger.info("Background OCR Tool Active (Resident Mode)...")

    # 4. Start the mainloop on the main thread
    # This keeps the script alive and listening
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
