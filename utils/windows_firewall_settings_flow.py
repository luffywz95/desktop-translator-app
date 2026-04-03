"""Windows Firewall preview state for Flet settings save (shared gather step)."""

from __future__ import annotations

from typing import Any

from utils.windows_firewall import (
    inspect_inbound_transfer_rule,
    inspect_outbound_transfer_rule,
)


def gather_transfer_firewall_state(
    *,
    new_receive_enabled: bool,
    new_upload_enabled: bool,
    old_receive: dict[str, Any],
    old_upload: dict[str, Any],
    receive_port: int,
    upload_port: int,
) -> dict[str, Any]:
    """Per-side inspect when enabled. old_* kept for API compatibility."""
    _ = old_receive, old_upload
    recv = None
    if new_receive_enabled:
        recv = inspect_inbound_transfer_rule(int(receive_port))
    upload = None
    if new_upload_enabled:
        upload = inspect_outbound_transfer_rule(int(upload_port))
    return {"recv": recv, "upload": upload}
