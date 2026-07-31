"""PostgreSQL proof for the schema-trigger and shipment-RLS baseline fix."""

import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import psycopg2
import pytest
from psycopg2.extras import Json

from tests._life_helpers import (
    SCHEMA_SQL,
    STUBS,
    make_disposable,
    require_test_db_url,
    schema_before_migration_or_skip,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260731220000_schema_trigger_rls_baseline.sql"
)
EXPECTED_BASE_DATABASE = "dtx_schema_trigger_rls_baseline"
TRIGGERS = {
    "transporter_profiles": "trg_transporter_profiles_updated_at",
    "fuel_station_profiles": "trg_fuel_station_profiles_updated_at",
    "shopkeeper_profiles": "trg_shopkeeper_profiles_updated_at",
}


def _local_test_url():
    url = require_test_db_url()
    if url == os.environ.get("SUPABASE_DB_URL", "").strip():
        pytest.fail("TEST_SUPABASE_DB_URL must not equal SUPABASE_DB_URL.")
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Baseline correction tests require local disposable PostgreSQL.")
    if parsed.path.lstrip("/") != EXPECTED_BASE_DATABASE:
        pytest.fail(
            "TEST_SUPABASE_DB_URL must name the exact baseline-correction database."
        )
    return url


def _disposable(*blocks):
    return make_disposable(_local_test_url(), *blocks)


def _migration_sql():
    return MIGRATION.read_text(encoding="utf-8")


def _trigger_inventory(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname, trigger.tgname, trigger.tgtype,
                   function.proname
            FROM pg_trigger AS trigger
            JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            JOIN pg_proc AS function ON function.oid = trigger.tgfoid
            WHERE namespace.nspname = 'public'
              AND trigger.tgname = ANY(%s)
              AND NOT trigger.tgisinternal
            ORDER BY relation.relname, trigger.tgname
            """,
            (list(TRIGGERS.values()),),
        )
        return cursor.fetchall()


def _foundation_metadata(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT relation.relname, trigger.tgname, trigger.tgtype,
                   function.proname
            FROM pg_trigger AS trigger
            JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            JOIN pg_proc AS function ON function.oid = trigger.tgfoid
            WHERE namespace.nspname = 'public'
              AND trigger.tgname = ANY(%s)
              AND NOT trigger.tgisinternal
            ORDER BY relation.relname, trigger.tgname
            """,
            (list(TRIGGERS.values()),),
        )
        triggers = cursor.fetchall()
        cursor.execute(
            """
            SELECT p.prosecdef, p.provolatile, p.prorettype = 'boolean'::regtype,
                   p.proconfig, pg_get_function_identity_arguments(p.oid),
                   pg_get_functiondef(p.oid)
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.proname = 'is_transporter_assigned_to_shipment'
            """
        )
        helper = cursor.fetchall()
        cursor.execute(
            """
            SELECT cmd, qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'shipments'
              AND policyname = 'shipments_transporter_read'
            """
        )
        policy = cursor.fetchall()
        cursor.execute(
            """
            SELECT coalesce(role.rolname, 'PUBLIC'), acl.privilege_type
            FROM pg_proc AS function
            CROSS JOIN LATERAL aclexplode(
                coalesce(
                    function.proacl,
                    acldefault('f', function.proowner)
                )
            ) AS acl
            LEFT JOIN pg_roles AS role ON role.oid = acl.grantee
            WHERE function.oid =
                'public.is_transporter_assigned_to_shipment(bigint)'::regprocedure
              AND (acl.grantee = 0 OR role.rolname IN ('anon', 'authenticated'))
            ORDER BY 1, 2
            """
        )
        grants = cursor.fetchall()
    return {
        "triggers": triggers,
        "helper": helper,
        "policy": policy,
        "grants": grants,
    }


def test_migration_applies_to_locked_origin_main_and_reapplies():
    url, cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
    )
    conn = psycopg2.connect(url)
    try:
        before = _trigger_inventory(conn)
        assert len(before) == 3
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(_migration_sql())
                cursor.execute(_migration_sql())
        after = _trigger_inventory(conn)
        assert after == before
        metadata = _foundation_metadata(conn)
        assert len(metadata["helper"]) == 1
        assert len(metadata["policy"]) == 1
    finally:
        conn.close()
        cleanup()


