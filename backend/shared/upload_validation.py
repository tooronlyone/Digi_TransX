"""Content-verified, metadata-stripped upload validation for V1 media and truck docs."""

from io import BytesIO
import os
from pathlib import Path
import re
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


MAX_IMAGE_PIXELS = 25_000_000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

IMAGE_EXT_TO_PILLOW = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}

MIME_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
}

_MP4_BRANDS = frozenset({
    b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"M4A ", b"f4v ", b"dash", b"msnv",
})
_MOV_BRANDS = frozenset({b"qt  "})
_DANGEROUS_PDF_TOKEN_RE = re.compile(
    rb"/(?:JavaScript|JS|Launch|OpenAction|AA|SubmitForm)\b", re.IGNORECASE
)


def _read_bounded_stream(stream, max_bytes):
    if stream is None:
        return b""
    try:
        stream.seek(0)
    except Exception:
        pass
    chunks = []
    total = 0
    chunk_size = 65536
    while total <= max_bytes:
        chunk = stream.read(min(chunk_size, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    try:
        stream.seek(0)
    except Exception:
        pass
    return b"".join(chunks)


def _matches_image_magic(raw_bytes, extension):
    if extension in {"jpg", "jpeg"}:
        return len(raw_bytes) >= 3 and raw_bytes[:3] == b"\xff\xd8\xff"
    if extension == "png":
        return len(raw_bytes) >= 8 and raw_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    if extension == "webp":
        return len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP"
    return False


def _sanitize_image(raw_bytes, extension, max_bytes, error_cls, invalid_content_msg):
    if not _matches_image_magic(raw_bytes, extension):
        raise error_cls(invalid_content_msg)
    expected_format = IMAGE_EXT_TO_PILLOW[extension]
    prior_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(BytesIO(raw_bytes)) as verified_img:
            if (verified_img.format or "").upper() != expected_format:
                raise error_cls(invalid_content_msg)
            verified_img.verify()

        with Image.open(BytesIO(raw_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            img.load()
            width, height = img.size
            if width <= 0 or height <= 0 or (width * height) > MAX_IMAGE_PIXELS:
                raise error_cls("Image dimensions exceed the maximum allowed resolution.")
            if img.mode == "P":
                img = img.convert("RGBA" if "transparency" in img.info else "RGB")
            if expected_format == "JPEG":
                if img.mode != "RGB":
                    img = img.convert("RGB")
                save_kwargs = {"format": "JPEG", "quality": 90, "optimize": True}
            elif expected_format == "PNG":
                if img.mode not in {"RGB", "RGBA", "L", "LA"}:
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                save_kwargs = {"format": "PNG", "optimize": True}
            else:
                if img.mode not in {"RGB", "RGBA", "L"}:
                    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
                save_kwargs = {"format": "WEBP", "quality": 90}

            # Re-encode into a fresh container so EXIF, XMP, IPTC, and trailing payloads are stripped.
            clean_image = Image.new(img.mode, img.size)
            clean_image.paste(img)
            out = BytesIO()
            clean_image.save(out, **save_kwargs)
            sanitized = out.getvalue()
    except error_cls:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise error_cls(invalid_content_msg) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = prior_max_pixels

    if not sanitized or len(sanitized) > max_bytes:
        raise error_cls("Uploaded image exceeds the maximum supported size after processing.")
    return sanitized


def _validate_pdf(raw_bytes, error_cls, invalid_content_msg):
    if len(raw_bytes) < 32:
        raise error_cls(invalid_content_msg)
    if not (raw_bytes.startswith(b"%PDF-1.") or raw_bytes.startswith(b"%PDF-2.")):
        raise error_cls(invalid_content_msg)
    if b"%%EOF" not in raw_bytes[-4096:]:
        raise error_cls(invalid_content_msg)
    if _DANGEROUS_PDF_TOKEN_RE.search(raw_bytes):
        raise error_cls("PDF files containing active scripts or launch actions are not allowed.")
    return raw_bytes


def _validate_video(raw_bytes, extension, error_cls, invalid_content_msg):
    if len(raw_bytes) < 16:
        raise error_cls(invalid_content_msg)
    box_size = int.from_bytes(raw_bytes[:4], "big")
    if box_size < 12 or raw_bytes[4:8] != b"ftyp":
        raise error_cls(invalid_content_msg)
    brand = raw_bytes[8:12]
    if extension == "mp4" and brand not in _MP4_BRANDS:
        raise error_cls(invalid_content_msg)
    if extension == "mov" and brand not in _MOV_BRANDS:
        raise error_cls(invalid_content_msg)
    return raw_bytes


def validate_and_sanitize_upload(
    file_storage,
    *,
    owner_prefix,
    allowed_extensions,
    max_bytes=MAX_UPLOAD_BYTES,
    error_cls=ValueError,
    invalid_extension_message="Unsupported file type.",
    oversized_message="Uploaded file exceeds maximum size.",
    invalid_content_message="Uploaded file content does not match a valid supported format.",
):
    """Validate extension, size, magic signature, and image structure cleanly.

    Returns ``(generated_filename, sanitized_file_storage)``.
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        raise error_cls("A file is required.")

    safe_original = secure_filename(file_storage.filename or "")
    extension = Path(safe_original).suffix.lower().lstrip(".")
    if not extension or extension not in allowed_extensions:
        raise error_cls(invalid_extension_message)

    raw_bytes = _read_bounded_stream(getattr(file_storage, "stream", None), max_bytes)
    if not raw_bytes:
        raise error_cls("Uploaded file cannot be empty.")
    if len(raw_bytes) > max_bytes:
        raise error_cls(oversized_message)

    if extension in IMAGE_EXT_TO_PILLOW:
        sanitized_bytes = _sanitize_image(
            raw_bytes, extension, max_bytes, error_cls, invalid_content_message
        )
    elif extension == "pdf":
        sanitized_bytes = _validate_pdf(raw_bytes, error_cls, invalid_content_message)
    elif extension in {"mp4", "mov"}:
        sanitized_bytes = _validate_video(raw_bytes, extension, error_cls, invalid_content_message)
    else:
        raise error_cls(invalid_extension_message)

    generated_name = f"{owner_prefix}_{uuid4().hex}.{extension}"
    mime_type = MIME_BY_EXTENSION[extension]
    sanitized_storage = FileStorage(
        stream=BytesIO(sanitized_bytes),
        filename=generated_name,
        content_type=mime_type,
    )
    return generated_name, sanitized_storage
