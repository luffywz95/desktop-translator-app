## Phase 1 Validation Matrix (Tk -> Flet Migration)

| Area | Status | Notes |
|---|---|---|
| Compile (`python -m compileall flet_app.py app/ui_flet`) | PASS | Automated |
| Import smoke (`import flet_app` + `app.ui_flet.*`) | PASS | Automated (`import-ok`) |
| Startup smoke: Tk mode | PASS | Automated (no immediate crash) |
| Startup smoke: Flet mode | PASS | Automated (no immediate crash) |
| Runtime gate behavior (visible UI) | PENDING | Manual |
| Flet shell tabs render | PENDING | Manual |
| Translation > Text flow | PENDING | Manual |
| Translation > Image flow | PENDING | Manual |
| Settings overlay open/close/save | PENDING | Manual |
| Thread-safe UI write-back under repeated operations | PENDING | Manual |
| Tk legacy regression guard after Flet run | PENDING | Manual |

**Phase 1 decision:** `PENDING` until all manual checks are `PASS`.
