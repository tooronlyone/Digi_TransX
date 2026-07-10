from flask import Blueprint, request, send_from_directory

from auth.helpers import json_response, login_required, require_csrf, timestamp_bundle
from shared.db import open_db
from .helpers import (
    CHAT_UPLOADS_DIR,
    MEDIA_MESSAGE,
    MEDIA_REQUEST_APPROVED,
    MEDIA_REQUEST_DENIED,
    MEDIA_REQUEST_FULFILLED,
    MEDIA_REQUEST_MESSAGE,
    MEDIA_REQUEST_PENDING,
    SYSTEM_MESSAGE,
    make_chat_upload_relative_path,
    make_media_approval_system_message,
    parse_message_payload,
    serialize_message,
    serialize_thread,
    validate_media_file,
)


chat_blueprint = Blueprint("chat", __name__)


def get_thread_with_parties(db, thread_id, user_id):
    row = db.execute(
        """
        SELECT
            ct.*,
            ap.title AS agreement_title,
            ap.service_area AS agreement_service_area,
            ap.status AS agreement_status,
            COALESCE(NULLIF(trim(client.full_name), ''), trim(COALESCE(client.first_name, '') || ' ' || COALESCE(client.last_name, '')), client.email, 'Client') AS client_name,
            COALESCE(NULLIF(trim(transporter.full_name), ''), trim(COALESCE(transporter.first_name, '') || ' ' || COALESCE(transporter.last_name, '')), transporter.email, 'Transporter') AS transporter_name,
            COALESCE(NULLIF(trim(admin.full_name), ''), trim(COALESCE(admin.first_name, '') || ' ' || COALESCE(admin.last_name, '')), admin.email, 'Admin') AS admin_name,
            (
                SELECT COALESCE(
                    CASE
                        WHEN message_type = 'media' THEN '[Media]'
                        WHEN message_type = 'media_request' THEN COALESCE(content, 'Media request')
                        WHEN message_type = 'system' THEN COALESCE(content, 'System update')
                        ELSE COALESCE(content, '')
                    END,
                    ''
                )
                FROM chat_messages
                WHERE thread_id = ct.id
                ORDER BY id DESC
                LIMIT 1
            ) AS last_message_preview,
            (
                SELECT COUNT(*)
                FROM chat_messages
                WHERE thread_id = ct.id
                  AND sender_user_id <> ?
                  AND is_read = 0
            ) AS unread_count
        FROM chat_threads ct
        LEFT JOIN agreement_posts ap ON ap.id = ct.agreement_post_id
        JOIN users client ON client.id = ct.client_user_id
        JOIN users transporter ON transporter.id = ct.transporter_user_id
        LEFT JOIN users admin ON admin.id = ct.admin_user_id
        WHERE ct.id = ?
        """,
        (user_id, thread_id),
    ).fetchone()
    return dict(row) if row else None


def user_can_access_thread(thread, user_id):
    return user_id in {thread["client_user_id"], thread["transporter_user_id"]} or (
        bool(thread.get("is_group_chat")) and thread.get("admin_user_id") == user_id
    )


def get_thread_or_error(db, thread_id, user_id):
    thread = get_thread_with_parties(db, thread_id, user_id)
    if not thread:
        return None, json_response({"success": False, "message": "Chat thread not found."}, 404)
    if not user_can_access_thread(thread, user_id):
        return None, json_response({"success": False, "message": "You are not allowed to access this chat."}, 403)
    return thread, None


def get_sender_name(db, user_id):
    row = db.execute(
        """
        SELECT COALESCE(NULLIF(trim(full_name), ''), trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')), email, 'User') AS name
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    return row["name"] if row else "User"


def insert_chat_message(db, thread_id, sender_user_id, message_type, content="", media_path=None, media_request_status=None):
    stamp = timestamp_bundle()["iso"]
    db.execute(
        """
        INSERT INTO chat_messages (
            thread_id, sender_user_id, message_type, content, media_path, media_request_status, is_read, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (thread_id, sender_user_id, message_type, content or None, media_path, media_request_status, stamp),
    )
    message_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute("UPDATE chat_threads SET last_message_at = ? WHERE id = ?", (stamp, thread_id))
    row = db.execute(
        """
        SELECT
            cm.*,
            COALESCE(NULLIF(trim(u.full_name), ''), trim(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')), u.email, 'User') AS sender_name
        FROM chat_messages cm
        JOIN users u ON u.id = cm.sender_user_id
        WHERE cm.id = ?
        """,
        (message_id,),
    ).fetchone()
    return dict(row) if row else None


def get_pending_media_request_for_sender(db, thread_id, sender_user_id):
    counterpart_id = db.execute(
        """
        SELECT CASE
            WHEN client_user_id = ? THEN transporter_user_id
            ELSE client_user_id
        END AS other_user_id
        FROM chat_threads
        WHERE id = ?
        """,
        (sender_user_id, thread_id),
    ).fetchone()
    other_user_id = counterpart_id["other_user_id"] if counterpart_id else None
    if not other_user_id:
        return None
    row = db.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE thread_id = ?
          AND message_type = 'media_request'
          AND sender_user_id = ?
          AND media_request_status = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (thread_id, sender_user_id, MEDIA_REQUEST_APPROVED),
    ).fetchone()
    return dict(row) if row else None