def test_migration_repairs_only_trigger_drift_without_backfill():
    drift = "\n".join(
        f"DROP TRIGGER {trigger} ON public.{table};"
        for table, trigger in TRIGGERS.items()
    )
    url, cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
        drift,
    )
    conn = psycopg2.connect(url)
    fixed_timestamp = "2000-01-01T00:00:00+00:00"
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.users (id, email, cnic, role, legacy_role)
                    VALUES
                        (101, 'trigger-transporter@example.invalid', 'TRIGGER-101',
                         'transporter', 'transporter'),
                        (102, 'trigger-fuel@example.invalid', 'TRIGGER-102',
                         'fuel_station_manager', 'fuel_station_manager'),
                        (103, 'trigger-shop@example.invalid', 'TRIGGER-103',
                         'shopkeeper', 'shopkeeper')
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO public.transporter_profiles
                        (user_id, company_name, created_at, updated_at)
                    VALUES (101, 'Before', %s, %s)
                    """,
                    (fixed_timestamp, fixed_timestamp),
                )
                cursor.execute(
                    """
                    INSERT INTO public.fuel_station_profiles
                        (user_id, station_name, created_at, updated_at)
                    VALUES (102, 'Before', %s, %s)
                    """,
                    (fixed_timestamp, fixed_timestamp),
                )
                cursor.execute(
                    """
                    INSERT INTO public.shopkeeper_profiles
                        (user_id, shop_name, created_at, updated_at)
                    VALUES (103, 'Before', %s, %s)
                    """,
                    (fixed_timestamp, fixed_timestamp),
                )
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM transporter_profiles),
                    (SELECT count(*) FROM fuel_station_profiles),
                    (SELECT count(*) FROM shopkeeper_profiles),
                    (SELECT count(*) FROM shipments),
                    (SELECT count(*) FROM payments)
                """
            )
            counts_before = cursor.fetchone()
            cursor.execute(
                """
                SELECT
                    (SELECT updated_at FROM transporter_profiles WHERE user_id = 101),
                    (SELECT updated_at FROM fuel_station_profiles WHERE user_id = 102),
                    (SELECT updated_at FROM shopkeeper_profiles WHERE user_id = 103)
                """
            )
            timestamps_before = cursor.fetchone()

        with conn:
            with conn.cursor() as cursor:
                cursor.execute(_migration_sql())

        assert len(_trigger_inventory(conn)) == 3
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM transporter_profiles),
                    (SELECT count(*) FROM fuel_station_profiles),
                    (SELECT count(*) FROM shopkeeper_profiles),
                    (SELECT count(*) FROM shipments),
                    (SELECT count(*) FROM payments)
                """
            )
            assert cursor.fetchone() == counts_before
            cursor.execute(
                """
                SELECT
                    (SELECT updated_at FROM transporter_profiles WHERE user_id = 101),
                    (SELECT updated_at FROM fuel_station_profiles WHERE user_id = 102),
                    (SELECT updated_at FROM shopkeeper_profiles WHERE user_id = 103)
                """
            )
            assert cursor.fetchone() == timestamps_before

        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE transporter_profiles SET company_name = 'After' "
                    "WHERE user_id = 101"
                )
                cursor.execute(
                    "UPDATE fuel_station_profiles SET station_name = 'After' "
                    "WHERE user_id = 102"
                )
                cursor.execute(
                    "UPDATE shopkeeper_profiles SET shop_name = 'After' "
                    "WHERE user_id = 103"
                )
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT updated_at > %s FROM transporter_profiles WHERE user_id = 101),
                    (SELECT updated_at > %s FROM fuel_station_profiles WHERE user_id = 102),
                    (SELECT updated_at > %s FROM shopkeeper_profiles WHERE user_id = 103)
                """,
                (fixed_timestamp, fixed_timestamp, fixed_timestamp),
            )
            assert cursor.fetchone() == (True, True, True)
    finally:
        conn.close()
        cleanup()


def test_fresh_schema_and_migrated_schema_converge():
    drift = "\n".join(
        f"DROP TRIGGER {trigger} ON public.{table};"
        for table, trigger in TRIGGERS.items()
    )
    migrated_url, migrated_cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
        drift,
        _migration_sql(),
    )
    fresh_url, fresh_cleanup = _disposable(
        STUBS,
        SCHEMA_SQL.read_text(encoding="utf-8"),
    )
    migrated = psycopg2.connect(migrated_url)
    fresh = psycopg2.connect(fresh_url)
    try:
        assert _foundation_metadata(migrated) == _foundation_metadata(fresh)
    finally:
        migrated.close()
        fresh.close()
        migrated_cleanup()
        fresh_cleanup()


