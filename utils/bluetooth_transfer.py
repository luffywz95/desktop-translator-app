"""
Bluetooth device discovery, pairing, and OBEX Object Push file send (Windows WinRT).

Requires: pip install winrt-runtime winrt-Windows.Devices.Bluetooth
          winrt-Windows.Devices.Bluetooth.Rfcomm winrt-Windows.Devices.Enumeration
          winrt-Windows.Foundation winrt-Windows.Networking.Sockets
          winrt-Windows.Storage.Streams
"""

from __future__ import annotations

import asyncio
import os
import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

__all__ = [
    "BtDeviceInfo",
    "bluetooth_transfer_available",
    "list_devices_async",
    "pair_device_async",
    "send_file_obex_async",
]


@dataclass
class BtDeviceInfo:
    device_id: str
    name: str
    is_paired: bool
    can_pair: bool


def bluetooth_transfer_available() -> Tuple[bool, str]:
    try:
        from winrt.windows.devices.bluetooth import BluetoothDevice  # noqa: F401
        from winrt.windows.devices.enumeration import DeviceInformation  # noqa: F401

        return True, ""
    except ImportError as e:
        return False, (
            "Bluetooth transfer needs WinRT packages. From the project folder run:\n"
            "pip install winrt-runtime winrt-Windows.Devices.Bluetooth "
            "winrt-Windows.Devices.Bluetooth.Rfcomm winrt-Windows.Devices.Enumeration "
            "winrt-Windows.Foundation winrt-Windows.Networking.Sockets "
            "winrt-Windows.Storage.Streams"
        )


def _collection_to_list(devices) -> List:
    return [devices[i] for i in range(devices.size)]


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
    from winrt.windows.devices.enumeration import DeviceInformation, DevicePairingResultStatus

    info = await DeviceInformation.create_from_id_async(device_id)
    pr = info.pairing
    if pr.is_paired:
        return True, "Already paired."
    if not pr.can_pair:
        return False, "This device cannot be paired from here (open Windows Bluetooth settings)."
    result = await pr.pair_async()
    st = result.status
    if st == DevicePairingResultStatus.PAIRED:
        return True, "Paired successfully."
    if st == DevicePairingResultStatus.ALREADY_PAIRED:
        return True, "Already paired."
    return False, f"Pairing failed: {st.name}"


def _parse_obex_connect_id(resp: bytes) -> Optional[int]:
    if len(resp) < 3 or resp[0] not in (0xA0, 0x90):
        return None
    total = (resp[1] << 8) | resp[2]
    i = 3
    while i + 2 < len(resp) and i < total:
        hid = resp[i]
        if hid == 0xCB:
            if i + 6 <= len(resp):
                return int.from_bytes(resp[i + 3 : i + 7], "big")
            return None
        if hid in (0x01, 0x02, 0x48, 0x49):
            if i + 2 > len(resp):
                break
            hl = (resp[i + 1] << 8) | resp[i + 2]
            if hl < 3:
                break
            i += hl
        elif 0xC0 <= hid <= 0xFF:
            if i + 1 >= len(resp):
                break
            vl = resp[i + 1]
            i += 2 + vl
        else:
            break
    return None


def _obex_name_header(filename: str) -> bytes:
    base = os.path.basename(filename) or "file.bin"
    body = base.encode("utf-16-be") + b"\x00\x00"
    total = 3 + len(body)
    return struct.pack(">BH", 0x01, total) + body


def _obex_length_header(n: int) -> bytes:
    return struct.pack(">BBL", 0xC3, 5, n)


def _obex_body_header(data: bytes, final: bool) -> bytes:
    opcode = 0x49 if final else 0x48
    total = 3 + len(data)
    return struct.pack(">BH", opcode, total) + data


def _obex_connect_packet() -> bytes:
    return bytes([0x80, 0x00, 0x07, 0x10, 0x00, 0x20, 0x00])


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
        payload.extend([0xCB, 0x00, 0x05])
        payload.extend(struct.pack(">I", conn_id))
    payload.extend(name_hdr)
    payload.extend(length_hdr)
    payload.extend(_obex_body_header(body, is_final_body))
    plen = 3 + len(payload)
    return bytes([opcode, (plen >> 8) & 0xFF, plen & 0xFF]) + bytes(payload)


async def _read_obex_chunk(reader) -> bytes:
    from winrt.windows.storage.streams import DataReader, InputStreamOptions

    dr = DataReader(reader)
    dr.input_stream_options = InputStreamOptions.PARTIAL
    n = await dr.load_async(8192)
    if n == 0:
        return b""
    out = bytearray()
    for _ in range(int(n)):
        out.append(dr.read_byte())
    return bytes(out)


async def _write_obex(writer, data: bytes) -> None:
    from winrt.windows.storage.streams import DataWriter

    dw = DataWriter(writer)
    dw.write_bytes(bytearray(data))
    await dw.store_async()
    await dw.flush_async()


async def send_file_obex_async(device_id: str, file_path: str) -> Tuple[bool, str]:
    from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice, BluetoothError
    from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
    from winrt.windows.devices.enumeration import DeviceAccessStatus
    from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocket

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
        return False, "Access to the Bluetooth service was denied. Allow access in Windows."

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

        await _write_obex(writer, _obex_connect_packet())
        r0 = await _read_obex_chunk(reader)
        if len(r0) < 3 or r0[0] not in (0xA0, 0x90):
            return False, f"OBEX connect rejected ({r0[:16]!r})."

        conn_id = _parse_obex_connect_id(r0)

        name_hdr = _obex_name_header(file_path)
        len_hdr = _obex_length_header(size)

        max_body = 2048
        remaining = size
        first_put = True
        with open(file_path, "rb") as f:
            while remaining > 0:
                chunk = f.read(min(max_body, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                is_final = remaining == 0
                if first_put:
                    pkt = _obex_put_packet(conn_id, name_hdr, len_hdr, chunk, is_final)
                    first_put = False
                else:
                    pkt = _obex_put_packet(conn_id, b"", b"", chunk, is_final)
                await _write_obex(writer, pkt)
                ack = await _read_obex_chunk(reader)
                if is_final:
                    if len(ack) >= 1 and ack[0] in (0xA0, 0x90):
                        return True, "File sent."
                    return False, f"OBEX put failed ({ack[:32]!r})."
                if len(ack) >= 1 and ack[0] not in (0xA0, 0x90, 0x10):
                    return False, f"OBEX put interrupted ({ack[:32]!r})."

        return False, "Unexpected end while sending file."
    except OSError as e:
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