@chat_blueprint.get("/uploads/chat/<path:filename>")
def serve_chat_upload(filename):
    return send_from_directory(CHAT_UPLOADS_DIR, filename)


@chat_blueprint.get("/api/chat/threads")
@login_required
def list_threads():
    user_id = request.current_user["id"]
    with open_db() as db:
        rows = db.execute(
            """
            SELECT
                ct.*,
                ap.title AS agreement_title,
                ap.service_area AS agreement_service_area,
                ap.status AS agreement_status,
                COALESCE(NULLIF(trim(client.full_name), ''), trim(COALESCE(client.first_name, '') || ' ' || COALESCE(client.last_name, '')), client.email, 'Client') AS client_name,
                COALESCE(NULLIF(trim(transporter.full_name), ''), trim(COALESCE(transporter.first_name, '') || ' ' || COALESCE(transporter.last_name, '')), transporter.email, 'Transporter') AS transporter_name,
                (
                    SELECT COALESCE(
                        CASE
                            WHEN message_type = 'media' THEN '[Media]'
                            WHEN message_type = 'media_request' THEN COALESCE(content, 'Media request')
                            WHEN message_type = 'system' THEN COALESCE(content, 'System update')
                            ELSE COALESCE(content, '')
                        END,
                        ''
                    )
                    FROM chat_messages
                    WHERE thread_id = ct.id
                    ORDER BY id DESC
                    LIMIT 1
                ) AS last_message_preview,
                (
                    SELECT COUNT(*)
                    FROM chat_messages
                    WHERE thread_id = ct.id
                      AND sender_user_id <> ?
                      AND is_read = 0
                ) AS unread_count
            FROM chat_threads ct
            LEFT JOIN agreement_posts ap ON ap.id = ct.agreement_post_id
            LEFT JOIN users admin ON admin.id = ct.admin_user_id
            JOIN users client ON client.id = ct.client_user_id
            JOIN users transporter ON transporter.id = ct.transporter_user_id
            WHERE ct.client_user_id = ? OR ct.transporter_user_id = ? OR (ct.is_group_chat = 1 AND ct.admin_user_id = ?)
            ORDER BY
                CASE WHEN ct.last_message_at IS NULL OR trim(ct.last_message_at) = '' THEN 1 ELSE 0 END,
                ct.last_message_at DESC,
                ct.id DESC
            """,
            (user_id, user_id, user_id, user_id),
        ).fetchall()

    threads = [serialize_thread(dict(row), user_id) for row in rows]
    return json_response({"success": True, "threads": threads})


