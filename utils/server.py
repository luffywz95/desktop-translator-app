import os
import sys

# Project root must be on sys.path when this file is run directly (python utils/server.py).
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from flask import Flask, jsonify, render_template, request  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from components.logger import Logger  # noqa: E402

# --- Transfer Hub: image + generic file uploads (separate folders & handlers) ---

IMAGE_FOLDER = os.path.join(_root, "received", "images")
FILE_FOLDER = os.path.join(_root, "received", "files")
ALLOWED_IMAGE_EXTENSIONS = frozenset(
    ".jpg .jpeg .png .gif .webp .bmp .tif .tiff .heic .heif .ico .avif".split()
)

os.makedirs(IMAGE_FOLDER, exist_ok=True)
os.makedirs(FILE_FOLDER, exist_ok=True)

app = Flask(
    __name__,
    template_folder=os.path.join(_root, "templates"),
)

logger = Logger().get()


def _ext_ok(filename: str, allowed: frozenset[str]) -> bool:
    return os.path.splitext(filename)[1].lower() in allowed


def _handle_image_upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No image file provided"}), 400
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if not _ext_ok(file.filename, ALLOWED_IMAGE_EXTENSIONS):
        return (
            jsonify(
                {
                    "error": "Not a supported image type. "
                    "Use common formats (JPEG, PNG, GIF, WebP, HEIC, etc.)."
                }
            ),
            400,
        )

    filename = secure_filename(file.filename)
    filepath = os.path.join(IMAGE_FOLDER, filename)
    file.save(filepath)
    logger.info(f"[Transfer Hub] Image saved: {filepath}")

    # --- OCR / processing hook ---
    text = "Example OCR Result: 'Hello World'"

    return jsonify(
        {
            "message": "Image received successfully!",
            "filename": filename,
            "ocr_result": text,
        }
    ), 200


def _handle_file_upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(FILE_FOLDER, filename)
    file.save(filepath)
    size_bytes = os.path.getsize(filepath)
    logger.info(f"[Transfer Hub] File saved: {filepath} ({size_bytes} bytes)")

    return jsonify(
        {
            "message": "File received successfully!",
            "filename": filename,
            "size_bytes": size_bytes,
        }
    ), 200


@app.route("/")
def transfer_hub_home():
    """Transfer Hub — tabbed UI for image vs. file uploads."""
    return render_template("transfer_hub.html")


@app.route("/upload/image", methods=["POST"])
def upload_image():
    return _handle_image_upload()


@app.route("/upload/file", methods=["POST"])
def upload_file():
    return _handle_file_upload()


# Backward compatibility for older clients (e.g. Flutter) posting to /upload-image
@app.route("/upload-image", methods=["POST"])
def upload_image_legacy():
    return _handle_image_upload()


if __name__ == "__main__":
    # use_reloader=False: when launched from main.pyw, a single child process must be stoppable.
    # TRANSFER_HUB_DEBUG=1 enables Flask debug for manual runs (python utils/server.py).
    # TRANSFER_HUB_HOST / TRANSFER_HUB_PORT set by utils.transfer_hub_runner (LAN vs localhost).
    _debug = os.environ.get("TRANSFER_HUB_DEBUG", "").lower() in ("1", "true", "yes")
    _host = os.environ.get("TRANSFER_HUB_HOST", "127.0.0.1")
    _port = int(os.environ.get("TRANSFER_HUB_PORT", "5000"))
    app.run(
        host=_host,
        port=_port,
        debug=_debug,
        use_reloader=False,
    )
