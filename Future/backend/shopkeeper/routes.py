from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from secrets import token_hex

from flask import Blueprint, request

from auth.helpers import csrf_error, json_response, login_required
from shared.db import open_db
from shared.validation import finite_decimal
from shared.payments import parse_positive_id


shopkeeper_blueprint = Blueprint("shopkeeper", __name__, url_prefix="/api/shopkeeper")

PRODUCT_UNITS = {
    "piece", "pair", "set", "dozen", "pack", "box", "bottle", "can",
    "liter", "milliliter", "gallon", "kilogram", "gram", "meter", "foot",
}
DECIMAL_UNITS = {"liter", "milliliter", "gallon", "kilogram", "gram", "meter", "foot"}


def _shopkeeper_only():
    role = str(request.current_user.get("role") or "").strip().lower()
    if role != "shopkeeper":
        return json_response({"success": False, "message": "Shopkeeper access is required."}, 403)
    return None


def _serialize_product(row):
    stock = float(row["stock_quantity"])
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row.get("category") or "",
        "price": float(row["price"]),
        "stock_quantity": int(stock) if stock.is_integer() else stock,
        "unit": row.get("unit") or "piece",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _product_values(data):
    if not isinstance(data,dict):
        return None, "A JSON object is required."
    name = str(data.get("name") or "").strip()
    category = str(data.get("category") or "").strip()
    unit = str(data.get("unit") or "piece").strip().lower()
    try:
        price = finite_decimal(data.get("price"),"Price",scale=2)
        stock = finite_decimal(data.get("stock_quantity"),"Stock quantity",maximum=Decimal("1000000000"),scale=3)
    except ValueError as exc:
        return None, str(exc)
    if not name:
        return None, "Product name is required."
    if unit not in PRODUCT_UNITS:
        return None, "Select a valid measurement unit."
    if unit not in DECIMAL_UNITS and stock != stock.to_integral_value():
        return None, "This unit requires a whole-number stock quantity."
    return (name, category, price, stock, unit), None


@shopkeeper_blueprint.get("/products")
@login_required
def list_products():
    denied = _shopkeeper_only()
    if denied:
        return denied
    with open_db() as db:
        rows = db.execute(
            """
            SELECT id, name, category, price, stock_quantity, unit, created_at, updated_at
            FROM shop_products
            WHERE shop_user_id = %s
            ORDER BY name ASC, id DESC
            """,
            (request.current_user["id"],),
        ).fetchall()
    return json_response({"success": True, "data": [_serialize_product(row) for row in rows]})


@shopkeeper_blueprint.post("/products")
@login_required
def create_product():
    err = csrf_error()
    if err:
        return err
    denied = _shopkeeper_only()
    if denied:
        return denied
    values, message = _product_values(request.get_json(silent=True) or {})
    if message:
        return json_response({"success": False, "message": message}, 400)
    with open_db() as db:
        row = db.execute(
            """
            INSERT INTO shop_products (shop_user_id, name, category, price, stock_quantity, unit)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, name, category, price, stock_quantity, unit, created_at, updated_at
            """,
            (request.current_user["id"], *values),
        ).fetchone()
        db.commit()
    return json_response({"success": True, "data": _serialize_product(row)}, 201)


@shopkeeper_blueprint.put("/products/<int:product_id>")
@login_required
def update_product(product_id):
    err = csrf_error()
    if err:
        return err
    denied = _shopkeeper_only()
    if denied:
        return denied
    values, message = _product_values(request.get_json(silent=True) or {})
    if message:
        return json_response({"success": False, "message": message}, 400)
    with open_db() as db:
        row = db.execute(
            """
            UPDATE shop_products
            SET name = %s, category = %s, price = %s, stock_quantity = %s,
                unit = %s, updated_at = NOW()
            WHERE id = %s AND shop_user_id = %s
            RETURNING id, name, category, price, stock_quantity, unit, created_at, updated_at
            """,
            (*values, product_id, request.current_user["id"]),
        ).fetchone()
        if not row:
            return json_response({"success": False, "message": "Product not found."}, 404)
        db.commit()
    return json_response({"success": True, "data": _serialize_product(row)})


@shopkeeper_blueprint.delete("/products/<int:product_id>")
@login_required
def delete_product(product_id):
    err = csrf_error()
    if err:
        return err
    denied = _shopkeeper_only()
    if denied:
        return denied
    with open_db() as db:
        result = db.execute(
            "DELETE FROM shop_products WHERE id = %s AND shop_user_id = %s",
            (product_id, request.current_user["id"]),
        )
        if result.rowcount == 0:
            return json_response({"success": False, "message": "Product not found."}, 404)
        db.commit()
    return json_response({"success": True, "message": "Product deleted."})


