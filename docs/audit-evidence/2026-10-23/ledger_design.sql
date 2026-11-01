CREATE TABLE public.ledger_accounts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_user_id bigint REFERENCES public.users(id) ON DELETE RESTRICT,
    purpose text NOT NULL,
    currency text NOT NULL CHECK (currency='PKR'),
    normal_side text NOT NULL CHECK (normal_side IN ('debit','credit')),
    allow_negative boolean NOT NULL DEFAULT false,
    UNIQUE(id,currency),
    UNIQUE(owner_user_id,purpose,currency)
);
CREATE TABLE public.ledger_journals (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE CHECK (length(event_key) BETWEEN 1 AND 200),
    event_kind text NOT NULL CHECK (length(event_kind) BETWEEN 1 AND 80),
    request_body jsonb NOT NULL,
    posting_xid xid8 NOT NULL DEFAULT pg_current_xact_id(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.ledger_entries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journal_id bigint NOT NULL REFERENCES public.ledger_journals(id) ON DELETE RESTRICT,
    account_id bigint NOT NULL,
    currency text NOT NULL,
    debit_minor bigint NOT NULL DEFAULT 0,
    credit_minor bigint NOT NULL DEFAULT 0,
    FOREIGN KEY(account_id,currency) REFERENCES public.ledger_accounts(id,currency),
    CHECK (debit_minor BETWEEN 0 AND 9000000000000000),
    CHECK (credit_minor BETWEEN 0 AND 9000000000000000),
    CHECK ((debit_minor>0 AND credit_minor=0) OR (credit_minor>0 AND debit_minor=0)),
    UNIQUE(journal_id,account_id)
);
CREATE INDEX ledger_entries_account ON public.ledger_entries(account_id,journal_id);
CREATE FUNCTION public.require_open_journal_transaction() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM public.ledger_journals j
                  WHERE j.id=NEW.journal_id AND j.posting_xid=pg_current_xact_id()) THEN
        RAISE EXCEPTION 'Cannot append to a posted journal';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ledger_entries_same_transaction BEFORE INSERT ON public.ledger_entries
