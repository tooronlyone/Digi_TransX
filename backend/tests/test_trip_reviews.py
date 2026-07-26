import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from .test_trip_lifecycle import _completed, _open_dispute, seed_ready_order


CSRF_JSON = {"X-CSRF-Token": "test-csrf-token", "Content-Type": "application/json"}
VALID_REVIEW = {"rating": 5, "comment": "Delivered as agreed."}


def _post(client, url, payload):
    return client.post(url, json=payload, headers=CSRF_JSON)


def _review_url(seed):
    return f"/api/orders/{seed['order_id']}/trips/{seed['trip_id']}/review"


def _confirm_url(seed):
    return (
        f"/api/orders/{seed['order_id']}/trips/"
        f"{seed['trip_id']}/confirm-delivery"
    )


def _new_order_payload():
    pickup = datetime.now() + timedelta(days=2)
    return {
        "pickup_location": "Lahore",
        "dropoff_location": "Karachi",
        "pickup_date": pickup.strftime("%Y-%m-%d"),
        "pickup_time": "10:00",
        "goods_type": "Steel",
        "goods_weight_tons": 5,
        "goods_commodity": "steel_bars",
    }


def _state_snapshot(db, seed):
    wallet = db.execute(
        "SELECT balance FROM wallets WHERE user_id = %s",
        (seed["transporter"]["id"],),
    ).fetchone()
    return {
        "trip_status": db.execute(
            "SELECT status FROM shipment_trips WHERE id = %s",
            (seed["trip_id"],),
        ).fetchone()["status"],
        "shipment_status": db.execute(
            "SELECT status FROM shipments WHERE id = %s",
            (seed["order_id"],),
        ).fetchone()["status"],
        "payment_status": db.execute(
            "SELECT status FROM payments WHERE id = %s",
            (seed["payment_id"],),
        ).fetchone()["status"],
        "wallet_balance": Decimal(str(wallet["balance"])) if wallet else None,
        "payout_count": db.execute(
            "SELECT COUNT(*) AS c FROM wallet_transactions "
            "WHERE type = 'order_payout' AND reference_id = %s",
            (f"payout:trip:{seed['trip_id']}",),
        ).fetchone()["c"],
        "review_count": db.execute(
            "SELECT COUNT(*) AS c FROM shipment_trip_reviews WHERE trip_id = %s",
            (seed["trip_id"],),
        ).fetchone()["c"],
        "history_count": db.execute(
            "SELECT COUNT(*) AS c FROM shipment_status_history WHERE shipment_id = %s",
            (seed["order_id"],),
        ).fetchone()["c"],
        "notification_count": db.execute(
            "SELECT COUNT(*) AS c FROM shipment_notifications WHERE trip_id = %s",
            (seed["trip_id"],),
        ).fetchone()["c"],
    }


