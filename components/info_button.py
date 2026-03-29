import customtkinter as ctk

from components.tooltip import ToolTip


class InfoButton(ctk.CTkButton):
    def __init__(
        self,
        master,
        tooltip_text,
        **kwargs,
    ):
        # 1. Grab the parent's background color so we can mimic it
        # If the master is a CTkFrame, we use its fg_color.
        # If it's the root window, we might need a default like "#2b2b2b"
        bg_color = getattr(master, "cget", lambda x: "#2b2b2b")("fg_color")

        # If the parent color IS "transparent", we have to keep digging or
        # provide a fallback, because hover_color CANNOT be "transparent".
        if bg_color == "transparent":
            bg_color = "#2b2b2b"  # Standard CTk dark theme background

        theme_options = {
            "width": 25,
            "height": 25,
            "fg_color": bg_color,
            "text_color": "#3498db",
            "hover_color": bg_color,
            "font": ("Arial", 14, "bold"),
            "corner_radius": 12,
            "text": "ⓘ",
        }

        theme_options.update(kwargs)

        super().__init__(master, **theme_options)

        ToolTip(self, text=tooltip_text)


# --- Usage Examples ---

# Standard Blue Info
# info = InfoButton(root, "Standard Info")

# Warning Yellow Info
# warning = InfoButton(root, "Be careful!", icon_color="#f1c40f", hover_color="#444400")

# Error Red Info
# error = InfoButton(root, "Critical Error", icon_color="#e74c3c", hover_color="#2c3e50")
