from __future__ import annotations

from typing import Any, TypedDict


class ReceiveFileConfig(TypedDict):
    enable: bool
    port: int


class UploadFileConfig(TypedDict):
    enable: bool
    port: int
    remote_url: str
    remote_token: str


def get_port_or_default(raw: str, default: int = 5000) -> int:
    try:
        port = int(str(raw).strip())
        if 1 <= port <= 65535:
            return port
    except (TypeError, ValueError):
        pass
    return int(default)


def normalized_receive_file(settings: dict[str, Any]) -> ReceiveFileConfig:
    data = settings.get("receive_file")
    if not isinstance(data, dict):
        data = {}
    port = get_port_or_default(str(data.get("port", 5000)), 5000)
    return {"enable": bool(data.get("enable", False)), "port": port}


def normalized_upload_file(settings: dict[str, Any]) -> UploadFileConfig:
    data = settings.get("upload_file")
    if not isinstance(data, dict):
        data = {}
    port = get_port_or_default(str(data.get("port", 5000)), 5000)
    return {
        "enable": bool(data.get("enable", False)),
        "port": port,
        "remote_url": str(data.get("remote_url", "") or "").strip(),
        "remote_token": str(data.get("remote_token", "") or ""),
    }


def persist_transfer_hub_atomic(
    settings: Any,
    receive: ReceiveFileConfig,
    upload: UploadFileConfig,
) -> None:
    settings.begin_batch()
    settings["receive_file"] = dict(receive)
    settings["upload_file"] = dict(upload)
    settings.commit()