FOR EACH ROW EXECUTE FUNCTION public.require_open_journal_transaction();
CREATE FUNCTION public.reject_posted_ledger_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'Posted ledger history is immutable; post a reversing journal';
END $$;
CREATE TRIGGER ledger_entries_immutable BEFORE UPDATE OR DELETE ON public.ledger_entries
FOR EACH ROW EXECUTE FUNCTION public.reject_posted_ledger_mutation();
CREATE TRIGGER ledger_journals_immutable BEFORE UPDATE OR DELETE ON public.ledger_journals
FOR EACH ROW EXECUTE FUNCTION public.reject_posted_ledger_mutation();
CREATE FUNCTION public.assert_balanced_journal() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE target bigint; n bigint; bad boolean;
BEGIN
    IF TG_TABLE_NAME='ledger_journals' THEN
        target := NEW.id;
    ELSE
        target := NEW.journal_id;
    END IF;
    SELECT count(*) INTO n FROM public.ledger_entries WHERE journal_id=target;
    SELECT EXISTS (
        SELECT currency FROM public.ledger_entries WHERE journal_id=target
        GROUP BY currency HAVING sum(debit_minor)<>sum(credit_minor)
    ) INTO bad;
    IF n<2 OR bad THEN RAISE EXCEPTION 'Journal % is not balanced',target; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ledger_header_balance AFTER INSERT ON public.ledger_journals
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.assert_balanced_journal();
CREATE CONSTRAINT TRIGGER ledger_line_balance AFTER INSERT ON public.ledger_entries
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.assert_balanced_journal();
CREATE TYPE public.ledger_line_input AS (
    account_id bigint,
    debit_minor bigint,
    credit_minor bigint
);
CREATE FUNCTION public.post_ledger_journal(
    p_key text,p_kind text,p_currency text,p_lines public.ledger_line_input[]
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    result_id bigint; previous public.ledger_journals%ROWTYPE; body jsonb;
    total_rows bigint; account_count bigint; line record; account record;
    delta numeric; current_balance numeric;
BEGIN
    total_rows := coalesce(cardinality(p_lines),0);
    IF p_currency IS DISTINCT FROM 'PKR' OR total_rows<2 OR total_rows>100 THEN
        RAISE EXCEPTION 'Invalid journal';
    END IF;
    IF EXISTS(SELECT 1 FROM unnest(p_lines) x
              WHERE x.account_id IS NULL OR x.debit_minor IS NULL OR x.credit_minor IS NULL
                OR x.debit_minor<0 OR x.credit_minor<0
                OR x.debit_minor>9000000000000000 OR x.credit_minor>9000000000000000
                OR NOT ((x.debit_minor>0 AND x.credit_minor=0)
                     OR (x.credit_minor>0 AND x.debit_minor=0))) THEN
        RAISE EXCEPTION 'Invalid journal line';
    END IF;
    SELECT count(DISTINCT x.account_id) INTO account_count FROM unnest(p_lines) x;
    IF account_count<>total_rows THEN RAISE EXCEPTION 'Duplicate account line'; END IF;
    SELECT sum(x.debit_minor)-sum(x.credit_minor) INTO delta FROM unnest(p_lines) x;
    IF delta<>0 THEN RAISE EXCEPTION 'Journal is not balanced'; END IF;
    SELECT jsonb_build_object('currency',p_currency,'lines',
           jsonb_agg(to_jsonb(x) ORDER BY x.account_id)) INTO body FROM unnest(p_lines) x;
    INSERT INTO public.ledger_journals(event_key,event_kind,request_body)
    VALUES(p_key,p_kind,body) ON CONFLICT(event_key) DO NOTHING RETURNING id INTO result_id;
    IF result_id IS NULL THEN
        SELECT * INTO STRICT previous FROM public.ledger_journals WHERE event_key=p_key;
        IF previous.event_kind IS DISTINCT FROM p_kind OR previous.request_body IS DISTINCT FROM body THEN
            RAISE EXCEPTION 'Idempotency key reused for different journal';
        END IF;
        RETURN previous.id;
    END IF;
    account_count := 0;
    FOR account IN SELECT a.* FROM public.ledger_accounts a
                   WHERE a.id IN(SELECT x.account_id FROM unnest(p_lines) x)
                   ORDER BY a.id FOR UPDATE LOOP
        account_count := account_count+1;
        IF account.currency<>p_currency THEN RAISE EXCEPTION 'Currency mismatch'; END IF;
        SELECT * INTO STRICT line FROM unnest(p_lines) x WHERE x.account_id=account.id;
        SELECT coalesce(sum(e.debit_minor-e.credit_minor),0) INTO current_balance
        FROM public.ledger_entries e WHERE e.account_id=account.id;
        current_balance := current_balance+line.debit_minor-line.credit_minor;
        IF account.normal_side='credit' THEN current_balance := -current_balance; END IF;
        IF NOT account.allow_negative AND current_balance<0 THEN
            RAISE EXCEPTION 'Insufficient funds in account %',account.id;
        END IF;
    END LOOP;
    IF account_count<>total_rows THEN RAISE EXCEPTION 'Account missing'; END IF;
    INSERT INTO public.ledger_entries(journal_id,account_id,currency,debit_minor,credit_minor)
    SELECT result_id,x.account_id,p_currency,x.debit_minor,x.credit_minor FROM unnest(p_lines) x;
    RETURN result_id;
END $$;
ALTER TABLE public.ledger_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ledger_journals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ledger_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ledger_accounts,public.ledger_journals,public.ledger_entries
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.post_ledger_journal(text,text,text,public.ledger_line_input[])
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.assert_balanced_journal(),public.reject_posted_ledger_mutation()
FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.require_open_journal_transaction() FROM PUBLIC,anon,authenticated;
CREATE TABLE public.payment_outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    journal_id bigint NOT NULL REFERENCES public.ledger_journals(id) ON DELETE RESTRICT,
    operation text NOT NULL CHECK(operation IN('charge','refund','payout')),
    amount_minor bigint NOT NULL CHECK(amount_minor BETWEEN 1 AND 9000000000000000),
    currency text NOT NULL CHECK(currency='PKR'),
    destination_token text,
    state text NOT NULL DEFAULT 'queued'
      CHECK(state IN('queued','submitting','succeeded','failed','reconciling')),
    provider_reference text,
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX payment_outbox_ready ON public.payment_outbox(available_at,id) WHERE state='queued';
ALTER TABLE public.payment_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.payment_outbox FROM PUBLIC,anon,authenticated;
