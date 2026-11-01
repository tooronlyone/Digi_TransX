"""PostgreSQL migration, integrity, concurrency, and RLS tests for reviews."""

import hashlib
import threading
from pathlib import Path

import psycopg2
import pytest

from tests._life_helpers import (
    SCHEMA_SQL,
    STUBS,
    make_disposable,
    require_test_db_url,
    run_sql,
    schema_before_migration_or_skip,
)


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260726200000_shipment_trip_reviews.sql"
)
REVIEW_CONSTRAINTS = (
    "shipment_trip_reviews_pkey",
    "shipment_trip_reviews_rating_check",
    "shipment_trip_reviews_comment_check",
    "shipment_trip_reviews_trip_unique",
    "shipment_trip_reviews_shipment_client_fk",
    "shipment_trip_reviews_trip_shipment_fk",
    "shipment_trip_reviews_trip_transporter_fk",
    "shipment_trip_reviews_client_user_fk",
    "shipment_trip_reviews_transporter_user_fk",
)
REVIEW_POLICIES = (
    "admin_all_shipment_trip_reviews",
    "trip_reviews_client_read",
    "trip_reviews_transporter_read",
)


def _disposable(*blocks):
    return make_disposable(require_test_db_url(), *blocks)


def _seed_user(cursor, suffix, role, legacy_role):
    email = f"{suffix}@test"
    cnic = hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:13]
    cursor.execute(
        """
        INSERT INTO auth.users (email, raw_user_meta_data)
        VALUES (
            %s,
            jsonb_build_object('legacy_role', %s, 'cnic', %s)
        )
        RETURNING id
        """,
        (email, legacy_role, cnic),
    )
    auth_id = cursor.fetchone()[0]
    cursor.execute(
        """
        UPDATE users
        SET role = %s, legacy_role = %s, cnic = %s
        WHERE auth_id = %s
        RETURNING id
        """,
        (role, legacy_role, cnic, auth_id),
    )
    return cursor.fetchone()[0], auth_id


def _seed_trip(conn, suffix, *, status="completed"):
    with conn.cursor() as cursor:
        client_id, client_auth = _seed_user(
            cursor,
            f"client-{suffix}",
            "customer",
            "everyday_user",
        )
        transporter_id, transporter_auth = _seed_user(
            cursor,
            f"transporter-{suffix}",
            "transporter",
            "transporter",
        )
        cursor.execute(
            """
            INSERT INTO vehicles (
                owner_user_id, truck_number, truck_type, chassis_number,
                capacity_tons, main_use, status
            ) VALUES (%s, %s, 'flatbed', %s, 20, 'general', 'active')
            RETURNING id
            """,
            (
                transporter_id,
                f"TRK-{suffix}",
                f"CHS-{suffix}",
            ),
        )
        truck_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO shipments (
                client_user_id, pickup_city, dropoff_city, pickup_date,
                pickup_time, goods_type, goods_weight_tons,
                seeker_kind_snapshot, status
            ) VALUES (%s, 'Lahore', 'Karachi', '2026-08-01', '09:00',
                      'Steel', 5, 'everyday', %s)
            RETURNING id
            """,
            (client_id, status),
        )
        shipment_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO shipment_bids (
                order_id, transporter_user_id, truck_id, bid_price, status
            ) VALUES (%s, %s, %s, 10000, 'accepted')
            RETURNING id
            """,
            (shipment_id, transporter_id, truck_id),
        )
        bid_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE shipments SET accepted_bid_id = %s WHERE id = %s",
            (bid_id, shipment_id),
        )
        cursor.execute(
            """
            INSERT INTO shipment_trips (
                order_id, accepted_bid_id, transporter_user_id, truck_id,
                status, trip_completed_at, delivery_confirmed_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                CASE WHEN %s = 'completed' THEN now() END,
                CASE WHEN %s = 'completed' THEN now() END
            )
            RETURNING id
            """,
            (
                shipment_id,
                bid_id,
                transporter_id,
                truck_id,
                status,
                status,
                status,
            ),
        )
        trip_id = cursor.fetchone()[0]
    conn.commit()
    return {
        "shipment_id": shipment_id,
        "trip_id": trip_id,
        "client_id": client_id,
        "client_auth": client_auth,
        "transporter_id": transporter_id,
        "transporter_auth": transporter_auth,
    }


