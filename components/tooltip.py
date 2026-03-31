import customtkinter as ctk


# --- Lightweight Tooltip Helper ---
class ToolTip:
    _active_tooltip = None

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self._show_job = None
        self._hide_job = None
        self._show_delay_ms = 320
        self._auto_hide_ms = 2500

        self.widget.bind("<Enter>", lambda e: self.schedule_show_tip(), add="+")
        # Hide tooltip on mouse leave and mouse click on the widget
        self.widget.bind("<Leave>", lambda e: self.hide_tip(), add="+")
        self.widget.bind("<ButtonPress>", lambda e: self.hide_tip(), add="+")
        self.widget.bind("<FocusOut>", lambda e: self.hide_tip(), add="+")
        self.widget.bind("<Unmap>", lambda e: self.hide_tip(), add="+")
        self.widget.bind("<Destroy>", lambda e: self.hide_tip(), add="+")

    def schedule_show_tip(self):
        if self.tip_window or not self.text:
            return
        self._cancel_scheduled_show()
        self._show_job = self.widget.after(self._show_delay_ms, self.show_tip)

    def _cancel_scheduled_show(self):
        if self._show_job is not None:
            try:
                self.widget.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

    def show_tip(self):
        if self.tip_window or not self.text:
            return

        # Ensure only one tooltip is visible at a time across the app.
        if ToolTip._active_tooltip and ToolTip._active_tooltip is not self:
            ToolTip._active_tooltip.hide_tip()

        # Pointer-based position works for non-text widgets (buttons, frames, etc.).
        x = self.widget.winfo_pointerx() + 14
        y = self.widget.winfo_pointery() + 18
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        ToolTip._active_tooltip = self
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.wm_geometry(f"+{x}+{y}")
        # Also hide when the mouse leaves the tooltip itself or when it is clicked
        tw.bind("<Leave>", lambda e: self.hide_tip(), add="+")
        tw.bind("<ButtonPress>", lambda e: self.hide_tip(), add="+")
        tw.bind("<FocusOut>", lambda e: self.hide_tip(), add="+")
        tw.bind("<Destroy>", lambda e: self.hide_tip(), add="+")
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
        self._schedule_auto_hide()

    def update_tip_text(self, text):
        self.text = text
        if self.tip_window:
            self._destroy_tip_window()
        self.show_tip()

    def _schedule_auto_hide(self):
        self._cancel_auto_hide()
        self._hide_job = self.widget.after(self._auto_hide_ms, self.hide_tip)

    def _cancel_auto_hide(self):
        if self._hide_job is not None:
            try:
                self.widget.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None

    def _destroy_tip_window(self):
        self._cancel_scheduled_show()
        self._cancel_auto_hide()
        if not self.tip_window:
            if ToolTip._active_tooltip is self:
                ToolTip._active_tooltip = None
            return
        try:
            self.tip_window.destroy()
        except Exception:
            pass
        finally:
            self.tip_window = None
            if ToolTip._active_tooltip is self:
                ToolTip._active_tooltip = None

    def hide_tip(self):
        self._destroy_tip_window()
