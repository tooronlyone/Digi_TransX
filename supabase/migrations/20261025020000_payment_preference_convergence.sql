-- Repair the existing checkout/default-card split without granting payment consent.
-- A selected active default is authoritative; updating its pointer never enables
-- automatic shortfall charging. Existing consent flags remain unchanged.
DO $$
DECLARE owners bigint[]; owner_id bigint;
BEGIN
    SELECT array_agg(DISTINCT user_id ORDER BY user_id) INTO owners
      FROM public.saved_payment_methods WHERE status='active' AND is_default;
    IF owners IS NULL THEN RETURN; END IF;
    -- Same owner -> advisory ordering as checkout/card-setting mutations. Read
    -- the selected method again after these locks; do not apply an old snapshot
    -- over a default card changed concurrently by the owner.
    PERFORM u.id FROM public.users u WHERE u.id=ANY(owners) ORDER BY u.id FOR UPDATE;
    FOREACH owner_id IN ARRAY owners LOOP
        PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('dtx.payment-settings:'||owner_id::text,0));
    END LOOP;
    INSERT INTO public.user_payment_preferences(
    user_id,default_payment_method_id,auto_shortfall_charge_enabled,created_at,updated_at)
SELECT user_id,id,false,now(),now() FROM public.saved_payment_methods
 WHERE user_id=ANY(owners) AND status='active' AND is_default
ON CONFLICT(user_id) DO UPDATE
    SET default_payment_method_id=excluded.default_payment_method_id,updated_at=now()
    WHERE public.user_payment_preferences.default_payment_method_id
          IS DISTINCT FROM excluded.default_payment_method_id;
END $$;