def _insert_review(conn, trip, rating=5, comment="Good delivery"):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO shipment_trip_reviews (
                shipment_id, trip_id, client_user_id, transporter_user_id,
                rating, comment
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                trip["shipment_id"],
                trip["trip_id"],
                trip["client_id"],
                trip["transporter_id"],
                rating,
                comment,
            ),
        )
        review_id = cursor.fetchone()[0]
    conn.commit()
    return review_id


def _metadata(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'public.shipment_trip_reviews'::regclass
            ORDER BY conname
            """
        )
        constraints = dict(cursor.fetchall())
        cursor.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'shipment_trip_reviews'
            ORDER BY indexname
            """
        )
        indexes = dict(cursor.fetchall())
        cursor.execute(
            """
            SELECT policyname, cmd, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'shipment_trip_reviews'
            ORDER BY policyname
            """
        )
        policies = cursor.fetchall()
        cursor.execute(
            """
            SELECT relrowsecurity
            FROM pg_class
            WHERE oid = 'public.shipment_trip_reviews'::regclass
            """
        )
        rls = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT pg_get_viewdef('public.transporter_review_aggregates'::regclass, true)
            """
        )
        view = " ".join(cursor.fetchone()[0].split())
    return {
        "constraints": constraints,
        "indexes": indexes,
        "policies": policies,
        "rls": rls,
        "view": view,
    }


def test_review_migration_applies_to_origin_main_reapplies_and_preserves_legacy_trip():
    url, cleanup = _disposable(STUBS, schema_before_migration_or_skip(MIGRATION))
    conn = psycopg2.connect(url)
    try:
        legacy = _seed_trip(conn, "legacy")
        sql = MIGRATION.read_text(encoding="utf-8")
        run_sql(conn, sql)
        run_sql(conn, sql)

        metadata = _metadata(conn)
        assert set(metadata["constraints"]) == set(REVIEW_CONSTRAINTS)
        assert metadata["rls"] is True
        assert {row[0] for row in metadata["policies"]} == set(REVIEW_POLICIES)
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM shipment_trips WHERE id = %s",
                (legacy["trip_id"],),
            )
            assert cursor.fetchone()[0] == "completed"
            cursor.execute("SELECT COUNT(*) FROM shipment_trip_reviews")
            assert cursor.fetchone()[0] == 0
    finally:
        conn.close()
        cleanup()


def test_fresh_schema_loads_and_converges_semantically_with_migrated_origin():
    migrated_url, migrated_cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
        MIGRATION.read_text(encoding="utf-8"),
    )
    fresh_url, fresh_cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    migrated = psycopg2.connect(migrated_url)
    fresh = psycopg2.connect(fresh_url)
    try:
        run_sql(fresh, MIGRATION.read_text(encoding="utf-8"))
        assert _metadata(migrated) == _metadata(fresh)
    finally:
        migrated.close()
        fresh.close()
        migrated_cleanup()
        fresh_cleanup()


def test_relationship_anomaly_aborts_migration_without_data_loss():
    url, cleanup = _disposable(STUBS, schema_before_migration_or_skip(MIGRATION))
    conn = psycopg2.connect(url)
    try:
        first = _seed_trip(conn, "anomaly-a")
        second = _seed_trip(conn, "anomaly-b")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE shipment_trip_reviews (
                    id bigint generated by default as identity,
                    shipment_id bigint,
                    trip_id bigint,
                    client_user_id bigint,
                    transporter_user_id bigint,
                    rating integer,
                    comment text,
                    created_at timestamptz default now()
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO shipment_trip_reviews (
                    shipment_id, trip_id, client_user_id,
                    transporter_user_id, rating
                ) VALUES (%s, %s, %s, %s, 5)
                """,
                (
                    first["shipment_id"],
                    second["trip_id"],
                    first["client_id"],
                    first["transporter_id"],
                ),
            )
        conn.commit()

        with pytest.raises(psycopg2.errors.CheckViolation) as exc:
            run_sql(conn, MIGRATION.read_text(encoding="utf-8"))
        assert "trip_shipment_mismatches=1" in str(exc.value)
        conn.rollback()

        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM shipment_trip_reviews")
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "SELECT COUNT(*) FROM shipments WHERE id = ANY(%s)",
                ([first["shipment_id"], second["shipment_id"]],),
            )
            assert cursor.fetchone()[0] == 2
            cursor.execute(
                """
                SELECT COUNT(*) FROM pg_constraint
                WHERE conrelid = 'public.shipment_trip_reviews'::regclass
                """
            )
            assert cursor.fetchone()[0] == 0
    finally:
        conn.close()
        cleanup()


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_database_rating_bounds_reject_insert(rating):
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    conn = psycopg2.connect(url)
    try:
        trip = _seed_trip(conn, f"rating-{rating}")
        with pytest.raises(psycopg2.errors.CheckViolation):
            _insert_review(conn, trip, rating=rating)
        conn.rollback()
    finally:
        conn.close()
        cleanup()


