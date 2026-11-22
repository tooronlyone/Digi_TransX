"""Deferred V2 Shop Owner POS regression tests (archived outside V1 suite)."""

from decimal import Decimal


def _product(env, client, name="Item", price="1.00", stock="6.000", unit="piece"):
    response = client.post(
        "/api/shopkeeper/products",
        headers=env.headers,
        json={"name": name, "price": price, "stock_quantity": stock, "unit": unit},
    )
    assert response.status_code == 201, response.json
    return response.json["data"]["id"]


def test_pos_merges_duplicate_product_before_stock_validation(remediation_env):
    env = remediation_env
    user = env.user("shopkeeper")
    client, _ = env.login(user)
    product_id = _product(env, client)
    body = {
        "amount_paid": "10.00",
        "items": [
            {"product_id": product_id, "quantity": 4},
            {"product_id": product_id, "quantity": 4},
        ],
    }
    assert client.post("/api/shopkeeper/sales", headers=env.headers, json=body).status_code == 409
    body["items"][0]["quantity"] = 2
    body["items"][1]["quantity"] = 3
    response = client.post("/api/shopkeeper/sales", headers=env.headers, json=body)
    assert response.status_code == 201, response.json
    assert len(response.json["data"]["items"]) == 1
    assert response.json["data"]["items"][0]["quantity"] == 5
    with env.db() as db:
        assert (
            db.execute("SELECT stock_quantity FROM shop_products WHERE id=%s", (product_id,)).fetchone()[
                "stock_quantity"
            ]
            == 1
        )


def test_pos_rounded_lines_equal_receipt_and_paid_amount(remediation_env):
    env = remediation_env
    client, _ = env.login(env.user("shopkeeper"))
    ids = [_product(env, client, name=f"Liquid {i}", price="0.01", unit="liter") for i in range(2)]
    response = client.post(
        "/api/shopkeeper/sales",
        headers=env.headers,
        json={
            "amount_paid": "0.02",
            "items": [{"product_id": p, "quantity": "0.500"} for p in ids],
        },
    )
    assert response.status_code == 201, response.json
    data = response.json["data"]
    assert sum(Decimal(str(item["subtotal"])) for item in data["items"]) == Decimal("0.02")
    assert data["total_amount"] == 0.02 and data["change_amount"] == 0
