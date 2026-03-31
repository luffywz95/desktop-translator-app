from __future__ import annotations

import customtkinter as ctk

from components.image_tab_controls import build_image_tab_controls
from components.text_tab_controls import build_text_tab_controls
from components.tooltip import ToolTip
from components.convert_image_tab_controls import build_convert_image_tab_controls
from components.upload_tab_controls import build_upload_tab_controls
from components.web_crawler_tab_controls import build_web_crawler_tab_controls


def build_main_ui(app, lang_map: dict, settings: dict, dnd_files: str) -> None:
    app.main_frame = ctk.CTkFrame(app, fg_color="transparent")
    app.main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

    app.tab_frame = ctk.CTkTabview(
        app.main_frame,
        corner_radius=0,
        border_width=0,
    )
    app.tab_frame.pack(fill="both", expand=True, padx=0, pady=0)
    app.tab_frame.add("Translation")
    app.tab_frame.add("Upload")
    app.tab_frame.add("Convert Image")
    app.tab_frame.add("Web Crawler")

    _top_tab_widths = {
        "Translation": 98,
        "Upload": 72,
        "Convert Image": 118,
        "Web Crawler": 114,
    }
    for name, button in app.tab_frame._segmented_button._buttons_dict.items():
        button.configure(
            width=_top_tab_widths.get(str(name), 90),
            corner_radius=5,
            font=("Segoe UI", 12, "bold"),
        )

    translation_shell = app.tab_frame.tab("Translation")
    translation_shell.grid_columnconfigure(0, weight=1)
    translation_shell.grid_rowconfigure(0, weight=0)
    translation_shell.grid_rowconfigure(1, weight=0)
    translation_shell.grid_rowconfigure(2, weight=1)
    translation_shell.grid_rowconfigure(3, weight=0)

    app.translation_tabview = ctk.CTkTabview(
        translation_shell,
        height=260,
        corner_radius=0,
        border_width=0,
    )
    app.translation_tabview.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
    app.translation_tabview.add("Image")
    app.translation_tabview.add("Text")

    for button in app.translation_tabview._segmented_button._buttons_dict.values():
        button.configure(
            width=40, height=8, corner_radius=5, font=("Segoe UI", 10, "bold")
        )

    build_image_tab_controls(app, app.translation_tabview, dnd_files)
    build_text_tab_controls(app, app.translation_tabview)

    app.trans_opt_frame = ctk.CTkFrame(translation_shell, fg_color="transparent")
    app.trans_opt_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

    app.trans_cb_main = ctk.CTkCheckBox(
        app.trans_opt_frame, text="Translate to:", command=app._sync_trans_state
    )
    app.trans_cb_main.pack(side="left", padx=(0, 10))

    app.lang_menu_main = ctk.CTkOptionMenu(
        app.trans_opt_frame,
        values=list(lang_map.keys()),
        command=app._sync_lang_state,
    )
    app.lang_menu_main.pack(side="left", fill="x", expand=True)

    app.result_frame = ctk.CTkFrame(translation_shell, fg_color="transparent")
    app.result_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
    app.result_frame.grid_rowconfigure(1, weight=1)
    app.result_frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(app.result_frame, text="Result:").grid(row=0, column=0, sticky="w")
    app.result_box = ctk.CTkTextbox(app.result_frame, height=100, font=("Segoe UI", 13))
    app.result_box.grid(row=1, column=0, sticky="nsew")

    app.copy_btn = ctk.CTkButton(
        app.result_box,
        image=app.copy_icon,
        width=30,
        height=30,
        command=app.copy_result,
        state="disabled",
        fg_color=("#dbdbdb", "#3d3d3d"),
        hover_color=("#cfcfcf", "#4d4d4d"),
        text_color=("#000000", "#ffffff"),
        text="",
        corner_radius=8,
    )
    app.copy_btn.place(relx=0.98, rely=0.95, anchor="se")
    ToolTip(app.copy_btn, "Copy the result to the clipboard")

    app.voice_opt_frame = ctk.CTkFrame(translation_shell, fg_color="transparent")
    app.voice_opt_frame.grid(row=3, column=0, sticky="ew")

    app.current_voices = app._get_voice_list()

    app.selected_voices_dict = {
        voice.id: f"{voice.name} ({voice.gender}, {voice.age})"
        for voice in filter(
            lambda x: [
                x.languages.__contains__(v)
                for v in lang_map[settings["target_lang"]]["tts_lang"]
            ].__contains__(True),
            app.current_voices,
        )
    }

    app.voice_var_main = ctk.StringVar(
        value=list(app.selected_voices_dict.values())[0],
    )
    app.voice_menu_main = ctk.CTkOptionMenu(
        app.voice_opt_frame,
        values=list(app.selected_voices_dict.values()),
        dynamic_resizing=False,
        variable=app.voice_var_main,
    )
    app.voice_menu_main.pack(side="left", fill="x", expand=True)

    app.voice_tooltip = ToolTip(
        app.voice_menu_main, f"Current voice: {app.voice_var_main.get()}"
    )
    app.voice_var_main.trace_add(
        "write",
        lambda value: app.voice_tooltip.update_tip_text(text=f"Current voice: {value}"),
    )

    app.voice_btn = ctk.CTkButton(
        app.voice_opt_frame,
        text="🔊 Speak",
        command=app.toggle_speech,
        state="disabled",
        width=80,
        fg_color="#9b59b6",
        hover_color="#8e44ad",
    )
    app.voice_btn.configure(corner_radius=8, font=("Segoe UI", 13, "bold"))
    app.voice_btn.pack(side="left", fill="x", padx=(5, 0))

    upload_shell = app.tab_frame.tab("Upload")
    build_upload_tab_controls(app, upload_shell, settings, dnd_files)

    convert_shell = app.tab_frame.tab("Convert Image")
    convert_shell.grid_columnconfigure(0, weight=1)
    convert_shell.grid_rowconfigure(0, weight=1)
    build_convert_image_tab_controls(app, convert_shell, dnd_files)

    crawler_shell = app.tab_frame.tab("Web Crawler")
    crawler_shell.grid_columnconfigure(0, weight=1)
    crawler_shell.grid_rowconfigure(0, weight=1)
    build_web_crawler_tab_controls(app, crawler_shell)
