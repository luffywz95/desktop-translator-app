import customtkinter as ctk


# --- Lightweight Tooltip Helper ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", lambda e: self.show_tip())
        self.widget.bind("<Leave>", lambda e: self.hide_tip())

    def show_tip(self):
        if self.tip_window or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(
            tw,
            text=self.text,
            justify="left",
            fg_color="#333333",
            text_color="white",
            corner_radius=6,
            padx=10,
            pady=5,
        )
        label.pack()

    def hide_tip(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
