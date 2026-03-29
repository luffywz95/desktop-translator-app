"""
Bluetooth device discovery, pairing, and OBEX Object Push file send (Windows WinRT).

Requires: pip install winrt-runtime winrt-Windows.Devices.Bluetooth
          winrt-Windows.Devices.Bluetooth.Rfcomm winrt-Windows.Devices.Enumeration
          winrt-Windows.Foundation winrt-Windows.Foundation.Collections
          winrt-Windows.Networking winrt-Windows.Networking.Sockets
          winrt-Windows.Storage.Streams
"""

from __future__ import annotations

import asyncio
import os
import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

__all__ = [
    "BT_SEND_WATCHDOG_USER_MSG",
    "BtDeviceInfo",
    "bluetooth_send_ui_watchdog_timeout_sec",
    "bluetooth_transfer_available",
    "has_bluetooth_adapter_async",
    "list_devices_async",
    "pair_device_async",
    "send_file_obex_async",
]

# WinRT/HRESULT observed when the stream/socket is closed by the peer or OS.
_WINRT_OBJECT_CLOSED = -2147483629

# UI watchdog budget (see bluetooth_send_ui_watchdog_timeout_sec). Not used with asyncio.wait_for:
# winrt.runtime.wrap_async awaits the WinRT op again after cancel; if cancel does not complete,
# that wait blocks forever and asyncio.wait_for never returns.
_BT_SOCKET_CONNECT_BUDGET_SEC = 60.0

BT_SEND_WATCHDOG_USER_MSG = (
    "Bluetooth transfer took too long waiting for the other device. "
    "It may have declined the file, or the connection stalled. Try again."
)


