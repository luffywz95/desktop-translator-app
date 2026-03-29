"""Remote upload feature service for the Upload tab."""

from __future__ import annotations

from utils.remote_upload import post_file_multipart


def upload_file(url: str, local_path: str, token: str | None = None) -> tuple[int, str]:
    """
    Upload a file using multipart/form-data.
    Returns (status_code, response_text_or_error).
    """
    return post_file_multipart(
        url,
        local_path,
        field_name="file",
        bearer_token=token or None,
    )
