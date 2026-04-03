from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from logging import Logger
from typing import Any, Callable

import flet as ft
from PIL import Image

from app.controllers import app_actions_controller as app_actions
from app.controllers import image_source_controller as image_actions
from app.controllers import text_processing_controller as text_actions
from utils.persistence import DEFAULT_TARGET_LANG, normalize_theme_mode_setting
from app.state.transfer_settings import (
    get_port_or_default,
    normalized_receive_file,
    normalized_upload_file,
    persist_transfer_hub_atomic,
)
from utils.transfer_hub_client_url import build_transfer_hub_http_url
from app.services.speech_service import get_installed_voices
from app.ui_flet.theme import GLOBAL_RADIUS, TRANSLATION_ACTION_BUTTON_HEIGHT, input_outline_kwargs


class VarProxy:
    def __init__(self, value: Any = None):
        self._value = value
        self._callbacks: list[Callable[[str, str, str], None]] = []

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value
        for cb in self._callbacks:
            try:
                cb("", "", "")
            except Exception:
                continue

    def trace_add(self, _mode: str, callback: Callable[[str, str, str], None]) -> None:
        self._callbacks.append(callback)


class TextProxy:
    def __init__(self, control: ft.TextField):
        self.control = control

    def delete(self, _start: str = "1.0", _end: str = "end") -> None:
        self.control.value = ""

    def insert(self, index: str, text: str) -> None:
        if index == "end":
            self.control.value = (self.control.value or "") + (text or "")
        else:
            self.control.value = text or ""

    def get(self, _start: str = "1.0", _end: str = "end-1c") -> str:
        return self.control.value or ""

    def winfo_exists(self) -> bool:
        return True

    def see(self, _index: str = "end") -> None:
        return


class EntryProxy:
    def __init__(self, control: ft.TextField):
        self.control = control

    def get(self) -> str:
        return self.control.value or ""

    def delete(self, _start: int = 0, _end: str = "end") -> None:
        self.control.value = ""

    def insert(self, _index: int, text: str) -> None:
        self.control.value = text or ""

    def configure(self, *, state: str | None = None) -> None:
        if state is not None:
            self.control.disabled = state == "disabled"

    def winfo_exists(self) -> bool:
        return True


class ButtonProxy:
    def __init__(self, control: ft.Control):
        self.control = control

    def configure(self, **kwargs: Any) -> None:
        state = kwargs.get("state")
        if state is not None:
            self.control.disabled = state == "disabled"
        text = kwargs.get("text")
        if text is not None:
            if hasattr(self.control, "text"):
                self.control.text = text
            elif hasattr(self.control, "content"):
                self.control.content = text

    def winfo_exists(self) -> bool:
        return True


class LabelProxy:
    def __init__(self, control: ft.Text):
        self.control = control
        self._visible = False

    def configure(self, **kwargs: Any) -> None:
        if "text" in kwargs:
            self.control.value = kwargs["text"]

    def winfo_ismapped(self) -> bool:
        return self._visible

    def grid_remove(self) -> None:
        self._visible = False
        self.control.visible = False

    def grid(self, **_kwargs: Any) -> None:
        self._visible = True
        self.control.visible = True

    def lift(self, _target: Any = None) -> None:
        return


@dataclass(slots=True)
class HotkeyRowProxy:
    key_input: EntryProxy
    enabled_var: VarProxy


