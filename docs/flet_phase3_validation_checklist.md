# Flet Migration Phase 3 Validation Checklist

Phase 3 closes **feature parity** (Flet vs legacy Tk for real workflows), **stabilization** (no recurring Flet 0.84+ API/runtime banners), and a light **cleanup** decision (whether compat shims in `flet_app.py` stay for now).

**Prerequisites:** Phase 1 and Phase 2 scenarios are familiar; this document assumes those tabs exist and controllers are shared with Tk.

## Test environment

- OS: Windows desktop (primary target).
- Deps: `pip install -r requirements.txt` — `flet` / `flet-desktop` versions should match (see `requirements.txt`).
- Flet launch: PowerShell  
  `$env:UI_RUNTIME="flet"; python main.pyw`
- Tk sanity: run without `UI_RUNTIME` after Flet checks.

Legend for matrices: `PASS` | `FAIL` | `BLOCKED` | `PENDING`

---

## 0) Automated smoke (no GUI)

Does **not** replace §1–§9; use after pulls or before a release build.

Last run in repo: **2026-04-02**

- [x] `python -m compileall -q flet_app.py app/ui_flet utils app/bootstrap.py`
- [x] `python -c "import flet_app"`
- [x] `python -c "from app.ui_flet.firewall_save_flow import start_flet_firewall_then_save; from utils.windows_firewall_settings_flow import gather_transfer_firewall_state"`

If all three succeed, the **§1 optional compile** check below is already covered.

---

## 1) Stabilization — startup and runtime

- [ ] Flet window opens with **no red error banner** on first paint.
- [ ] Switch **all four** top-level tabs once; return to **Translation**.
  - Expected: no `Unknown control`, `TypeError` on constructors, or missing-attribute errors in-banner.
- [ ] Resize window **small → large** on **Translation > Text** and **> Image**.
  - Expected: language dropdown visible next to “Translate to:”; **Translate** / primary actions reachable (scroll if needed).
- [ ] Optional quick compile (or rely on **§0**):  
  `python -m compileall -q flet_app.py app/ui_flet`

---

## 2) Translation — parity smoke

Compare behavior to Tk where it matters (same backends, same settings file).

- [ ] **Image:** Choose file → preview → Process → result; **Reset** clears appropriately.
- [ ] **Image:** **From Clipboard** loads a bitmap from the clipboard (or shows error if none).
- [ ] **Image:** Click the preview area, then **Ctrl+V** (armed shortcut): pastes clipboard image without stealing paste from URL/result/text fields.
- [ ] **Image:** **From URL** → Load → Process (or expected error message, no hard crash).
- [ ] **Text:** type text → **Translate** → result area updates; **Copy** works.
- [ ] **Translate to:** checkbox + **language dropdown** show and persist selection (restart app optional spot-check).
- [ ] **Speak** path: if voices exist, smoke-test enable/disable without UI freeze.

---

## 3) Upload tab — Remote

- [ ] Browse → pick file → path shows; **Upload file** runs; status area updates (success or clear error).
- [ ] URL/token fields editable; behavior matches expectations from Tk for the same backend.

---

## 4) Upload tab — Bluetooth

- [ ] **Select device** opens dialog; list/refresh behaves; close without crash.
- [ ] Browse file(s) → queue UI updates; remove-from-queue works.
- [ ] **Upload** / **Doctor** (if used): completes or surfaces errors without freezing the shell.
- [ ] If Doctor offers **SendTo auto-fix**, **Yes** / **No** in the Flet modal runs the fix or declines (no blocking `askyesno`).

---

## 5) Convert Image

- [ ] **Add files** → queue list; per-row remove; **Clear queue**.
- [ ] **Browse** output folder → path shown; **START CONVERSION** enables only when inputs valid.
- [ ] Run conversion on a small test set → progress/complete path; no uncaught thread errors in UI.

---

## 6) Web Crawler

- [ ] **Browse** (output/location) opens native folder dialog; path appears in UI.
- [ ] **START SPIDER** / stop behavior: log area updates; no immediate crash on invalid URL (message OK).
- [ ] **EXPORT DATA** / **VIEW ITEMS** (if applicable after a run): behave like Tk for the same project folder rules.
  - Flet: **VIEW ITEMS** opens a scrollable **AlertDialog** (`show_scrollable_info`), not a separate Tk window.

---

## 7) Settings overlay

- [ ] Open gear → **Save & Close** / **Close**; values persist across tab switches.
- [ ] Reopen after changing ports/URL/token; confirm no duplicate overlays or stuck dim layer.
- [ ] After changing **Receive** port or enablement, **Save & Close**; confirm **Transfer Hub** picks up changes (same behavior as Tk: `restart_transfer_hub_server` runs from `FletAppBridge`).
- [ ] **Windows (Flet):** With **Receive** and/or **Upload** enabled, **Save & Close** → answer the firewall prompts (Yes/No, rule replacement, UAC). Behavior should match Tk (`utils/windows_firewall_settings_flow.py` + `app/ui_flet/firewall_save_flow.py`).
- [ ] Change **Invoke hotkey key** in settings → **Save & Close**; press the new global shortcut.
  - Expected: Flet window comes to foreground (`page.window.to_front()` via `keyboard` hook). Session end removes the hook.
