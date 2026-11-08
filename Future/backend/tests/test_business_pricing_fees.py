"""Rules 1–2: exact fees and real PostgreSQL bid/marketplace transactions.

Integration tests only create disposable databases on an explicitly configured
loopback server. There is no application-database fallback or external I/O.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
import threading
from urllib.parse import urlsplit

from flask import Flask, request
import psycopg2
import pytest

from shared.commissions import itemized_fee, fee_schedule
from shared.db import Db
from orders.market_pricing import reference_from_values, validate_bid_reference, market_reference, market_key, verified_transporter_rating
from orders import routes
from marketplace import service
from shared.payments import CheckoutError
from tests._life_helpers import make_disposable, require_test_db_url, STUBS, SCHEMA_SQL


def test_bootstrap_second_and_third_arithmetic_mean():
    reference = reference_from_values([])
    assert reference["bootstrap"] and reference["market_average"] is None
    validate_bid_reference(Decimal("50000"), reference)
    assert reference_from_values(["50000"])["market_average"] == "50000.00"
    assert reference_from_values(["50000", "60000"])["market_average"] == "55000.00"
    assert reference_from_values(["50000", "60000", "55000"])["market_average"] == "55000.00"


@pytest.mark.parametrize("rating,upper", [(None,"60000.00"),("4.499999","60000.00"),("4.5","70000.00"),("5","70000.00")])
def test_verified_rating_corridor_boundary(rating, upper):
    reference = reference_from_values(["50000"], rating)
    assert reference["minimum_bid"] == "40000.00" and reference["maximum_bid"] == upper
    validate_bid_reference(Decimal("40000"), reference)
    validate_bid_reference(Decimal(upper), reference)
    for price in [Decimal("39999.99"), Decimal(upper)+Decimal("0.01")]:
        with pytest.raises(ValueError, match="between PKR"):
            validate_bid_reference(price, reference)


def test_fractional_reference_bounds_never_allow_a_paisa_outside_corridor():
    reference = reference_from_values(["1.00", "1.01", "1.01"])
    assert reference["minimum_bid"] == "0.81"
    assert reference["maximum_bid"] == "1.20"


@pytest.mark.parametrize("kind,gross,fee,net", [("freight","100000.00","20000.00","80000.00"),
    ("marketplace","10000.00","1000.00","9000.00"),("client","100000.00","0.00","100000.00"),
    ("fuel","25000.00","0.00","25000.00")])
def test_approved_itemized_commissions(kind,gross,fee,net):
    invoice = itemized_fee(gross,kind)
    assert invoice["total_fee"] == fee and invoice["net_amount"] == net
    assert sum((Decimal(line["amount"]) for line in invoice["components"]),Decimal(0)) == Decimal(fee)
    assert Decimal(invoice["total_fee"])+Decimal(invoice["net_amount"]) == Decimal(gross)


@pytest.mark.parametrize("gross",["0.01","0.03","0.05","0.15","0.25","9.99","99999999.99"])
@pytest.mark.parametrize("kind",["freight","marketplace"])
def test_rounding_itemization_reconciles_even_tiny_amounts(gross,kind):
    invoice=itemized_fee(gross,kind)
    assert all(Decimal(component["amount"])>=0 for component in invoice["components"])
    assert sum((Decimal(c["amount"]) for c in invoice["components"]),Decimal(0))==Decimal(invoice["total_fee"])
    assert Decimal(invoice["net_amount"])+Decimal(invoice["total_fee"])==Decimal(gross)


@pytest.mark.parametrize("bad",["NaN","Infinity","-1","1.001"])
def test_invalid_fee_base_rejected(bad):
    with pytest.raises(ValueError): itemized_fee(bad,"freight")


def test_fee_labels_and_percentages_are_complete():
    assert [c["percentage"] for c in fee_schedule("freight")["components"]]==["10.00","5.00","3.00","2.00"]
    assert [c["percentage"] for c in fee_schedule("marketplace")["components"]]==["6.00","2.00","2.00"]


@pytest.fixture(scope="module")
def rule_db_url():
    base=require_test_db_url()
    if urlsplit(base).hostname not in {"127.0.0.1","localhost","::1"}:
        pytest.fail("Business-rule integration tests require loopback PostgreSQL.")
    schema=SCHEMA_SQL.read_text(encoding="utf-8")
    for name,marker in (("20261026000000_financial_journal.sql","CREATE TABLE IF NOT EXISTS public.financial_journal ("),):
        if marker not in schema:
            schema += "\n"+(SCHEMA_SQL.parent/"migrations"/name).read_text(encoding="utf-8")
    # Replay the actual forward migration over canonical for an idempotence
    # check as well as exercising its final constraints and trigger bodies.
    schema += "\n"+(SCHEMA_SQL.parent/"migrations"/"20261026010000_market_pricing_fees.sql").read_text(encoding="utf-8")
    url,cleanup=make_disposable(base,STUBS,schema)
    try: yield url
    finally: cleanup()


@pytest.fixture
def store(rule_db_url,monkeypatch):
    @contextmanager
    def connect():
        conn=psycopg2.connect(rule_db_url)
        try:
            yield Db(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally: conn.close()
    monkeypatch.setattr(routes,"open_db",connect)
    monkeypatch.setattr(routes,"csrf_error",lambda:None)
    app=Flask(__name__)
    app.config.update(TESTING=True,SECRET_KEY="business-rule-test-only")
    with connect() as db:
        for i in range(1,7):
            role="customer" if i==1 else ("shopkeeper" if i==5 else "admin" if i==6 else "transporter")
            legacy="service_seeker" if i==1 else ("shopkeeper" if i==5 else "platform_admin" if i==6 else "logistics_provider")
            db.execute("INSERT INTO users(id,full_name,email,cnic,role,legacy_role) VALUES(%s,%s,%s,%s,%s,%s)",
                       (i,f"Rule Test {i}",f"rules{i}@example.invalid",str(i).zfill(13),role,legacy))
        for i in (2,3,4):
            db.execute("INSERT INTO vehicles(id,owner_user_id,truck_number,chassis_number,truck_type,capacity_tons,main_use,status,current_city) "
                       "VALUES(%s,%s,%s,%s,'flatbed',25,'cargo','active','Lahore')",(i,i,f"TEST-{i}",f"CHASSIS-{i}"))
    try:
        with app.app_context(): yield connect,app
    finally:
        # Journal records deliberately survive fixture cleanup. Keep resource
        # sequences advancing so later cases cannot reuse a prior journal key.
        with connect() as db: db.execute("TRUNCATE users CONTINUE IDENTITY CASCADE")


def _order(db,**changes):
    data=dict(client_user_id=1,pickup_city="Lahore",dropoff_city="Karachi",pickup_date="2026-11-01",pickup_time="10:00",
              goods_type="steel",goods_weight_tons=Decimal("10"),seeker_kind_snapshot="business",required_truck_types='["flatbed"]',status="open")
    data.update(changes)
    return db.execute_exact("INSERT INTO shipments("+",".join(data)+") VALUES("+",".join(["%s"]*len(data))+") RETURNING *",tuple(data.values())).fetchone()


def _bid_call(app,order_id,owner,price):
    with app.test_request_context(f"/api/orders/{order_id}/bids",method="POST",json={"truck_id":owner,"bid_price":price,"rating":5}):
        request.current_user={"id":owner,"role":"logistics_provider"}
        response=routes.create_bid.__wrapped__(order_id)
        return response.status_code,response.get_json()


def test_bid_bootstrap_recalculation_withdrawal_and_audit(store):
    connect,app=store
    with connect() as db: order=_order(db)
    first=_bid_call(app,order["id"],2,"50000")
    assert first[0]==200 and first[1]["market_reference"]["market_average"]=="50000.00"
    second=_bid_call(app,order["id"],3,"60000")
    third=_bid_call(app,order["id"],4,"55000")
    assert second[0]==third[0]==200
    assert second[1]["market_reference"]["market_average"]==third[1]["market_reference"]["market_average"]=="55000.00"
    with connect() as db:
        audit=db.execute_exact("SELECT * FROM shipment_bids WHERE id=%s",(second[1]["bid"]["id"],)).fetchone()
        assert audit["market_reference_average"]==Decimal("50000")
        assert audit["market_minimum_bid"]==Decimal("40000") and audit["market_maximum_bid"]==Decimal("60000")
    with app.test_request_context(method="POST"):
        request.current_user={"id":3,"role":"logistics_provider"}
        assert routes.withdraw_bid.__wrapped__(order["id"],second[1]["bid"]["id"]).status_code==200
    with connect() as db:
        truck=db.execute_exact("SELECT * FROM vehicles WHERE id=2").fetchone()
        assert market_reference(db,order,truck,2)["market_average"]=="52500.00"
        db.execute("UPDATE shipment_bids SET market_ineligible_reason='verified fraud' WHERE id=%s",(third[1]["bid"]["id"],))
        assert market_reference(db,order,truck,2)["market_average"]=="50000.00"


def test_rejected_bid_does_not_change_reference_and_client_rating_is_ignored(store):
    connect,app=store
    with connect() as db: order=_order(db)
    assert _bid_call(app,order["id"],2,"50000")[0]==200
    response=_bid_call(app,order["id"],3,"65000")
    assert response[0]==400 and response[1]["market_reference"]["premium"] is False
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM shipment_bids").fetchone()["n"]==1


def test_distinct_eligible_bids_across_shipments_get_equal_observation_weight(store):
    connect,app=store
    with connect() as db: first,second=_order(db),_order(db)
    assert _bid_call(app,first["id"],2,"50000")[0]==200
    response=_bid_call(app,second["id"],2,"60000")
    assert response[0]==200 and response[1]["market_reference"]["sample_count"]==2
    assert response[1]["market_reference"]["market_average"]=="55000.00"
    duplicate=_bid_call(app,second["id"],2,"55000")
    assert duplicate[0]==400


def test_concurrent_bootstrap_bids_validate_against_committed_predecessor(store):
    connect,app=store
    with connect() as db: order=_order(db)
    start=threading.Barrier(2)
    def submit(owner,price):
        start.wait(timeout=10)
        return _bid_call(app,order["id"],owner,price)
    with ThreadPoolExecutor(2) as pool:
        a,b=pool.submit(submit,2,"50000"),pool.submit(submit,3,"100000")
        results=[a.result(timeout=20),b.result(timeout=20)]
    assert sorted(status for status,_ in results)==[200,400]
    with connect() as db: assert db.execute("SELECT count(*) AS n FROM shipment_bids").fetchone()["n"]==1


def test_historical_fares_equal_weight_and_exact_cargo_matching(store):
    connect,app=store
    with connect() as db:
        db.execute("UPDATE vehicles SET current_city='Lahore City'")
        historical=_order(db,pickup_city=" Lahore  City ")
        bid=db.execute("INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) VALUES(%s,2,2,50000,'accepted') RETURNING id",(historical["id"],)).fetchone()["id"]
        db.execute("UPDATE shipments SET accepted_bid_id=%s,status='completed' WHERE id=%s",(bid,historical["id"]))
        db.execute("INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status,trip_completed_at) VALUES(%s,%s,2,2,'completed',now())",(historical["id"],bid))
        current=_order(db,pickup_city="Lahore City")
    assert _bid_call(app,current["id"],3,"60000")[1]["market_reference"]["market_average"]=="55000.00"
    with connect() as db:
        truck=db.execute_exact("SELECT * FROM vehicles WHERE id=2").fetchone()
        other=_order(db,pickup_city="Lahore City",goods_weight_tons=Decimal("11"))
        assert market_reference(db,other,truck)["bootstrap"]
        assert market_key(current,truck)!=market_key(other,truck)


def test_premium_rating_is_derived_from_completed_review_records(store):
    connect,app=store
    with connect() as db:
        for rating in (4,5):
            historical=_order(db)
            bid=db.execute("INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) VALUES(%s,3,3,50000,'accepted') RETURNING id",(historical["id"],)).fetchone()["id"]
            db.execute("UPDATE shipments SET accepted_bid_id=%s,status='completed' WHERE id=%s",(bid,historical["id"]))
            trip=db.execute("INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status,trip_completed_at) VALUES(%s,%s,3,3,'completed',now()) RETURNING id",(historical["id"],bid)).fetchone()["id"]
            db.execute("INSERT INTO shipment_trip_reviews(shipment_id,trip_id,client_user_id,transporter_user_id,rating) VALUES(%s,%s,1,3,%s)",(historical["id"],trip,rating))
        assert verified_transporter_rating(db,3)==Decimal("4.5")
        assert verified_transporter_rating(db,4) is None
        current=_order(db)
    result=_bid_call(app,current["id"],3,"70000")
    assert result[0]==200 and result[1]["market_reference"]["premium"] is True


def _market_order(connect,price="10000.00",delivery="pickup"):
    buyer={"id":1,"role":"service_seeker"}
    with connect() as db:
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(1,'client',50000,0,0,true)")
        part=db.execute("INSERT INTO marketplace_parts(shop_user_id,title,category,price,stock_quantity) VALUES(5,'Filter','engine',%s,5) RETURNING id",(Decimal(price),)).fetchone()["id"]
        order=service.perform_marketplace_checkout(db,buyer,{"items":[{"part_id":part,"quantity":1}],"delivery_type":delivery,"delivery_address":"Test address"},"new-market-order-01")
        db.execute("UPDATE marketplace_orders SET fulfillment_status=%s WHERE id=%s",("ready_for_pickup" if delivery=="pickup" else "dispatched",order["id"]))
    return order,part


def test_marketplace_10_percent_once_and_balanced_itemized_invoice(store):
    connect,app=store
    order,_=_market_order(connect)
    start=threading.Barrier(2)
    def verify():
        with app.app_context():
            start.wait(timeout=10)
            with connect() as db:
                return service.perform_delivery_verification(db,{"id":5,"role":"shopkeeper"},order["id"],order["delivery_otp"])
    with ThreadPoolExecutor(2) as pool:
        results=[pool.submit(verify),pool.submit(verify)]
        assert all(future.result(timeout=20)["success"] for future in results)
    for _ in range(1):
        with connect() as db:
            assert service.perform_delivery_verification(db,{"id":5,"role":"shopkeeper"},order["id"],order["delivery_otp"])["success"]
    with connect() as db:
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=5").fetchone()["balance"]==Decimal("9000.00")
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=1").fetchone()["balance"]==Decimal("40000.00")
        invoice=db.execute_exact("SELECT * FROM marketplace_financial_events").fetchall()
        assert len(invoice)==1 and invoice[0]["platform_fee"]==Decimal("1000.00")
        assert not db.execute("SELECT journal_id FROM financial_journal_lines GROUP BY journal_id HAVING sum(amount)<>0").fetchall()


def test_delivery_charge_is_not_an_unapproved_commission_base(store):
    connect,app=store
    order,_=_market_order(connect,delivery="delivery")
    with connect() as db:
        service.perform_delivery_verification(db,{"id":5,"role":"shopkeeper"},order["id"],order["delivery_otp"])
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=5").fetchone()["balance"]==Decimal("9500.00")


def test_partial_refunds_reverse_fee_cumulatively_and_replay_safely(store):
    connect,app=store
    order,_=_market_order(connect,price="0.15")
    with connect() as db: service.perform_delivery_verification(db,{"id":5,"role":"shopkeeper"},order["id"],order["delivery_otp"])
    actor={"id":6,"role":"platform_admin"}
    payload={"amount":"0.05","eligible_sale_amount":"0.05","reason":"Verified partial return","decision_reference":"case-1"}
    for key in ("refund-partial-0001","refund-partial-0002","refund-partial-0003"):
        with connect() as db: result=service.perform_marketplace_refund(db,actor,order["id"],payload,key)
        with connect() as db: replay=service.perform_marketplace_refund(db,actor,order["id"],payload,key)
        assert replay["replayed"] and replay["refund_event_id"]==result["refund_event_id"]
    with connect() as db:
        assert db.execute_exact("SELECT sum(platform_fee) AS fee FROM marketplace_financial_events WHERE event_type='refund'").fetchone()["fee"]==Decimal("0.02")
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=1").fetchone()["balance"]==Decimal("50000.00")
        assert db.execute_exact("SELECT balance FROM wallets WHERE user_id=5").fetchone()["balance"]==Decimal("0.00")


def test_unsettled_full_refund_returns_hold_and_inventory_without_fee(store):
    connect,app=store
    order,part=_market_order(connect)
    with connect() as db:
        db.execute("UPDATE marketplace_orders SET fulfillment_status='confirmed' WHERE id=%s",(order["id"],))
        payload={"amount":"10000","eligible_sale_amount":"10000","reason":"Authorized cancellation","decision_reference":"case-2"}
        service.perform_marketplace_refund(db,{"id":6,"role":"platform_admin"},order["id"],payload,"cancel-refund-0001")
    with connect() as db:
        wallet=db.execute_exact("SELECT balance,locked_balance FROM wallets WHERE user_id=1").fetchone()
        assert wallet=={"balance":Decimal("50000"),"locked_balance":Decimal("0")}
        assert db.execute("SELECT stock_quantity FROM marketplace_parts WHERE id=%s",(part,)).fetchone()["stock_quantity"]==5
        assert db.execute_exact("SELECT platform_fee FROM marketplace_financial_events").fetchone()["platform_fee"]==0


def test_cancellation_restock_and_new_checkout_share_consistent_lock_order(store):
    connect,app=store
    order,part=_market_order(connect)
    with connect() as db: db.execute("UPDATE marketplace_orders SET fulfillment_status='confirmed' WHERE id=%s",(order["id"],))
    start=threading.Barrier(2)
    def operation(refund):
        with app.app_context():
            start.wait(timeout=10)
            with connect() as db:
                if refund:
                    return service.perform_marketplace_refund(db,{"id":6,"role":"platform_admin"},order["id"],
                        {"amount":"10000","eligible_sale_amount":"10000","reason":"Verified cancellation","decision_reference":"case-concurrent"},"parallel-refund-01")
                return service.perform_marketplace_checkout(db,{"id":1,"role":"service_seeker"},
                    {"items":[{"part_id":part,"quantity":1}],"delivery_type":"pickup"},"parallel-checkout-01")
    with ThreadPoolExecutor(2) as pool:
        futures=[pool.submit(operation,True),pool.submit(operation,False)]
        assert all(future.result(timeout=20) for future in futures)
    with connect() as db:
        assert db.execute("SELECT stock_quantity FROM marketplace_parts WHERE id=%s",(part,)).fetchone()["stock_quantity"]==4
        assert db.execute_exact("SELECT locked_balance FROM wallets WHERE user_id=1").fetchone()["locked_balance"]==Decimal("10000")


def test_unapproved_cod_fee_funding_blocks_checkout():
    with pytest.raises(CheckoutError) as error:
        service.parse_checkout({"items":[{"part_id":1}],"delivery_type":"pickup","payment_method":"cod"},{"id":1})
    assert error.value.code=="marketplace_cod_fee_policy_required"


def test_market_audit_and_financial_invoices_are_immutable_and_private(store):
    connect,app=store
    with connect() as db: order=_order(db)
    result=_bid_call(app,order["id"],2,"50000")
    with pytest.raises(psycopg2.Error),connect() as db:
        db.execute("UPDATE shipment_bids SET market_reference_average=1 WHERE id=%s",(result[1]["bid"]["id"],))
    market,_=_market_order(connect)
    with connect() as db:
        service.perform_delivery_verification(db,{"id":5,"role":"shopkeeper"},market["id"],market["delivery_otp"])
        assert not db.execute("SELECT has_table_privilege('authenticated','marketplace_financial_events','SELECT') AS allowed").fetchone()["allowed"]
        assert db.execute("SELECT relrowsecurity FROM pg_class WHERE oid='marketplace_financial_events'::regclass").fetchone()["relrowsecurity"]
    with pytest.raises(psycopg2.Error),connect() as db:
        db.execute("UPDATE marketplace_financial_events SET platform_fee=0 WHERE order_id=%s",(market["id"],))
    with pytest.raises(psycopg2.Error),connect() as db:
        db.execute("UPDATE marketplace_orders SET business_fee_version=NULL WHERE id=%s",(market["id"],))
