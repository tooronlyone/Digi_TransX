"""Fleet role boundaries and SQL reputation guards, using disposable accounts."""
from uuid import uuid4
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extras import Json

from tests.remediation_harness import remediation_database_url, remediation_env
from tests.test_driver_workflow_hardening import _graph, _driver, _invite, _accept, _set_status
from tests._life_helpers import STUBS, SCHEMA_SQL, make_disposable, require_test_db_url

MIGRATION=Path(__file__).resolve().parents[2]/"supabase/migrations/20261025010000_driver_workflow_integrity.sql"


@pytest.fixture
def legacy_connection():
    baseline=SCHEMA_SQL.read_text(encoding="utf-8").split("-- BEGIN 25 OCTOBER 2026 DRIVER WORKFLOW HARDENING",1)[0]
    url,cleanup=make_disposable(require_test_db_url(),STUBS,baseline)
    conn=psycopg2.connect(url)
    try:
        yield conn
    finally:
        conn.close()
        cleanup()


def _legacy_fleet(cursor):
    users=[]
    for role in ("driver","logistics_provider","service_seeker"):
        auth_id=str(uuid4())
        cursor.execute("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
                       (auth_id,uuid4().hex+"@legacy.invalid",Json({"legacy_role":role})))
        cursor.execute("SELECT id FROM users WHERE auth_id=%s",(auth_id,))
        users.append(cursor.fetchone()[0])
    driver,owner,customer=users
    cursor.execute("INSERT INTO vehicles(owner_user_id,truck_number,chassis_number,truck_type,capacity_tons,main_use,status) "
                   "VALUES(%s,%s,%s,'Cargo',10,'Cargo','active') RETURNING id",(owner,uuid4().hex,uuid4().hex))
    truck=cursor.fetchone()[0]
    cursor.execute("INSERT INTO driver_profiles(user_id,unique_driver_id,license_number,rating,rating_count,current_truck_id,is_available) "
                   "VALUES(%s,%s,'TEST',5,1,%s,false)",(driver,"DRV-"+uuid4().hex[:12],truck))
    return driver,owner,customer,truck


@pytest.mark.parametrize("ghost_unavailable",[False,True])
def test_upgrade_preserves_raw_legacy_reports_but_removes_unproven_reputation_and_auto_link(legacy_connection,ghost_unavailable):
    conn=legacy_connection
    with conn,conn.cursor() as cursor:
        driver,owner,_,truck=_legacy_fleet(cursor)
        if ghost_unavailable:
            cursor.execute("UPDATE driver_profiles SET current_truck_id=NULL WHERE user_id=%s",(driver,))
        cursor.execute("INSERT INTO driver_reviews(driver_user_id,reviewer_user_id,rating,comment) VALUES(%s,%s,5,'Legacy unproven review')",(driver,owner))
        cursor.execute("INSERT INTO driver_incidents(driver_user_id,reporter_user_id,incident_type,description,status) VALUES(%s,%s,'theft','Legacy unproven allegation','confirmed')",(driver,owner))
        cursor.execute(MIGRATION.read_text(encoding="utf-8"))
        cursor.execute(MIGRATION.read_text(encoding="utf-8"))
        cursor.execute("SELECT rating,rating_count,current_truck_id,is_available FROM driver_profiles WHERE user_id=%s",(driver,))
        assert cursor.fetchone()==(None,0,None,True)
        cursor.execute("SELECT comment,assignment_id FROM driver_reviews WHERE driver_user_id=%s",(driver,))
        assert cursor.fetchall()==[("Legacy unproven review",None)]
        cursor.execute("SELECT description,status,assignment_id FROM driver_incidents WHERE driver_user_id=%s",(driver,))
        assert cursor.fetchall()==[("Legacy unproven allegation","confirmed",None)]
        cursor.execute("SELECT count(*) FROM vehicles WHERE id=%s",(truck,))
        assert cursor.fetchone()==(1,)


