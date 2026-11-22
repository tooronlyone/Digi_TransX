-- Withdrawal and agreement notifications belong to an account without a
-- shipment. Keep the shipment FK, recipient ownership and RLS unchanged.
ALTER TABLE public.shipment_notifications ALTER COLUMN order_id DROP NOT NULL;
