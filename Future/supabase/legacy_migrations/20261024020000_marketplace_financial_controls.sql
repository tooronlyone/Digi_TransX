-- Backend-only delivery proofs and checkout idempotency. No historical
-- plaintext OTP is trustworthy: buyers must request a fresh proof in the API.
ALTER TABLE public.marketplace_orders
    ADD COLUMN IF NOT EXISTS checkout_key text,
    ADD COLUMN IF NOT EXISTS request_fingerprint text;
DO $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_constraint
                  WHERE conrelid='public.marketplace_orders'::regclass
                    AND conname='marketplace_checkout_request_binding') THEN
        ALTER TABLE public.marketplace_orders ADD CONSTRAINT marketplace_checkout_request_binding
        CHECK((checkout_key IS NULL AND request_fingerprint IS NULL)
              OR (checkout_key IS NOT NULL AND length(checkout_key) BETWEEN 8 AND 128
                  AND request_fingerprint IS NOT NULL
                  AND request_fingerprint ~ '^[0-9a-f]{64}$'));
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS marketplace_orders_buyer_checkout_key
    ON public.marketplace_orders(buyer_user_id,checkout_key) WHERE checkout_key IS NOT NULL;

DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM public.wallet_transactions
              WHERE type IN('parts_purchase','parts_sale') AND reference_id IS NOT NULL
              GROUP BY wallet_id,type,reference_id HAVING count(*)>1) THEN
        RAISE EXCEPTION 'Duplicate marketplace wallet legs require explicit reconciliation';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS wallet_transactions_marketplace_leg
    ON public.wallet_transactions(wallet_id,type,reference_id)
    WHERE type IN('parts_purchase','parts_sale') AND reference_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.marketplace_delivery_secrets(
    order_id bigint PRIMARY KEY REFERENCES public.marketplace_orders(id) ON DELETE CASCADE,
    otp_digest text NOT NULL CHECK(otp_digest ~ '^[0-9a-f]{64}$'),
    expires_at timestamptz NOT NULL,
    failed_attempts integer NOT NULL DEFAULT 0 CHECK(failed_attempts BETWEEN 0 AND 5),
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(expires_at>created_at),
    CHECK(consumed_at IS NULL OR consumed_at>=created_at)
);
ALTER TABLE public.marketplace_delivery_secrets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.marketplace_delivery_secrets FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.marketplace_delivery_secrets TO service_role;
DROP POLICY IF EXISTS backend_service_access ON public.marketplace_delivery_secrets;
CREATE POLICY backend_service_access ON public.marketplace_delivery_secrets
    FOR ALL TO service_role USING(true) WITH CHECK(true);
UPDATE public.marketplace_orders SET delivery_otp=NULL WHERE delivery_otp IS NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_constraint
                  WHERE conrelid='public.marketplace_orders'::regclass
                    AND conname='marketplace_plaintext_otp_disabled') THEN
        ALTER TABLE public.marketplace_orders ADD CONSTRAINT marketplace_plaintext_otp_disabled
            CHECK(delivery_otp IS NULL);
    END IF;
END $$;

-- NOT VALID preserves legacy rows for explicit reconciliation. New writes and
-- updates must satisfy these invariants immediately; no balance is rewritten.
DO $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='public.wallets'::regclass
                  AND conname='wallets_money_invariants') THEN
        ALTER TABLE public.wallets ADD CONSTRAINT wallets_money_invariants
        CHECK(balance>=0 AND balance<'Infinity'::numeric
              AND locked_balance>=0 AND locked_balance<'Infinity'::numeric
              AND locked_balance<=balance
              AND minimum_required>=0 AND minimum_required<'Infinity'::numeric) NOT VALID;
    END IF;
END $$;
