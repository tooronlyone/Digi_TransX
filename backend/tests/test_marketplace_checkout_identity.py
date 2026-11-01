"""A stale account's cart must not create an order using the next login's cookie."""
from contextlib import contextmanager

import pytest

from marketplace import routes as marketplace_routes
from tests.remediation_harness import remediation_database_url,remediation_env


@pytest.fixture
def marketplace_env(remediation_env,monkeypatch):
    env=remediation_env
    env.app.register_blueprint(marketplace_routes.marketplace_blueprint)
    monkeypatch.setattr(marketplace_routes,"open_db",env.db)
    return env


@pytest.mark.parametrize("expected",[None,"","0","-1","NaN","Infinity","true","1.5"])
def test_unbound_checkout_is_rejected_before_inventory_wallet_or_provider_work(marketplace_env,monkeypatch,expected):
    env=marketplace_env
    user=env.user()
    client,_=env.login(user)
    def forbidden():
        pytest.fail("An unbound checkout must not enter the marketplace transaction")
    monkeypatch.setattr(marketplace_routes,"open_db",forbidden)
    headers={**env.headers,"Idempotency-Key":"identity-guard-probe"}
    if expected is not None:
        headers["X-DTX-Expected-User-Id"]=expected
    response=client.post("/api/marketplace/orders",headers=headers,json={})
    assert response.status_code==400,response.json
    assert response.json["code"]=="checkout_account_required"


def test_account_switch_with_new_csrf_cannot_submit_previous_accounts_cart(marketplace_env,monkeypatch):
    env=marketplace_env
    old_user,new_user=env.user(),env.user()
    client,_=env.login(old_user)
    # The browser is now authenticated as B. A's pending form already holds A's
    # owner-bound header, even if its delayed CSRF request obtains B's token.
    client,_=env.login(new_user,client)
    calls=[]
    @contextmanager
    def guarded_transaction():
        calls.append("transaction")
        with env.db() as db:
            yield db
    def checkout(db,user,payload,key):
        calls.append(user["id"])
        return {"id":37,"replayed":False}
    monkeypatch.setattr(marketplace_routes,"open_db",guarded_transaction)
    monkeypatch.setattr(marketplace_routes,"perform_marketplace_checkout",checkout)
    headers={**env.headers,"Idempotency-Key":"stale-cart-account-probe","X-DTX-Expected-User-Id":str(old_user["id"])}
    rejected=client.post("/api/marketplace/orders",headers=headers,json={"cart_from":"old_account"})
    assert rejected.status_code==409 and rejected.json["code"]=="checkout_account_changed"
    assert calls==[]
    headers["X-DTX-Expected-User-Id"]=str(new_user["id"])
    accepted=client.post("/api/marketplace/orders",headers=headers,json={"cart_from":"new_account"})
    assert accepted.status_code==201,accepted.json
    assert calls==["transaction",new_user["id"]]
