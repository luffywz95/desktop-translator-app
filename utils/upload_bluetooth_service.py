"""Bluetooth upload feature service for the Upload tab."""

from __future__ import annotations

from utils import bluetooth_transfer as bt


_IOS_NAME_HINTS = ("iphone", "ipad", "ipod", "ios")


def is_ios_like_name(device_name: str) -> bool:
    """Best-effort iOS name detection for UI guardrails."""
    low = (device_name or "").strip().lower()
    return any(tag in low for tag in _IOS_NAME_HINTS)


def bluetooth_runtime_available() -> tuple[bool, str]:
    """Check WinRT Bluetooth runtime/package availability."""
    return bt.bluetooth_transfer_available()


def send_file_to_device(device_id: str, local_path: str) -> tuple[bool, str]:
    """Send file over OBEX Object Push to selected device id."""
    return bt.run_coroutine(bt.send_file_obex_async(device_id, local_path))
