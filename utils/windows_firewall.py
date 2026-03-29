"""Windows Defender Firewall helpers for receive/upload TCP rules."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import time
from typing import Literal

from utils.logger import Logger

logger = Logger().get()

# Stable display names (no port suffix).
TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME = "The Owl Receive File TCP"
TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME = "The Owl Upload File TCP"

_LEGACY_INBOUND_PATTERN = r"^The Owl Receive File TCP \d+$"
_LEGACY_OUTBOUND_PATTERN = r"^The Owl Upload File TCP \d+$"

FirewallPreviewAction = Literal["noop", "add", "replace"]


def transfer_hub_inbound_rule_name(port: int = 0) -> str:
    """Backward-compatible fixed display name (port ignored)."""
    return TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME


def transfer_hub_outbound_rule_name(port: int = 0) -> str:
    """Backward-compatible fixed display name (port ignored)."""
    return TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME


def _creationflags_no_window() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _powershell_exe() -> str:
    return os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )


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


def _powershell_json(script: str) -> dict | None:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=_creationflags_no_window(),
        )
        if r.returncode != 0:
            logger.warning(
                "PowerShell firewall preview failed rc=%s err=%s",
                r.returncode,
                (r.stderr or "")[:500],
            )
            return None
        raw = (r.stdout or "").strip()
        if not raw:
            return None
        return json.loads(raw)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.warning("PowerShell firewall preview failed: %s", e)
        return None


def _tcp_port_allowed_powershell(
    direction: str, port: int, use_local_port: bool
) -> bool:
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
    """True if an enabled inbound allow rule exists for this local TCP port."""
    if sys.platform != "win32":
        return True
    return _tcp_port_allowed_powershell("Inbound", port, use_local_port=True)


def outbound_tcp_port_allowed(port: int = 5000) -> bool:
    """True if an enabled outbound allow rule exists for this remote TCP port."""
    if sys.platform != "win32":
        return True
    return _tcp_port_allowed_powershell("Outbound", port, use_local_port=False)


def wait_for_inbound_tcp_allowed(
    port: int = 5000,
    timeout_s: float = 15.0,
    interval_s: float = 0.25,
) -> bool:
    """
    Poll until inbound_tcp_port_allowed is true or timeout.
    Use after UAC because the elevated process may finish after the UI unblocks.
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


def _preview_script(
    direction: str,
    port: int,
    fixed: str,
    legacy_re: str,
    port_field: str,
) -> str:
    fixed_esc = fixed.replace("'", "''")
    legacy_esc = legacy_re.replace("'", "''")
    return rf"""
$ErrorActionPreference = 'SilentlyContinue'
$fixed = '{fixed_esc}'
$legacyRe = '{legacy_esc}'
$p = [int]{int(port)}
$direction = '{direction}'
$portField = '{port_field}'
$all = @(Get-NetFirewallRule -Direction $direction -ErrorAction SilentlyContinue | Where-Object {{
  $_.DisplayName -eq $fixed -or $_.DisplayName -match $legacyRe
}})
if ($all.Count -eq 0) {{
  (@{{ action = 'add'; names = @() }} | ConvertTo-Json -Compress -Depth 6)
  exit 0
}}
$legacy = @($all | Where-Object {{ $_.DisplayName -match $legacyRe }})
if ($legacy.Count -gt 0) {{
  (@{{ action = 'replace'; names = @($all | ForEach-Object {{ $_.DisplayName }}) }} | ConvertTo-Json -Compress -Depth 6)
  exit 0
}}
$fixedRules = @($all | Where-Object {{ $_.DisplayName -eq $fixed }})
if ($fixedRules.Count -eq 1) {{
  $r = $fixedRules[0]
  if ($r.Enabled -eq $true) {{
    $tf = @($r | Get-NetFirewallPortFilter) | Where-Object {{ $_.Protocol -eq 'TCP' }} | Select-Object -First 1
    if ($null -ne $tf) {{
      $ports = @($tf.$portField) | ForEach-Object {{ [int]$_ }}
      if ($ports.Count -eq 1 -and $ports[0] -eq $p) {{
        (@{{ action = 'noop'; names = @() }} | ConvertTo-Json -Compress -Depth 6)
        exit 0
      }}
    }}
  }}
}}
(@{{ action = 'replace'; names = @($all | ForEach-Object {{ $_.DisplayName }}) }} | ConvertTo-Json -Compress -Depth 6)
exit 0
"""


def preview_inbound_transfer_firewall_action(
    port: int,
) -> tuple[FirewallPreviewAction, list[str]]:
    """Classify work: noop / add-only / replace (delete app rules then add)."""
    if sys.platform != "win32":
        return "noop", []
    data = _powershell_json(
        _preview_script(
            "Inbound",
            port,
            TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME,
            _LEGACY_INBOUND_PATTERN,
            "LocalPort",
        )
    )
    if not data:
        return "add", []
    action = str(data.get("action", "replace"))
    if action not in ("noop", "add", "replace"):
        action = "replace"
    names = data.get("names") or []
    if isinstance(names, str):
        names = [names]
    elif not isinstance(names, list):
        names = []
    names = [str(x) for x in names]
    return action, names  # type: ignore[return-value]


