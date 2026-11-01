"""Validate the proposed audit ledger on a new loopback-only disposable DB."""
from pathlib import Path
import psycopg2

ROOT = Path(__file__).resolve().parent
DSN = "postgresql://audit_local@127.0.0.1:15477/audit_ledger_validation_final"


def connect():
    return psycopg2.connect(DSN)


def post(conn, key, debit_account, credit_account, amount, kind="funding"):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT public.post_ledger_journal(%s,%s,'PKR',ARRAY["
            "ROW(%s,%s,0)::public.ledger_line_input,"
            "ROW(%s,0,%s)::public.ledger_line_input])",
            (key, kind, debit_account, amount, credit_account, amount),
        )
        return cur.fetchone()[0]


def expect_rejection(label, operation):
    conn = connect()
    try:
        operation(conn)
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        print(label + ": rejected: " + exc.diag.message_primary)
    else:
        raise AssertionError(label + ": unexpectedly accepted")
    finally:
        conn.close()


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE public.users(id bigint PRIMARY KEY)")
        ddl = (ROOT / "ledger_design.sql").read_text(encoding="utf-8")
        cur.execute(ddl)
        cur.execute("INSERT INTO public.users(id) VALUES(1),(2)")
        cur.execute(
            "INSERT INTO public.ledger_accounts(owner_user_id,purpose,currency,normal_side) "
            "VALUES(NULL,'provider_receivable','PKR','debit'),"
            "(1,'available_funds','PKR','credit'),"
            "(2,'available_funds','PKR','credit'),"
            "(NULL,'extra_asset','PKR','debit'),"
            "(NULL,'extra_liability','PKR','credit')"
        )
    journal_id = post(conn, "fund-1", 1, 2, 10000)
print("balanced_funding: committed journal " + str(journal_id))

with connect() as conn:
    replay = post(conn, "fund-1", 1, 2, 10000)
    assert replay == journal_id
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.ledger_journals WHERE event_key='fund-1'")
        assert cur.fetchone()[0] == 1
print("idempotent_replay: same journal, one header")

expect_rejection("changed_payload", lambda conn: post(conn, "fund-1", 1, 2, 10001))
expect_rejection("overdraft", lambda conn: post(conn, "withdraw-1", 2, 3, 10001, "transfer"))


def mutate(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE public.ledger_entries SET debit_minor=20000 WHERE journal_id=%s AND account_id=1", (journal_id,))


def mutate_header(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE public.ledger_journals SET event_kind='changed' WHERE id=%s", (journal_id,))


def direct_unbalanced(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO public.ledger_journals(event_key,event_kind,request_body) VALUES('unbalanced','test','{}') RETURNING id")
        bad_journal = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO public.ledger_entries(journal_id,account_id,currency,debit_minor,credit_minor) "
            "VALUES(%s,1,'PKR',100,0),(%s,2,'PKR',0,99)", (bad_journal, bad_journal)
        )
    print("unbalanced_direct_entries: insert accepted before deferred commit check")


expect_rejection("entry_immutability", mutate)
expect_rejection("header_immutability", mutate_header)
expect_rejection("unbalanced_direct_commit", direct_unbalanced)

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT coalesce(sum(debit_minor-credit_minor),0) FROM public.ledger_entries WHERE account_id=2")
        assert cur.fetchone()[0] == -10000
        cur.execute("SELECT count(*) FROM public.ledger_journals")
        assert cur.fetchone()[0] == 1
print("failed_posts_rollback: initial funds and journal count unchanged")

# Test the meaning of immutable history beyond UPDATE/DELETE prevention.
def append_posted(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ledger_entries(journal_id,account_id,currency,debit_minor,credit_minor) "
            "VALUES(%s,4,'PKR',100,0),(%s,5,'PKR',0,100)", (journal_id, journal_id)
        )


expect_rejection("post_commit_balanced_append", append_posted)
print("FINAL: all requested ledger checks passed against actual design SQL")