def _seed_user(cursor, number, role, legacy_role):
    auth_id = UUID(int=number)
    cursor.execute(
        """
        INSERT INTO auth.users (id, email, raw_user_meta_data)
        VALUES (%s, %s, %s)
        """,
        (
            str(auth_id),
            f"rls-{number}@example.invalid",
            Json(
                {
                    "full_name": f"RLS {number}",
                    "cnic": f"RLS-{number}",
                    "role": legacy_role,
                    "legacy_role": legacy_role,
                }
            ),
        ),
    )
    cursor.execute(
        "SELECT id FROM public.users WHERE auth_id = %s",
        (str(auth_id),),
    )
    user_id = cursor.fetchone()[0]
    cursor.execute(
        "UPDATE public.users SET role = %s, legacy_role = %s WHERE id = %s",
        (role, legacy_role, user_id),
    )
    return user_id, auth_id


def _seed_shipment(cursor, owner_id, status, suffix):
    cursor.execute(
        """
        INSERT INTO public.shipments (
            client_user_id, pickup_city, dropoff_city, pickup_date,
            pickup_time, goods_type, goods_weight_tons,
            seeker_kind_snapshot, status
        ) VALUES (%s, 'Karachi', 'Lahore', DATE '2030-01-01',
                  '09:00', 'general', 10, 'business', %s)
        RETURNING id
        """,
        (owner_id, status),
    )
    return cursor.fetchone()[0]


def _seed_trip(cursor, shipment_id, transporter_id, suffix):
    cursor.execute(
        """
        INSERT INTO public.vehicles (
            owner_user_id, truck_number, truck_type, chassis_number,
            capacity_tons, main_use, status
        ) VALUES (%s, %s, 'flatbed', %s, 20, 'goods', 'on_job')
        RETURNING id
        """,
        (transporter_id, f"RLS-{suffix}", f"CHASSIS-{suffix}"),
    )
    truck_id = cursor.fetchone()[0]
    cursor.execute(
        """
        INSERT INTO public.shipment_bids (
            order_id, transporter_user_id, truck_id, bid_price, status
        ) VALUES (%s, %s, %s, 1000, 'accepted')
        RETURNING id
        """,
        (shipment_id, transporter_id, truck_id),
    )
    bid_id = cursor.fetchone()[0]
    cursor.execute(
        "UPDATE public.shipments SET accepted_bid_id = %s WHERE id = %s",
        (bid_id, shipment_id),
    )
    cursor.execute(
        """
        INSERT INTO public.shipment_trips (
            order_id, accepted_bid_id, transporter_user_id, truck_id, status
        ) VALUES (%s, %s, %s, %s, 'ready_to_start')
        RETURNING id
        """,
        (shipment_id, bid_id, transporter_id, truck_id),
    )
    return cursor.fetchone()[0]


def _set_role(cursor, role, auth_id=None):
    cursor.execute("RESET ROLE")
    cursor.execute(
        "SELECT set_config('request.jwt.claim.sub', %s, false)",
        ("" if auth_id is None else str(auth_id),),
    )
    cursor.execute(f"SET ROLE {role}")


def _visible_ids(cursor, table):
    cursor.execute(f"SELECT id FROM public.{table} ORDER BY id")
    return [row[0] for row in cursor.fetchall()]