def _serialize_item(row):
    quantity = float(row["quantity"])
    return {
        "product_id": row.get("product_id"),
        "product_name": row["product_name"],
        "unit": row.get("unit") or "piece",
        "quantity": int(quantity) if quantity.is_integer() else quantity,
        "unit_price": float(row["unit_price"]),
        "subtotal": float(row["subtotal"]),
    }


def _serialize_sale(sale, items):
    return {
        "id": sale["id"],
        "receipt_number": sale["receipt_number"],
        "purchaser_name": sale.get("purchaser_name") or "",
        "total_amount": float(sale["total_amount"]),
        "amount_paid": float(sale["amount_paid"]),
        "change_amount": float(sale["change_amount"]),
        "sale_date": sale["sale_date"],
        "created_at": sale["created_at"],
        "items": [_serialize_item(item) for item in items],
    }


def _sale_with_items(db, sale_id, shop_user_id):
    sale = db.execute(
        "SELECT * FROM shop_sales WHERE id = %s AND shop_user_id = %s",
        (sale_id, shop_user_id),
    ).fetchone()
    if not sale:
        return None
    items = db.execute(
        "SELECT * FROM shop_sale_items WHERE sale_id = %s ORDER BY id",
        (sale_id,),
    ).fetchall()
    return _serialize_sale(sale,items)


