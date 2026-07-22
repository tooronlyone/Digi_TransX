import os
import re
import time
from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename

from shared.db import BASE_DIR


CHAT_UPLOADS_DIR = BASE_DIR / "backend" / "uploads" / "chat"
ALLOWED_MEDIA_EXTENSIONS = {"jpg", "jpeg", "png", "mp4", "mov"}
MAX_MESSAGE_LENGTH = 2000
MAX_MEDIA_BYTES = 10 * 1024 * 1024
MEDIA_REQUEST_PENDING = "pending"
MEDIA_REQUEST_APPROVED = "approved"
MEDIA_REQUEST_DENIED = "denied"
MEDIA_REQUEST_FULFILLED = "fulfilled"
TEXT_MESSAGE = "text"
MEDIA_REQUEST_MESSAGE = "media_request"
MEDIA_MESSAGE = "media"
SYSTEM_MESSAGE = "system"
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
VIDEO_EXTENSIONS = {"mp4", "mov"}


def normalize_message_type(value):
    return (value or TEXT_MESSAGE).strip().lower()


def parse_message_payload(data):
    message_type = normalize_message_type(data.get("message_type"))
    content = (data.get("content") or "").strip()

    if message_type == TEXT_MESSAGE:
        if not content:
            raise ValueError("Message content is required.")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message content cannot exceed {MAX_MESSAGE_LENGTH} characters.")
    elif message_type == MEDIA_REQUEST_MESSAGE:
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message content cannot exceed {MAX_MESSAGE_LENGTH} characters.")
    else:
        raise ValueError("Invalid message type.")

    return message_type, content


def validate_media_file(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Media file is required.")

    safe_name = secure_filename(file_storage.filename)
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in ALLOWED_MEDIA_EXTENSIONS:
        raise ValueError("Only JPG, JPEG, PNG, MP4, and MOV files are allowed.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_MEDIA_BYTES:
        raise ValueError("Media file must be 10MB or smaller.")

    return safe_name, extension


def make_chat_upload_relative_path(thread_id, file_storage):
    """Upload chat media to Supabase Storage. Returns the stored filename."""
    from shared.storage import upload_file_storage

    safe_name, _ = validate_media_file(file_storage)
    stem = Path(safe_name).stem or "media"
    extension = Path(safe_name).suffix.lower()
    compact_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-") or "media"
    filename = f"{thread_id}_{int(time.time())}_{uuid4().hex[:8]}_{compact_stem}{extension}"
    upload_file_storage(f"uploads/chat/{filename}", file_storage)
    return filename


def ensure_one_time_thread(db, shipment_id, trip_id, client_user_id, transporter_user_id):
    """Create (or reuse) the single chat thread for an accepted one-time order.

    One thread per accepted one-time shipment (uniq_chat_thread_one_time). Safe
    to call repeatedly and concurrently — a race falls back to the existing row.
    Does NOT commit. Returns the thread id.
    """
    from shared.db import IntegrityError

    existing = db.execute(
        "SELECT id FROM chat_threads WHERE shipment_id = %s", (shipment_id,)
    ).fetchone()
    if existing:
        return existing["id"]
    try:
        row = db.execute(
            """
            INSERT INTO chat_threads (
                client_user_id, transporter_user_id, shipment_id, one_time_trip_id, created_at
            ) VALUES (%s, %s, %s, %s, now())
            RETURNING id
            """,
            (client_user_id, transporter_user_id, shipment_id, trip_id),
        ).fetchone()
        return row["id"]
    except IntegrityError:
        # Concurrent creator won the unique index — reuse their row.
        existing = db.execute(
            "SELECT id FROM chat_threads WHERE shipment_id = %s", (shipment_id,)
        ).fetchone()
        return existing["id"] if existing else None


def build_thread_order_summary(row):
    # One-time order threads carry a shipment_id; agreement threads carry an
    # agreement_post_id. Present whichever this thread is bound to.
    if row.get("shipment_id"):
        return {
            "id": row.get("shipment_id"),
            "pickup_city": row.get("order_pickup_city") or "Pickup",
            "dropoff_city": row.get("order_dropoff_city") or "Drop-off",
            "status": row.get("order_status") or "open",
            "route_label": (
                f"{row.get('order_pickup_city') or 'Pickup'} → "
                f"{row.get('order_dropoff_city') or 'Drop-off'}"
            ),
            "kind": "one_time",
        }
    return {
        "id": row.get("agreement_post_id"),
        "pickup_city": row.get("agreement_title") or "Agreement",
        "dropoff_city": row.get("agreement_service_area") or "",
        "status": row.get("agreement_status") or "open",
        "route_label": row.get("agreement_title") or "Agreement shipment",
        "kind": "agreement",
    }


def serialize_thread(row, current_user_id):
    row = dict(row)
    other_user_id = row["transporter_user_id"] if row["client_user_id"] == current_user_id else row["client_user_id"]
    other_party_name = row["transporter_name"] if row["client_user_id"] == current_user_id else row["client_name"]
    return {
        "id": row["id"],
        "agreement_post_id": row.get("agreement_post_id"),
        "agreement_bid_id": row.get("agreement_bid_id"),
        "client_user_id": row["client_user_id"],
        "transporter_user_id": row["transporter_user_id"],
        "other_user_id": other_user_id,
        "other_party_name": other_party_name,
        "last_message_at": row["last_message_at"] or row["created_at"],
        "last_message_preview": row.get("last_message_preview") or "No messages yet.",
        "unread_count": int(row.get("unread_count") or 0),
        "order": build_thread_order_summary(row),
    }


def serialize_message(row, current_user_id=None):
    media_filename = row["media_path"] if row["media_path"] else None
    extension = media_filename.rsplit(".", 1)[-1].lower() if media_filename and "." in media_filename else ""
    message = {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "sender_user_id": row["sender_user_id"],
        "sender_name": row.get("sender_name") or "User",
        "message_type": row["message_type"],
        "content": row["content"] or "",
        "media_path": f"/uploads/chat/{media_filename}" if media_filename else None,
        "media_request_status": row["media_request_status"],
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
        "is_own": current_user_id is not None and row["sender_user_id"] == current_user_id,
        "media_kind": "image" if extension in IMAGE_EXTENSIONS else ("video" if extension in VIDEO_EXTENSIONS else None),
    }
    return message


def make_media_approval_system_message(requester_name):
    base = "Media request approved - you can now send a photo/video"
    if requester_name:
        return f"{base}, {requester_name}."
    return base
