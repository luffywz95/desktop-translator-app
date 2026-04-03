# Flet Migration Phase 4 Validation Checklist

Phase 4 makes **Flet the only UI**: Tk / CustomTkinter / `components/` / `app/ui/` removed; entry is `python main.pyw` → [`flet_app.run_flet_app()`](../flet_app.py) after [`app.bootstrap.setup_application_environment()`](../app/bootstrap.py).

**Rollback:** git tag `legacy/tk-phase3` (pre-removal snapshot).

Legend: `PASS` | `FAIL` | `BLOCKED` | `PENDING`

---

## 0) Automated smoke (no GUI)

- [ ] `python -m compileall -q flet_app.py main.pyw app bootstrap.py utils`
- [ ] `python -c "import flet_app"`
- [ ] Repo search: no `tkinter` / `customtkinter` imports under `app/`, `flet_app.py`, `main.pyw`

---

## 1) Entry and single instance

- [ ] First launch: window opens; no red Flet banner.
- [ ] Second launch while first is running: **native** “already running” dialog (not Tk); second process exits.
- [ ] `app.pid` written; Tesseract path from `.env` / default still honored for OCR.

---

## 2) Tabs and workflows

Exercise the same scenarios as Phase 3 §2–§6 (Translation, Upload Remote/Bluetooth, Convert Image, Web Crawler). Controllers are Flet-only; there is no Tk fallback.

---

## 3) Settings and firewall

- [ ] Settings **Save & Close** persists hotkeys, transfer hub, remote URL/token.
- [ ] Windows: firewall flow still runs from [`app/ui_flet/firewall_save_flow.py`](../app/ui_flet/firewall_save_flow.py) using [`gather_transfer_firewall_state`](../utils/windows_firewall_settings_flow.py).

---

## 4) Hotkeys and session end

- [ ] Invoke hotkey brings window forward; background hotkey + clipboard OCR behave as in Phase 3.
- [ ] Closing the app stops Transfer Hub and removes keyboard hooks.

---

## 5) Speech (no Tk)

- [ ] **Speak** with a valid voice works; missing voice shows **snackbar** / `showerror` on the bridge (not `tkinter.messagebox`).

---

## 6) Phase 4 matrix

| Area | Status | Notes |
|------|--------|--------|
| Flet-only entry + bootstrap | PENDING | |
| No Tk/CTk in app tree | PENDING | |
| Functional parity vs Phase 3 | PENDING | |
| requirements.txt trimmed | PENDING | |
| README launch | PENDING | |

### Final decision

- Phase 4 result: **PENDING** until matrix rows are **PASS** on your machine.

---

## Known gaps (unchanged from Phase 3)

- OS Explorer → Translation image **drag-and-drop** is still not available on Flet desktop; use file picker, clipboard, or URL.
