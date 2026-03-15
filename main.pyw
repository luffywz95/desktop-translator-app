import os
import customtkinter as ctk
from tkinter import messagebox
from numpy import spacing
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinterdnd2.TkinterDnD import _require as _require_tkdnd
from PIL import ImageGrab, Image, ImageOps
import pytesseract
import keyboard
import pyperclip
import threading
import ctypes
import logging
import logging.handlers
import sys
from dotenv import load_dotenv
import pyttsx3

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

        self.title("OCR Desktop Tool")
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
        self.deiconify()  # Bring back from hidden state
        self.lift()  # Move to top of window stack
        self.focus_force()  # Take keyboard focus
        self.attributes("-alpha", 1.0)  # Ensure it's opaque

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

        # OCR Tab
        self.ocr_frame = self.tab_frame.tab("Image")
        # set height of frame
        self.ocr_frame.configure(height=220)
        self.placeholder_text = "Drag & Drop Image Here\nor press Ctrl+V to paste"
        self.img_zone = ctk.CTkLabel(
            self.ocr_frame,
            text=self.placeholder_text,
            fg_color=("#ebebeb", "#2b2b2b"),
            corner_radius=15,
            text_color="gray",
        )
        self.img_zone.pack(fill="x", pady=(0, 15))
        self.img_zone.drop_target_register(DND_FILES)
        self.img_zone.dnd_bind("<<Drop>>", self.handle_drop)
        self.bind("<Control-v>", self.handle_paste)

        # Button Frame at the bottom right corner of the OCR frame
        self.btn_frame = ctk.CTkFrame(self.ocr_frame, fg_color="transparent")
        # relx/rely = 1.0 means 100% of the width/height (far right, far bottom)
        # anchor="se" ensures the corner of the frame itself is the attachment point
        self.btn_frame.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=-5)

        self.refresh_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔄 Process",
            width=100,
            command=self.process_image,
            state="disabled",
        )
        self.refresh_btn.pack(side="right", fill="x")
        ToolTip(self.refresh_btn, "Process the image")

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

        # Text Editor for translation Tab
        self.trans_frame = self.tab_frame.tab("Text")
        self.trans_frame.configure(height=220)
        self.trans_text_editor = ctk.CTkTextbox(
            self.trans_frame,
            height=170,
            font=("Segoe UI", 13),
            undo=True,  # <--- CRITICAL: Enable the undo stack
            autoseparators=True,  # <--- Automatically creates a "checkpoint" on space/enter
        )
        self.trans_text_editor.pack(fill="x", pady=(0, 0))
        self.trans_text_editor.bind("<Control-v>", self.handle_paste)
        self.translate_btn = ctk.CTkButton(
            self.trans_frame,
            text="🌐 Translate",
            command=self.translate_text,
            width=100,
        )
        ToolTip(self.translate_btn, "Translate the text in the text editor")
        self.translate_btn.pack(side="right", padx=10, pady=0, fill="x")

        self.trans_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.trans_frame.pack(fill="x", pady=10)
        self.trans_cb_main = ctk.CTkCheckBox(
            self.trans_frame, text="Translate to:", command=self._sync_trans_state
        )
        self.trans_cb_main.pack(side="left", padx=(0, 10))
        self.lang_menu_main = ctk.CTkOptionMenu(
            self.trans_frame,
            values=list(LANG_MAP.keys()),
            command=self._sync_lang_state,
        )
        self.lang_menu_main.pack(side="left", fill="x", expand=True)

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

        # Container for Action Buttons
        self.action_btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.action_btn_frame.pack(fill="x")

        # Voice Button
        self.voice_btn = ctk.CTkButton(
            self.action_btn_frame,
            text="🔊 Speak",
            command=self.toggle_speech,
            state="disabled",
            height=45,
            width=100,
            fg_color="#9b59b6",
            hover_color="#8e44ad",
        )
        self.voice_btn.pack(side="right")

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
        self.settings_panel._label.grid_configure(pady=(10, 0), padx=20)

        # region Hotkey Settings
        # Application Invoke Hotkey
        HotkeySettingRow(
            self.settings_panel,
            label_text="Enable Hotkey for Application Invoke:",
            default_key="Q",
            is_enabled=state["hotkey_settings"]["application_invoke_hotkey"]["enable"],
            tooltip_text="Invoke the application",
        ).pack(pady=10, padx=30, fill="x")

        # Background Process Hotkey
        HotkeySettingRow(
            self.settings_panel,
            label_text="Enable Hotkey for Background Process:",
            default_key="X",
            is_enabled=state["hotkey_settings"]["background_process_hotkey"]["enable"],
            tooltip_text="Instant process the recently captured image, the result will be copied to the clipboard",
        ).pack(pady=10, padx=30, fill="x")
        # endregion

        # Opacity Toggles
        self.dim_var = ctk.BooleanVar(value=state["enable_focus_dim"])
        ctk.CTkCheckBox(
            self.settings_panel, text="Auto-dim on Focus Lost", variable=self.dim_var
        ).pack(pady=10, padx=30, anchor="w")

        ctk.CTkLabel(self.settings_panel, text="Focus-out Opacity Level:").pack(
            pady=(10, 0), padx=30, anchor="w"
        )
        self.opacity_slider = ctk.CTkSlider(
            self.settings_panel, from_=0.1, to=1.0, command=self._update_opacity_val
        )
        self.opacity_slider.set(state["idle_opacity"])
        self.opacity_slider.pack(pady=10, padx=30, fill="x")

        # Voice Management Section
        # Button to trigger Windows installation
        install_btn = ctk.CTkButton(
            self.settings_panel,
            text="➕ Install New Voices",
            fg_color="#3498db",
            command=self._install_voice_ui,
            height=30,
        )
        install_btn.pack(pady=10, padx=30)

        separator = ctk.CTkFrame(
            self.settings_modal,
            height=2,
            fg_color=("#dbdbdb", "#3d3d3d"),
            border_width=0,
        )
        separator.pack(fill="x", padx=15, pady=(5, 0))

        self.save_btn = ctk.CTkButton(
            self.settings_modal,
            text="Save & Close",
            corner_radius=12,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self.close_settings,
        )
        self.save_btn.pack(fill="x", padx=25, pady=(10, 20))

        # Close the settings panel via shortcut
        self._hotkey_handle_close = keyboard.add_hotkey(
            "esc", lambda: self.after(0, lambda: self.close_settings())
        )

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

        # Display current voices (Optional: informative only)
        current_voices = self._get_voice_list()
        voice_info = f"Detected: {len(current_voices)} voices"
        ctk.CTkLabel(
            self.voice_management_frame,
            text=voice_info,
            font=("Arial", 10),
            text_color="gray",
        ).pack()

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
            self, fg_color="#1a1a1a", bg_color="#1a1a1a", corner_radius=0
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
        self.display_img = None
        self.img_zone.configure(image=self.display_img, text=self.placeholder_text)
        self.result_box.delete("1.0", "end")
        self.refresh_btn.configure(state="disabled")
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
            if state["hotkey_settings"]["background_process_hotkey"][
                "enable"
            ] and not self.state("active"):
                self.copy_result()

    # --- OCR Logic ---
    def process_image(self):
        if state["current_img"]:
            self.result_box.delete("1.0", "end")
            self.result_box.insert("1.0", "⚙️ Processing...")
            thumb = state["current_img"].copy()
            thumb.thumbnail((500, 220))

            # Store the CTkImage as a class attribute (self.display_img)
            # This prevents garbage collection!
            self.display_img = ctk.CTkImage(
                light_image=thumb, dark_image=thumb, size=(thumb.width, thumb.height)
            )

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
        self.refresh_btn.configure(state="normal")
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

    # 2. Hide it immediately so it stays 'resident' in the background
    app.withdraw()

    # 3. Register the hotkey to just 'deiconify' (unhide) the app
    # We don't need a separate thread here because the app is already 'alive'
    keyboard.add_hotkey("ctrl+shift+q", show_app_request)

    logger.info("Background OCR Tool Active (Resident Mode)...")

    # 4. Start the mainloop on the main thread
    # This keeps the script alive and listening
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