- [ ] Enable **background process hotkey** → **Save & Close**; copy an image, focus another app, press the shortcut.
  - Expected: OCR runs; if the Flet window was not focused, result is copied to clipboard (matches Tk `handle_paste` + `state()` semantics via `WindowEvent` focus tracking).

---

## 8) Threading and tab churn

- [ ] During a long OCR/convert/crawl, **switch tabs** and back.
  - Expected: eventual completion or error visible; UI stays interactive.
- [ ] Deliberately trigger a handled error (bad file, empty field).
  - Expected: snack/message style feedback, no dead UI.

---

## 9) Legacy regression (post–Phase 4)

- [ ] **N/A for Tk** — Tk was removed in Phase 4. Use [flet_phase4_validation_checklist.md](flet_phase4_validation_checklist.md) and tag `legacy/tk-phase3` if you need the old UI.
- [ ] Optional: `python -c "import flet_app"` after edits to shared controllers.

---

## 10) Cleanup decision (optional, not blocking PASS)

**Recorded for this repo (Phase 3):** Keep `flet_app.py` compat shims (FilledButton/Dropdown/FilePicker/Tab) until Flet’s public API stabilizes across minor releases; remove shims in a dedicated pass once all call sites use native 0.84+ constructors and event patterns.

- [x] **Documented** (see paragraph above).

---

## 11) Phase 3 pass/fail matrix

| Area | Status | Evidence / Notes |
|------|--------|------------------|
| Stabilization: clean startup + tab sweep | PENDING | |
| Translation Image/Text + dropdown + layout | PENDING | |
| Upload Remote | PENDING | |
| Upload Bluetooth + dialog | PENDING | |
| Convert Image queue + output + run | PENDING | |
| Web Crawler browse + run/export smoke | PENDING | |
| Settings overlay | PENDING | |
| Threading / tab churn | PENDING | |
| Tk legacy smoke | PENDING | |
| Cleanup decision recorded | PASS | See §10 — keep shims until upstream stabilizes |
| Global invoke hotkey + re-bind after save | PENDING | |
| Clipboard + armed Ctrl+V; background hotkey | PENDING | |

### Final decision

- Phase 3 result: **PENDING**
- Promote to **PASS** only when every **functional** row above (excluding optional cleanup row if you defer it) is **PASS** on your machine.
- Use **BLOCKED** when environment (device, network, API keys) prevents a test; note the blocker in **Evidence / Notes**.

---

## 12) Code-complete scope (what this repo implements for Phase 3)

Use this as the engineering “done” list; your **matrix PASS** still requires manual runs on your PC.

| Delivered | Notes |
|-----------|--------|
| Flet 0.84 control/API alignment | Shims in `flet_app.py`; `material_tabs`, `file_dialogs`, layout fixes |
| Transfer Hub | Start on launch, restart after settings save, stop on session end |
| Scrollable **VIEW ITEMS** | `FletAppBridge.show_scrollable_info` |
| Global **invoke** hotkey | `keyboard.add_hotkey` → `run_task(window.to_front)`; `_sync_invoke_hotkey` after settings save; removed on disconnect/close |
| Bluetooth Doctor SendTo fix | `schedule_confirm_dialog` (Yes/No) instead of dead `askyesno` |
| Clipboard / paste | **From Clipboard** button; tap image zone then Ctrl/Cmd+V (`page.on_keyboard_event`); disarm when URL/result/text/voice/lang fields focus |
| Background hotkey | `keyboard.add_hotkey` → `handle_paste` on UI thread; `state()` uses `WindowEvent` focus for auto-copy when blurred |
| Windows Firewall on save (Flet) | `start_flet_firewall_then_save` — same checks/elevation as Tk; `gather_transfer_firewall_state` shared in `utils/windows_firewall_settings_flow.py` |
| Known gap vs Tk | **OS Explorer → image zone** drag-and-drop: Flet desktop controls do not expose native file drop on the Translation preview; use **Choose file**, **From Clipboard**, or **From URL** |

---

## Quick triage hints

- **Unknown control: FilePicker** — pickers must not be added to `page.overlay`; use `app/ui_flet/file_dialogs.py` patterns and construct pickers under page context.
- **Button / Tab / alignment TypeErrors** — align with Flet 0.84 (`content` vs `text`, `material_tabs`, `ft.BoxFit`, etc.); see `flet_app.py` shims.
- **Language dropdown missing** — avoid `expand=True` on `Row` inside a `Column` for toolbar rows; see `translation_view.py`.