def preview_outbound_transfer_firewall_action(
    port: int,
) -> tuple[FirewallPreviewAction, list[str]]:
    if sys.platform != "win32":
        return "noop", []
    data = _powershell_json(
        _preview_script(
            "Outbound",
            port,
            TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME,
            _LEGACY_OUTBOUND_PATTERN,
            "RemotePort",
        )
    )
    if not data:
        return "add", []
    action = str(data.get("action", "replace"))
    if action not in ("noop", "add", "replace"):
        action = "replace"
    names = data.get("names") or []
    if isinstance(names, str):
        names = [names]
    elif not isinstance(names, list):
        names = []
    names = [str(x) for x in names]
    return action, names  # type: ignore[return-value]


def _inbound_delete_add_script(new_port: int) -> str:
    fixed = TRANSFER_HUB_INBOUND_RULE_DISPLAY_NAME.replace("'", "''")
    legacy = _LEGACY_INBOUND_PATTERN.replace("'", "''")
    p = int(new_port)
    return rf"""
$ErrorActionPreference = 'Stop'
$fixed = '{fixed}'
$legacyRe = '{legacy}'
$p = {p}
$all = @(Get-NetFirewallRule -Direction Inbound -ErrorAction SilentlyContinue | Where-Object {{
  $_.DisplayName -eq $fixed -or $_.DisplayName -match $legacyRe
}})
if ($all.Count -eq 0) {{
  New-NetFirewallRule -DisplayName $fixed -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p
  exit 0
}}
$legacy = @($all | Where-Object {{ $_.DisplayName -match $legacyRe }})
if ($legacy.Count -eq 0 -and $all.Count -eq 1 -and $all[0].DisplayName -eq $fixed -and $all[0].Enabled -eq $true) {{
  $tf = @($all[0] | Get-NetFirewallPortFilter) | Where-Object {{ $_.Protocol -eq 'TCP' }} | Select-Object -First 1
  if ($null -ne $tf) {{
    $ports = @($tf.LocalPort) | ForEach-Object {{ [int]$_ }}
    if ($ports.Count -eq 1 -and $ports[0] -eq $p) {{ exit 0 }}
  }}
}}
foreach ($r in $all) {{
  Remove-NetFirewallRule -InputObject $r -Confirm:$false
}}
New-NetFirewallRule -DisplayName $fixed -Direction Inbound -Action Allow -Protocol TCP -LocalPort $p
exit 0
"""


def _outbound_delete_add_script(new_port: int) -> str:
    fixed = TRANSFER_HUB_OUTBOUND_RULE_DISPLAY_NAME.replace("'", "''")
    legacy = _LEGACY_OUTBOUND_PATTERN.replace("'", "''")
    p = int(new_port)
    return rf"""
$ErrorActionPreference = 'Stop'
$fixed = '{fixed}'
$legacyRe = '{legacy}'
$p = {p}
$all = @(Get-NetFirewallRule -Direction Outbound -ErrorAction SilentlyContinue | Where-Object {{
  $_.DisplayName -eq $fixed -or $_.DisplayName -match $legacyRe
}})
if ($all.Count -eq 0) {{
  New-NetFirewallRule -DisplayName $fixed -Direction Outbound -Action Allow -Protocol TCP -RemotePort $p
  exit 0
}}
$legacy = @($all | Where-Object {{ $_.DisplayName -match $legacyRe }})
if ($legacy.Count -eq 0 -and $all.Count -eq 1 -and $all[0].DisplayName -eq $fixed -and $all[0].Enabled -eq $true) {{
  $tf = @($all[0] | Get-NetFirewallPortFilter) | Where-Object {{ $_.Protocol -eq 'TCP' }} | Select-Object -First 1
  if ($null -ne $tf) {{
    $ports = @($tf.RemotePort) | ForEach-Object {{ [int]$_ }}
    if ($ports.Count -eq 1 -and $ports[0] -eq $p) {{ exit 0 }}
  }}
}}
foreach ($r in $all) {{
  Remove-NetFirewallRule -InputObject $r -Confirm:$false
}}
New-NetFirewallRule -DisplayName $fixed -Direction Outbound -Action Allow -Protocol TCP -RemotePort $p
exit 0
"""


def _launch_powershell_elevated(script: str) -> bool:
    if sys.platform != "win32":
        return True
    try:
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        ps = _powershell_exe()
        params = (
            "-NoProfile -NonInteractive -ExecutionPolicy Bypass "
            f"-EncodedCommand {encoded}"
        )
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            ps,
            params,
            None,
            1,
        )
        ok = ret > 32
        if not ok:
            logger.error("ShellExecute for elevated PowerShell failed with code %s", ret)
        return ok
    except Exception as e:
        logger.error("Could not launch elevated PowerShell: %s", e)
        return False


def apply_inbound_transfer_rule_elevated(_old_port: int, new_port: int) -> bool:
    """Remove mismatched app inbound rules, then add one rule for new_port (elevated)."""
    if sys.platform != "win32":
        return True
    return _launch_powershell_elevated(_inbound_delete_add_script(new_port))


def apply_outbound_transfer_rule_elevated(_old_port: int, new_port: int) -> bool:
    """Remove mismatched app outbound rules, then add one rule for new_port (elevated)."""
    if sys.platform != "win32":
        return True
    return _launch_powershell_elevated(_outbound_delete_add_script(new_port))


def add_transfer_hub_rule_elevated(port: int = 5000) -> bool:
    """Deprecated: use apply_inbound_transfer_rule_elevated(new_port)."""
    return apply_inbound_transfer_rule_elevated(port)


def add_upload_file_rule_elevated(port: int = 5000) -> bool:
    """Deprecated: use apply_outbound_transfer_rule_elevated(new_port)."""
    return apply_outbound_transfer_rule_elevated(port)
