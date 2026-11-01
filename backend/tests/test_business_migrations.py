"""Rules 1-4 upgrade/replay, legacy financial preservation and RLS proofs."""
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2
import pytest

from shared.db import Db
from tests._life_helpers import make_disposable, require_test_db_url, STUBS, SCHEMA_SQL
from tests.test_trip_lifecycle import seed_ready_order

MARKER='-- BEGIN RULES 1-4 BUSINESS POLICY CUTOVER'
MIGRATIONS=sorted((SCHEMA_SQL.parent/'migrations').glob('20261026*.sql'))
PRIVATE_TABLES=('financial_journal','financial_journal_lines','delivery_otp_challenges',
    'freight_settlements','security_reserves','security_reserve_entries','security_reserve_policy',
    'security_reserve_brackets','delivery_incident_evidence','freight_settlement_resolutions',
    'fuel_platform_treasury','fuel_credit_accounts','fuel_vouchers','fuel_credit_events',
    'owner_operator_credentials','operational_incidents','trip_cancellation_requests')


@pytest.mark.parametrize('path',['fresh','upgrade'])
def test_business_migrations_preserve_history_replay_and_private_rls(path):
    base=require_test_db_url()
    if urlsplit(base).hostname not in {'127.0.0.1','localhost','::1'}:
        pytest.fail('Business migration tests require disposable loopback PostgreSQL.')
    snapshot=SCHEMA_SQL.read_text(encoding='utf-8')
    baseline=snapshot if path=='fresh' else snapshot.split(MARKER)[0]
    url,cleanup=make_disposable(base,STUBS,baseline)
    try:
        with psycopg2.connect(url) as connection:
            db=Db(connection)
            seed=seed_ready_order(db)
            old_payment=db.execute_exact('SELECT id,bid_price,company_fee,transporter_amount,status,wallet_funded_amount,card_funded_amount FROM payments WHERE id=%s',(seed['payment_id'],)).fetchone()
            old_wallets=db.execute_exact('SELECT id,user_id,balance,locked_balance,minimum_required FROM wallets ORDER BY id').fetchall()
            old_counts={row['tablename']:db.execute('SELECT count(*) AS n FROM public.'+row['tablename']).fetchone()['n'] for row in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()}
            for _ in range(2):
                for migration in MIGRATIONS:
                    db.execute(migration.read_text(encoding='utf-8'))
                connection.commit()
            assert db.execute_exact('SELECT id,bid_price,company_fee,transporter_amount,status,wallet_funded_amount,card_funded_amount FROM payments WHERE id=%s',(seed['payment_id'],)).fetchone()==old_payment
            assert db.execute_exact('SELECT id,user_id,balance,locked_balance,minimum_required FROM wallets ORDER BY id').fetchall()==old_wallets
            for table,count in old_counts.items():
                assert db.execute('SELECT count(*) AS n FROM public.'+table).fetchone()['n']==count,(table,count)
            assert db.execute('SELECT business_rules_version FROM payments WHERE id=%s',(seed['payment_id'],)).fetchone()['business_rules_version'] is None
            for table in PRIVATE_TABLES:
                state=db.execute('SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass',('public.'+table,)).fetchone()
                assert state and state['relrowsecurity'],table
                for role in ('anon','authenticated'):
                    for permission in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE'):
                        assert not db.execute('SELECT has_table_privilege(%s,%s,%s) AS allowed',(role,'public.'+table,permission)).fetchone()['allowed'],(table,role,permission)
            assert db.execute("SELECT count(*) AS n FROM security_reserve_brackets").fetchone()['n']==5
            assert db.execute("SELECT progressive_percent FROM security_reserve_policy").fetchone()['progressive_percent'] is None
            assert db.execute('SELECT count(*) AS n FROM fuel_platform_treasury').fetchone()['n']==0
            # Database-side finite checks catch a privileged writer bypassing
            # the HTTP Decimal parser, not just malformed request strings.
            db.execute('SAVEPOINT finite_test')
            with pytest.raises(psycopg2.errors.CheckViolation):
                db.execute("INSERT INTO fuel_credit_accounts(transporter_user_id,authorized_limit,utilized_credit,outstanding_credit) VALUES(%s,20000,'NaN','NaN')",(seed['transporter']['id'],))
            db.execute('ROLLBACK TO SAVEPOINT finite_test')
    finally:
        cleanup()
