from __future__ import annotations

import base64
import io
import os
import sys
import threading
import time
from typing import Any, Callable

import flet as ft
from PIL import Image
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.ui_flet.theme import GLOBAL_RADIUS, INPUT_OUTLINE_COLOR, PRIMARY, input_outline_kwargs
from utils.open_local_path import open_local_path
from utils.receive_paths import IMAGE_EXTENSIONS, list_received_entries

# Flet Image requires non-empty `src` at construction; use a 1×1 transparent PNG when no real image yet.
_PLACEHOLDER_IMAGE_SRC = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# Receive list: soft row hover and low-contrast action icons (readable but not loud).
_RECEIVE_ROW_HOVER_BG = ft.Colors.with_opacity(0.055, ft.Colors.ON_SURFACE)
_RECEIVE_ROW_SELECTED_BG = ft.Colors.with_opacity(0.12, PRIMARY)
_RECEIVE_ROW_SELECTED_HOVER_BG = ft.Colors.with_opacity(0.15, PRIMARY)
_RECEIVE_ACTION_ICON = ft.Colors.with_opacity(0.48, ft.Colors.ON_SURFACE)
_RECEIVE_ACTION_ICON_HOVER = ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)
_RECEIVE_ACTION_BTN_BG_HOVER = ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)


def _qr_png_data_url(url: str) -> str:
    import qrcode

    qr = qrcode.QRCode(version=None, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _image_path_to_preview_data_url(path: str, max_side: int = 720) -> str | None:
    try:
        with Image.open(path) as im:
            if getattr(im, "n_frames", 1) > 1:
                im.seek(0)
            im = im.convert("RGBA") if im.mode in ("P", "RGBA") else im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _pdf_first_page_data_url(path: str, max_side: int = 720) -> str | None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
        try:
            if doc.page_count < 1:
                return None
            page = doc.load_page(0)
            rect = page.rect
            scale = min(max_side / max(rect.width, 1), max_side / max(rect.height, 1), 2.0)
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png = pix.tobytes("png")
            return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        finally:
            doc.close()
    except Exception:
        return None


def _preview_data_url_for_path(path: str, folder_key: str) -> tuple[str | None, str]:
    ext = os.path.splitext(path)[1].lower()
    if folder_key == "images" or ext in IMAGE_EXTENSIONS:
        u = _image_path_to_preview_data_url(path)
        if u:
            return u, ""
        return None, "Could not load image preview."
    if ext == ".pdf":
        u = _pdf_first_page_data_url(path)
        if u:
            return u, ""
        return None, "PDF preview unavailable (open the file to view)."
    return None, "No preview for this type — double-click to open."


class _ReceiveFolderHandler(FileSystemEventHandler):
    def __init__(self, schedule_refresh: Callable[[], None]) -> None:
        super().__init__()
        self._schedule_refresh = schedule_refresh

    def on_created(self, event: Any) -> None:
        if event.is_directory:
            return
        self._schedule_refresh()

    def on_modified(self, event: Any) -> None:
        if event.is_directory:
            return
        self._schedule_refresh()

    def on_moved(self, event: Any) -> None:
        if event.is_directory:
            return
        self._schedule_refresh()

    def on_deleted(self, event: Any) -> None:
        if event.is_directory:
            return
        self._schedule_refresh()


def build_receive_view(app: Any, _page: ft.Page) -> ft.Control:
    from utils.receive_paths import RECEIVED_FILES_DIR, RECEIVED_IMAGES_DIR, ensure_received_dirs

    # Left column ~240px; leave room for copy IconButton (~48) and spacing.
    _HUB_URL_CELL_W = 186

    hub_url_stored: list[str] = [""]
    hub_url_expand_field: list[bool] = [False]

    qr_image = ft.Image(src=_PLACEHOLDER_IMAGE_SRC, width=200, height=200, fit=ft.BoxFit.CONTAIN)
    public_tunnel_ring = ft.ProgressRing(width=40, height=40, stroke_width=3)
    qr_loading_overlay = ft.Container(
        visible=False,
        width=200,
        height=200,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
        content=ft.Column(
            [public_tunnel_ring],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        ),
    )
    qr_stack = ft.Stack(
        width=200,
        height=200,
        controls=[qr_image, qr_loading_overlay],
    )
    hint_text = ft.Text(size=11, color=ft.Colors.GREY_600)

    hub_url_override: list[str | None] = [None]
    tunnel_proc_holder: list[Any] = [None]
    tunnel_busy: list[bool] = [False]

    hub_url_plain_text = ft.Text(
        size=12,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        no_wrap=True,
    )

    def _sync_hub_url_field_selection_end() -> None:
        v = hub_url_field.value or ""
        n = len(v)
        hub_url_field.selection = ft.TextSelection(base_offset=n, extent_offset=n)

    def on_hub_url_field_focus(_e: ft.ControlEvent | None = None) -> None:
        _sync_hub_url_field_selection_end()
        app._safe_page_update()

    def on_hub_url_field_blur(_e: ft.ControlEvent | None = None) -> None:
        hub_url_expand_field[0] = False
        hub_url_collapsed.visible = True
        hub_url_field.visible = False
        app._safe_page_update()

    def on_hub_url_collapsed_tap(_e: ft.ControlEvent | None = None) -> None:
        hub_url_expand_field[0] = True
        hub_url_collapsed.visible = False
        hub_url_field.visible = True
        hub_url_field.value = hub_url_stored[0]
        app._safe_page_update()
        hub_url_field.focus()
        _sync_hub_url_field_selection_end()
        app._safe_page_update()

    hub_url_collapsed = ft.Container(
        visible=True,
        width=_HUB_URL_CELL_W,
        height=40,
        border=ft.border.all(1, INPUT_OUTLINE_COLOR),
        border_radius=GLOBAL_RADIUS,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        alignment=ft.Alignment(-1, 0),
        content=ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=on_hub_url_collapsed_tap,
            content=hub_url_plain_text,
        ),
    )

    hub_url_field = ft.TextField(
        visible=False,
        width=_HUB_URL_CELL_W,
        read_only=True,
        dense=True,
        text_size=12,
        max_lines=1,
        min_lines=1,
        multiline=False,
        on_focus=on_hub_url_field_focus,
        on_blur=on_hub_url_field_blur,
        **input_outline_kwargs(),
    )

    def copy_hub_url(_e: ft.ControlEvent | None = None) -> None:
        try:
            import pyperclip

            pyperclip.copy(hub_url_stored[0] or "")
            app.page.snack_bar = ft.SnackBar(ft.Text("URL copied"), open=True)
            app._safe_page_update()
        except Exception as ex:
            app.showerror("Copy", str(ex))

    hub_url_copy_btn = ft.IconButton(
        icon=ft.Icons.CONTENT_COPY_OUTLINED,
        tooltip="Copy URL",
        icon_size=20,
        style=ft.ButtonStyle(padding=4),
        on_click=copy_hub_url,
    )

    hub_url_row = ft.Container(
        width=240,
        content=ft.Row(
            [
                ft.Stack(
                    width=_HUB_URL_CELL_W,
                    height=40,
                    controls=[hub_url_collapsed, hub_url_field],
                ),
                hub_url_copy_btn,
            ],
            spacing=4,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    _cf_tunnel_tip = (
        "Public URL uses a free Cloudflare quick tunnel (trycloudflare.com; needs the cloudflared CLI on PATH) "
        "for a temporary internet-accessible link."
    )

    public_tunnel_btn = ft.OutlinedButton(
        text="Generate Public URL",
        tooltip=(
            "Requires the cloudflared CLI on PATH. Creates a temporary public HTTPS URL "
            "(trycloudflare.com) that forwards to this PC's Transfer Hub."
        ),
    )
    use_lan_btn = ft.TextButton(
        content="Use LAN / local URL",
        visible=False,
        tooltip="Stop the tunnel and show the normal Transfer Hub link again.",
    )

    preview_image = ft.Image(
        src=_PLACEHOLDER_IMAGE_SRC,
        visible=False,
        fit=ft.BoxFit.CONTAIN,
        width=480,
        height=360,
    )
    preview_message = ft.Text(size=13, color=ft.Colors.GREY_700)

    preview_stack = ft.Stack(
        [
            ft.Container(
                content=preview_image,
                alignment=ft.Alignment(0, 0),
                expand=True,
            ),
            ft.Container(
                content=preview_message,
                alignment=ft.Alignment(0, 0),
                padding=16,
                expand=True,
            ),
        ],
        expand=True,
    )

    preview_panel = ft.Container(
        content=preview_stack,
        border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=GLOBAL_RADIUS,
        padding=8,
        expand=True,
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.BLACK),
    )

    list_column = ft.Column([], spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    selected_path: list[str | None] = [None]
    last_click: dict[str, Any] = {"path": None, "t": 0.0}

    def apply_preview(path: str, folder_key: str) -> None:
        selected_path[0] = path
        data_url, msg = _preview_data_url_for_path(path, folder_key)
        if data_url:
            preview_image.src = data_url
            preview_image.visible = True
            preview_message.value = ""
        else:
            preview_image.src = _PLACEHOLDER_IMAGE_SRC
            preview_image.visible = False
            preview_message.value = msg or "No preview."
        app._safe_page_update()

    def handle_item_click(path: str, folder_key: str) -> None:
        now = time.monotonic()
        if last_click["path"] == path and (now - float(last_click["t"])) < 0.45:
            open_local_path(path)
            last_click["path"] = None
            last_click["t"] = 0.0
            return
        last_click["path"] = path
        last_click["t"] = now
        apply_preview(path, folder_key)
        render_file_list()

    def _receive_snack(msg: str) -> None:
        app.page.snack_bar = ft.SnackBar(ft.Text(msg), open=True)
        app._safe_page_update()

    def _receive_plain_icon_button(
        icon: Any,
        tooltip: str,
        *,
        on_click: Callable[[ft.ControlEvent], None],
    ) -> ft.IconButton:
        return ft.IconButton(
            icon=icon,
            tooltip=tooltip,
            icon_size=17,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: _RECEIVE_ACTION_ICON,
                    ft.ControlState.HOVERED: _RECEIVE_ACTION_ICON_HOVER,
                },
                bgcolor={
                    ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
                    ft.ControlState.HOVERED: _RECEIVE_ACTION_BTN_BG_HOVER,
                },
                padding=4,
            ),
            on_click=on_click,
        )

    def _on_received_item_row_hover(
        e: ft.ControlEvent, row_box: ft.Container, selected: bool
    ) -> None:
        entered = bool(getattr(e, "data", False))
        if selected:
            row_box.bgcolor = _RECEIVE_ROW_SELECTED_HOVER_BG if entered else _RECEIVE_ROW_SELECTED_BG
        else:
            row_box.bgcolor = _RECEIVE_ROW_HOVER_BG if entered else None
        app._safe_page_update()

    def on_receive_copy(_e: ft.ControlEvent, path: str) -> None:
        try:
            import pyperclip

            from utils.windows_clipboard_files import set_clipboard_file_paths

            if sys.platform == "win32" and set_clipboard_file_paths([path], move=False):
                _receive_snack("File copied — paste in File Explorer.")
            else:
                pyperclip.copy(path)
                _receive_snack("Path copied to clipboard.")
        except Exception as ex:
            app.showerror("Copy", str(ex))

    def on_receive_cut(_e: ft.ControlEvent, path: str) -> None:
        try:
            import pyperclip

            from utils.windows_clipboard_files import set_clipboard_file_paths

            if sys.platform == "win32" and set_clipboard_file_paths([path], move=True):
                _receive_snack("Cut — paste in File Explorer to move.")
            else:
                pyperclip.copy(path)
                _receive_snack("Path copied (paste in Explorer to move).")
        except Exception as ex:
            app.showerror("Cut", str(ex))

    def on_receive_delete(_e: ft.ControlEvent, path: str, display_name: str) -> None:
        def do_delete() -> None:
            try:
                os.remove(path)
            except OSError as ex:
                app.showerror("Delete failed", str(ex))
                return
            if selected_path[0] == path:
                selected_path[0] = None
                preview_image.src = _PLACEHOLDER_IMAGE_SRC
                preview_image.visible = False
                preview_message.value = "File removed."
            render_file_list()
            _receive_snack(f"Deleted \"{display_name}\"")

        def second_confirm() -> None:
            app.schedule_confirm_dialog(
                "Confirm permanently delete",
                f'This cannot be undone. Permanently delete "{display_name}"?',
                on_yes=do_delete,
            )

        app.schedule_confirm_dialog(
            "Delete file?",
            f'Delete "{display_name}" from the received folder?',
            on_yes=second_confirm,
        )

    def render_file_list() -> None:
        entries = list_received_entries()
        sel = selected_path[0]
        rows: list[ft.Control] = []
        current_section: str | None = None
        for folder_key, name, full_path, _mt in entries:
            if current_section != folder_key:
                current_section = folder_key
                label = "images" if folder_key == "images" else "files"
                rows.append(
                    ft.Container(
                        padding=ft.padding.only(top=8 if rows else 0, bottom=4),
                        content=ft.Text(label, weight=ft.FontWeight.BOLD, size=13),
                    )
                )
            is_sel = full_path == sel
            icon = ft.Icons.IMAGE_OUTLINED if folder_key == "images" else ft.Icons.INSERT_DRIVE_FILE_OUTLINED
            title_col = ft.Column(
                [
                    ft.Text(name, size=13, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(
                        "images" if folder_key == "images" else "files",
                        size=11,
                        color=ft.Colors.GREY_600,
                    ),
                ],
                spacing=0,
                tight=True,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            )
            row_select = ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda _e, p=full_path, fk=folder_key: handle_item_click(p, fk),
                content=ft.Row(
                    [
                        ft.Icon(icon, size=20),
                        title_col,
                    ],
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True,
                ),
            )
            action_row = ft.Row(
                [
                    _receive_plain_icon_button(
                        ft.Icons.CONTENT_COPY_OUTLINED,
                        "Copy file (or path)",
                        on_click=lambda e, p=full_path: on_receive_copy(e, p),
                    ),
                    _receive_plain_icon_button(
                        ft.Icons.CONTENT_CUT,
                        "Cut file for moving in File Explorer",
                        on_click=lambda e, p=full_path: on_receive_cut(e, p),
                    ),
                    _receive_plain_icon_button(
                        ft.Icons.DELETE_OUTLINE,
                        "Delete file",
                        on_click=lambda e, p=full_path, n=name: on_receive_delete(e, p, n),
                    ),
                ],
                spacing=0,
                tight=True,
            )
            row_box_holder: list[ft.Container | None] = [None]

            def _row_hover(ev: ft.ControlEvent) -> None:
                box = row_box_holder[0]
                if box is not None:
                    _on_received_item_row_hover(ev, box, is_sel)

            row_box_holder[0] = ft.Container(
                border_radius=GLOBAL_RADIUS,
                bgcolor=_RECEIVE_ROW_SELECTED_BG if is_sel else None,
                padding=ft.padding.symmetric(horizontal=4, vertical=2),
                on_hover=_row_hover,
                content=ft.Row(
                    [
                        ft.Container(content=row_select, expand=True),
                        action_row,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
            rows.append(row_box_holder[0])
        list_column.controls = rows or [ft.Text("No files received yet.", color=ft.Colors.GREY_600)]
        app._safe_page_update()

    def refresh_hub_surface() -> None:
        override = hub_url_override[0]
        url = override if override else app.transfer_hub_display_url()
        hub_url_stored[0] = url
        hub_url_plain_text.value = url
        hub_url_field.value = url
        if hub_url_expand_field[0] and hub_url_field.visible:
            _sync_hub_url_field_selection_end()
        try:
            qr_image.src = _qr_png_data_url(url)
        except Exception:
            qr_image.src = _PLACEHOLDER_IMAGE_SRC
        allow_lan = app._receive_listen_params()[0]
        use_lan_btn.visible = bool(override)

        if override:
            hint_text.value = (
                "Cloudflare quick tunnel: anyone with this link can reach your Transfer Hub while it runs. "
                "The URL changes each time you start a new tunnel."
            )
        elif not allow_lan:
            hint_text.value = (
                'Turn on "Receive file" in settings so phones on your LAN can open this URL. ' + _cf_tunnel_tip
            )
        else:
            hint_text.value = (
                "Scan with a phone on the same network to open the Transfer Hub. " + _cf_tunnel_tip
            )
        app._safe_page_update()

    def _kill_tunnel_process() -> None:
        proc = tunnel_proc_holder[0]
        tunnel_proc_holder[0] = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=4)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def stop_cloudflare_tunnel(*, refresh_ui: bool = True) -> None:
        _kill_tunnel_process()
        hub_url_override[0] = None
        if refresh_ui:
            hub_url_expand_field[0] = False
            hub_url_collapsed.visible = True
            hub_url_field.visible = False
            tunnel_busy[0] = False
            use_lan_btn.visible = False
            public_tunnel_btn.disabled = False
            qr_loading_overlay.visible = False
            refresh_hub_surface()

    def revert_to_local_hub(_e: ft.ControlEvent | None = None) -> None:
        stop_cloudflare_tunnel(refresh_ui=True)

    def on_public_tunnel_click(_e: ft.ControlEvent) -> None:
        if tunnel_busy[0]:
            return

        def work() -> None:
            try:
                from utils.cloudflare_quick_tunnel import start_quick_tunnel

                local_url = app.local_transfer_hub_tunnel_target_url()
                public_url, proc = start_quick_tunnel(local_url)

                def apply_ok() -> None:
                    tunnel_busy[0] = False
                    tunnel_proc_holder[0] = proc
                    hub_url_override[0] = public_url
                    public_tunnel_btn.disabled = False
                    qr_loading_overlay.visible = False
                    use_lan_btn.visible = True
                    refresh_hub_surface()

                app.run_on_ui(apply_ok)
            except Exception as ex:
                def apply_err() -> None:
                    tunnel_busy[0] = False
                    public_tunnel_btn.disabled = False
                    qr_loading_overlay.visible = False
                    msg = str(ex)
                    if isinstance(ex, FileNotFoundError):
                        msg = (
                            "cloudflared was not found in PATH. Install the Cloudflare Tunnel CLI, "
                            "then restart the app or open a new terminal so PATH is updated. "
                            "See: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
                        )
                    app.showerror("Cloudflare tunnel", msg)
                    refresh_hub_surface()

                app.run_on_ui(apply_err)

        tunnel_busy[0] = True
        _kill_tunnel_process()
        hub_url_override[0] = None
        hub_url_expand_field[0] = False
        hub_url_collapsed.visible = True
        hub_url_field.visible = False
        public_tunnel_btn.disabled = True
        qr_loading_overlay.visible = True
        use_lan_btn.visible = False
        refresh_hub_surface()
        threading.Thread(target=work, daemon=True).start()

    public_tunnel_btn.on_click = on_public_tunnel_click
    use_lan_btn.on_click = revert_to_local_hub

    debounce_handle: list[Any] = [None]

    def schedule_list_refresh() -> None:
        h = debounce_handle[0]
        if h is not None:
            app.after_cancel(h)
        debounce_handle[0] = app.after(350, run_list_refresh)

    def run_list_refresh() -> None:
        debounce_handle[0] = None
        render_file_list()

    observer_holder: list[Observer | None] = [None]

    def start_folder_watcher() -> None:
        if observer_holder[0] is not None:
            return
        ensure_received_dirs()

        def on_fs_event() -> None:
            app.run_on_ui(schedule_list_refresh)

        handler = _ReceiveFolderHandler(schedule_refresh=on_fs_event)
        obs = Observer()
        obs.schedule(handler, str(RECEIVED_IMAGES_DIR), recursive=False)
        obs.schedule(handler, str(RECEIVED_FILES_DIR), recursive=False)
        obs.start()
        observer_holder[0] = obs

    def stop_folder_watcher() -> None:
        h = debounce_handle[0]
        if h is not None:
            app.after_cancel(h)
            debounce_handle[0] = None
        obs = observer_holder[0]
        if obs is not None:
            obs.stop()
            try:
                obs.join(timeout=2.5)
            except Exception:
                pass
            observer_holder[0] = None

    def refresh_all() -> None:
        refresh_hub_surface()
        render_file_list()

    app._receive_tab_refresh_hub = refresh_hub_surface
    app._stop_receive_folder_watcher = stop_folder_watcher
    app._stop_cloudflare_quick_tunnel = lambda: stop_cloudflare_tunnel(refresh_ui=False)

    refresh_btn = ft.IconButton(
        icon=ft.Icons.REFRESH,
        tooltip="Refresh received file list",
        on_click=lambda _e: refresh_all(),
    )

    header_row = ft.Row(
        [
            ft.Text("Received files", weight=ft.FontWeight.BOLD, size=14, expand=True),
            refresh_btn,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    right_column = ft.Column(
        [
            preview_panel,
            header_row,
            ft.Container(content=list_column, expand=True),
        ],
        spacing=10,
        expand=True,
    )

    left_column = ft.Container(
        width=240,
        content=ft.Column(
            [
                ft.Text("Transfer Hub", weight=ft.FontWeight.BOLD, size=14),
                qr_stack,
                hub_url_row,
                ft.Row(
                    [public_tunnel_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    tight=True,
                ),
                use_lan_btn,
                hint_text,
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    body = ft.Row(
        [
            left_column,
            ft.VerticalDivider(width=1),
            right_column,
        ],
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START,
        expand=True,
    )

    refresh_all()
    start_folder_watcher()

    return ft.Container(expand=True, content=body)