def test_upgrade_refuses_to_invent_consent_and_rolls_back_partial_ddl(legacy_connection):
    conn=legacy_connection
    with conn,conn.cursor() as cursor:
        driver,owner,customer,truck=_legacy_fleet(cursor)
        cursor.execute("INSERT INTO shipments(client_user_id,pickup_city,dropoff_city,pickup_date,pickup_time,goods_type,goods_weight_tons,seeker_kind_snapshot,status) "
                       "VALUES(%s,'A','B',CURRENT_DATE,'10:00','Goods',1,'business','ready_to_start') RETURNING id",(customer,))
        order=cursor.fetchone()[0]
        cursor.execute("INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) VALUES(%s,%s,%s,1000,'accepted') RETURNING id",(order,owner,truck))
        bid=cursor.fetchone()[0]
        cursor.execute("INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status) VALUES(%s,%s,%s,%s,'ready_to_start') RETURNING id",(order,bid,owner,truck))
        trip=cursor.fetchone()[0]
        cursor.execute("INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_id,status) VALUES(%s,%s,%s,%s,'accepted') RETURNING id",(driver,owner,truck,trip))
        assignment=cursor.fetchone()[0]
        cursor.execute("SAVEPOINT attempted_upgrade")
        with pytest.raises(psycopg2.Error) as failure:
            cursor.execute(MIGRATION.read_text(encoding="utf-8"))
        assert failure.value.pgcode=="P0001"
        cursor.execute("ROLLBACK TO SAVEPOINT attempted_upgrade")
        cursor.execute("SELECT status FROM driver_trip_assignments WHERE id=%s",(assignment,))
        assert cursor.fetchone()==("accepted",)
        cursor.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='driver_trip_assignments' AND column_name='accepted_at'")
        assert cursor.fetchone()==(0,)


@pytest.mark.parametrize("old_consent",[None,False,True])
def test_legacy_default_card_convergence_preserves_consent_and_is_idempotent(legacy_connection,old_consent):
    conn=legacy_connection
    with conn,conn.cursor() as cursor:
        _,_,customer,_=_legacy_fleet(cursor)
        cards=[]
        for is_default in (False,True):
            cursor.execute("INSERT INTO saved_payment_methods(user_id,provider_token,card_last_four,expiry_month,expiry_year,is_default) "
                           "VALUES(%s,%s,'4242',12,2030,%s) RETURNING id",(customer,uuid4().hex,is_default))
            cards.append(cursor.fetchone()[0])
        if old_consent is not None:
            cursor.execute("INSERT INTO user_payment_preferences(user_id,default_payment_method_id,auto_shortfall_charge_enabled) VALUES(%s,%s,%s)",
                           (customer,cards[0],old_consent))
        convergence=MIGRATION.with_name("20261025020000_payment_preference_convergence.sql").read_text(encoding="utf-8")
        cursor.execute(convergence)
        cursor.execute("SELECT default_payment_method_id,auto_shortfall_charge_enabled,updated_at FROM user_payment_preferences WHERE user_id=%s",(customer,))
        first=cursor.fetchone()
        assert first[:2]==(cards[1],bool(old_consent))
        cursor.execute(convergence)
        cursor.execute("SELECT default_payment_method_id,auto_shortfall_charge_enabled,updated_at FROM user_payment_preferences WHERE user_id=%s",(customer,))
        assert cursor.fetchone()==first
        cursor.execute("SELECT count(*) FROM user_payment_preferences WHERE user_id=%s",(customer,))
        assert cursor.fetchone()==(1,)


@pytest.mark.parametrize("role",["service_seeker","everyday_user","driver","shopkeeper","fuel_station_manager"])
def test_non_transporter_cannot_register_truck_even_with_valid_csrf(remediation_env,role):
    env=remediation_env
    user=env.user(role)
    client,_=env.login(user)
    response=client.post("/api/trucks",headers=env.headers,data={})
    assert response.status_code==403,response.json
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM vehicles WHERE owner_user_id=%s",(user["id"],)).fetchone()["n"]==0


@pytest.mark.parametrize("role",["transporter","logistics_provider"])
def test_truck_creation_does_not_bind_visible_driver_id_or_claim_driver_identity(remediation_env,role):
    env=remediation_env
    user=env.user(role)
    driver,code=_driver(env)
    client,_=env.login(user)
    truck_number="CONSENT-"+uuid4().hex[:8]
    response=client.post("/api/trucks",headers=env.headers,data={
        "truckNumber":truck_number,"truckCompany":"Hino","truckModel":"500","truckType":"Truck",
        "chassisNumber":"TEST"+uuid4().hex[:13].upper(),"payload_min_tons":"0","payload_max_tons":"10",
        "uniqueDriverId":code,"driverName":"Forged identity","driverCnic":"1234567890123",
    })
    assert response.status_code==200,response.json
    assert response.json["driver_assignment_status"]=="unassigned"
    with env.db() as db:
        row=db.execute("SELECT driver_name,driver_cnic FROM vehicles WHERE truck_number=%s",(truck_number,)).fetchone()
        assert row=={"driver_name":None,"driver_cnic":None}
        assert db.execute("SELECT current_truck_id FROM driver_profiles WHERE user_id=%s",(driver["id"],)).fetchone()["current_truck_id"] is None
        assert db.execute("SELECT count(*) AS n FROM driver_trip_assignments WHERE driver_user_id=%s",(driver["id"],)).fetchone()["n"]==0


