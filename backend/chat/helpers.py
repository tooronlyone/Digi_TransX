import os
import re
import time
from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename

from auth.helpers import timestamp_bundle
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
    safe_name, _ = validate_media_file(file_storage)
    CHAT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(safe_name).stem or "media"
    extension = Path(safe_name).suffix.lower()
    compact_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-") or "media"
    filename = f"{thread_id}_{int(time.time())}_{uuid4().hex[:8]}_{compact_stem}{extension}"
    file_storage.save(CHAT_UPLOADS_DIR / filename)
    return filename


def build_thread_order_summary(row):
    return {
        "id": row["order_id"],
        "pickup_city": row["pickup_city"],
        "pickup_area": row["pickup_area"] or "",
        "dropoff_city": row["dropoff_city"],
        "dropoff_area": row["dropoff_area"] or "",
        "status": row["order_status"],
        "route_label": f"{row['pickup_city']} to {row['dropoff_city']}",
    }


def serialize_thread(row, current_user_id):
    other_user_id = row["transporter_user_id"] if row["client_user_id"] == current_user_id else row["client_user_id"]
    other_party_name = row["transporter_name"] if row["client_user_id"] == current_user_id else row["client_name"]
    return {
        "id": row["id"],
        "order_id": row["order_id"],
        "bid_id": row["bid_id"],
        "client_user_id": row["client_user_id"],
        "transporter_user_id": row["transporter_user_id"],
        "other_user_id": other_user_id,
        "other_party_name": other_party_name,
        "last_message_at": row["last_message_at"] or row["created_at"],
        "last_message_preview": row["last_message_preview"] or "No messages yet.",
        "unread_count": int(row["unread_count"] or 0),
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


def create_thread_for_bid(db, order, transporter_user_id, bid_id=None):
    stamp = timestamp_bundle()["iso"]
    db.execute(
        """
        INSERT OR IGNORE INTO chat_threads (
            order_id, client_user_id, transporter_user_id, bid_id, last_message_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (order["id"], order["client_user_id"], transporter_user_id, bid_id, stamp, stamp),
    )
    if bid_id:
        db.execute(
            """
            UPDATE chat_threads
            SET bid_id = COALESCE(bid_id, ?)
            WHERE order_id = ? AND transporter_user_id = ?
            """,
            (bid_id, order["id"], transporter_user_id),
        )