@chat_blueprint.get("/api/chat/threads/<int:thread_id>/messages")
@login_required
def list_messages(thread_id):
    user_id = request.current_user["id"]
    after_raw = (request.args.get("after_id") or "").strip()
    after_id = None
    if after_raw:
        try:
            after_id = int(after_raw)
        except ValueError:
            return json_response({"success": False, "message": "Invalid after_id value."}, 400)

    with open_db() as db:
        thread, error = get_thread_or_error(db, thread_id, user_id)
        if error:
            return error

        if after_id:
            rows = db.execute(
                """
                SELECT
                    cm.*,
                    COALESCE(NULLIF(trim(u.full_name), ''), trim(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')), u.email, 'User') AS sender_name
                FROM chat_messages cm
                JOIN users u ON u.id = cm.sender_user_id
                WHERE cm.thread_id = ? AND cm.id > ?
                ORDER BY cm.id ASC
                """,
                (thread_id, after_id),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT *
                FROM (
                    SELECT
                        cm.*,
                        COALESCE(NULLIF(trim(u.full_name), ''), trim(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')), u.email, 'User') AS sender_name
                    FROM chat_messages cm
                    JOIN users u ON u.id = cm.sender_user_id
                    WHERE cm.thread_id = ?
                    ORDER BY cm.id DESC
                    LIMIT 50
                )
                ORDER BY id ASC
                """,
                (thread_id,),
            ).fetchall()

        unread_rows = db.execute(
            """
            SELECT id
            FROM chat_messages
            WHERE thread_id = ?
              AND sender_user_id <> ?
              AND is_read = 0
            """,
            (thread_id, user_id),
        ).fetchall()
        if unread_rows:
            db.execute(
                """
                UPDATE chat_messages
                SET is_read = 1
                WHERE thread_id = ?
                  AND sender_user_id <> ?
                  AND is_read = 0
                """,
                (thread_id, user_id),
            )
            db.commit()
            thread["unread_count"] = 0
            unread_ids = {row["id"] for row in unread_rows}
            rows = [
                {**dict(row), "is_read": 1 if row["id"] in unread_ids and row["sender_user_id"] != user_id else row["is_read"]}
                for row in rows
            ]

    messages = [serialize_message(dict(row), user_id) for row in rows]
    return json_response({"success": True, "messages": messages, "thread": serialize_thread(thread, user_id)})


@chat_blueprint.post("/api/chat/threads/<int:thread_id>/messages")
@login_required
def send_message(thread_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    data = request.get_json(silent=True) or {}
    try:
        message_type, content = parse_message_payload(data)
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        thread, error = get_thread_or_error(db, thread_id, user_id)
        if error:
            return error

        media_request_status = MEDIA_REQUEST_PENDING if message_type == MEDIA_REQUEST_MESSAGE else None
        row = insert_chat_message(db, thread_id, user_id, message_type, content=content, media_request_status=media_request_status)
        db.commit()

    return json_response({"success": True, "message": serialize_message(row, user_id)})


@chat_blueprint.post("/api/chat/threads/<int:thread_id>/messages/<int:message_id>/respond-media-request")
@login_required
def respond_media_request(thread_id, message_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    action = ((request.get_json(silent=True) or {}).get("action") or "").strip().lower()
    if action not in {"approve", "deny"}:
        return json_response({"success": False, "message": "Action must be approve or deny."}, 400)

    user_id = request.current_user["id"]
    with open_db() as db:
        thread, error = get_thread_or_error(db, thread_id, user_id)
        if error:
            return error

        row = db.execute(
            """
            SELECT *
            FROM chat_messages
            WHERE id = ? AND thread_id = ?
            """,
            (message_id, thread_id),
        ).fetchone()
        if not row:
            return json_response({"success": False, "message": "Media request not found."}, 404)
        message = dict(row)
        if message["message_type"] != MEDIA_REQUEST_MESSAGE:
            return json_response({"success": False, "message": "Only media requests can be responded to."}, 400)
        if message["media_request_status"] != MEDIA_REQUEST_PENDING:
            return json_response({"success": False, "message": "This media request has already been handled."}, 400)
        if message["sender_user_id"] == user_id:
            return json_response({"success": False, "message": "You cannot respond to your own media request."}, 403)

        next_status = MEDIA_REQUEST_APPROVED if action == "approve" else MEDIA_REQUEST_DENIED
        db.execute(
            "UPDATE chat_messages SET media_request_status = ? WHERE id = ? AND thread_id = ?",
            (next_status, message_id, thread_id),
        )
        if action == "approve":
            requester_name = get_sender_name(db, message["sender_user_id"])
            insert_chat_message(
                db,
                thread_id,
                user_id,
                SYSTEM_MESSAGE,
                content=make_media_approval_system_message(requester_name),
            )
        db.commit()

    return json_response({"success": True, "message": f"Request {'approved' if action == 'approve' else 'denied'}"})


@chat_blueprint.post("/api/chat/threads/<int:thread_id>/messages/media")
@login_required
def send_media_message(thread_id):
    if not require_csrf():
        return json_response({"success": False, "message": "Invalid CSRF token."}, 403)

    user_id = request.current_user["id"]
    file_storage = request.files.get("media")
    try:
        validate_media_file(file_storage)
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    with open_db() as db:
        thread, error = get_thread_or_error(db, thread_id, user_id)
        if error:
            return error

        approved_request = get_pending_media_request_for_sender(db, thread_id, user_id)
        if not approved_request:
            return json_response({"success": False, "message": "No pending approval available for media upload."}, 400)

        filename = make_chat_upload_relative_path(thread_id, file_storage)
        row = insert_chat_message(db, thread_id, user_id, MEDIA_MESSAGE, media_path=filename)
        db.execute(
            """
            UPDATE chat_messages
            SET media_request_status = ?
            WHERE id = ? AND thread_id = ?
            """,
            (MEDIA_REQUEST_FULFILLED, approved_request["id"], thread_id),
        )
        db.commit()

    return json_response({"success": True, "message": serialize_message(row, user_id)})