def test_real_roles_preserve_access_without_recursion_or_helper_abuse():
    url, cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
        _migration_sql(),
    )
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                owner_one, owner_one_auth = _seed_user(
                    cursor, 1, "customer", "service_seeker"
                )
                owner_two, _ = _seed_user(
                    cursor, 2, "customer", "service_seeker"
                )
                unrelated, unrelated_auth = _seed_user(
                    cursor, 3, "customer", "everyday_user"
                )
                transporter_one, transporter_one_auth = _seed_user(
                    cursor, 4, "transporter", "transporter"
                )
                transporter_two, transporter_two_auth = _seed_user(
                    cursor, 5, "transporter", "transporter"
                )
                _, admin_auth = _seed_user(
                    cursor, 6, "admin", "platform_admin"
                )
                protected_one = _seed_shipment(
                    cursor, owner_one, "ready_to_start", "one"
                )
                protected_two = _seed_shipment(
                    cursor, owner_two, "ready_to_start", "two"
                )
                open_shipment = _seed_shipment(
                    cursor, owner_two, "open", "open"
                )
                trip_one = _seed_trip(
                    cursor, protected_one, transporter_one, "one"
                )
                trip_two = _seed_trip(
                    cursor, protected_two, transporter_two, "two"
                )
                cursor.execute("GRANT USAGE ON SCHEMA public TO anon, authenticated")
                cursor.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON public.shipments, public.shipment_trips "
                    "TO anon, authenticated"
                )

        with conn.cursor() as cursor:
            _set_role(cursor, "anon")
            assert _visible_ids(cursor, "shipments") == []
            assert _visible_ids(cursor, "shipment_trips") == []
            cursor.execute(
                "SELECT public.is_transporter_assigned_to_shipment(%s)",
                (protected_one,),
            )
            assert cursor.fetchone()[0] is False

            _set_role(cursor, "authenticated", unrelated_auth)
            assert _visible_ids(cursor, "shipments") == []
            assert _visible_ids(cursor, "shipment_trips") == []
            cursor.execute(
                "SELECT public.is_transporter_assigned_to_shipment(%s)",
                (protected_one,),
            )
            assert cursor.fetchone()[0] is False

            _set_role(cursor, "authenticated", owner_one_auth)
            assert _visible_ids(cursor, "shipments") == [protected_one]
            assert _visible_ids(cursor, "shipment_trips") == [trip_one]
            cursor.execute(
                "SELECT public.is_transporter_assigned_to_shipment(%s)",
                (protected_one,),
            )
            assert cursor.fetchone()[0] is False

            _set_role(cursor, "authenticated", transporter_one_auth)
            assert _visible_ids(cursor, "shipments") == [
                protected_one,
                open_shipment,
            ]
            assert _visible_ids(cursor, "shipment_trips") == [trip_one]
            cursor.execute(
                """
                SELECT
                    public.is_transporter_assigned_to_shipment(%s),
                    public.is_transporter_assigned_to_shipment(%s)
                """,
                (protected_one, protected_two),
            )
            assert cursor.fetchone() == (True, False)

            _set_role(cursor, "authenticated", transporter_two_auth)
            assert _visible_ids(cursor, "shipments") == [
                protected_two,
                open_shipment,
            ]
            assert _visible_ids(cursor, "shipment_trips") == [trip_two]
            cursor.execute(
                """
                SELECT
                    public.is_transporter_assigned_to_shipment(%s),
                    public.is_transporter_assigned_to_shipment(%s)
                """,
                (protected_one, protected_two),
            )
            assert cursor.fetchone() == (False, True)

            _set_role(cursor, "authenticated", admin_auth)
            assert _visible_ids(cursor, "shipments") == [
                protected_one,
                protected_two,
                open_shipment,
            ]
            assert _visible_ids(cursor, "shipment_trips") == [trip_one, trip_two]
            cursor.execute("RESET ROLE")

        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    coalesce(bool_or(acl.grantee = 0), false),
                    coalesce(bool_or(role.rolname = 'anon'), false),
                    coalesce(bool_or(role.rolname = 'authenticated'), false)
                FROM pg_proc AS function
                CROSS JOIN LATERAL aclexplode(
                    coalesce(
                        function.proacl,
                        acldefault('f', function.proowner)
                    )
                ) AS acl
                LEFT JOIN pg_roles AS role ON role.oid = acl.grantee
                WHERE function.oid =
                    'public.is_transporter_assigned_to_shipment(bigint)'::regprocedure
                  AND acl.privilege_type = 'EXECUTE'
                """
            )
            assert cursor.fetchone() == (False, True, True)
            cursor.execute(
                """
                SELECT prosecdef, prorettype = 'boolean'::regtype, proconfig
                FROM pg_proc
                WHERE oid =
                    'public.is_transporter_assigned_to_shipment(bigint)'::regprocedure
                """
            )
            assert cursor.fetchone() == (
                True,
                True,
                ["search_path=pg_catalog"],
            )
    finally:
        conn.rollback()
        conn.close()
        cleanup()


def test_migration_does_not_change_shipment_or_trip_table_privileges():
    url, cleanup = _disposable(
        STUBS,
        schema_before_migration_or_skip(MIGRATION),
    )
    conn = psycopg2.connect(url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("GRANT ALL ON shipments, shipment_trips TO anon, authenticated")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT grantee, table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = 'public'
                  AND table_name IN ('shipments', 'shipment_trips')
                  AND grantee IN ('anon', 'authenticated')
                ORDER BY grantee, table_name, privilege_type
                """
            )
            before = cursor.fetchall()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(_migration_sql())
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT grantee, table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = 'public'
                  AND table_name IN ('shipments', 'shipment_trips')
                  AND grantee IN ('anon', 'authenticated')
                ORDER BY grantee, table_name, privilege_type
                """
            )
            assert cursor.fetchall() == before
    finally:
        conn.close()
        cleanup()
