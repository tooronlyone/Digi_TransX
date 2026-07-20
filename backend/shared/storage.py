"""Supabase Storage helpers — all app files live in one private bucket.

Path conventions (kept identical to the old local layout so the stored
DB values and frontend URLs do not change):
  uploads/trucks/<filename>   truck photo / insurance / RC book
  uploads/chat/<filename>     chat media
"""

import mimetypes
import os

from auth.helpers import timestamp_bundle
from shared.supabase_client import get_service_client


STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "shipment-documents")


def guess_content_type(filename):
    return mimetypes.guess_type(filename or "")[0] or "application/octet-stream"


def upload_bytes(path, data, content_type=None):
    """Upload bytes to the bucket at the given path (overwrites)."""
    get_service_client().storage.from_(STORAGE_BUCKET).upload(
        path,
        data,
        {"content-type": content_type or guess_content_type(path), "upsert": "true"},
    )
    return path


def upload_file_storage(path, file_storage):
    """Upload a werkzeug FileStorage to the bucket. Returns the storage path."""
    data = file_storage.read()
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass
    content_type = file_storage.mimetype or guess_content_type(file_storage.filename)
    upload_bytes(path, data, content_type)
    return path


def download_bytes(path):
    """Download a file from the bucket. Returns bytes or None."""
    try:
        return get_service_client().storage.from_(STORAGE_BUCKET).download(path)
    except Exception:
        return None


def record_document(
    db,
    owner_user_id,
    storage_path,
    doc_type,
    vehicle_id=None,
    shipment_id=None,
    file_name=None,
    mime_type=None,
    size_bytes=None,
):
    """Insert a metadata row into public.documents for an uploaded file."""
    db.execute(
        """
        INSERT INTO documents (
            owner_user_id, shipment_id, vehicle_id, doc_type, storage_path,
            file_name, mime_type, size_bytes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_user_id,
            shipment_id,
            vehicle_id,
            doc_type,
            storage_path,
            file_name,
            mime_type,
            size_bytes,
            timestamp_bundle()["iso"],
        ),
    )