def test_database_rating_bounds_reject_update_and_review_is_immutable_via_rls():
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    conn = psycopg2.connect(url)
    try:
        trip = _seed_trip(conn, "rating-update")
        review_id = _insert_review(conn, trip, rating=5)
        with pytest.raises(psycopg2.errors.CheckViolation):
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE shipment_trip_reviews SET rating = 0 WHERE id = %s",
                    (review_id,),
                )
        conn.rollback()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT rating FROM shipment_trip_reviews WHERE id = %s",
                (review_id,),
            )
            assert cursor.fetchone()[0] == 5
    finally:
        conn.close()
        cleanup()


@pytest.mark.parametrize(
    "field",
    ["shipment_client", "trip_shipment", "trip_transporter"],
)
def test_database_composite_relationships_reject_mixed_ids(field):
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    conn = psycopg2.connect(url)
    try:
        first = _seed_trip(conn, f"binding-{field}-a")
        second = _seed_trip(conn, f"binding-{field}-b")
        values = {
            "shipment_id": first["shipment_id"],
            "trip_id": first["trip_id"],
            "client_id": first["client_id"],
            "transporter_id": first["transporter_id"],
        }
        if field == "shipment_client":
            values["client_id"] = second["client_id"]
        elif field == "trip_shipment":
            values["shipment_id"] = second["shipment_id"]
            values["client_id"] = second["client_id"]
        else:
            values["transporter_id"] = second["transporter_id"]

        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO shipment_trip_reviews (
                        shipment_id, trip_id, client_user_id,
                        transporter_user_id, rating
                    ) VALUES (%s, %s, %s, %s, 5)
                    """,
                    (
                        values["shipment_id"],
                        values["trip_id"],
                        values["client_id"],
                        values["transporter_id"],
                    ),
                )
        conn.rollback()
    finally:
        conn.close()
        cleanup()


def test_concurrent_duplicate_review_is_rejected_and_one_row_survives():
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    setup = psycopg2.connect(url)
    try:
        trip = _seed_trip(setup, "concurrent")
        barrier = threading.Barrier(2)
        results = []

        def worker(rating):
            conn = psycopg2.connect(url)
            try:
                barrier.wait()
                _insert_review(conn, trip, rating=rating)
                results.append("inserted")
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                results.append("duplicate")
            finally:
                conn.close()

        threads = [
            threading.Thread(target=worker, args=(4,)),
            threading.Thread(target=worker, args=(5,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not any(thread.is_alive() for thread in threads)
        assert sorted(results) == ["duplicate", "inserted"]
        with setup.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM shipment_trip_reviews WHERE trip_id = %s",
                (trip["trip_id"],),
            )
            assert cursor.fetchone()[0] == 1
    finally:
        setup.close()
        cleanup()


def _set_authenticated(cursor, auth_id):
    cursor.execute("RESET ROLE")
    cursor.execute(
        "SELECT set_config('request.jwt.claim.sub', %s, false)",
        (str(auth_id),),
    )
    cursor.execute("SET ROLE authenticated")


def test_review_rls_with_real_non_superuser_role_and_safe_aggregate_view():
    url, cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    conn = psycopg2.connect(url)
    try:
        first = _seed_trip(conn, "rls-a")
        second = _seed_trip(conn, "rls-b")
        _insert_review(conn, first, rating=5, comment="Private client comment")
        _insert_review(conn, second, rating=3, comment="Another private comment")
        with conn.cursor() as cursor:
            _, unrelated_auth = _seed_user(
                cursor,
                "unrelated",
                "customer",
                "everyday_user",
            )
            _, admin_auth = _seed_user(
                cursor,
                "admin-review-rls",
                "admin",
                "platform_admin",
            )
            cursor.execute("GRANT USAGE ON SCHEMA public TO authenticated")
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON shipment_trip_reviews TO authenticated"
            )
            cursor.execute(
                "GRANT SELECT ON transporter_review_aggregates TO authenticated"
            )
            cursor.execute(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
                "TO authenticated"
            )
        conn.commit()

        with conn.cursor() as cursor:
            _set_authenticated(cursor, first["client_auth"])
            cursor.execute(
                "SELECT trip_id, comment FROM shipment_trip_reviews ORDER BY trip_id"
            )
            assert cursor.fetchall() == [
                (first["trip_id"], "Private client comment")
            ]

            _set_authenticated(cursor, first["transporter_auth"])
            cursor.execute("SELECT trip_id FROM shipment_trip_reviews")
            assert cursor.fetchall() == [(first["trip_id"],)]

            _set_authenticated(cursor, unrelated_auth)
            cursor.execute("SELECT trip_id FROM shipment_trip_reviews")
            assert cursor.fetchall() == []
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'transporter_review_aggregates'
                ORDER BY ordinal_position
                """
            )
            assert [row[0] for row in cursor.fetchall()] == [
                "transporter_user_id",
                "rating_average",
                "rating_count",
            ]
            cursor.execute("SELECT * FROM transporter_review_aggregates")
            assert cursor.fetchall() == []

            _set_authenticated(cursor, admin_auth)
            cursor.execute("SELECT COUNT(*) FROM shipment_trip_reviews")
            assert cursor.fetchone()[0] == 2
            cursor.execute("RESET ROLE")
        conn.commit()

        with conn.cursor() as cursor:
            _set_authenticated(cursor, unrelated_auth)
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cursor.execute(
                    """
                    INSERT INTO shipment_trip_reviews (
                        shipment_id, trip_id, client_user_id,
                        transporter_user_id, rating
                    ) VALUES (%s, %s, %s, %s, 5)
                    """,
                    (
                        first["shipment_id"],
                        first["trip_id"],
                        first["client_id"],
                        first["transporter_id"],
                    ),
                )
        conn.rollback()

        with conn.cursor() as cursor:
            _set_authenticated(cursor, first["client_auth"])
            cursor.execute(
                "UPDATE shipment_trip_reviews SET rating = 1 WHERE trip_id = %s",
                (first["trip_id"],),
            )
            assert cursor.rowcount == 0
            cursor.execute(
                "DELETE FROM shipment_trip_reviews WHERE trip_id = %s",
                (first["trip_id"],),
            )
            assert cursor.rowcount == 0
            cursor.execute("RESET ROLE")
        conn.rollback()

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT rating FROM shipment_trip_reviews WHERE trip_id = %s",
                (first["trip_id"],),
            )
            assert cursor.fetchone()[0] == 5
    finally:
        conn.close()
        cleanup()