class FletAppBridge:
    def __init__(self, page: ft.Page, *, settings: Any, lang_map: dict[str, Any], logger: Logger):
        self.page = page
        self.settings = settings
        self.lang_map = lang_map
        self.logger = logger
        self.theme_mode = normalize_theme_mode_setting(settings.get("theme_mode"))
        self.is_speaking = False
        self.placeholder_text = (
            "Use Choose file, drag file(s) onto the window (Windows desktop), or From URL"
        )
        self._choose_url_visible = False
        self.display_img = None
        self._scroll_preview_dialog: ft.AlertDialog | None = None
        self._paste_image_shortcut_armed = False
        self._window_focused = True

        self.current_voices = get_installed_voices(logger)
        self.selected_voices_dict: dict[str, str] = {}
        self.voice_var_main = VarProxy("")
        self._timer_handles: set[threading.Timer] = set()

    def _safe_page_update(self) -> None:
        try:
            self.page.update()
        except Exception:
            # Page may already be disposed during shutdown.
            return

    def run_on_ui(self, callback: Callable[[], None]) -> None:
        async def _runner() -> None:
            try:
                callback()
            except Exception:
                self.logger.exception("Flet UI callback failed")
            self._safe_page_update()

        try:
            self.page.run_task(_runner)
        except Exception:
            return

    def after(self, ms: int, callback: Callable[[], None]) -> None:
        if ms <= 0:
            self.run_on_ui(callback)
            return None

        timer = threading.Timer(ms / 1000, lambda: self.run_on_ui(callback))
        timer.daemon = True
        self._timer_handles.add(timer)
        timer.start()
        return timer

    def after_cancel(self, handle: Any) -> None:
        if isinstance(handle, threading.Timer):
            try:
                handle.cancel()
            except Exception:
                return
            self._timer_handles.discard(handle)

    def state(self) -> str:
        # Tk uses non-"normal" when minimized/unfocused; drives background hotkey auto-copy.
        return "normal" if self._window_focused else "iconic"

    def winfo_exists(self) -> bool:
        return True

    def _get_port_or_default(self, raw: str, default: int = 5000) -> int:
        return get_port_or_default(raw, default)

    def _normalized_receive_file(self) -> dict[str, Any]:
        return normalized_receive_file(self.settings)

    def _normalized_upload_file(self) -> dict[str, Any]:
        return normalized_upload_file(self.settings)

    def _persist_transfer_hub_atomic(self, receive: dict[str, Any], upload: dict[str, Any]) -> None:
        persist_transfer_hub_atomic(self.settings, receive, upload)

    def _receive_listen_params(self) -> tuple[bool, int]:
        r = self._normalized_receive_file()
        return bool(r["enable"]), int(r["port"])

    def transfer_hub_display_url(self) -> str:
        allow_lan, port = self._receive_listen_params()
        return build_transfer_hub_http_url(allow_lan=allow_lan, port=port)

    def local_transfer_hub_tunnel_target_url(self) -> str:
        """HTTP URL on loopback for Cloudflare Tunnel (or similar) to proxy to the Transfer Hub."""
        _enable, port = self._receive_listen_params()
        return f"http://127.0.0.1:{int(port)}/"

    def _ensure_transfer_hub_running(self) -> None:
        try:
            from utils.transfer_hub_runner import start_transfer_hub_server
        except Exception:
            self.logger.exception("Transfer Hub import failed (start)")
            return
        try:
            allow_lan, port = self._receive_listen_params()
            start_transfer_hub_server(allow_lan=allow_lan, port=port)
        except Exception:
            self.logger.exception("Transfer Hub start failed")

    def _stop_transfer_hub_session(self) -> None:
        try:
            from utils.transfer_hub_runner import stop_transfer_hub_server

            stop_transfer_hub_server()
        except Exception:
            self.logger.exception("Transfer Hub stop failed")

    def _on_window_event(self, e: ft.WindowEvent) -> None:
        if e.type == ft.WindowEventType.FOCUS:
            self._window_focused = True
        elif e.type == ft.WindowEventType.BLUR:
            self._window_focused = False

    def _arm_paste_image_shortcut(self, _e: ft.ControlEvent | None = None) -> None:
        self._paste_image_shortcut_armed = True

    def _disarm_paste_image_shortcut(self, _e: ft.ControlEvent | None = None) -> None:
        self._paste_image_shortcut_armed = False

    def _on_page_keyboard_event(self, e: ft.KeyboardEvent) -> None:
        if e.key == "Escape" and self.settings.get("settings_open"):
            if hasattr(self, "close_settings"):
                self.close_settings()
            return

        if not self._paste_image_shortcut_armed:
            return
        if e.alt:
            return
        if not (e.ctrl or e.meta):
            return
        key_lower = (e.key or "").strip().lower()
        is_v = key_lower == "v" or key_lower.endswith(" v") or "key v" in key_lower
        if not is_v:
            return
        image_actions.choose_from_clipboard(self, settings=self.settings)
        self._safe_page_update()

    def _restart_transfer_hub_if_visible(self) -> None:
        stop_cf = getattr(self, "_stop_cloudflare_quick_tunnel", None)
        if callable(stop_cf):
            try:
                stop_cf()
            except Exception:
                self.logger.exception("Stop Cloudflare quick tunnel failed (restart hub)")
        try:
            from utils.transfer_hub_runner import restart_transfer_hub_server
        except Exception:
            self.logger.exception("Transfer Hub import failed (restart)")
            return
        try:
            allow_lan, port = self._receive_listen_params()
            restart_transfer_hub_server(allow_lan=allow_lan, port=port)
        except Exception:
            self.logger.exception("Transfer Hub restart failed")
        cb = getattr(self, "_receive_tab_refresh_hub", None)
        if callable(cb):
            self.run_on_ui(cb)

    def showinfo(self, title: str, message: str, **_kwargs: Any) -> None:
        self.page.snack_bar = ft.SnackBar(ft.Text(f"{title}: {message}"), open=True)
        self._safe_page_update()

    def showwarning(self, title: str, message: str, **_kwargs: Any) -> None:
        self.page.snack_bar = ft.SnackBar(ft.Text(f"{title}: {message}"), open=True)
        self._safe_page_update()

    def showerror(self, title: str, message: str, **_kwargs: Any) -> None:
        self.page.snack_bar = ft.SnackBar(ft.Text(f"{title}: {message}"), open=True)
        self._safe_page_update()

    def _close_scroll_preview(self, _e: ft.ControlEvent | None = None) -> None:
        if self._scroll_preview_dialog is not None:
            self._scroll_preview_dialog.open = False
        self._safe_page_update()

    def show_scrollable_info(self, title: str, body: str) -> None:
        """Modal preview for long text (e.g. Web Crawler extracted items)."""
        if self._scroll_preview_dialog is None:
            title_t = ft.Text(size=18, weight=ft.FontWeight.BOLD)
            body_f = ft.TextField(
                read_only=True,
                multiline=True,
                min_lines=16,
                max_lines=28,
                expand=True,
                text_size=13,
                border_radius=GLOBAL_RADIUS,
                **input_outline_kwargs(),
            )
            self._scroll_preview_dialog = ft.AlertDialog(
                modal=True,
                title=title_t,
                content=ft.Container(width=720, height=440, padding=8, content=body_f),
                actions=[
                    ft.FilledButton(
                        "Close",
                        height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                        tooltip="Close this preview",
                        on_click=self._close_scroll_preview,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            self._scroll_preview_title_ref = title_t
            self._scroll_preview_body_ref = body_f
            self.page.overlay.append(self._scroll_preview_dialog)
        self._scroll_preview_title_ref.value = title
        self._scroll_preview_body_ref.value = body if body else "(empty)"
        self._scroll_preview_dialog.open = True
        self._safe_page_update()

    def schedule_info_dialog(
        self,
        title: str,
        message: str,
        *,
        on_ok: Callable[[], None] | None = None,
    ) -> None:
        """Non-blocking OK-only modal (e.g. firewall status). Must run from UI context."""

        called = [False]
        def do_ok() -> None:
            if called[0]: return
            called[0] = True
            if on_ok:
                try:
                    on_ok()
                except Exception:
                    self.logger.exception("schedule_info_dialog on_ok")

        def close(dlg: ft.AlertDialog) -> None:
            dlg.open = False
            self._safe_page_update()

        def ok_click(_e: ft.ControlEvent, dlg: ft.AlertDialog) -> None:
            close(dlg)
            do_ok()

        def on_dismiss(_e: ft.ControlEvent) -> None:
            do_ok()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(
                width=480,
                padding=8,
                content=ft.Text(message, selectable=True),
            ),
            actions=[
                ft.FilledButton(
                    "OK",
                    height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                    tooltip="Dismiss",
                    on_click=lambda e: ok_click(e, dlg),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=on_dismiss,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self._safe_page_update()

    def schedule_confirm_dialog(
        self,
        title: str,
        message: str,
        *,
        on_yes: Callable[[], None],
        on_no: Callable[[], None] | None = None,
    ) -> None:
        """Non-blocking Yes/No (e.g. Bluetooth Doctor fix). Must run from UI context."""

        called = [False]
        def do_yes() -> None:
            if called[0]: return
            called[0] = True
            try:
                on_yes()
            except Exception:
                self.logger.exception("schedule_confirm_dialog on_yes")

        def do_no() -> None:
            if called[0]: return
            called[0] = True
            if on_no:
                try:
                    on_no()
                except Exception:
                    self.logger.exception("schedule_confirm_dialog on_no")

        def close(dlg: ft.AlertDialog) -> None:
            dlg.open = False
            self._safe_page_update()

        def yes_click(_e: ft.ControlEvent, dlg: ft.AlertDialog) -> None:
            close(dlg)
            do_yes()

        def no_click(_e: ft.ControlEvent, dlg: ft.AlertDialog) -> None:
            close(dlg)
            do_no()

        def on_dismiss(_e: ft.ControlEvent) -> None:
            do_no()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(
                width=480,
                padding=8,
                content=ft.Text(message, selectable=True),
            ),
            actions=[
                ft.OutlinedButton(
                    "No",
                    height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                    tooltip="Cancel and do not apply the suggested action",
                    on_click=lambda e: no_click(e, dlg),
                ),
                ft.FilledButton(
                    "Yes",
                    height=TRANSLATION_ACTION_BUTTON_HEIGHT,
                    tooltip="Confirm and run the suggested action",
                    on_click=lambda e: yes_click(e, dlg),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=on_dismiss,
        )
        self.page.overlay.append(dlg)
        dlg.open = True
        self._safe_page_update()

    def askyesno(self, _title: str, _message: str, **_kwargs: Any) -> bool:
        # Keep deterministic non-blocking behavior for controller calls.
        return False

    def split_drop_paths(self, data: str) -> list[str]:
        raw = (data or "").strip()
        if not raw:
            return []
        if raw.startswith("{") and raw.endswith("}"):
            return [raw.strip("{}")]
        return [p.strip("{}") for p in raw.split() if p.strip()]

    def _flet_make_entry_proxy(self, value: str = "") -> EntryProxy:
        return EntryProxy(
            ft.TextField(value=value, border_radius=GLOBAL_RADIUS, **input_outline_kwargs()),
        )

    def _clear_choose_fail(self) -> None:
        self.choose_fail_label.configure(text="")
        self.choose_fail_label.grid_remove()
        self._safe_page_update()

    def _show_choose_fail(self, message: str) -> None:
        short = (message or "").strip()
        if len(short) > 160:
            short = short[:157] + "..."
        self.choose_fail_label.configure(text=short)
        self.choose_fail_label.grid()
        self._safe_page_update()

    def _hide_url_entry(self) -> None:
        self._choose_url_visible = False
        self.url_row.visible = False
        self._safe_page_update()

    def _show_url_entry(self) -> None:
        self._choose_url_visible = True
        self.url_row.visible = True
        self._safe_page_update()

    def _sync_trans_state(self, _event: ft.ControlEvent | None = None) -> None:
        self.settings["enable_translation"] = bool(self.trans_cb_main.value)
        if self.settings["current_img"] is not None:
            self.process_image()

    def _sync_lang_state(self, _event: ft.ControlEvent | None = None) -> None:
        # Dropdown on_select can run before `value` is committed; read after UI tick.
        def apply() -> None:
            val = self.lang_menu_main.value
            if not val or val not in self.lang_map:
                return
            self.settings["target_lang"] = val
            self._refresh_voice_choices()
            if self.settings["enable_translation"] and self.settings["current_img"] is not None:
                self.process_image()

        self.run_on_ui(apply)

    @staticmethod
    def _voice_menu_label(voice: Any) -> str:
        name = getattr(voice, "name", None) or getattr(voice, "id", "") or "Voice"
        gender = getattr(voice, "gender", None)
        age = getattr(voice, "age", None)
        if gender and age:
            return f"{name} ({gender}, {age})"
        return str(name)

    def _refresh_voice_choices(self) -> None:
        target = self.settings["target_lang"]
        if target not in self.lang_map:
            self.settings["target_lang"] = DEFAULT_TARGET_LANG
            target = DEFAULT_TARGET_LANG
            if hasattr(self, "lang_menu_main"):
                self.lang_menu_main.value = target
        tts_langs = self.lang_map[target]["tts_lang"]
        voices: dict[str, str] = {}
        for voice in self.current_voices:
            if not hasattr(voice, "id") or not hasattr(voice, "languages"):
                continue
            try:
                langs = voice.languages
                if isinstance(langs, (str, bytes)):
                    langs = [langs]
                tags = []
                for x in langs:
                    if isinstance(x, bytes):
                        tags.append(x.decode("utf-8", errors="ignore"))
                    else:
                        tags.append(str(x))
                if any(tag in tags for tag in tts_langs):
                    voices[voice.id] = self._voice_menu_label(voice)
            except Exception:
                continue
        self.selected_voices_dict = voices
        options = list(self.selected_voices_dict.values())
        self.voice_menu_main.options = [ft.dropdown.Option(v) for v in options]
        if options:
            self.voice_var_main.set(options[0])
            self.voice_menu_main.value = options[0]
            if hasattr(self, "voice_btn"):
                self.voice_btn.configure(state="normal")
        else:
            self.voice_var_main.set("")
            self.voice_menu_main.value = None
            if hasattr(self, "voice_btn"):
                self.voice_btn.configure(state="disabled")
        self._safe_page_update()

    def _update_image_preview(self) -> None:
        img = self.settings.get("current_img")
        if img is None:
            self.img_zone.content = ft.Text(self.placeholder_text, color=ft.Colors.GREY_500)
            self._safe_page_update()
            return
        rendered = img.copy()
        rendered.thumbnail((500, 220))
        buf = io.BytesIO()
        rendered.save(buf, format="PNG")
        self.img_zone.content = ft.Image(src=buf.getvalue(), fit=ft.BoxFit.CONTAIN)
        self._safe_page_update()

    def process_image(self) -> None:
        if not self.settings["current_img"]:
            return
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", "⚙️ Processing...")
        self._update_image_preview()
        threading.Thread(
            target=lambda: text_actions.ocr_worker(
                self,
                settings=self.settings,
                lang_map=self.lang_map,
            ),
            daemon=True,
        ).start()

    def translate_text(self) -> None:
        text_actions.translate_text(
            self,
            settings=self.settings,
            lang_map=self.lang_map,
            logger=self.logger,
        )
        self._safe_page_update()

    def toggle_speech(self) -> None:
        text_actions.toggle_speech(self, settings=self.settings, logger=self.logger)

    def _update_results(self, text: str) -> None:
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", text if text else "No text found.")
        self.process_btn.configure(state="normal")
        self.copy_btn.configure(state="normal" if text else "disabled")
        voice_state = "normal" if text and bool(self.selected_voices_dict) else "disabled"
        self.voice_btn.configure(state=voice_state)
        self._safe_page_update()

    def clear_all(self) -> None:
        self.settings["current_img"] = None
        self._update_image_preview()
        self.result_box.delete("1.0", "end")
        self.process_btn.configure(state="disabled")
        self.copy_btn.configure(state="disabled")
        self.voice_btn.configure(state="disabled")
        self._hide_url_entry()
        self._clear_choose_fail()
        self.url_entry.delete(0, "end")
        self._safe_page_update()

    def copy_result(self) -> None:
        app_actions.copy_result(self)

    def _load_image_from_url_async(self) -> None:
        image_actions.load_image_from_url_async(
            self,
            settings=self.settings,
            logger=self.logger,
        )

    def load_image_path(self, path: str) -> None:
        image_actions.load_image_path(
            self,
            path,
            settings=self.settings,
            logger=self.logger,
        )

    def set_current_image(self, image: Image.Image) -> None:
        self.settings["current_img"] = image
        self._clear_choose_fail()
        self.process_image()
