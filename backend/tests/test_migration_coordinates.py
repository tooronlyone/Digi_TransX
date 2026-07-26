"""PostgreSQL smoke tests for the coordinate-integrity migration."""

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
    / "20260724190000_one_time_coordinate_integrity.sql"
)
CONSTRAINTS = (
    "shipments_pickup_coords_pair",
    "shipments_pickup_lat_finite_range",
    "shipments_pickup_lng_finite_range",
    "shipments_dropoff_coords_pair",
    "shipments_dropoff_lat_finite_range",
    "shipments_dropoff_lng_finite_range",
    "vehicles_current_lat_finite_range",
    "vehicles_current_lng_finite_range",
)


def _constraint_counts(conn):
    with conn.cursor() as cur:
        cur.execute(
            "select conname,count(*) from pg_constraint "
            "where conname=any(%s) group by conname order by conname",
            (list(CONSTRAINTS),),
        )
        return dict(cur.fetchall())


def _disposable(*blocks):
    return make_disposable(require_test_db_url(), *blocks)


def test_migration_applies_to_origin_main_and_reapplies_idempotently():
    url, cleanup = _disposable(STUBS, schema_before_migration_or_skip(MIGRATION))
    conn = psycopg2.connect(url)
    try:
        sql = MIGRATION.read_text(encoding="utf-8")
        run_sql(conn, sql)
        assert _constraint_counts(conn) == {name: 1 for name in sorted(CONSTRAINTS)}
        run_sql(conn, sql)
        assert _constraint_counts(conn) == {name: 1 for name in sorted(CONSTRAINTS)}
    finally:
        conn.close()
        cleanup()


def test_fresh_corrected_schema_has_final_constraints_and_accepts_reapply():
    url, cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    conn = psycopg2.connect(url)
    try:
        assert _constraint_counts(conn) == {name: 1 for name in sorted(CONSTRAINTS)}
        run_sql(conn, MIGRATION.read_text(encoding="utf-8"))
        assert _constraint_counts(conn) == {name: 1 for name in sorted(CONSTRAINTS)}
    finally:
        conn.close()
        cleanup()


def test_anomaly_precheck_aborts_with_counts_and_preserves_data():
    url, cleanup = _disposable(STUBS, schema_before_migration_or_skip(MIGRATION))
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into users (email,cnic,role,legacy_role) "
                "values ('coord-anomaly@test','coord-anomaly','customer',"
                "'service_seeker') returning id"
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "insert into shipments "
                "(client_user_id,pickup_city,dropoff_city,pickup_date,pickup_time,"
                "goods_type,goods_weight_tons,seeker_kind_snapshot,pickup_lat,"
                "pickup_lng) "
                "values (%s,'Gujranwala','Lahore','2026-08-01','12:00',"
                "'General cargo',2.5,'business',999,999) returning id",
                (user_id,),
            )
            order_id = cur.fetchone()[0]
        conn.commit()

        with pytest.raises(psycopg2.errors.CheckViolation) as exc:
            run_sql(conn, MIGRATION.read_text(encoding="utf-8"))
        assert "shipments.pickup_lat=1" in str(exc.value)
        assert "shipments.pickup_lng=1" in str(exc.value)
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("select pickup_lat,pickup_lng from shipments where id=%s", (order_id,))
            assert cur.fetchone() == (999.0, 999.0)
        assert _constraint_counts(conn) == {}
    finally:
        conn.close()
        cleanup()


def test_corrected_schema_rejects_direct_invalid_insert_and_update():
    url, cleanup = _disposable(STUBS, SCHEMA_SQL.read_text(encoding="utf-8"))
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into users (email,cnic,role,legacy_role) "
                "values ('coord-db@test','coord-db','customer','service_seeker') "
                "returning id"
            )
            user_id = cur.fetchone()[0]
        conn.commit()

        with pytest.raises(psycopg2.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "insert into shipments "
                    "(client_user_id,pickup_city,dropoff_city,pickup_date,"
                    "pickup_time,goods_type,goods_weight_tons,"
                    "seeker_kind_snapshot,pickup_lat,pickup_lng) "
                    "values (%s,'A','B','2026-08-01','12:00','Cargo',1,"
                    "'business','NaN'::double precision,0)",
                    (user_id,),
                )
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute(
                "insert into vehicles "
                "(owner_user_id,truck_number,truck_type,chassis_number,"
                "capacity_tons,main_use,current_lat,current_lng) "
                "values (%s,'COORD-DB','Truck','COORD-DB-CHASSIS',5,"
                "'Cargo',null,null) returning id",
                (user_id,),
            )
            truck_id = cur.fetchone()[0]
        conn.commit()
        with pytest.raises(psycopg2.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute(
                    "update vehicles set current_lat=0,"
                    "current_lng='Infinity'::double precision where id=%s",
                    (truck_id,),
                )
        conn.rollback()
    finally:
        conn.close()
        cleanup()