@shopkeeper_blueprint.post("/sales")
@login_required
def create_sale():
    err = csrf_error()
    if err:
        return err
    denied = _shopkeeper_only()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict):
        return json_response({"success": False, "message": "A JSON object is required."}, 400)
    requested_items = data.get("items") or []
    if not isinstance(requested_items,list) or not 1 <= len(requested_items) <= 100:
        return json_response({"success": False, "message": "Add at least one product to the sale."}, 400)
    try:
        amount_paid = finite_decimal(data.get("amount_paid"),"Amount paid",maximum=Decimal("999999999999.99"),scale=2)
        quantities = {}
        for requested in requested_items:
            if not isinstance(requested,dict):
                raise ValueError("Each sale item must be an object.")
            product_id = parse_positive_id(requested.get("product_id"),"Product ID")
            quantity = finite_decimal(requested.get("quantity"),"Quantity",minimum=Decimal("0.001"),
                                      maximum=Decimal("1000000000"),scale=3)
            quantities[product_id] = quantities.get(product_id,Decimal(0))+quantity
            finite_decimal(quantities[product_id],"Total product quantity",maximum=Decimal("1000000000"),scale=3)
    except ValueError as exc:
        return json_response({"success": False, "message": str(exc)}, 400)

    shop_user_id = request.current_user["id"]
    with open_db() as db:
        prepared = []
        total = Decimal("0")
        # One row per product, with a consistent lock order across all sales.
        for product_id,quantity in sorted(quantities.items()):
            product = db.execute(
                "SELECT * FROM shop_products WHERE id = %s AND shop_user_id = %s FOR UPDATE",
                (product_id, shop_user_id),
            ).fetchone()
            if not product:
                return json_response({"success": False, "message": "A selected product is no longer available."}, 409)
            try:
                stock = finite_decimal(product["stock_quantity"],"Product stock",maximum=Decimal("1000000000"),scale=3)
                unit_price = finite_decimal(product["price"],"Product price",scale=2)
            except ValueError:
                return json_response({"success": False, "message": "A product needs valid price/stock before sale."}, 409)
            unit = product.get("unit") or "piece"
            if unit not in DECIMAL_UNITS and quantity != quantity.to_integral_value():
                return json_response({"success": False, "message": f"{product['name']} requires a whole-number quantity."}, 400)
            if quantity > stock:
                return json_response({"success": False, "message": f"Only {stock} {unit} of {product['name']} remain in stock."}, 409)
            subtotal = (unit_price * quantity).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            total += subtotal
            prepared.append((product, quantity, unit_price, subtotal))
        if total > Decimal("999999999999.99"):
            return json_response({"success": False, "message": "Sale total exceeds the supported limit."}, 400)
        if amount_paid < total:
            return json_response({"success": False, "message": "Amount paid is less than the sale total."}, 400)

        receipt_number = f"DTX-{token_hex(4).upper()}"
        sale = db.execute(
            """
            INSERT INTO shop_sales (
                shop_user_id, receipt_number, purchaser_name, total_amount,
                amount_paid, change_amount, sale_date
            ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE)
            RETURNING id
            """,
            (
                shop_user_id, receipt_number, str(data.get("purchaser_name") or "").strip(),
                total, amount_paid, amount_paid - total,
            ),
        ).fetchone()
        for product, quantity, unit_price, subtotal in prepared:
            db.execute(
                """
                INSERT INTO shop_sale_items (
                    sale_id, product_id, product_name, unit, quantity, unit_price, subtotal
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (sale["id"], product["id"], product["name"], product.get("unit") or "piece", quantity, unit_price, subtotal),
            )
            db.execute(
                "UPDATE shop_products SET stock_quantity = stock_quantity - %s, updated_at = NOW() WHERE id = %s",
                (quantity, product["id"]),
            )
        db.commit()
        completed = _sale_with_items(db, sale["id"], shop_user_id)
    return json_response({"success": True, "data": {"sale_id": sale["id"], **completed}}, 201)


@shopkeeper_blueprint.get("/sales/<int:sale_id>")
@login_required
def get_sale(sale_id):
    denied = _shopkeeper_only()
    if denied:
        return denied
    with open_db() as db:
        sale = _sale_with_items(db, sale_id, request.current_user["id"])
    if not sale:
        return json_response({"success": False, "message": "Sale not found."}, 404)
    return json_response({"success": True, "data": sale})


@shopkeeper_blueprint.get("/sales")
@login_required
def list_sales():
    denied = _shopkeeper_only()
    if denied:
        return denied
    try:
        date_from = date.fromisoformat(request.args.get("date_from") or "1900-01-01")
        date_to = date.fromisoformat(request.args.get("date_to") or "2999-12-31")
        limit = min(max(int(request.args.get("limit") or 100), 1), 200)
        if date_from > date_to:
            raise ValueError("Reversed date range")
    except (ValueError,TypeError):
        return json_response({"success": False,"message": "Use valid ISO dates and a whole-number limit."},400)
    with open_db() as db:
        rows = db.execute(
            """
            SELECT * FROM shop_sales
            WHERE shop_user_id = %s AND sale_date BETWEEN %s AND %s
            ORDER BY created_at DESC, id DESC LIMIT %s
            """,
            (request.current_user["id"], date_from, date_to, limit),
        ).fetchall()
        grouped_items = {row["id"]: [] for row in rows}
        if rows:
            items = db.execute(
                "SELECT * FROM shop_sale_items WHERE sale_id = ANY(%s) ORDER BY sale_id, id",
                (list(grouped_items),),
            ).fetchall()
            for item in items:
                grouped_items[item["sale_id"]].append(item)
        sales = [_serialize_sale(row,grouped_items[row["id"]]) for row in rows]
    return json_response({"success": True, "data": sales})


@shopkeeper_blueprint.get("/sales/analytics")
@login_required
def sales_analytics():
    denied = _shopkeeper_only()
    if denied:
        return denied
    date_from = request.args.get("date_from") or "1900-01-01"
    date_to = request.args.get("date_to") or "2999-12-31"
    owner = request.current_user["id"]
    with open_db() as db:
        summary = db.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0) AS total_revenue,
                   COUNT(*) AS total_sales,
                   COALESCE(AVG(total_amount), 0) AS avg_sale_value
            FROM shop_sales WHERE shop_user_id = %s AND sale_date BETWEEN %s AND %s
            """,
            (owner, date_from, date_to),
        ).fetchone()
        revenue = db.execute(
            """
            SELECT sale_date AS date, SUM(total_amount) AS revenue
            FROM shop_sales WHERE shop_user_id = %s AND sale_date BETWEEN %s AND %s
            GROUP BY sale_date ORDER BY sale_date
            """,
            (owner, date_from, date_to),
        ).fetchall()
        products = db.execute(
            """
            SELECT i.product_name, SUM(i.quantity) AS total_qty, SUM(i.subtotal) AS total_revenue
            FROM shop_sale_items i JOIN shop_sales s ON s.id = i.sale_id
            WHERE s.shop_user_id = %s AND s.sale_date BETWEEN %s AND %s
            GROUP BY i.product_name ORDER BY total_revenue DESC
            """,
            (owner, date_from, date_to),
        ).fetchall()
    return json_response({"success": True, "data": {
        "summary": summary,
        "revenue_by_date": revenue,
        "top_products": products,
    }})