def _create_completed_trip(db, seed, rating=None, comment=None):
    order_id = db.execute(
        """
        INSERT INTO shipments (
            client_user_id, pickup_city, dropoff_city, pickup_date, pickup_time,
            goods_type, goods_weight_tons, seeker_kind_snapshot, status
        ) VALUES (%s, 'Lahore', 'Karachi', '2026-08-04', '09:00',
                  'Steel', 5, 'everyday', 'completed')
        RETURNING id
        """,
        (seed["client"]["id"],),
    ).fetchone()["id"]
    bid_id = db.execute(
        """
        INSERT INTO shipment_bids (
            order_id, transporter_user_id, truck_id, bid_price, status
        ) VALUES (%s, %s, %s, 10000, 'accepted')
        RETURNING id
        """,
        (order_id, seed["transporter"]["id"], seed["truck_id"]),
    ).fetchone()["id"]
    db.execute(
        "UPDATE shipments SET accepted_bid_id = %s WHERE id = %s",
        (bid_id, order_id),
    )
    trip_id = db.execute(
        """
        INSERT INTO shipment_trips (
            order_id, accepted_bid_id, transporter_user_id, truck_id,
            status, trip_completed_at, delivery_confirmed_at
        ) VALUES (%s, %s, %s, %s, 'completed', now(), now())
        RETURNING id
        """,
        (order_id, bid_id, seed["transporter"]["id"], seed["truck_id"]),
    ).fetchone()["id"]
    if rating is not None:
        db.execute(
            """
            INSERT INTO shipment_trip_reviews (
                shipment_id, trip_id, client_user_id, transporter_user_id,
                rating, comment
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                order_id,
                trip_id,
                seed["client"]["id"],
                seed["transporter"]["id"],
                rating,
                comment,
            ),
        )
    db.commit()
    return order_id, trip_id


def test_client_yes_missing_rating_causes_zero_mutations(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    before = _state_snapshot(client.db, seed)

    response = _post(client, _confirm_url(seed), {"decision": "yes"})

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_rating"
    assert _state_snapshot(client.db, seed) == before
    assert before["trip_status"] == "awaiting_client_confirmation"
    assert before["shipment_status"] == "awaiting_client_confirmation"
    assert before["payment_status"] == "held"


@pytest.mark.parametrize("rating", [1, 5])
def test_client_yes_rating_bounds_commit_review_completion_and_payout(client, rating):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    before = _state_snapshot(client.db, seed)

    response = _post(
        client,
        _confirm_url(seed),
        {
            "decision": "yes",
            "rating": rating,
            "comment": "  Smooth delivery and good communication.  ",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["review"]["rating"] == rating
    review = client.db.execute(
        "SELECT * FROM shipment_trip_reviews WHERE trip_id = %s",
        (seed["trip_id"],),
    ).fetchone()
    assert review["rating"] == rating
    assert review["comment"] == "Smooth delivery and good communication."
    after = _state_snapshot(client.db, seed)
    assert after["trip_status"] == "completed"
    assert after["shipment_status"] == "completed"
    assert after["payment_status"] == "released"
    assert after["wallet_balance"] == seed["transporter_amount"]
    assert after["payout_count"] == 1
    assert after["review_count"] == 1
    assert after["history_count"] == before["history_count"] + 1
    assert after["notification_count"] == before["notification_count"] + 2


def test_client_yes_forced_review_insert_failure_rolls_back_completion_and_payout(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    before = _state_snapshot(client.db, seed)
    client.db.execute(
        """
        CREATE OR REPLACE FUNCTION fail_review_insert_for_test()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'forced review insert failure';
        END;
        $$
        """
    )
    client.db.execute(
        """
        CREATE TRIGGER fail_review_insert_for_test
        BEFORE INSERT ON shipment_trip_reviews
        FOR EACH ROW EXECUTE FUNCTION fail_review_insert_for_test()
        """
    )
    client.db.commit()
    try:
        import psycopg2

        with pytest.raises(psycopg2.errors.RaiseException):
            _post(
                client,
                _confirm_url(seed),
                {"decision": "yes", **VALID_REVIEW},
            )
        assert _state_snapshot(client.db, seed) == before
    finally:
        client.db.rollback()
        client.db.execute(
            "DROP TRIGGER IF EXISTS fail_review_insert_for_test "
            "ON shipment_trip_reviews"
        )
        client.db.execute("DROP FUNCTION IF EXISTS fail_review_insert_for_test()")
        client.db.commit()


def test_client_yes_exact_replay_is_idempotent(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    first = _post(client, _confirm_url(seed), {"decision": "yes", **VALID_REVIEW})
    assert first.status_code == 200
    before_replay = _state_snapshot(client.db, seed)

    replay = _post(client, _confirm_url(seed), {"decision": "yes", **VALID_REVIEW})

    assert replay.status_code == 200
    assert replay.get_json()["already"] is True
    assert replay.get_json()["review"]["rating"] == VALID_REVIEW["rating"]
    assert _state_snapshot(client.db, seed) == before_replay


def test_client_yes_different_replay_returns_review_already_submitted(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    assert _post(
        client,
        _confirm_url(seed),
        {"decision": "yes", **VALID_REVIEW},
    ).status_code == 200
    before_replay = _state_snapshot(client.db, seed)

    replay = _post(
        client,
        _confirm_url(seed),
        {"decision": "yes", "rating": 4, "comment": "Different"},
    )

    assert replay.status_code == 409
    assert replay.get_json()["code"] == "review_already_submitted"
    assert _state_snapshot(client.db, seed) == before_replay


def test_concurrent_client_yes_requests_create_one_review_and_one_payout(
    client,
    pg_session_info,
):
    import psycopg2

    from orders.lifecycle import perform_client_confirm
    from shared.db import Db

    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        conn = psycopg2.connect(pg_session_info["url"])
        db = Db(conn)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f'set search_path to "{pg_session_info["schema"]}"'
                )
            conn.commit()
            barrier.wait()
            result = perform_client_confirm(
                db,
                seed["client"],
                seed["order_id"],
                seed["trip_id"],
                "yes",
                review_payload=VALID_REVIEW,
            )
            conn.commit()
            results.append(result["already"])
        except Exception as exc:  # pragma: no cover - asserted below
            conn.rollback()
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [False, True]
    state = _state_snapshot(client.db, seed)
    assert state["review_count"] == 1
    assert state["payout_count"] == 1
    assert state["payment_status"] == "released"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rating": 0},
        {"rating": 6},
        {"rating": -1},
        {"rating": 4.0},
        {"rating": 4.5},
        {"rating": True},
        {"rating": None},
        {"rating": []},
        {"rating": {}},
        {"rating": "nan"},
        {"rating": "infinity"},
        {"rating": float("nan")},
        {"rating": float("inf")},
        [],
    ],
)
def test_rating_validation_rejects_invalid_payloads(payload):
    from orders.reviews import validate_review_payload
    from shared.payments import CheckoutError

    with pytest.raises(CheckoutError) as exc:
        validate_review_payload(payload)
    assert exc.value.status == 400


def test_rating_validation_accepts_integer_numeric_string_contract():
    from orders.reviews import validate_review_payload

    assert validate_review_payload({"rating": "5"})["rating"] == 5


def test_comment_whitespace_becomes_null_and_html_remains_plain_text():
    from orders.reviews import validate_review_payload

    assert validate_review_payload({"rating": 3, "comment": "   "})["comment"] is None
    text = '<script>alert("x")</script><b>not markup</b>'
    assert validate_review_payload({"rating": 3, "comment": text})["comment"] == text


def test_comment_over_length_and_non_text_are_rejected():
    from orders.reviews import validate_review_payload
    from shared.payments import CheckoutError

    with pytest.raises(CheckoutError) as too_long:
        validate_review_payload({"rating": 3, "comment": "x" * 1001})
    assert too_long.value.code == "review_comment_too_long"
    with pytest.raises(CheckoutError) as non_text:
        validate_review_payload({"rating": 3, "comment": {"html": "<b>x</b>"}})
    assert non_text.value.code == "invalid_review_comment"


def test_review_authorization_and_exact_derived_relationships(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    other = seed_ready_order(client.db, client_kind="everyday")

    client.login(other["client"])
    assert _post(client, _review_url(seed), VALID_REVIEW).status_code == 403
    assert client.get(_review_url(seed)).status_code == 403

    client.login(seed["transporter"])
    assert _post(client, _review_url(seed), VALID_REVIEW).status_code == 403

    client.db.execute(
        """
        UPDATE shipment_trips
        SET status = 'completed', trip_completed_at = now(),
            delivery_confirmed_at = now()
        WHERE id = %s
        """,
        (seed["trip_id"],),
    )
    client.db.execute(
        "UPDATE shipments SET status = 'completed' WHERE id = %s",
        (seed["order_id"],),
    )
    client.db.commit()
    client.login(seed["client"])
    response = _post(
        client,
        _review_url(seed),
        {**VALID_REVIEW, "transporter_user_id": other["transporter"]["id"]},
    )
    assert response.status_code == 200
    review = client.db.execute(
        "SELECT transporter_user_id FROM shipment_trip_reviews WHERE trip_id = %s",
        (seed["trip_id"],),
    ).fetchone()
    assert review["transporter_user_id"] == seed["transporter"]["id"]
    assert review["transporter_user_id"] != other["transporter"]["id"]


def test_review_before_success_and_wrong_shipment_trip_pair_are_rejected(client):
    first = seed_ready_order(client.db, client_kind="everyday")
    second = seed_ready_order(client.db, client_kind="everyday")
    client.login(first["client"])

    early = _post(client, _review_url(first), VALID_REVIEW)
    mismatch = _post(
        client,
        f"/api/orders/{first['order_id']}/trips/{second['trip_id']}/review",
        VALID_REVIEW,
    )

    assert early.status_code == 409
    assert early.get_json()["code"] == "review_not_eligible"
    assert mismatch.status_code == 404


def test_submitted_review_is_readable_by_client_transporter_and_admin(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    _completed(client.db, seed)
    client.login(seed["client"])
    assert _post(client, _review_url(seed), VALID_REVIEW).status_code == 409
    client.db.execute(
        """
        UPDATE shipment_trips
        SET status = 'completed', trip_completed_at = now(),
            delivery_confirmed_at = now()
        WHERE id = %s
        """,
        (seed["trip_id"],),
    )
    client.db.execute(
        "UPDATE shipments SET status = 'completed' WHERE id = %s",
        (seed["order_id"],),
    )
    client.db.commit()
    assert _post(client, _review_url(seed), VALID_REVIEW).status_code == 200
    assert client.get(_review_url(seed)).status_code == 200
    client.login(seed["transporter"])
    assert client.get(_review_url(seed)).status_code == 200
    client.login(seed["admin"])
    assert client.get(_review_url(seed)).status_code == 200


def test_client_win_refund_rejects_review_and_has_no_pending_requirement(client):
    from orders.lifecycle import resolve_dispute_client_win

    seed = seed_ready_order(client.db, client_kind="everyday")
    dispute_id = _open_dispute(client.db, seed, "no")
    resolve_dispute_client_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Refund approved.",
    )
    client.db.commit()
    client.login(seed["client"])

    response = _post(client, _review_url(seed), {"rating": 2})

    assert response.status_code == 409
    assert response.get_json()["code"] == "review_not_eligible"
    assert client.get("/api/reviews/pending").get_json()["pending_reviews"] == []


def test_admin_transporter_win_pays_once_notifies_once_and_requires_later_review(client):
    from orders.lifecycle import resolve_dispute_transporter_win
    from shared import notifications as notif

    seed = seed_ready_order(client.db, client_kind="everyday")
    dispute_id = _open_dispute(client.db, seed, "no")
    first = resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()
    replay = resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()

    assert first["already"] is False
    assert replay["already"] is True
    state = _state_snapshot(client.db, seed)
    assert state["payment_status"] == "released"
    assert state["payout_count"] == 1
    assert state["review_count"] == 0
    required_notes = client.db.execute(
        """
        SELECT COUNT(*) AS c FROM shipment_notifications
        WHERE trip_id = %s AND user_id = %s AND notification_type = %s
        """,
        (seed["trip_id"], seed["client"]["id"], notif.REVIEW_REQUIRED),
    ).fetchone()["c"]
    assert required_notes == 1
    client.login(seed["client"])
    pending = client.get("/api/reviews/pending").get_json()["pending_reviews"]
    assert [row["trip_id"] for row in pending] == [seed["trip_id"]]


def test_later_pending_review_never_replays_payment_refund_or_status(client):
    from orders.lifecycle import resolve_dispute_transporter_win

    seed = seed_ready_order(client.db, client_kind="everyday")
    dispute_id = _open_dispute(client.db, seed, "no")
    resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()
    before = _state_snapshot(client.db, seed)
    dispute_before = dict(
        client.db.execute(
            "SELECT status, resolution, resolved_at FROM shipment_disputes WHERE id = %s",
            (dispute_id,),
        ).fetchone()
    )
    client.login(seed["client"])

    response = _post(client, _review_url(seed), {"rating": 4, "comment": ""})

    assert response.status_code == 200
    after = _state_snapshot(client.db, seed)
    assert after["payout_count"] == before["payout_count"] == 1
    assert after["payment_status"] == before["payment_status"] == "released"
    assert after["trip_status"] == before["trip_status"] == "completed"
    assert after["shipment_status"] == before["shipment_status"] == "completed"
    assert after["review_count"] == 1
    dispute_after = dict(
        client.db.execute(
            "SELECT status, resolution, resolved_at FROM shipment_disputes WHERE id = %s",
            (dispute_id,),
        ).fetchone()
    )
    assert dispute_after == dispute_before


def test_standalone_pending_review_replay_is_idempotent_and_conflicting_replay_is_rejected(client):
    from orders.lifecycle import resolve_dispute_transporter_win
    from shared import notifications as notif

    seed = seed_ready_order(client.db, client_kind="everyday")
    dispute_id = _open_dispute(client.db, seed, "no")
    resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()
    client.login(seed["client"])

    first = _post(client, _review_url(seed), VALID_REVIEW)
    state_after_first = _state_snapshot(client.db, seed)
    exact_replay = _post(client, _review_url(seed), VALID_REVIEW)
    conflicting_replay = _post(
        client,
        _review_url(seed),
        {"rating": 4, "comment": "Different review."},
    )

    assert first.status_code == 200
    assert first.get_json()["already"] is False
    assert exact_replay.status_code == 200
    assert exact_replay.get_json()["already"] is True
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.get_json()["code"] == "review_already_submitted"
    assert _state_snapshot(client.db, seed) == state_after_first
    submitted_notes = client.db.execute(
        """
        SELECT COUNT(*) AS c FROM shipment_notifications
        WHERE trip_id = %s AND user_id = %s AND notification_type = %s
        """,
        (seed["trip_id"], seed["transporter"]["id"], notif.REVIEW_SUBMITTED),
    ).fetchone()["c"]
    assert submitted_notes == 1
    assert state_after_first["payout_count"] == 1
    assert state_after_first["review_count"] == 1


def test_legacy_completed_unrated_trip_is_pending_without_fake_backfill(client):
    seed = seed_ready_order(client.db, client_kind="everyday")
    client.db.execute(
        """
        UPDATE shipment_trips
        SET status = 'completed', trip_completed_at = now(),
            delivery_confirmed_at = now()
        WHERE id = %s
        """,
        (seed["trip_id"],),
    )
    client.db.execute(
        "UPDATE shipments SET status = 'completed' WHERE id = %s",
        (seed["order_id"],),
    )
    client.db.execute(
        "UPDATE payments SET status = 'released', released_at = now() WHERE id = %s",
        (seed["payment_id"],),
    )
    client.db.commit()
    client.login(seed["client"])

    pending = client.get("/api/reviews/pending").get_json()["pending_reviews"]

    assert [row["trip_id"] for row in pending] == [seed["trip_id"]]
    assert client.db.execute(
        "SELECT COUNT(*) AS c FROM shipment_trip_reviews"
    ).fetchone()["c"] == 0


@pytest.mark.parametrize("client_kind", ["everyday", "business"])
def test_pending_gate_blocks_then_allows_new_one_time_order(client, client_kind):
    from orders.lifecycle import resolve_dispute_transporter_win

    seed = seed_ready_order(client.db, client_kind=client_kind)
    dispute_id = _open_dispute(client.db, seed, "no")
    resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()
    client.login(seed["client"])

    blocked = _post(client, "/api/orders", _new_order_payload())
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "review_required"
    assert blocked.get_json()["pending_review"]["trip_id"] == seed["trip_id"]

    assert _post(client, _review_url(seed), VALID_REVIEW).status_code == 200
    assert client.get("/api/reviews/pending").get_json()["pending_reviews"] == []
    allowed = _post(client, "/api/orders", _new_order_payload())
    assert allowed.status_code == 200


def test_business_pending_review_does_not_gate_agreement_or_notification_routes(client):
    from orders.lifecycle import resolve_dispute_transporter_win

    seed = seed_ready_order(client.db, client_kind="business")
    dispute_id = _open_dispute(client.db, seed, "no")
    resolve_dispute_transporter_win(
        client.db,
        seed["admin"],
        dispute_id,
        "Proof accepted.",
    )
    client.db.commit()
    client.login(seed["client"])

    agreement = _post(client, "/api/agreements/posts", {})
    assert agreement.status_code == 400
    assert agreement.get_json().get("code") != "review_required"
    assert client.get("/api/notifications").status_code == 200
    assert client.post("/auth/logout", headers=CSRF_JSON).status_code == 200


def test_aggregate_query_no_reviews_returns_null_zero_and_one_db_call(client):
    from orders.helpers import fetch_enriched_bids

    seed = seed_ready_order(client.db, client_kind="everyday")
    order = dict(
        client.db.execute(
            "SELECT * FROM shipments WHERE id = %s",
            (seed["order_id"],),
        ).fetchone()
    )

    class RecordingDb:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            return self.wrapped.execute(sql, params)

    recording = RecordingDb(client.db)
    bids = fetch_enriched_bids(recording, order)

    assert len(recording.calls) == 1
    assert len(bids) == 1
    assert bids[0]["transporter"]["rating_average"] is None
    assert bids[0]["transporter"]["rating_count"] == 0


def test_aggregate_query_one_review_returns_exact_average_and_count(client):
    from orders.helpers import fetch_enriched_bids

    seed = seed_ready_order(client.db, client_kind="everyday")
    _create_completed_trip(client.db, seed, rating=4, comment="Private feedback")
    order = dict(
        client.db.execute(
            "SELECT * FROM shipments WHERE id = %s",
            (seed["order_id"],),
        ).fetchone()
    )

    bids = fetch_enriched_bids(client.db, order)

    assert len(bids) == 1
    assert bids[0]["transporter"]["rating_average"] == 4.0
    assert bids[0]["transporter"]["rating_count"] == 1
    assert "Private feedback" not in str(bids[0])


def test_aggregate_query_multiple_reviews_rounds_once_without_duplicates_or_leaks(client):
    from orders.helpers import fetch_enriched_bids

    seed = seed_ready_order(client.db, client_kind="everyday")
    for rating in (3, 4, 4):
        _create_completed_trip(
            client.db,
            seed,
            rating=rating,
            comment=f"Private review {rating}",
        )
    order = dict(
        client.db.execute(
            "SELECT * FROM shipments WHERE id = %s",
            (seed["order_id"],),
        ).fetchone()
    )

    bids = fetch_enriched_bids(client.db, order)

    assert len(bids) == 1
    transporter = bids[0]["transporter"]
    assert transporter["rating_average"] == 3.7
    assert transporter["rating_count"] == 3
    assert set(transporter) == {
        "id",
        "display_name",
        "company_name",
        "completed_trips",
        "rating_average",
        "rating_count",
    }
    assert "client_user_id" not in bids[0]
    assert "Private review" not in str(bids[0])
