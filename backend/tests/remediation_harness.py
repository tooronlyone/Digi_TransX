"""Disposable PostgreSQL + real Flask blueprints; never imports the global app."""
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg2
from psycopg2.extras import Json
import pytest
from flask import Flask

from tests._life_helpers import SCHEMA_SQL, STUBS, make_disposable, require_test_db_url
from shared.db import Db
from auth import helpers as auth_helpers, routes as auth_routes, credential_changes
from auth.session_service import create_session
from auth.trusted_device_service import create_trusted_device
from profile import routes as profile_routes
from fuelstation import routes as fuel_routes
from shopkeeper import routes as shop_routes
from orders import routes as order_routes
from contact import routes as contact_routes
from wallet import routes as wallet_routes
from driver import routes as driver_routes
from trucks import routes as truck_routes
from fuelstation import vouchers as fuel_voucher_routes
from driver import business_rules as driver_business_routes


@pytest.fixture(scope="module")
def remediation_database_url():
    base = require_test_db_url()
    if urlsplit(base).hostname not in {"127.0.0.1","localhost","::1"}:
        pytest.fail("Remediation fixtures require a disposable loopback PostgreSQL database.")
    url,cleanup = make_disposable(base,STUBS,SCHEMA_SQL.read_text(encoding="utf-8"))
    try:
        yield url
    finally:
        cleanup()


@pytest.fixture
def remediation_env(remediation_database_url,monkeypatch):
    @contextmanager
    def database():
        conn=psycopg2.connect(remediation_database_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            if not conn.closed:
                conn.rollback()
            raise
        finally:
            conn.close()
    for module in (auth_helpers,auth_routes,credential_changes,profile_routes,fuel_routes,shop_routes,order_routes,contact_routes,wallet_routes,driver_routes,truck_routes,fuel_voucher_routes,driver_business_routes):
        monkeypatch.setattr(module,"open_db",database)
    monkeypatch.setattr(contact_routes,"send_email",lambda *args,**kwargs:None)
    monkeypatch.setenv("DIGITRANSX_ENVIRONMENT","test")
    app=Flask(__name__)
    app.config.update(TESTING=True,SECRET_KEY="isolated-audit-remediation",SESSION_COOKIE_SECURE=False)
    for blueprint in (auth_routes.auth_blueprint,profile_routes.profile_blueprint,
                      fuel_routes.fuelstation_blueprint,shop_routes.shopkeeper_blueprint,order_routes.orders_blueprint,
                      contact_routes.contact_blueprint,wallet_routes.wallet_blueprint,driver_routes.driver_blueprint,truck_routes.trucks_blueprint):
        app.register_blueprint(blueprint)

    def user(role="service_seeker"):
        auth_id=str(uuid4())
        with database() as db:
            db.execute("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
                       (auth_id,f"{uuid4().hex}@remediation.invalid",
                        Json({"legacy_role":role,"full_name":"Remediation Fixture"})))
            return dict(db.execute("SELECT * FROM users WHERE auth_id=%s",(auth_id,)).fetchone())

    def login(user,client=None):
        client=client or app.test_client()
        with database() as db:
            device,device_id=create_trusted_device(db,user["id"])
            token,proof,session_id=create_session(db,user["id"],trusted_device_id=device_id)
        client.set_cookie("dtx_device_token",device)
        client.set_cookie("dtx_session_token",token)
        client.set_cookie("dtx_access_proof",proof)
        with client.session_transaction() as state:
            state["csrf_token"]="remediation-csrf"
        return client,session_id

    yield SimpleNamespace(app=app,db=database,user=user,login=login,
                          headers={"X-CSRF-Token":"remediation-csrf"},url=remediation_database_url)
