import customtkinter as ctk

from components.info_button import InfoButton
from components.tooltip import ToolTip


class HotkeySettingRow(ctk.CTkFrame):
    def __init__(
        self,
        master,
        label_text,
        default_key,
        is_enabled,
        always_enabled,
        tooltip_text,
        **kwargs,
    ):
        # 1. REMOVE your custom arguments from kwargs
        # .pop(key, default) removes the key and returns its value
        self.hotkey_event_handler = kwargs.pop("hotkey_event_handler", None)
        self.is_enabled_var_trace = kwargs.pop("is_enabled_var_trace", None)

        # 2. Now kwargs is "clean" (e.g., only contains things like 'width', 'height')
        # Pass the cleaned kwargs to the parent class
        super().__init__(master, fg_color="transparent", **kwargs)

        # 1. Label
        ctk.CTkLabel(self, text=label_text).pack(pady=0, anchor="w")

        # 2. Container for the controls
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", expand=True)

        # 3. Checkbox
        self.enabled_var = ctk.BooleanVar(value=bool(always_enabled or is_enabled))
        if not always_enabled and self.is_enabled_var_trace is not None:
            self.enabled_var.trace_add(
                "write",
                lambda *args: self.is_enabled_var_trace(self.enabled_var.get()),
            )

        self.checkbox = ctk.CTkCheckBox(
            controls_frame, text="", variable=self.enabled_var, width=24
        )
        self.checkbox.pack(side="left", pady=0, anchor="w")
        if always_enabled:
            self.checkbox.configure(state="disabled")
            self.checkbox.configure(fg_color="#808080")  # dim the checkbox
        ctk.CTkLabel(controls_frame, text="Ctrl + Shift + ").pack(
            side="left", padx=(0, 5)
        )

        # 4. Entry Input
        self.key_input = ctk.CTkEntry(controls_frame, width=35, font=("Segoe UI", 13))
        self.key_input.insert(0, default_key)
        self.key_input.pack(side="left", padx=0)
        # Call the event handler when the key is changed
        if self.hotkey_event_handler is not None:
            self.key_input.bind(
                "<KeyRelease>",
                lambda event: self.hotkey_event_handler(event),
            )

        if tooltip_text is not None:
            InfoButton(
                controls_frame,
                tooltip_text,
            ).pack(side="left", padx=(0, 5))

    def get_settings(self):
        """Helper to retrieve the current state of this row"""
        return {"enabled": self.enabled_var.get(), "key": self.key_input.get()}
