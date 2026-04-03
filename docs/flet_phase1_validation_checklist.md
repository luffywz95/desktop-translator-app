# Flet Migration Phase 1 Validation Checklist

This checklist validates the current Phase 1 scope:

- Flet shell + top-level tabs
- Translation tab (Image/Text) baseline behavior
- Settings overlay open/close/save baseline behavior
- Thread-safe UI write-back path through adapter
- No regressions to legacy Tk launch path

## Test Environment

**Note:** After Phase 4, the app is **Flet-only**; §1 “Runtime Gating” below is historical unless you restore Tk from tag `legacy/tk-phase3`.

- OS: Windows desktop
- Python deps installed (`pip install -r requirements.txt`)
- Entry point (Phase 4+): `python main.pyw` (Flet only). Legacy Tk: git tag `legacy/tk-phase3`.

## 1) Runtime Gating (Tk vs Flet)

- [ ] Launch without `UI_RUNTIME` env var.
  - Expected: legacy Tk UI opens/behaves as before.
- [ ] Launch with `UI_RUNTIME=flet`.
  - Expected: Flet window opens with title and shell tabs.
- [ ] Close and relaunch each mode one more time.
  - Expected: no startup exceptions in either mode.

## 2) Flet Shell Structure

- [ ] Verify top-level tabs exist: `Translation`, `Upload`, `Convert Image`, `Web Crawler`.
  - Expected: all four tabs are visible.
- [ ] Open non-Translation tabs.
  - Expected: placeholder text only (no crash/hang).
- [ ] Return to `Translation`.
  - Expected: nested tabs `Image` and `Text` are present.

## 3) Translation Text Flow (Phase 1 baseline)

- [ ] In `Translation > Text`, type plain text and click `Translate`.
  - Expected: result area updates and remains responsive.
- [ ] Toggle `Translate to` switch and repeat.
  - Expected: result still updates without UI freeze.
- [ ] Click copy icon after a result appears.
  - Expected: clipboard receives result text.

## 4) Translation Image Flow (Phase 1 baseline)

- [ ] In `Translation > Image`, click `Choose file` and pick an image with text.
  - Expected: image preview/result flow triggers without exception.
- [ ] Click `Process`.
  - Expected: status/result field updates and buttons re-enable.
- [ ] Click `Reset`.
  - Expected: preview/result clear and controls return to idle state.
- [ ] Use `From URL`, provide an image URL, then `Load`.
  - Expected: URL path does not crash UI; failures show short error text.

## 5) Settings Overlay Behavior

- [ ] Open settings from top-right gear icon.
  - Expected: dim overlay + settings card appears.
- [ ] Click `Close`.
  - Expected: overlay hides cleanly.
- [ ] Reopen settings, modify at least:
  - invoke hotkey key,
  - background hotkey toggle,
  - receive/upload port values,
  - remote URL/token.
- [ ] Click `Save & Close`.
  - Expected: overlay closes and app remains responsive.

## 6) Thread-Safe UI Write-Back (Smoke)

- [ ] Trigger OCR/translate operations repeatedly (3-5 times).
  - Expected: no `setState`/thread-access exceptions; UI remains interactive.
- [ ] While a background operation is running, switch tabs and return.
  - Expected: no crash, eventual result/status update still appears.
- [ ] Try invalid/edge input (empty text, bad URL, missing file).
  - Expected: graceful failure messaging, no dead UI.

## 7) Legacy Path Regression Guard

- [ ] Run Tk mode again after Flet checks.
  - Expected: hotkeys, settings modal, and transfer-related actions still launch.
- [ ] Confirm no import/runtime break introduced by Flet files.
  - Expected: Tk startup path untouched except runtime gate.

## 8) Pass/Fail Rule

Phase 1 is accepted when all items below are true:

- [ ] Runtime gate works for both modes.
- [ ] Flet shell and Translation tab are stable.
- [ ] Settings overlay open/close/save works.
- [ ] No thread-related UI exceptions during smoke tests.
- [ ] Tk legacy path still functions.

## Quick Triage Hints

- If Flet mode fails at startup:
  - Verify `flet` is installed and interpreter matches the environment used by `main.pyw`.
- If UI updates stop during background work:
  - Recheck adapter path (`after(...)` and `run_on_ui`) in `app/ui_flet/adapters/ui_bridge.py`.
- If settings changes do not persist:
  - Recheck save path in `app/ui_flet/settings_overlay.py` and transfer settings helpers.

## 9) Pass/Fail Matrix

Use this matrix to record outcomes quickly after each run.

Legend: `PASS` | `FAIL` | `BLOCKED` | `PENDING`

| Area | Status | Evidence / Notes |
|---|---|---|
| Compile (`python -m compileall flet_app.py app/ui_flet`) | PASS | Verified in automated sanity run. |
| Import smoke (`import flet_app` + `app.ui_flet.*`) | PASS | Verified in automated sanity run (`import-ok`). |
| Startup smoke: Tk mode | PASS | Process stayed alive during smoke window (no immediate crash). |
| Startup smoke: Flet mode | PASS | Process stayed alive during smoke window (no immediate crash). |
| Runtime gate behavior (window-level) | PENDING | Manual check required in visible UI. |
| Flet shell tabs render correctly | PENDING | Manual check required in visible UI. |
| Translation > Text flow | PENDING | Manual check required in visible UI. |
| Translation > Image flow | PENDING | Manual check required in visible UI. |
| Settings overlay open/close/save | PENDING | Manual check required in visible UI. |
| Thread-safe UI write-back | PENDING | Manual check required while triggering OCR/translate repeatedly. |
| Tk legacy regression guard | PENDING | Manual check after Flet run. |

### Final Decision

- Phase 1 result: `PENDING`
- Promote to `PASS` only when all `PENDING` items above are validated as `PASS`.

## 10) Phase 2 Extension Matrix

Phase 2 scope adds `Upload`, `Convert Image`, and `Web Crawler` Flet tabs.

| Area | Status | Evidence / Notes |
|---|---|---|
| Compile (`python -m compileall flet_app.py app/ui_flet app/controllers`) | PASS | Automated |
| Import smoke (`import flet_app` + `app.ui_flet.upload_view/convert_image_view/web_crawler_view`) | PASS | Automated (`phase2-import-ok`) |
| Flet startup smoke (`UI_RUNTIME=flet`) | PASS | Automated (`flet-phase2-startup-ok`) |
| Upload tab render + Remote/Bluetooth subviews | PENDING | Manual UI check |
| Bluetooth dialog picker open/refresh/pair/use | PENDING | Manual UI check |
| Bluetooth send watchdog completion behavior | PENDING | Manual UI check (large + small files) |
| Convert Image queue add/remove/clear/run/progress | PENDING | Manual UI check |
| Web Crawler dynamic fields/start/log/export/view | PENDING | Manual UI check |
| Tk legacy path after Phase 2 changes | PENDING | Manual UI check |

### Phase 2 Decision

- Phase 2 result: `PENDING`
- Promote to `PASS` only when all Phase 2 `PENDING` items pass.
