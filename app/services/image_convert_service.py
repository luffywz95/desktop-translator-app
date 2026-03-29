"""Pillow-based image format conversion for the Convert Image tab."""

from __future__ import annotations

from typing import Final

from PIL import Image

# Order matches design mockup; ICO kept for extra compatibility.
OUTPUT_FORMATS: Final[tuple[str, ...]] = (
    "PNG",
    "JPEG",
    "WEBP",
    "BMP",
    "GIF",
    "TIFF",
    "ICO",
)

LOSSY_FORMATS: Final[frozenset[str]] = frozenset({"JPEG", "WEBP"})


def default_extension(fmt: str) -> str:
    return {
        "PNG": ".png",
        "JPEG": ".jpg",
        "WEBP": ".webp",
        "BMP": ".bmp",
        "TIFF": ".tiff",
        "GIF": ".gif",
        "ICO": ".ico",
    }.get(fmt, ".png")


def open_image_first_frame(path: str) -> Image.Image:
    img = Image.open(path)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    return img.copy()


def prepare_for_format(img: Image.Image, fmt: str) -> Image.Image:
    if fmt == "JPEG":
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            alpha = img.getchannel("A") if img.mode == "RGBA" else None
            base = Image.new("RGB", img.size, (255, 255, 255))
            if alpha is not None:
                base.paste(img.convert("RGB"), mask=alpha)
            else:
                base.paste(img.convert("RGB"))
            return base
        return img.convert("RGB")

    if fmt == "BMP":
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA") if img.mode == "P" else img
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            return bg
        return img.convert("RGB")

    if fmt == "ICO":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        max_side = max(img.size)
        if max_side > 256:
            img = img.copy()
            img.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            return bg
        return img.convert("RGB")

    if fmt == "GIF":
        if img.mode not in ("P", "L", "1"):
            return img.convert("P", palette=Image.ADAPTIVE, colors=256)
        return img

    if fmt == "PNG":
        return img

    if fmt == "WEBP":
        return img

    if fmt == "TIFF":
        return img

    return img


def save_image(
    img: Image.Image,
    dest_path: str,
    fmt: str,
    *,
    quality: int,
    strip_metadata: bool = False,
) -> None:
    q = max(1, min(100, int(quality)))
    fmt_u = fmt.upper()
    work = img.copy() if strip_metadata else img
    if strip_metadata:
        work.info.clear()

    if fmt_u == "JPEG":
        kw: dict = {"quality": q, "optimize": True}
        if strip_metadata:
            kw["exif"] = b""
        work.save(dest_path, format="JPEG", **kw)
    elif fmt_u == "PNG":
        work.save(dest_path, format="PNG", optimize=True)
    elif fmt_u == "WEBP":
        work.save(dest_path, format="WEBP", quality=q, method=6)
    elif fmt_u == "BMP":
        work.save(dest_path, format="BMP")
    elif fmt_u == "TIFF":
        try:
            work.save(dest_path, format="TIFF", compression="tiff_lzw")
        except OSError:
            work.save(dest_path, format="TIFF")
    elif fmt_u == "GIF":
        work.save(dest_path, format="GIF", optimize=True)
    elif fmt_u == "ICO":
        work.save(dest_path, format="ICO", sizes=[work.size])
    else:
        work.save(dest_path)


def convert_file_to_path(
    src_path: str,
    dest_path: str,
    fmt: str,
    *,
    quality: int,
    strip_metadata: bool = False,
    cmyk_to_rgb: bool = False,
) -> None:
    img = open_image_first_frame(src_path)
    if cmyk_to_rgb and img.mode == "CMYK":
        img = img.convert("RGB")
    img = prepare_for_format(img, fmt)
    save_image(
        img, dest_path, fmt, quality=quality, strip_metadata=strip_metadata
    )
