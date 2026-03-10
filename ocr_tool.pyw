from asyncio.windows_events import NULL
import os
import customtkinter as ctk
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

# --- 1. System & Engine Setup ---
ctypes.windll.shcore.SetProcessDpiAwareness(1)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

state = {
    "enable_translation": False,
    "target_lang": "English",
    "enable_shortcut": True,
    "enable_focus_dim": True,
    "idle_opacity": 1,
    "current_img": None,
    "ocr_langs": "chi_sim+chi_tra+eng",
    "settings_open": False,
    "is_pinned": False
}

LANG_MAP = {
    "English": "en", "Chinese (Simplified)": "zh-CN", 
    "Chinese (Traditional)": "zh-TW", "Japanese": "ja", "Korean": "ko"
}

logger = None
def setup_logger():
    global logger
    if not logger:
        logger = logging.getLogger("OCR Tool - Sam Leung")
        logger.setLevel(logging.INFO)
        os.makedirs("logs", exist_ok=True)
        handler = logging.handlers.RotatingFileHandler("logs/ocr_tool.log", maxBytes=1024*1024, backupCount=5)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)
    return logger

# --- Lightweight Tooltip Helper ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", lambda e: self.show_tip())
        self.widget.bind("<Leave>", lambda e: self.hide_tip())

    def show_tip(self):
        if self.tip_window or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(tw, text=self.text, justify="left",
                             fg_color="#333333", text_color="white", 
                             corner_radius=6, padx=10, pady=5)
        label.pack()

    def hide_tip(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class OCRApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        _require_tkdnd(self)

        # set an icon from the assets folder
        self.iconbitmap(os.path.join(os.path.dirname(__file__), "assets", "icon.ico"))

        # set app desktop icon
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.samleung.ocrtool")

        self.title("OCR Desktop Tool")
        self.geometry("400x600")
        self.minsize(400, 650)
        ctk.set_appearance_mode("system")
        
        self._hotkey_handle_capture = None
        self.mask_layer = None 
        
        self._setup_menu()
        self._setup_main_ui()
        self._setup_settings_panel()
        
        self._bind_global_hotkey()
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        
    def show_app(self):
        self.deiconify()     # Bring back from hidden state
        self.lift()          # Move to top of window stack
        self.focus_force()   # Take keyboard focus
        self.attributes("-alpha", 1.0) # Ensure it's opaque

    def _setup_menu(self):
        self.menu_bar = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.menu_bar.pack(fill="x", side="top")
        
        # Requirement 1: Pin Button (Icon Only)
        self.pin_btn = ctk.CTkButton(
            self.menu_bar, text="📌", width=40, height=30, 
            fg_color="transparent", hover_color="#3d3d3d",
            command=self.toggle_pin
        )
        self.pin_btn.pack(side="right", padx=(0, 5))

        self.settings_btn = ctk.CTkButton(
            self.menu_bar, text="⚙️", width=40, height=30, 
            command=self.open_settings, fg_color="transparent", font=("Arial", 16)
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
        self.img_zone = ctk.CTkLabel(self.ocr_frame, text=self.placeholder_text, 
                                     fg_color=("#ebebeb", "#2b2b2b"), corner_radius=15, text_color="gray")
        self.img_zone.pack(fill="x", pady=(0, 15))
        self.img_zone.drop_target_register(DND_FILES)
        self.img_zone.dnd_bind('<<Drop>>', self.handle_drop)
        self.bind('<Control-v>', self.handle_paste)

        # Text Editor for translation Tab
        self.trans_frame = self.tab_frame.tab("Text")
        # set height of frame
        self.trans_frame.configure(height=220)
        self.trans_text_editor = ctk.CTkTextbox(self.trans_frame, height=180, font=("Segoe UI", 13))
        self.trans_text_editor.pack(fill="x", pady=(0, 15))
        self.trans_text_editor.bind("<Control-v>", self.handle_paste)
        # add a button to translate the text
        self.translate_btn = ctk.CTkButton(self.trans_frame, text="🌐 Translate", command=self.translate_text, width=100)
        ToolTip(self.translate_btn, "Translate the text in the text editor")
        self.translate_btn.pack(side="right", padx=(0, 10), fill="x", expand=True)

        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.pack(fill="x", pady=5)
        self.refresh_btn = ctk.CTkButton(self.btn_frame, text="🔄 Refresh", width=100, command=self.process_image, state="disabled")
        self.refresh_btn.pack(side="left", padx=(0, 10))
        self.clear_btn = ctk.CTkButton(self.btn_frame, text="🗑️ Clear", width=100, command=self.clear_all, fg_color="#e74c3c", hover_color="#c0392b")
        self.clear_btn.pack(side="left")

        self.trans_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.trans_frame.pack(fill="x", pady=10)
        self.trans_cb_main = ctk.CTkCheckBox(self.trans_frame, text="Translate to:", command=self._sync_trans_state)
        self.trans_cb_main.pack(side="left", padx=(0, 10))
        self.lang_menu_main = ctk.CTkOptionMenu(self.trans_frame, values=list(LANG_MAP.keys()), command=self._sync_lang_state)
        self.lang_menu_main.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(self.main_frame, text="Result:").pack(anchor="w")
        self.result_box = ctk.CTkTextbox(self.main_frame, height=100, font=("Segoe UI", 13))
        self.result_box.pack(fill="both", expand=True, pady=10)
        self.copy_btn = ctk.CTkButton(self.main_frame, text="📋 Copy to Clipboard", command=self.copy_result, state="disabled", height=45, font=("Arial", 14, "bold"))
        self.copy_btn.pack(fill="x")

    def _setup_settings_panel(self):
        self.settings_panel = ctk.CTkFrame(self, fg_color=("#ffffff", "#2b2b2b"), border_width=2, corner_radius=20)
        ctk.CTkLabel(self.settings_panel, text="Application Settings", font=("Arial", 20, "bold")).pack(pady=20)
        
        # Requirement 2: Shortcut Row with Information Button
        hk_row = ctk.CTkFrame(self.settings_panel, fg_color="transparent")
        hk_row.pack(pady=10, padx=30, fill="x")
        
        self.hk_var = ctk.BooleanVar(value=state["enable_shortcut"])
        ctk.CTkCheckBox(hk_row, text="Enable Shortcut (Ctrl+Shift+X)", variable=self.hk_var).pack(side="left")
        
        info_btn = ctk.CTkButton(hk_row, text="ⓘ", width=25, height=25, fg_color="transparent", 
                                 text_color="#3498db", font=("Arial", 14, "bold"), hover_color="#333333")
        info_btn.pack(side="left", padx=5)
        # info_btn.configure(state="disabled")
        ToolTip(info_btn, "Instant process the recently captured image,\nthe result will be copied to the clipboard")

        # Opacity Toggles
        self.dim_var = ctk.BooleanVar(value=state["enable_focus_dim"])
        ctk.CTkCheckBox(self.settings_panel, text="Auto-dim on Focus Lost", variable=self.dim_var).pack(pady=10, padx=30, anchor="w")

        ctk.CTkLabel(self.settings_panel, text="Focus-out Opacity Level:").pack(pady=(10, 0), padx=30, anchor="w")
        self.opacity_slider = ctk.CTkSlider(self.settings_panel, from_=0.1, to=1.0, command=self._update_opacity_val)
        self.opacity_slider.set(state["idle_opacity"])
        self.opacity_slider.pack(pady=10, padx=30, fill="x")
        
        ctk.CTkButton(self.settings_panel, text="Save & Close", fg_color="#2ecc71", hover_color="#27ae60", command=self.close_settings).pack(pady=30)

        # Close the settings panel via shortcut
        self._hotkey_handle_close = keyboard.add_hotkey('esc', lambda: self.after(0, lambda: self.close_settings()))

    # --- Logic ---
    def toggle_pin(self):
        state["is_pinned"] = not state["is_pinned"]
        self.attributes("-topmost", state["is_pinned"])
        self.pin_btn.configure(fg_color="#3498db" if state["is_pinned"] else "transparent")

    def open_settings(self):
        state["settings_open"] = True
        self.mask_layer = ctk.CTkFrame(self, fg_color="#1a1a1a", bg_color="#1a1a1a", corner_radius=0)
        self.mask_layer.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.settings_panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.8, relheight=0.6)
        self.settings_panel.lift()

    def close_settings(self):
        state["settings_open"] = False
        if self.mask_layer: self.mask_layer.destroy()
        if self.settings_panel: self.settings_panel.place_forget()
        self.attributes("-alpha", 1.0)

    def _update_opacity_val(self, val):
        state["idle_opacity"] = float(val)

    def _on_focus_in(self, event=None):
        self.attributes("-alpha", 1.0)

    def _on_focus_out(self, event=None):
        if state["is_pinned"] == False: return
        if state["enable_focus_dim"] and not state["settings_open"]:
            self.attributes("-alpha", state["idle_opacity"])

    def _sync_trans_state(self):
        state["enable_translation"] = self.trans_cb_main.get()
        if state["current_img"]: self.process_image()

    def _sync_lang_state(self, choice):
        state["target_lang"] = choice
        if state["enable_translation"] and state["current_img"]: self.process_image()

    def _bind_global_hotkey(self):
        if self._hotkey_handle_capture: keyboard.remove_hotkey(self._hotkey_handle_capture)
        # Process the image via shortcut
        if state["enable_shortcut"]:
            self._hotkey_handle_capture = keyboard.add_hotkey('ctrl+shift+x', lambda: self.after(0, self.handle_paste))

    def clear_all(self):
        state["current_img"] = None
        self.img_zone.configure(image=None, text=self.placeholder_text)
        self.result_box.delete("1.0", "end")
        self.refresh_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")

    def handle_drop(self, event):
        try:
            state["current_img"] = Image.open(event.data.strip('{}'))
            self.process_image()
        except: pass

    def handle_paste(self, event=None):
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            state["current_img"] = img
            self.process_image()
            if state["enable_shortcut"]: self.copy_result()

    def process_image(self):
        if state["current_img"]:
            self.result_box.delete("1.0", "end")
            self.result_box.insert("1.0", "⚙️ Processing...")
            thumb = state["current_img"].copy()
            thumb.thumbnail((500, 220))
            self.img_zone.configure(image=ctk.CTkImage(thumb, size=(thumb.width, thumb.height)), text="")
            threading.Thread(target=self._ocr_worker, daemon=True).start()

    def _ocr_worker(self):
        try:
            img = ImageOps.autocontrast(state["current_img"].convert('L'))
            text = pytesseract.image_to_string(img, lang=state["ocr_langs"], config='--psm 6').strip()
            if text and state["enable_translation"]:
                from deep_translator import GoogleTranslator
                text = GoogleTranslator(source='auto', target=LANG_MAP[state["target_lang"]]).translate(text)
            self.after(0, lambda: self._update_results(text))
        except Exception as e:
            self.after(0, lambda: self.result_box.insert("end", f"\nError: {e}"))

    def translate_text(self):
        try:
            text = self.trans_text_editor.get("1.0", "end-1c")
            if text:
                from deep_translator import GoogleTranslator
                text = GoogleTranslator(source='auto', target=LANG_MAP[state["target_lang"]]).translate(text)
                self.after(0, lambda: self._update_results(text))
        except Exception as e:
            self.after(0, lambda: self.result_box.insert("end", f"\nError: {e}"))

    def _update_results(self, text):
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text if text else "No text found.")
        self.refresh_btn.configure(state="normal")
        self.copy_btn.configure(state="normal" if text else "disabled")

    def copy_result(self):
        content = self.result_box.get("1.0", "end-1c")
        if content: pyperclip.copy(content)

def show_app_request():
    """Triggered by hotkey: Safely tells the existing app to show itself."""
    if 'app' in globals() and app.winfo_exists():
        # Use .after() to ensure the command runs in the GUI's own thread context
        app.after(0, app.show_app)
    else:
        logger.error("App instance not found or destroyed.")

if __name__ == "__main__":
    logger = setup_logger()

    # 1. Initialize the app on the MAIN thread
    app = OCRApp()
    
    # 2. Hide it immediately so it stays 'resident' in the background
    app.withdraw() 

    # 3. Register the hotkey to just 'deiconify' (unhide) the app
    # We don't need a separate thread here because the app is already 'alive'
    keyboard.add_hotkey('ctrl+shift+q', show_app_request)

    logger.info("Background OCR Tool Active (Resident Mode)...")

    # 4. Start the mainloop on the main thread
    # This keeps the script alive and listening
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)