"""Order/card integrity and constant-cost list regressions on disposable PG.

No global app or real payment/network provider is used. Route authentication and
CSRF are real; query counters wrap only the domain connection, not auth reads.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
from threading import Event
from uuid import uuid4

import pytest

from orders import routes as order_routes
from payments import routes as payment_routes
from marketplace import routes as marketplace_routes
from shopkeeper import routes as shop_routes
from shared import payments
from wallet import helpers as wallet_helpers
from tests.remediation_harness import remediation_database_url, remediation_env


INSURANCE_ACCEPTANCE = {"insurance_notice_accepted": True, "insurance_notice_version": "rules-1-4-v1"}

CARD = {"card_number":"4242424242424242","card_expiry":"12/30",
        "card_cvc":"123","card_holder_name":"Disposable Test Payer"}


def _shipment(db,customer,transporter=None):
    order_id=db.execute(
        "INSERT INTO shipments(client_user_id,status,pickup_city,dropoff_city,pickup_date,pickup_time,"
        "pickup_lat,pickup_lng,goods_type,goods_weight_tons,estimated_budget,seeker_kind_snapshot) "
        "VALUES(%s,'open','Gujranwala','Lahore',%s,'10:00',32.1877,74.1945,'General',5,100,'business') RETURNING id",
        (customer["id"],date.today()+timedelta(days=7)),
    ).fetchone()["id"]
    if transporter is None:
        return order_id,None
    db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) VALUES(%s,'transporter',30000,30000,30000,true) ON CONFLICT(user_id) DO NOTHING",(transporter["id"],))
    truck_id=db.execute(
        "INSERT INTO vehicles(owner_user_id,truck_number,truck_company,truck_model,truck_type,chassis_number,"
        "capacity_tons,payload_max_tons,main_use,current_city,current_lat,current_lng,service_radius_km,status) "
        "VALUES(%s,%s,'Volvo','Volvo FH','Cargo Truck',%s,100,100,'general','Gujranwala',32.1877,74.1945,100,'active') RETURNING id",
        (transporter["id"],"REG-"+uuid4().hex[:12],"CHASSIS-"+uuid4().hex[:12]),
    ).fetchone()["id"]
    bid_id=db.execute(
        "INSERT INTO shipment_bids(order_id,transporter_user_id,truck_id,bid_price,status) "
        "VALUES(%s,%s,%s,100,'pending') RETURNING id",(order_id,transporter["id"],truck_id),
    ).fetchone()["id"]
    return order_id,bid_id


class ObservedDb:
    def __init__(self,db,observe):
        self.db,self.observe=db,observe
    def execute(self,sql,params=()):
        self.observe(sql)
        return self.db.execute_exact(sql,params)
    def execute_exact(self,sql,params=()):
        return self.execute(sql,params)
    def commit(self):
        self.db.commit()
    def rollback(self):
        self.db.rollback()


@pytest.mark.parametrize("strong_owner_lock",[True,False])
def test_mpin_session_owner_lock_and_source_writer_fk_are_compatible(remediation_env,strong_owner_lock):
    """Reproduce the former 40P01 cycle, then exercise the production lock.

    A delivery/fuel writer owns source -> wallet before writing a wallet FK.
    MPIN owns user -> session -> device before waiting for that same source.
    A KEY SHARE FK read must be compatible with the MPIN user's lock.
    """
    import psycopg2
    from auth.session_service import lock_session_user_and_device
    from auth.trusted_device_service import digest_token
    env=remediation_env
    customer=env.user()
    owner=env.user('logistics_provider')
    with env.db() as db:
        order_id,bid_id=_shipment(db,customer,owner)
        truck=db.execute('SELECT truck_id FROM shipment_bids WHERE id=%s',(bid_id,)).fetchone()['truck_id']
        trip_id=db.execute("INSERT INTO shipment_trips(order_id,accepted_bid_id,transporter_user_id,truck_id,status) VALUES(%s,%s,%s,%s,'in_progress') RETURNING id",(order_id,bid_id,owner['id'],truck)).fetchone()['id']
    client,session_id=env.login(owner)
    device_digest=digest_token(client.get_cookie('dtx_device_token').value)
    source_locked,gate_waiting=Event(),Event()

    def source_writer():
        try:
            with env.app.app_context(),env.db() as db:
                db.execute("SET LOCAL statement_timeout='8s'")
                db.execute("SET LOCAL deadlock_timeout='100ms'")
                db.execute('SELECT id FROM shipment_trips WHERE id=%s FOR UPDATE',(trip_id,))
                wallet=dict(db.execute_exact('SELECT * FROM wallets WHERE user_id=%s FOR UPDATE',(owner['id'],)).fetchone())
                source_locked.set()
                assert gate_waiting.wait(10),'MPIN gate never acquired its bound user/session/device'
                assert wallet_helpers.adjust_wallet_balance(db,wallet,owner['id'],25,'test_credit') is None
            return 'ok'
        except psycopg2.Error as exc:
            return exc.pgcode

    class AuthGateDb(ObservedDb):
        def execute(self,sql,params=()):
            if strong_owner_lock and 'from users' in sql.lower():
                sql=sql.replace('FOR NO KEY UPDATE','FOR UPDATE')
            return self.db.execute(sql,params)

    def mpin_gate():
        try:
            assert source_locked.wait(10),'Financial writer never acquired its source'
            with env.db() as db:
                db.execute("SET LOCAL statement_timeout='8s'")
                db.execute("SET LOCAL deadlock_timeout='100ms'")
                durable,user,device=lock_session_user_and_device(AuthGateDb(db,lambda sql:None),session_id,owner['id'],device_digest)
                assert durable and user and device
                gate_waiting.set()
                db.execute('SELECT id FROM shipment_trips WHERE id=%s FOR UPDATE',(trip_id,))
            return 'ok'
        except psycopg2.Error as exc:
            return exc.pgcode
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=[future.result(15) for future in (pool.submit(source_writer),pool.submit(mpin_gate))]
    if strong_owner_lock:
        assert sorted(outcomes)==['40P01','ok']
    else:
        assert outcomes==['ok','ok']
        with env.db() as db:
            assert db.execute_exact('SELECT balance,locked_balance FROM wallets WHERE user_id=%s',(owner['id'],)).fetchone()=={'balance':30025,'locked_balance':30000}


@pytest.mark.parametrize("first",["checkout","withdraw"])
def test_withdraw_and_checkout_serialize_at_the_same_shipment_lock(remediation_env,monkeypatch,first):
    env=remediation_env
    customer=env.user("service_seeker")
    customer["role"]=customer["legacy_role"]
    transporter=env.user("logistics_provider")
    client,_=env.login(transporter)
    with env.db() as db:
        order_id,bid_id=_shipment(db,customer,transporter)
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
                   "VALUES(%s,'client',1000,0,0,true)",(customer["id"],))
    first_locked,competitor_attempted,release=Event(),Event(),Event()

    class RacingDb(ObservedDb):
        def execute(self,sql,params=()):
            locks_shipment="from shipments" in sql.lower() and "for update" in sql.lower()
            if locks_shipment and self.actor!=first:
                competitor_attempted.set()
            result=self.db.execute(sql,params)
            if locks_shipment and self.actor==first:
                first_locked.set()
                assert release.wait(15),"First owner was not released"
            return result
    @contextmanager
    def withdrawal_db():
        with env.db() as db:
            observed=RacingDb(db,lambda sql:None)
            observed.actor="withdraw"
            yield observed
    monkeypatch.setattr(order_routes,"open_db",withdrawal_db)
    def withdraw():
        return client.post(f"/api/orders/{order_id}/bids/{bid_id}/withdraw",headers=env.headers).status_code
    def checkout():
        with env.app.app_context():
            try:
                with env.db() as db:
                    observed=RacingDb(db,lambda sql:None)
                    observed.actor="checkout"
                    payments.perform_checkout(observed,customer,order_id,bid_id,INSURANCE_ACCEPTANCE,idempotency_key="race-"+uuid4().hex)
                return 200
            except payments.CheckoutError as exc:
                return exc.status
    tasks={"withdraw":withdraw,"checkout":checkout}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future=pool.submit(tasks[first])
        assert first_locked.wait(15),"First transaction never acquired shipment lock"
        second_future=pool.submit(tasks["withdraw" if first=="checkout" else "checkout"])
        try:
            assert competitor_attempted.wait(15),"Competing operation never reached the shared lock"
        finally:
            release.set()
        first_status,second_status=first_future.result(20),second_future.result(20)
    assert first_status==200
    assert second_status==(400 if first=="checkout" else 409)
    with env.db() as db:
        assert db.execute("SELECT status FROM shipment_bids WHERE id=%s",(bid_id,)).fetchone()["status"]==("accepted" if first=="checkout" else "withdrawn")
        assert db.execute("SELECT count(*) AS n FROM payments WHERE shipment_id=%s",(order_id,)).fetchone()["n"]==(1 if first=="checkout" else 0)
        assert db.execute("SELECT count(*) AS n FROM shipment_trips WHERE order_id=%s",(order_id,)).fetchone()["n"]==(1 if first=="checkout" else 0)
        assert db.execute("SELECT balance FROM wallets WHERE user_id=%s",(customer["id"],)).fetchone()["balance"]==(900 if first=="checkout" else 1000)


@pytest.mark.parametrize("order_count",[0,1,25])
def test_my_orders_uses_one_domain_query_with_correct_counts_and_ownership(remediation_env,monkeypatch,order_count):
    env=remediation_env
    customer=env.user()
    outsider=env.user()
    transporter=env.user("logistics_provider")
    expected={}
    with env.db() as db:
        foreign_id,_=_shipment(db,outsider)
        for index in range(order_count):
            order_id,bid_id=_shipment(db,customer,transporter)
            if index%2:
                db.execute("UPDATE shipment_bids SET status='withdrawn' WHERE id=%s",(bid_id,))
            expected[order_id]=0 if index%2 else 1
    client,_=env.login(customer)
    queries=[]
    @contextmanager
    def observed_db():
        with env.db() as db:
            yield ObservedDb(db,queries.append)
    monkeypatch.setattr(order_routes,"open_db",observed_db)
    response=client.get("/api/orders/my-orders")
    assert response.status_code==200,response.json
    assert {row["id"]:row["bid_count"] for row in response.json["orders"]}==expected
    assert foreign_id not in {row["id"] for row in response.json["orders"]}
    assert len(queries)==1


@pytest.mark.parametrize("sale_count",[0,1,25])
def test_sales_list_batches_items_with_constant_domain_query_count(remediation_env,monkeypatch,sale_count):
    env=remediation_env
    owner=env.user("shopkeeper")
    outsider=env.user("shopkeeper")
    expected={}
    with env.db() as db:
        for index in range(sale_count+1):
            sale_owner=outsider if index==sale_count else owner
            sale_id=db.execute(
                "INSERT INTO shop_sales(shop_user_id,receipt_number,purchaser_name,total_amount,amount_paid,change_amount) "
                "VALUES(%s,%s,%s,2,2,0) RETURNING id",
                (sale_owner["id"],"TEST-"+uuid4().hex,"Buyer-"+str(index)),
            ).fetchone()["id"]
            for line in range(2):
                db.execute("INSERT INTO shop_sale_items(sale_id,product_name,unit,quantity,unit_price,subtotal) "
                           "VALUES(%s,%s,'piece',1,1,1)",(sale_id,f"Item-{index}-{line}"))
            if index<sale_count:
                expected[sale_id]=[f"Item-{index}-{line}" for line in range(2)]
    client,_=env.login(owner)
    queries=[]
    @contextmanager
    def observed_db():
        with env.db() as db:
            yield ObservedDb(db,queries.append)
    monkeypatch.setattr(shop_routes,"open_db",observed_db)
    response=client.get("/api/shopkeeper/sales?limit=200")
    assert response.status_code==200,response.json
    assert {sale["id"]:[item["product_name"] for item in sale["items"]] for sale in response.json["data"]}==expected
    assert len(queries)==(2 if sale_count else 1)
    assert all(sale["total_amount"]==2 and sum(item["subtotal"] for item in sale["items"])==2 for sale in response.json["data"])


@pytest.mark.parametrize("query",["limit=bad","date_from=2026-02-31","date_from=2026-10-25&date_to=2026-10-24"])
def test_sales_list_invalid_filters_are_validation_errors(remediation_env,query):
    env=remediation_env
    client,_=env.login(env.user("shopkeeper"))
    assert client.get("/api/shopkeeper/sales?"+query).status_code==400


def test_full_wallet_checkout_preserves_existing_default_and_auto_charge_consent(remediation_env):
    env=remediation_env
    customer=env.user()
    transporter=env.user("logistics_provider")
    customer["role"]=customer["legacy_role"]
    with env.app.app_context(),env.db() as db:
        old=payments.create_saved_method(db,customer["id"],{
            "card_brand":"visa","card_last_four":"1111","expiry_month":12,"expiry_year":2030,
        },set_default=True)
        payments.upsert_payment_preferences(db,customer["id"],auto_enabled=True,default_method_id=old["id"])
        order_id,bid_id=_shipment(db,customer,transporter)
        db.execute("INSERT INTO wallets(user_id,role,balance,minimum_required,is_minimum_met) VALUES(%s,'client',1000,0,true)",(customer["id"],))
        payments.perform_checkout(db,customer,order_id,bid_id,{**INSURANCE_ACCEPTANCE,"card":CARD,"save_card":True,"set_default":True},idempotency_key="saved-card-"+uuid4().hex)
    with env.db() as db:
        methods=payments.list_saved_methods(db,customer["id"])
        default=[method for method in methods if method["is_default"]]
        assert len(default)==1 and default[0]["id"]==old["id"]
        preference=payments.get_payment_preferences(db,customer["id"])
        assert preference["default_payment_method_id"]==default[0]["id"]
        assert preference["auto_shortfall_charge_enabled"] is True


def test_mpin_owner_locked_checkout_and_card_creation_have_no_fk_advisory_deadlock(remediation_env,monkeypatch):
    """The advisory-first implementation deadlocks this exact two-owner schedule.

    A holds the authentication owner, as MPIN consumption does. With owner-first
    guards B waits there and A can finish. Advisory-first lets B take the card
    guard then wait on the user's FK while A waits on B's guard (40P01).
    """
    env=remediation_env
    if "payments" not in env.app.blueprints:
        env.app.register_blueprint(payment_routes.payments_blueprint)
    customer=env.user()
    customer["role"]=customer["legacy_role"]
    transporter=env.user("logistics_provider")
    client,_=env.login(customer)
    with env.app.app_context(),env.db() as db:
        order_id,bid_id=_shipment(db,customer,transporter)
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
                   "VALUES(%s,'client',1000,0,0,true)",(customer["id"],))
        payments.upsert_payment_preferences(db,customer["id"],auto_enabled=True)
    owner_locked,card_checkpoint=Event(),Event()
    class CardDb(ObservedDb):
        def execute(self,sql,params=()):
            # Signal before the corrected owner's blocking lock; if regressed
            # to advisory-first, signal only once that guard has been acquired.
            if "from users" in sql.lower() and ("for update" in sql.lower() or "for no key update" in sql.lower()):
                card_checkpoint.set()
            result=self.db.execute(sql,params)
            if "pg_advisory_xact_lock" in sql.lower():
                card_checkpoint.set()
            return result
    @contextmanager
    def card_database():
        with env.db() as db:
            yield CardDb(db,lambda sql:None)
    monkeypatch.setattr(payment_routes,"open_db",card_database)
    def mpin_checkout():
        with env.app.app_context(),env.db() as db:
            db.execute("SELECT id FROM users WHERE id=%s FOR UPDATE",(customer["id"],))
            owner_locked.set()
            assert card_checkpoint.wait(15)
            payments.perform_checkout(db,customer,order_id,bid_id,INSURANCE_ACCEPTANCE,idempotency_key="mpin-card-race-"+uuid4().hex)
        return 200
    def add_card():
        return client.post("/api/payment-methods",headers=env.headers,json={**CARD,"set_default":True}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        checkout_future=pool.submit(mpin_checkout)
        assert owner_locked.wait(15)
        card_future=pool.submit(add_card)
        assert checkout_future.result(25)==200
        assert card_future.result(25)==201
    with env.db() as db:
        default=payments.get_default_saved_method(db,customer["id"])
        preferences=payments.get_payment_preferences(db,customer["id"])
        assert preferences["default_payment_method_id"]==default["id"]
        assert preferences["auto_shortfall_charge_enabled"] is True
        assert db.execute("SELECT balance FROM wallets WHERE user_id=%s",(customer["id"],)).fetchone()["balance"]==900


def test_checkout_owner_guard_allows_existing_wallet_writer_fk_lock(remediation_env):
    """A wallet credit holding its wallet can insert its owner FK during checkout.

    Checkout owns the payment-settings row before waiting on this writer's
    wallet. FOR UPDATE on that owner creates a real owner/wallet FK deadlock;
    FOR NO KEY UPDATE still serializes card settings and permits KEY SHARE.
    """
    env=remediation_env
    customer=env.user()
    customer["role"]=customer["legacy_role"]
    transporter=env.user("logistics_provider")
    with env.db() as db:
        order_id,bid_id=_shipment(db,customer,transporter)
        db.execute("INSERT INTO wallets(user_id,role,balance,locked_balance,minimum_required,is_minimum_met) "
                   "VALUES(%s,'client',1000,0,0,true)",(customer["id"],))
    wallet_locked,checkout_waiting=Event(),Event()

    class WalletWriterDb(ObservedDb):
        def execute(self,sql,params=()):
            result=self.db.execute(sql,params)
            if "from wallets" in sql.lower() and "for update" in sql.lower():
                wallet_locked.set()
                assert checkout_waiting.wait(10),"Checkout never reached the held wallet"
            return result

    class CheckoutDb(ObservedDb):
        def execute(self,sql,params=()):
            if "from wallets" in sql.lower() and "for update" in sql.lower():
                checkout_waiting.set()
            return self.db.execute_exact(sql,params)

    def credit():
        with env.app.app_context(),env.db() as db:
            db.execute("SET LOCAL statement_timeout='8s'")
            db.execute("SET LOCAL deadlock_timeout='200ms'")
            wallet=dict(db.execute("SELECT * FROM wallets WHERE user_id=%s",(customer["id"],)).fetchone())
            observed=WalletWriterDb(db,lambda sql:None)
            error=wallet_helpers.adjust_wallet_balance(observed,wallet,customer["id"],25,"test_credit")
            assert error is None

    def checkout():
        with env.app.app_context(),env.db() as db:
            db.execute("SET LOCAL statement_timeout='8s'")
            db.execute("SET LOCAL deadlock_timeout='200ms'")
            return payments.perform_checkout(CheckoutDb(db,lambda sql:None),customer,order_id,bid_id,INSURANCE_ACCEPTANCE,
                                             idempotency_key="wallet-fk-race-"+uuid4().hex)

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer=pool.submit(credit)
        assert wallet_locked.wait(10),"Credit never acquired the wallet"
        buyer=pool.submit(checkout)
        try:
            assert writer.result(15) is None
            assert buyer.result(15)["replayed"] is False
        finally:
            # Unblock the bounded writer if checkout failed before its wallet.
            checkout_waiting.set()
    with env.db() as db:
        assert db.execute("SELECT balance FROM wallets WHERE user_id=%s",(customer["id"],)).fetchone()["balance"]==925
        assert db.execute("SELECT type,amount FROM wallet_transactions WHERE user_id=%s ORDER BY id",
                          (customer["id"],)).fetchall()==[{"type":"test_credit","amount":25},{"type":"order_payment","amount":-100}]
        assert db.execute("SELECT count(*) AS n FROM payments WHERE shipment_id=%s",(order_id,)).fetchone()["n"]==1
        assert db.execute("SELECT count(*) AS n FROM shipment_trips WHERE order_id=%s",(order_id,)).fetchone()["n"]==1


@pytest.mark.parametrize("role",["driver","service_seeker","fuel_station_manager","logistics_provider"])
def test_all_marketplace_seller_actions_reject_authenticated_other_roles(remediation_env,monkeypatch,role):
    env=remediation_env
    if "marketplace" not in env.app.blueprints:
        env.app.register_blueprint(marketplace_routes.marketplace_blueprint)
    def forbidden_database():
        raise AssertionError("A rejected seller role must not enter marketplace SQL.")
    monkeypatch.setattr(marketplace_routes,"open_db",forbidden_database)
    client,_=env.login(env.user(role))
    requests=[
        ("GET","/api/marketplace/shop/parts"),
        ("POST","/api/marketplace/shop/parts"),
        ("GET","/api/marketplace/shop/orders"),
        ("POST","/api/marketplace/shop/orders/1/status"),
        ("POST","/api/marketplace/shop/orders/1/verify-otp"),
        ("DELETE","/api/marketplace/shop/parts/1"),
        ("POST","/api/marketplace/rfq/1/bid"),
    ]
    for method,path in requests:
        response=client.open(path,method=method,headers=env.headers,json={})
        assert response.status_code==403,(method,path,response.json)
