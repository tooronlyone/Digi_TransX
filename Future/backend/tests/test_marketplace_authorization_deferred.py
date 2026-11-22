"""Deferred V2 marketplace & shopkeeper database authorization proofs.

Archived from active V1 tests because Shopkeeper / Truck Parts Marketplace
(`shopkeeper_profiles`, `marketplace_orders`, `marketplace_delivery_secrets`,
`part_rfqs`, `part_rfq_bids`, `shop_products`, `shop_sales`, `shop_sale_items`)
is deferred to V2 and preserved under `Future/supabase/`.
"""
from pathlib import Path
from uuid import uuid4

import psycopg2
from psycopg2.extras import Json
import pytest

from tests._life_helpers import STUBS, make_disposable, require_test_db_url

ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCHEMA = ROOT / "Future" / "supabase" / "schema-with-agreements-v1.sql"
V2_MARKETPLACE_REF = ROOT / "Future" / "supabase" / "shopkeeper-marketplace-v2-reference.sql"


def _user(cursor, legacy_role="service_seeker"):
    auth_id = str(uuid4())
    email = f"{uuid4().hex}@deferred-marketplace.invalid"
    cursor.execute(
        "INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
        (auth_id, email, Json({"legacy_role": legacy_role, "full_name": "Audit fixture"})),
    )
    cursor.execute("SELECT id FROM public.users WHERE auth_id=%s", (auth_id,))
    return {"id": cursor.fetchone()[0], "auth_id": auth_id, "email": email}


def test_deferred_marketplace_request_binding_and_leg_uniqueness_reference_only():
    """Verify the archived Shopkeeper/Marketplace reference SQL stays intact."""
    ref_sql = V2_MARKETPLACE_REF.read_text(encoding="utf-8")
    assert "marketplace_checkout_request_binding" in ref_sql
    assert "marketplace_plaintext_otp_disabled" in ref_sql
    assert "wallet_transactions_marketplace_leg" in ref_sql
    assert "marketplace_delivery_secrets" in ref_sql
    assert "shop_products" in ref_sql
    assert LEGACY_SCHEMA.exists()
