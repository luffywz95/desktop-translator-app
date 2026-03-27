"""Windows Defender Firewall helpers for receive/upload TCP rules."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

from components.logger import Logger

logger = Logger().get()

def transfer_hub_inbound_rule_name(port: int) -> str:
    return f"The Owl Receive File TCP {int(port)}"


def transfer_hub_outbound_rule_name(port: int) -> str:
    return f"The Owl Upload File TCP {int(port)}"


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


def _named_rule_exists(name: str) -> bool:
    """True if rule exists by DisplayName."""
    if sys.platform != "win32":
        return True

    name_esc = name.replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$n = '{name_esc}'
$r = Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $r) {{ exit 0 }}
exit 1
"""
    if _powershell_ok(script):
        return True

    try:
        cmdline = f'netsh advfirewall firewall show rule name="{name}"'
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
        return "rule name:" in out or name.lower() in out
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.warning("netsh firewall rule show failed: %s", e)
        return False


def _tcp_port_allowed_powershell(direction: str, port: int, use_local_port: bool) -> bool:
    port_field = "LocalPort" if use_local_port else "RemotePort"
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$want = [int]{int(port)}
Get-NetFirewallRule -Direction {direction} -ErrorAction SilentlyContinue |
    Where-Object {{ $_.Enabled -eq $true -and $_.Action -eq 'Allow' }} |
    ForEach-Object {{
        $filters = $_ | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
        if ($null -eq $filters) {{ return }}
        foreach ($f in @($filters)) {{
            if ($f.Protocol -ne 'TCP') {{ continue }}
            foreach ($p in @($f.{port_field})) {{
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
    """True if inbound allow exists for local TCP port."""
    if sys.platform != "win32":
        return True
    if _named_rule_exists(transfer_hub_inbound_rule_name(port)):
        return True
    return _tcp_port_allowed_powershell("Inbound", port, use_local_port=True)


def outbound_tcp_port_allowed(port: int = 5000) -> bool:
    """True if outbound allow exists for remote TCP port."""
    if sys.platform != "win32":
        return True
    if _named_rule_exists(transfer_hub_outbound_rule_name(port)):
        return True
    return _tcp_port_allowed_powershell("Outbound", port, use_local_port=False)


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
    """Launch elevated netsh to add named inbound allow rule (local TCP port)."""
    if sys.platform != "win32":
        return True

    name = transfer_hub_inbound_rule_name(port).replace('"', '\\"')
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


def wait_for_outbound_tcp_allowed(
    port: int = 5000,
    timeout_s: float = 15.0,
    interval_s: float = 0.25,
) -> bool:
    """Poll until outbound_tcp_port_allowed is true or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if outbound_tcp_port_allowed(port):
            return True
        time.sleep(interval_s)
    ok = outbound_tcp_port_allowed(port)
    if not ok:
        logger.warning(
            "Outbound firewall check still failing after %.1fs wait (port %s).",
            timeout_s,
            port,
        )
    return ok


def add_upload_file_rule_elevated(port: int = 5000) -> bool:
    """Launch elevated netsh to add named outbound allow rule (remote TCP port)."""
    if sys.platform != "win32":
        return True

    name = transfer_hub_outbound_rule_name(port).replace('"', '\\"')
    params = (
        f'advfirewall firewall add rule name="{name}" '
        f"dir=out action=allow protocol=TCP remoteport={int(port)}"
    )
    try:
        netsh = _netsh_exe()
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            netsh,
            params,
            None,
            1,
        )
        ok = ret > 32
        if not ok:
            logger.error("ShellExecute for outbound netsh failed with code %s", ret)
        return ok
    except Exception as e:
        logger.error("Could not launch elevated outbound netsh: %s", e)
        return False
