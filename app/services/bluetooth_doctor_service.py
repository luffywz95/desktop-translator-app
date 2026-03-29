from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from logging import Logger


def doctor_sendto_has_bluetooth_entry(logger: Logger) -> bool:
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$sendto = [Environment]::GetFolderPath('SendTo')
if (-not $sendto -or -not (Test-Path $sendto)) { exit 2 }
$w = New-Object -ComObject WScript.Shell
$items = Get-ChildItem -Path $sendto -Filter *.lnk -File
foreach ($it in $items) {
    $name = ($it.BaseName + '').ToLowerInvariant()
    if ($name -like '*bluetooth*') { exit 0 }
    try {
        $sc = $w.CreateShortcut($it.FullName)
        $target = ($sc.TargetPath + '').ToLowerInvariant()
        if ($target.EndsWith('\fsquirt.exe') -or $target.Trim('"').EndsWith('\fsquirt.exe')) { exit 0 }
    } catch { }
}
exit 1
"""
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if cp.returncode != 0 and (cp.stderr or cp.stdout):
            logger.info(
                "[Bluetooth Doctor] SendTo probe rc=%s stderr=%s stdout=%s",
                cp.returncode,
                (cp.stderr or "").strip()[:200],
                (cp.stdout or "").strip()[:200],
            )
        return cp.returncode == 0
    except Exception as exc:
        logger.warning(f"[Bluetooth Doctor] SendTo probe failed: {exc}")
        sendto = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft",
            "Windows",
            "SendTo",
        )
        if not os.path.isdir(sendto):
            return False
        for name in os.listdir(sendto):
            lowered = name.lower()
            if ("bluetooth" in lowered) or ("fsquirt" in lowered):
                return True
        return False


def doctor_add_fsquirt_sendto_shortcut() -> tuple[bool, str]:
    ps = r"""
$ErrorActionPreference = 'Stop'
$sendto = [Environment]::GetFolderPath('SendTo')
if (-not $sendto -or -not (Test-Path $sendto)) { throw 'SendTo folder not found.' }
$target = Join-Path $env:SystemRoot 'System32\fsquirt.exe'
if (-not (Test-Path $target)) { throw "fsquirt.exe not found at $target" }
$lnk = Join-Path $sendto 'Bluetooth File Transfer.lnk'
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($lnk)
$s.TargetPath = $target
$s.WorkingDirectory = Split-Path $target
$s.IconLocation = "$target,0"
$s.Description = 'Bluetooth File Transfer'
$s.Save()
Write-Output $lnk
"""
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if cp.returncode != 0:
            err = (cp.stderr or cp.stdout or "Unknown error").strip()
            return False, err[:300]
        created = (cp.stdout or "").strip() or "Shortcut created."
        return True, created
    except Exception as exc:
        return False, str(exc)


@dataclass(frozen=True, slots=True)
class BluetoothDoctorSnapshot:
    report_lines: list[str]
    supports_bt: bool
    sendto_has_bt: bool
    fsquirt_ok: bool
    all_pass: bool
    should_offer_fix: bool
    ok_runtime: bool
    runtime_msg: str
    has_adapter: bool


def collect_bluetooth_doctor_snapshot(logger: Logger) -> BluetoothDoctorSnapshot:
    from utils import bluetooth_transfer as bt

    report: list[str] = []
    ok_runtime, runtime_msg = bt.bluetooth_transfer_available()
    has_adapter = False
    if ok_runtime:
        try:
            has_adapter = bool(bt.run_coroutine(bt.has_bluetooth_adapter_async()))
        except Exception as e:
            logger.warning(f"[Bluetooth Doctor] Adapter probe failed: {e}")
            has_adapter = False
    supports_bt = ok_runtime and has_adapter
    report.append(
        f"[1] Bluetooth support/adapter: {'OK' if supports_bt else 'FAIL'} "
        f"(runtime={'OK' if ok_runtime else 'Missing'}, adapter={'Found' if has_adapter else 'Not found'})"
    )
    if runtime_msg and not ok_runtime:
        report.append(f"    Runtime hint: {runtime_msg.splitlines()[0]}")
    logger.info(
        "[Bluetooth Doctor] Step1 runtime=%s adapter=%s",
        ok_runtime,
        has_adapter,
    )

    sendto_has_bt = doctor_sendto_has_bluetooth_entry(logger)
    report.append(
        f"[2] 'Send to' has Bluetooth entry: {'YES' if sendto_has_bt else 'NO'}"
    )
    logger.info("[Bluetooth Doctor] Step2 sendto_has_bt=%s", sendto_has_bt)

    fsquirt_path = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "fsquirt.exe",
    )
    exists = os.path.isfile(fsquirt_path)
    cmd_ok = False
    if exists:
        try:
            cp = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-Command fsquirt.exe | Out-Null",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            cmd_ok = cp.returncode == 0
        except Exception as e:
            logger.warning(f"[Bluetooth Doctor] Get-Command fsquirt failed: {e}")
            cmd_ok = False
    fsquirt_ok = exists and cmd_ok
    report.append(
        f"[3] fsquirt availability: {'OK' if fsquirt_ok else 'FAIL'} "
        f"(exists={'YES' if exists else 'NO'}, command={'YES' if cmd_ok else 'NO'})"
    )
    logger.info(
        "[Bluetooth Doctor] Step3 fsquirt_exists=%s command_ok=%s",
        exists,
        cmd_ok,
    )

    all_pass = supports_bt and sendto_has_bt and fsquirt_ok
    should_offer_fix = supports_bt and (not sendto_has_bt) and fsquirt_ok
    logger.info("[Bluetooth Doctor] Suggest_fix=%s", should_offer_fix)

    return BluetoothDoctorSnapshot(
        report_lines=report,
        supports_bt=supports_bt,
        sendto_has_bt=sendto_has_bt,
        fsquirt_ok=fsquirt_ok,
        all_pass=all_pass,
        should_offer_fix=should_offer_fix,
        ok_runtime=ok_runtime,
        runtime_msg=runtime_msg or "",
        has_adapter=has_adapter,
    )
