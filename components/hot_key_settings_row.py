import customtkinter as ctk

from components.tooltip import ToolTip


class HotkeySettingRow(ctk.CTkFrame):
    def __init__(
        self, master, label_text, default_key, is_enabled, tooltip_text, **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        # 1. Label
        ctk.CTkLabel(self, text=label_text).pack(pady=(10, 0), anchor="w")

        # 2. Container for the controls
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", expand=True)

        # 3. Checkbox
        self.enabled_var = ctk.BooleanVar(value=is_enabled)
        self.checkbox = ctk.CTkCheckBox(
            controls_frame, text="Ctrl+Shift+", variable=self.enabled_var
        )
        self.checkbox.pack(side="left", pady=0, fill="x", expand=True, anchor="w")

        # 4. Entry Input
        self.key_input = ctk.CTkEntry(controls_frame, width=35, font=("Segoe UI", 13))
        self.key_input.insert(0, default_key)
        self.key_input.pack(side="left", padx=5)

        # 5. Info Button
        self.info_btn = ctk.CTkButton(
            controls_frame,
            text="ⓘ",
            width=25,
            height=25,
            fg_color="transparent",
            text_color="#3498db",
            font=("Arial", 14, "bold"),
            hover_color="#333333",
        )
        self.info_btn.pack(side="left", padx=5)

        # Add Tooltip
        ToolTip(self.info_btn, tooltip_text)

    def get_settings(self):
        """Helper to retrieve the current state of this row"""
        return {"enabled": self.enabled_var.get(), "key": self.key_input.get()}
