from __future__ import annotations

from logging import Logger
from tkinter import messagebox
from typing import Any

import pyttsx3


def voice_id_for_languages(voices: Any, langs: list[str]) -> str | None:
    for voice in voices:
        if any(lang in voice.languages for lang in langs):
            return voice.id
    return None


def get_installed_voices(logger: Logger) -> Any:
    try:
        temp_engine = pyttsx3.init()
        return temp_engine.getProperty("voices")
    except Exception as e:
        logger.error(f"Error getting voice list: {e}")
        return ["No voices found"]


def speech_worker(
    app: Any,
    text: str,
    *,
    settings: dict[str, Any],
    logger: Logger,
) -> None:
    engine = None
    try:
        app.is_speaking = True
        app.after(
            0,
            lambda: app.voice_btn.configure(
                text="🛑 Speaking...",
                state="disabled",
            ),
        )

        engine = pyttsx3.init()
        engine.setProperty("rate", 150)

        selected_voice_id = next(
            k
            for k, v in app.selected_voices_dict.items()
            if v == app.voice_var_main.get()
        )

        if selected_voice_id:
            engine.setProperty("voice", selected_voice_id)
        else:
            messagebox.showerror(
                "No voice found",
                f'No voice found for "{settings["target_lang"]}". Please install a new voice from the settings.',
            )
            return

        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        logger.error(f"Speech error: {e}")
    finally:
        if engine:
            try:
                engine.stop()
            except Exception as e:
                logger.error(f"Error stopping engine: {e}")
                pass

        app.is_speaking = False
        app.after(
            0, lambda: app.voice_btn.configure(text="🔊 Speak", state="normal")
        )
