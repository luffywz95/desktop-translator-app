"""Windows Defender Firewall helpers for Transfer Hub (TCP inbound)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

from components.logger import Logger

logger = Logger().get()

# Must match the name used in netsh add rule (stable for show / duplicate checks).
TRANSFER_HUB_RULE_NAME = "The Owl Transfer Hub TCP 5000"


def _creationflags_no_window() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _netsh_exe() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "netsh.exe")


def _powershell_ok(script: str) -> bool:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_creationflags_no_window(),
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("PowerShell firewall check failed: %s", e)
        return False


def named_transfer_hub_rule_exists() -> bool:
    """
    True if our rule exists (DisplayName from netsh add), using several probes.
    """
    if sys.platform != "win32":
        return True

    # 1) WMI / DisplayName (matches what netsh add sets)
    name_esc = TRANSFER_HUB_RULE_NAME.replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$n = '{name_esc}'
$r = Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $r) {{ exit 0 }}
$r2 = Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {{
    $_.DisplayName -like '*Owl*Transfer*Hub*5000*' -or $_.DisplayName -eq $n
}} | Select-Object -First 1
if ($null -ne $r2) {{ exit 0 }}
exit 1
"""
    if _powershell_ok(script):
        return True

    # 2) netsh via cmd.exe so quoting matches an interactive shell
    try:
        cmdline = (
            f'netsh advfirewall firewall show rule name="{TRANSFER_HUB_RULE_NAME}"'
        )
        r = subprocess.run(
            ["cmd.exe", "/c", cmdline],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=_creationflags_no_window(),
        )
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if r.returncode != 0:
            return False
        if "no rules match" in out:
            return False
        return "rule name:" in out or TRANSFER_HUB_RULE_NAME.lower() in out
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("netsh firewall rule show failed: %s", e)
        return False


def _inbound_tcp_port_allowed_powershell(port: int) -> bool:
    """
    Any enabled inbound allow rule for TCP port (walk rules → port filters).
    """
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$want = [int]{int(port)}
Get-NetFirewallRule -Direction Inbound -ErrorAction SilentlyContinue |
    Where-Object {{ $_.Enabled -eq $true -and $_.Action -eq 'Allow' }} |
    ForEach-Object {{
        $filters = $_ | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
        if ($null -eq $filters) {{ return }}
        foreach ($f in @($filters)) {{
            if ($f.Protocol -ne 'TCP') {{ continue }}
            foreach ($p in @($f.LocalPort)) {{
                try {{
                    if ([int]$p -eq $want) {{ exit 0 }}
                }} catch {{ }}
            }}
        }}
    }}
exit 1
"""
    return _powershell_ok(script)


def inbound_tcp_port_allowed(port: int = 5000) -> bool:
    """
    True if our named rule exists, or any enabled inbound allow rule for this TCP port.
    Does not require admin. On non-Windows, always True.
    """
    if sys.platform != "win32":
        return True
    if named_transfer_hub_rule_exists():
        return True
    return _inbound_tcp_port_allowed_powershell(port)


def wait_for_inbound_tcp_allowed(
    port: int = 5000,
    timeout_s: float = 15.0,
    interval_s: float = 0.25,
) -> bool:
    """
    Poll until inbound_tcp_port_allowed is true or timeout.
    Use after UAC/netsh because the elevated process may finish after the UI unblocks.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if inbound_tcp_port_allowed(port):
            return True
        time.sleep(interval_s)
    ok = inbound_tcp_port_allowed(port)
    if not ok:
        logger.warning(
            "Firewall check still failing after %.1fs wait (port %s).",
            timeout_s,
            port,
        )
    return ok


def add_transfer_hub_rule_elevated(port: int = 5000) -> bool:
    """
    Launch an elevated netsh to add a named inbound allow rule. Shows UAC.
    Returns True if ShellExecute started the process (user may still cancel UAC).
    """
    if sys.platform != "win32":
        return True

    name = TRANSFER_HUB_RULE_NAME.replace('"', '\\"')
    params = (
        f'advfirewall firewall add rule name="{name}" '
        f"dir=in action=allow protocol=TCP localport={int(port)}"
    )
    try:
        netsh = _netsh_exe()
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            netsh,
            params,
            None,
            1,  # SW_SHOWNORMAL
        )
        ok = ret > 32
        if not ok:
            logger.error("ShellExecute for netsh failed with code %s", ret)
        return ok
    except Exception as e:
        logger.error("Could not launch elevated netsh: %s", e)
        return False