def bluetooth_send_ui_watchdog_timeout_sec(file_size_bytes: int) -> float:
    """
    Wall-clock limit for the Upload-tab Bluetooth send (main-thread Tk after callback).

    WinRT DataReader.load_async does not reliably honor asyncio cancellation, so the UI
    must not depend on asyncio.wait_for for recovery.
    """
    est_chunks = max(1, (max(0, int(file_size_bytes)) + 1500 - 1) // 1500)
    per_chunk_sec = 35.0
    transfer_budget = est_chunks * per_chunk_sec
    return min(14400.0, max(90.0, _BT_SOCKET_CONNECT_BUDGET_SEC + 15.0 + transfer_budget))


@dataclass
class BtDeviceInfo:
    device_id: str
    name: str
    is_paired: bool
    can_pair: bool


def bluetooth_transfer_available() -> Tuple[bool, str]:
    try:
        from winrt.windows.devices.bluetooth import BluetoothDevice  # noqa: F401
        from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId  # noqa: F401
        from winrt.windows.devices.enumeration import DeviceInformation  # noqa: F401
        from winrt.windows.networking import HostName  # noqa: F401
        from winrt.windows.networking.sockets import StreamSocket  # noqa: F401
        from winrt.windows.storage.streams import DataReader  # noqa: F401

        return True, ""
    except ImportError as e:
        return False, (
            "Bluetooth transfer needs WinRT packages. "
            f"Missing module: {e}. From the project folder run:\n"
            "pip install winrt-runtime winrt-Windows.Devices.Bluetooth "
            "winrt-Windows.Devices.Bluetooth.Rfcomm winrt-Windows.Devices.Enumeration "
            "winrt-Windows.Foundation winrt-Windows.Foundation.Collections "
            "winrt-Windows.Networking winrt-Windows.Networking.Sockets "
            "winrt-Windows.Storage.Streams"
        )


def _collection_to_list(devices) -> List:
    return [devices[i] for i in range(devices.size)]


async def has_bluetooth_adapter_async() -> bool:
    """Return True when Windows reports a default Bluetooth adapter."""
    try:
        from winrt.windows.devices.bluetooth import BluetoothAdapter
    except ImportError:
        return False
    try:
        adapter = await BluetoothAdapter.get_default_async()
        return adapter is not None
    except Exception:
        return False


def _merge_device_maps(
    paired_infos: List,
    extra_infos: List,
) -> dict[str, tuple]:
    """device_id -> (name, is_paired, can_pair)"""
    out: dict[str, tuple[str, bool, bool]] = {}
    for info in paired_infos:
        pid = info.id
        pr = info.pairing
        out[pid] = (info.name or pid, True, bool(pr.can_pair))
    for info in extra_infos:
        pid = info.id
        if pid in out:
            continue
        pr = info.pairing
        out[pid] = (info.name or pid, bool(pr.is_paired), bool(pr.can_pair))
    return out


async def list_devices_async(unpaired_timeout: float = 8.0) -> List[BtDeviceInfo]:
    from winrt.windows.devices.bluetooth import BluetoothDevice
    from winrt.windows.devices.enumeration import DeviceInformation

    aqs_paired = BluetoothDevice.get_device_selector_from_pairing_state(True)
    paired_coll = await DeviceInformation.find_all_async_aqs_filter(aqs_paired)
    paired_list = _collection_to_list(paired_coll)

    extra_list: List = []
    try:
        aqs_all = BluetoothDevice.get_device_selector_from_pairing_state(False)
        op = DeviceInformation.find_all_async_aqs_filter(aqs_all)
        all_coll = await asyncio.wait_for(op, timeout=unpaired_timeout)
        extra_list = _collection_to_list(all_coll)
    except (asyncio.TimeoutError, Exception):
        pass

    merged = _merge_device_maps(paired_list, extra_list)
    items = [
        BtDeviceInfo(
            device_id=pid,
            name=name,
            is_paired=is_paired,
            can_pair=can_pair,
        )
        for pid, (name, is_paired, can_pair) in sorted(
            merged.items(), key=lambda x: (not x[1][1], x[1][0].lower())
        )
    ]
    return items


async def pair_device_async(device_id: str) -> Tuple[bool, str]:
    from winrt.windows.devices.enumeration import (
        DeviceInformation,
        DevicePairingResultStatus,
    )

    info = await DeviceInformation.create_from_id_async(device_id)
    pr = info.pairing
    if pr.is_paired:
        return True, "Already paired."
    if not pr.can_pair:
        return (
            False,
            "This device cannot be paired from here (open Windows Bluetooth settings).",
        )
    result = await pr.pair_async()
    st = result.status
    if st == DevicePairingResultStatus.PAIRED:
        return True, "Paired successfully."
    if st == DevicePairingResultStatus.ALREADY_PAIRED:
        return True, "Already paired."
    return False, f"Pairing failed: {st.name}"


def _parse_obex_peer_mtu(resp: bytes) -> int:
    """Max OBEX packet length from CONNECT response (bytes 5–6 after 3-byte OBEX header)."""
    if len(resp) >= 7 and resp[0] in (0xA0, 0x90):
        return max(64, (resp[5] << 8) | resp[6])
    return 0x1000


def _parse_obex_connect_id(resp: bytes) -> Optional[int]:
    """Optional ConnectionId (0xCB + 4-byte value) after fixed 7-byte CONNECT response prefix."""
    if len(resp) < 3 or resp[0] not in (0xA0, 0x90):
        return None
    total = (resp[1] << 8) | resp[2]
    i = 7  # version, flags, max-packet (4 bytes) follow the 3-byte OBEX header
    while i < len(resp) and i < total:
        hid = resp[i]
        if hid == 0xCB:
            if i + 5 <= len(resp):
                return int.from_bytes(resp[i + 1 : i + 5], "big")
            return None
        if hid in (0x01, 0x02):
            if i + 2 > len(resp):
                break
            hl = (resp[i + 1] << 8) | resp[i + 2]
            if hl < 3:
                break
            i += hl
        elif hid in (0x48, 0x49):
            if i + 2 > len(resp):
                break
            hl = (resp[i + 1] << 8) | resp[i + 2]
            if hl < 3:
                break
            i += hl
        elif 0xC0 <= hid <= 0xCF:
            # 4-byte quantity (ConnectionId, Count, etc.): 1 + 4 bytes
            if i + 5 > len(resp):
                break
            i += 5
        else:
            break
    return None


def _obex_name_header(filename: str) -> bytes:
    base = os.path.basename(filename) or "file.bin"
    body = base.encode("utf-16-be") + b"\x00\x00"
    total = 3 + len(body)
    return struct.pack(">BH", 0x01, total) + body


def _obex_length_header(n: int) -> bytes:
    # OBEX 4-byte quantity header: id (0xC3) + 4-byte value
    return struct.pack(">BI", 0xC3, n)


def _obex_body_header(data: bytes, final: bool) -> bytes:
    opcode = 0x49 if final else 0x48
    total = 3 + len(data)
    return struct.pack(">BH", opcode, total) + data


def _obex_connect_packet() -> bytes:
    # Max OBEX packet size (big-endian at bytes 5–6). 0x0020 (32) is invalid — PUT frames exceed
    # it and the peer closes the socket; failure often surfaces on the next DataWriter.store_async.
    mtu = 0x1000
    return struct.pack(">BHBBH", 0x80, 7, 0x10, 0x00, mtu)


def _obex_put_packet(
    conn_id: Optional[int],
    name_hdr: bytes,
    length_hdr: bytes,
    body: bytes,
    is_final_body: bool,
) -> bytes:
    opcode = 0x82 if is_final_body else 0x02
    payload = bytearray()
    if conn_id is not None:
        # OBEX 4-byte quantity header: id (0xCB) + 4-byte value
        payload.extend([0xCB])
        payload.extend(struct.pack(">I", conn_id))
    payload.extend(name_hdr)
    payload.extend(length_hdr)
    payload.extend(_obex_body_header(body, is_final_body))
    plen = 3 + len(payload)
    return bytes([opcode, (plen >> 8) & 0xFF, plen & 0xFF]) + bytes(payload)


async def _read_exact(dr, n_bytes: int) -> bytes:
    """Read exactly n_bytes from a single shared WinRT DataReader (one per socket)."""
    if n_bytes <= 0:
        return b""
    out = bytearray()
    while len(out) < n_bytes:
        needed = n_bytes - len(out)
        loaded = await dr.load_async(needed)
        if loaded == 0:
            break
        chunk = bytearray(int(loaded))
        dr.read_bytes(chunk)
        out.extend(chunk)
    return bytes(out)


async def _read_obex_packet(dr) -> bytes:
    head = await _read_exact(dr, 3)
    if len(head) < 3:
        return head
    total = (head[1] << 8) | head[2]
    if total <= 3:
        return head
    body = await _read_exact(dr, total - 3)
    return head + body


async def _write_obex(dw, data: bytes) -> None:
    """Append to a single session DataWriter (one per socket output stream)."""
    dw.write_bytes(bytearray(data))
    await dw.store_async()
    await dw.flush_async()


async def send_file_obex_async(device_id: str, file_path: str) -> Tuple[bool, str]:
    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothCacheMode,
            BluetoothDevice,
            BluetoothError,
        )
        from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
        from winrt.windows.devices.enumeration import DeviceAccessStatus
        from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocket
        from winrt.windows.storage.streams import DataReader, DataWriter
    except ImportError as e:
        return (
            False,
            "Bluetooth runtime dependency missing. "
            f"{e}. Install with: pip install winrt-runtime "
            "winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Bluetooth.Rfcomm "
            "winrt-Windows.Devices.Enumeration winrt-Windows.Foundation "
            "winrt-Windows.Foundation.Collections winrt-Windows.Networking "
            "winrt-Windows.Networking.Sockets winrt-Windows.Storage.Streams",
        )

    if not os.path.isfile(file_path):
        return False, "File does not exist."

    size = os.path.getsize(file_path)
    device = await BluetoothDevice.from_id_async(device_id)
    if device is None:
        return False, "Could not open Bluetooth device."

    res = await device.get_rfcomm_services_for_id_with_cache_mode_async(
        RfcommServiceId.obex_object_push,
        BluetoothCacheMode.UNCACHED,
    )
    if res.error != BluetoothError.SUCCESS:
        return False, f"Bluetooth service query failed ({res.error.name})."
    svcs = res.services
    if svcs.size == 0:
        return False, "Object Push (OBEX) is not available on this device."

    svc = svcs[0]
    access = await svc.request_access_async()
    if access != DeviceAccessStatus.ALLOWED:
        return (
            False,
            "Access to the Bluetooth service was denied. Allow access in Windows.",
        )

    sock = StreamSocket()
    try:
        host = svc.connection_host_name
        port = svc.connection_service_name
        level = svc.protection_level
        if level == SocketProtectionLevel.PLAIN_SOCKET:
            level = svc.max_protection_level
        await sock.connect_with_protection_level_async(host, port, level)

        reader = sock.input_stream
        writer = sock.output_stream
        dr = DataReader(reader)
        dw = DataWriter(writer)

        await _write_obex(dw, _obex_connect_packet())
        r0 = await _read_obex_packet(dr)
        if len(r0) < 3 or r0[0] not in (0xA0, 0x90):
            if not r0:
                return (
                    False,
                    "The device closed the link before accepting the transfer. "
                    "Confirm on the phone that it is ready to receive files over Bluetooth.",
                )
            return (
                False,
                "The device rejected the transfer during setup, or the link dropped. "
                f"(Technical detail: {r0[:16]!r})",
            )

        conn_id = _parse_obex_connect_id(r0)
        peer_mtu = _parse_obex_peer_mtu(r0)

        name_hdr = _obex_name_header(file_path)
        len_hdr = _obex_length_header(size)
        # OBEX packet length must stay within negotiated MTU (opcode+len + headers + body chunk).
        put_overhead = (
            3
            + (5 if conn_id is not None else 0)
            + len(name_hdr)
            + len(len_hdr)
            + 3  # body header (opcode + 2-byte length, no body bytes yet)
        )
        max_body = max(256, min(2048, peer_mtu - put_overhead))
        remaining = size
        first_put = True
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(min(max_body, remaining)) if remaining > 0 else b""
                if remaining > 0 and not chunk:
                    return False, "Unexpected end while reading local file."
                remaining -= len(chunk)
                is_final = remaining == 0
                if first_put:
                    pkt = _obex_put_packet(conn_id, name_hdr, len_hdr, chunk, is_final)
                    first_put = False
                else:
                    pkt = _obex_put_packet(conn_id, b"", b"", chunk, is_final)
                await _write_obex(dw, pkt)
                ack = await _read_obex_packet(dr)
                if len(ack) < 3:
                    return (
                        False,
                        "The device stopped replying during the transfer. "
                        "It may have declined the file or disconnected.",
                    )
                if is_final:
                    if ack[0] in (0xA0, 0x90):
                        return True, "File sent."
                    return (
                        False,
                        "The device refused or could not complete the transfer. "
                        f"(Technical detail: {ack[:32]!r})",
                    )
                if ack[0] not in (0xA0, 0x90, 0x10):
                    return (
                        False,
                        "The transfer was interrupted by the device. "
                        f"(Technical detail: {ack[:32]!r})",
                    )

        return False, "Unexpected end while sending file."
    except OSError as e:
        # Convert opaque WinRT HRESULT text to an actionable Bluetooth message.
        if getattr(e, "winerror", None) == _WINRT_OBJECT_CLOSED:
            return (
                False,
                "Bluetooth connection was closed by the target device. "
                "Make sure the target supports OBEX Object Push, is paired, "
                "and is unlocked/ready to receive files, then try again.",
            )
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    finally:
        try:
            sock.close()
        except Exception:
            pass


def run_coroutine(coro):
    """Run async WinRT coroutine from a worker thread (fresh event loop)."""
    return asyncio.run(coro)
