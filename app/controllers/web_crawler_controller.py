from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_META_PREFIX = "[WEBCRAWLER_META]"


def _showinfo(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showinfo", None)
    if callable(h):
        h(title, message)


def _showwarning(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showwarning", None)
    if callable(h):
        h(title, message)


def _showerror(app: Any, title: str, message: str) -> None:
    h = getattr(app, "showerror", None)
    if callable(h):
        h(title, message)


def _append_log(app: Any, line: str) -> None:
    if not hasattr(app, "web_crawler_log"):
        return
    app.web_crawler_log.insert("end", f"{line.rstrip()}\n")
    app.web_crawler_log.see("end")


def _set_running(app: Any, running: bool) -> None:
    app.web_crawler_start_btn.configure(state="disabled" if running else "normal")


def _update_view_items_label(app: Any, count: int) -> None:
    compact = bool(getattr(app, "_web_crawler_compact", False))
    if compact:
        app.web_crawler_view_btn.configure(text="👁️")
        return
    app.web_crawler_view_btn.configure(text=f"👁️ VIEW ITEMS ({count})")


def _normalize_target_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    if "://" not in url:
        return f"https://{url}"
    return url


def _allowed_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def web_crawler_browse_location(app: Any) -> None:
    pick_dir = getattr(app, "pick_directory", None)
    if not callable(pick_dir):
        raise RuntimeError("pick_directory is required")
    path = pick_dir("Choose crawler output folder")
    if not path:
        return
    app.web_crawler_project_location_entry.delete(0, "end")
    app.web_crawler_project_location_entry.insert(0, path)


def web_crawler_add_field(app: Any, field_name: str = "", selector: str = "") -> None:
    mk_entry = getattr(app, "_flet_make_entry_proxy", None)
    if not callable(mk_entry):
        raise RuntimeError("_flet_make_entry_proxy is required")
    row = {
        "name_entry": mk_entry(field_name),
        "selector_entry": mk_entry(selector),
    }
    app._web_crawler_fields.append(row)
    render = getattr(app, "_flet_render_web_fields", None)
    if callable(render):
        render()


def web_crawler_sync_field_row_sizes(app: Any) -> None:
    """No-op for Flet (density handled in view)."""
    return


def web_crawler_remove_field(app: Any, row_frame: Any) -> None:
    app._web_crawler_fields = [r for r in app._web_crawler_fields if r is not row_frame]
    render = getattr(app, "_flet_render_web_fields", None)
    if callable(render):
        render()


def _build_config(app: Any) -> dict[str, Any] | None:
    target = _normalize_target_url(app.web_crawler_target_entry.get())
    if not target:
        _showwarning(app, "Web Crawler", "Please enter a target URL.")
        return None
    domain = _allowed_domain(target)
    if not domain:
        _showwarning(app, "Web Crawler", "Invalid URL. Please check target URL.")
        return None

    fields: list[dict[str, str]] = []
    for row in app._web_crawler_fields:
        name = row["name_entry"].get().strip()
        selector = row["selector_entry"].get().strip()
        if name and selector:
            fields.append({"name": name, "selector": selector})
    if not fields:
        _showwarning(app, "Web Crawler", "Add at least one field and selector.")
        return None

    wait_mode = app.web_crawler_readiness_var.get().strip()
    wait_selector = app.web_crawler_wait_selector_entry.get().strip()
    if wait_mode == "Wait for Element..." and not wait_selector:
        _showwarning(app, "Web Crawler", "Enter a selector for 'Wait for Element...' mode.")
        return None

    output_dir = (app.web_crawler_project_location_entry.get() or "").strip() or "./crawls/"
    out_path = Path(output_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    project_name = (app.web_crawler_project_name_entry.get() or "").strip() or "NewProject_01"
    result_format = (app.web_crawler_format_var.get() or "CSV").strip().lower()
    if result_format not in {"csv", "json"}:
        result_format = "csv"

    rendered = bool(app.web_crawler_js_var.get())
    delay = 2.0 if app.web_crawler_delay_var.get() else 0.0
    config = {
        "target_url": target,
        "allowed_domain": domain,
        "fields": fields,
        "rendered": rendered,
        "wait_mode": wait_mode,
        "wait_selector": wait_selector,
        "project_name": project_name,
        "output_dir": str(out_path),
        "result_format": result_format,
        "download_delay": delay,
        "robots_obey": bool(app.web_crawler_robots_var.get()),
        "ignore_images": bool(app.web_crawler_ignore_images_var.get()),
        "depth_limit": 2,
    }
    return config


def web_crawler_start(app: Any, logger: Any) -> None:
    proc = getattr(app, "_web_crawler_proc", None)
    if proc and proc.poll() is None:
        _showinfo(app, "Web Crawler", "Crawler is already running.")
        return

    config = _build_config(app)
    if not config:
        return

    cfg_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        delete=False,
    )
    with cfg_file:
        json.dump(config, cfg_file)
    cfg_path = cfg_file.name

    app._web_crawler_last_output = ""
    app._web_crawler_last_count = 0
    _update_view_items_label(app, 0)
    _append_log(app, f"[i] Spider '{config['project_name']}' initialized.")
    _append_log(app, f"[i] Strategy: {'JS-Rendered' if config['rendered'] else 'Static HTML'}")
    _set_running(app, True)

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "app.services.web_crawler.run_crawl",
        cfg_path,
    ]
    try:
        app._web_crawler_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
    except Exception as exc:
        _set_running(app, False)
        _showerror(app, "Web Crawler", f"Failed to start crawler:\n{exc}")
        return

    def watch() -> None:
        try:
            assert app._web_crawler_proc is not None
            for line in app._web_crawler_proc.stdout or []:
                text = line.rstrip()
                if text.startswith(_META_PREFIX):
                    try:
                        meta = json.loads(text[len(_META_PREFIX) :].strip())
                    except Exception:
                        meta = {}
                    app._web_crawler_last_output = str(meta.get("output_file", "") or "")
                    app._web_crawler_last_count = int(meta.get("item_count", 0) or 0)
                    app.after(
                        0,
                        lambda: _update_view_items_label(
                            app, app._web_crawler_last_count
                        ),
                    )
                    continue
                app.after(0, lambda t=text: _append_log(app, t))
            code = app._web_crawler_proc.wait()

            def done() -> None:
                _set_running(app, False)
                if code == 0:
                    _append_log(app, "[✓ DONE] Crawl finished.")
                else:
                    _append_log(app, f"[x ERR] Crawl exited with code {code}.")

            app.after(0, done)
        except Exception as exc:
            logger.error("Crawler watcher failed: %s", exc)
            app.after(0, lambda: _set_running(app, False))

    threading.Thread(target=watch, daemon=True).start()


def web_crawler_export_last(app: Any) -> None:
    output_path = getattr(app, "_web_crawler_last_output", "")
    if not output_path:
        _showinfo(app, "Web Crawler", "No export file found yet. Run the spider first.")
        return
    _showinfo(app, "Web Crawler", f"Latest export:\n{output_path}")


def web_crawler_view_items(app: Any) -> None:
    output_path = getattr(app, "_web_crawler_last_output", "")
    if not output_path or not os.path.exists(output_path):
        _showinfo(app, "Web Crawler", "No extracted items to preview.")
        return

    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read(4000)
    except Exception as exc:
        _showerror(app, "Web Crawler", f"Failed to read output:\n{exc}")
        return

    preview = getattr(app, "show_scrollable_info", None)
    if callable(preview):
        preview("Extracted Items Preview", content if content else "(empty)")
    else:
        _showinfo(app, "Extracted Items Preview", content if content else "(empty)")