def test_configuration_cannot_overwrite_consented_driver_identity(remediation_env):
    env=remediation_env
    graph=_graph(env)
    _accept(env,graph,_invite(env,graph))
    with env.db() as db:
        before=db.execute("SELECT driver_name,driver_cnic FROM vehicles WHERE id=%s",(graph.truck_id,)).fetchone()
        assert before["driver_name"]==graph.driver["full_name"]
    response=graph.owner_client.put(f"/api/trucks/{graph.truck_id}/configuration",headers=env.headers,data={
        "truck_number":"CONFIG-"+uuid4().hex[:8],"truck_company":"Hino","truck_model":"500","truck_type":"Truck",
        "max_capacity":"10","payload_min_tons":"0","payload_max_tons":"10",
        "chassis_number":"TEST"+uuid4().hex[:13].upper(),"operating_provinces":"Punjab",
        "driver_name":"Forged identity","driver_cnic":"1234567890123",
    })
    assert response.status_code==200,response.json
    with env.db() as db:
        assert db.execute("SELECT driver_name,driver_cnic FROM vehicles WHERE id=%s",(graph.truck_id,)).fetchone()==before


def test_direct_sql_review_and_incident_forgery_is_rejected(remediation_env):
    env=remediation_env
    graph=_graph(env)
    allocation=_invite(env,graph)
    _accept(env,graph,allocation)
    _set_status(env,graph,"completed")
    outsider=env.user("logistics_provider")
    bad_rows=[
        (None,graph.driver["id"],graph.owner["id"],graph.trip_id),
        (allocation,outsider["id"],graph.owner["id"],graph.trip_id),
        (allocation,graph.driver["id"],outsider["id"],graph.trip_id),
        (allocation,graph.driver["id"],graph.owner["id"],None),
    ]
    for row in bad_rows:
        with pytest.raises(psycopg2.IntegrityError) as error:
            with env.db() as db:
                db.execute("INSERT INTO driver_reviews(assignment_id,driver_user_id,reviewer_user_id,trip_id,rating) VALUES(%s,%s,%s,%s,5)",row)
        assert error.value.pgcode=="23514"
    with pytest.raises(psycopg2.IntegrityError) as error:
        with env.db() as db:
            db.execute("INSERT INTO driver_incidents(assignment_id,driver_user_id,reporter_user_id,trip_id,incident_type,description,status) "
                       "VALUES(%s,%s,%s,%s,'theft','Unreviewed allegation','confirmed')",
                       (allocation,graph.driver["id"],graph.owner["id"],graph.trip_id))
    assert error.value.pgcode=="23514"
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM driver_reviews WHERE assignment_id=%s",(allocation,)).fetchone()["n"]==0
        assert db.execute("SELECT count(*) AS n FROM driver_incidents WHERE assignment_id=%s",(allocation,)).fetchone()["n"]==0


def test_completed_allocation_cannot_forge_foreign_source_trip_provenance(remediation_env):
    env=remediation_env
    graph=_graph(env)
    foreign=_graph(env)
    _set_status(env,foreign,"completed")
    with env.db() as db:
        forged=db.execute("INSERT INTO driver_trip_assignments(driver_user_id,transporter_user_id,truck_id,trip_type,trip_id,status,accepted_at) "
                          "VALUES(%s,%s,%s,'one_time',%s,'completed',now()) RETURNING id",
                          (graph.driver["id"],graph.owner["id"],graph.truck_id,foreign.trip_id)).fetchone()["id"]
    with pytest.raises(psycopg2.IntegrityError) as error:
        with env.db() as db:
            db.execute("INSERT INTO driver_reviews(assignment_id,driver_user_id,reviewer_user_id,trip_id,rating) VALUES(%s,%s,%s,%s,5)",
                       (forged,graph.driver["id"],graph.owner["id"],foreign.trip_id))
    assert error.value.pgcode=="23514"


@pytest.mark.parametrize("kind",["one_time","agreement"])
def test_terminal_trip_cancels_unaccepted_invitation_instead_of_inventing_completed_consent(remediation_env,kind):
    env=remediation_env
    graph=_graph(env,kind=kind)
    allocation=_invite(env,graph)
    _set_status(env,graph,"completed")
    with env.db() as db:
        row=db.execute("SELECT status,accepted_at,completed_at FROM driver_trip_assignments WHERE id=%s",(allocation,)).fetchone()
        assert row=={"status":"cancelled","accepted_at":None,"completed_at":None}
    assert graph.driver_client.post(f"/api/driver/trips/{allocation}/respond",headers=env.headers,json={"action":"accept"}).status_code==409
