"""UI builder for Text tab controls."""

from __future__ import annotations

import customtkinter as ctk

from components.tooltip import ToolTip


def build_text_tab_controls(app, tab_frame) -> None:
    """Populate Text tab widgets and bind callbacks onto the app instance."""
    app.trans_frame = tab_frame.tab("Text")

    app.trans_text_editor = ctk.CTkTextbox(
        app.trans_frame,
        font=("Segoe UI", 13),
        undo=True,
        autoseparators=True,
    )
    app.trans_text_editor.place(anchor="nw", relheight=0.8, relwidth=1)
    app.trans_text_editor.bind("<Control-v>", app.handle_paste)

    app.btn_frame_2 = ctk.CTkFrame(app.trans_frame, fg_color="transparent")
    app.btn_frame_2.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=-5)

    app.translate_btn = ctk.CTkButton(
        app.btn_frame_2,
        text="🌐 Translate",
        command=app.translate_text,
        width=80,
    )
    app.translate_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
    app.translate_btn.pack(side="right", fill="x")
    ToolTip(app.translate_btn, "Translate the text in the text editor")
