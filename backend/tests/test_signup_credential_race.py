"""A delayed signup response cannot outlive a newer credential operation."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg2.extras import Json

from auth import credential_changes, routes as auth_routes, session_service
from auth.trusted_device_service import create_trusted_device
from tests.remediation_harness import remediation_database_url, remediation_env


def _payload():
    nonce = uuid4()
    return {
        "name": "Signup Race Fixture", "email": f"{nonce.hex}@signup-race.invalid",
        "phone": "03000000000", "cnic": f"{nonce.int % 10**13:013d}",
        "password": "initial-password", "role": "everyday_user", "city": "Lahore",
        "signup_terms_accepted": True,
        "signup_terms_version": "signup-terms-2026-10-27-v1",
        "signup_terms_role": "everyday_user",
    }


@pytest.mark.parametrize("newer_state", ["pending", "completed", "blocked"])
def test_signup_continuation_preserves_account_and_denies_stale_authority(
    remediation_env, monkeypatch, newer_state,
):
    env = remediation_env
    payload = _payload()
    created = {}
    compensation_calls = []

    def create_identity(email, password, metadata):
        auth_id = str(uuid4())
        # Reproduce Auth's committed trigger before the signup HTTP call returns.
        with env.db() as db:
            db.execute("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
                       (auth_id, email, Json(metadata)))
            owner = db.execute("SELECT * FROM users WHERE auth_id=%s", (auth_id,)).fetchone()
        created.update(owner)
        if newer_state == "pending":
            credential_changes.begin_password_change(owner["id"], auth_id, "password_reset")
        elif newer_state == "completed":
            credential_changes.execute_password_change(
                owner["id"], auth_id, "replacement-password", "password_reset", lambda *_: None,
            )
        else:
            with env.db() as db:
                db.execute("UPDATE users SET is_blocked=true WHERE id=%s", (owner["id"],))
        return SimpleNamespace(id=auth_id)

    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", create_identity)
    monkeypatch.setattr(auth_routes, "_compensate_signup_identity",
                        lambda *args: compensation_calls.append(args) or True)
    client = env.app.test_client()
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 409, response.json
    assert response.json["code"] == "signup_authentication_changed"
    assert compensation_calls == []
    assert client.get_cookie("dtx_session_token") is None
    with env.db() as db:
        owner = db.execute("SELECT * FROM users WHERE id=%s", (created["id"],)).fetchone()
        assert owner is not None
        assert db.execute("SELECT count(*) AS n FROM auth.users WHERE id=%s", (created["auth_id"],)).fetchone()["n"] == 1
        assert db.execute("SELECT count(*) AS n FROM user_sessions WHERE user_id=%s", (owner["id"],)).fetchone()["n"] == 0
        assert db.execute("SELECT count(*) AS n FROM trusted_devices WHERE user_id=%s", (owner["id"],)).fetchone()["n"] == 0
        assert db.execute("SELECT count(*) AS n FROM login_activity WHERE user_id=%s", (owner["id"],)).fetchone()["n"] == 0


def test_fresh_signup_still_issues_one_authenticated_session(remediation_env, monkeypatch):
    env = remediation_env
    payload = _payload()

    def create_identity(email, password, metadata):
        auth_id = str(uuid4())
        with env.db() as db:
            db.execute("INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES(%s,%s,%s)",
                       (auth_id, email, Json(metadata)))
        return SimpleNamespace(id=auth_id)

    monkeypatch.setattr(auth_routes, "supabase_create_signup_user", create_identity)
    client = env.app.test_client()
    response = client.post("/auth/signup", json=payload)
    assert response.status_code == 200, response.json
    assert client.get("/auth/me").status_code == 200
    with env.db() as db:
        owner = db.execute("SELECT * FROM users WHERE email=%s", (payload["email"],)).fetchone()
        assert db.execute("SELECT count(*) AS n FROM user_sessions WHERE user_id=%s", (owner["id"],)).fetchone()["n"] == 1


def test_session_issuer_rejects_pending_owner_even_with_an_active_device(remediation_env):
    env = remediation_env
    owner = env.user()
    with env.db() as db:
        _, device_id = create_trusted_device(db, owner["id"])
        db.execute("UPDATE users SET password_change_pending=true WHERE id=%s", (owner["id"],))
    with pytest.raises(session_service.SessionFoundationError):
        with env.db() as db:
            session_service.create_session(db, owner["id"], trusted_device_id=device_id)
    with env.db() as db:
        assert db.execute("SELECT count(*) AS n FROM user_sessions WHERE user_id=%s", (owner["id"],)).fetchone()["n"] == 0


@pytest.mark.parametrize("newer_state",["pending","completed","session","blocked"])
def test_compensation_preserves_authority_acquired_after_signup_rollback(
    remediation_env,monkeypatch,newer_state,
):
    env = remediation_env
    owner = env.user()
    if newer_state == "session":
        env.login(owner)
    elif newer_state == "blocked":
        with env.db() as db:
            db.execute("UPDATE users SET is_blocked=true WHERE id=%s",(owner["id"],))
    elif newer_state == "pending":
        credential_changes.begin_password_change(owner["id"],owner["auth_id"],"password_reset")
    else:
        credential_changes.execute_password_change(
            owner["id"],owner["auth_id"],"replacement-password","password_reset",lambda *_:None,
        )
    provider_deletions = []
    monkeypatch.setattr(auth_routes,"supabase_signup_identity_is_owned",lambda *_:True)
    monkeypatch.setattr(auth_routes,"supabase_delete_created_signup_user",
                        lambda *args: provider_deletions.append(args) or True)
    assert auth_routes._compensate_signup_identity(owner["auth_id"],"signup.test") is False
    assert provider_deletions == []
    with env.db() as db:
        assert db.execute("SELECT id FROM users WHERE id=%s",(owner["id"],)).fetchone() is not None
        assert db.execute("SELECT id FROM auth.users WHERE id=%s",(owner["auth_id"],)).fetchone() is not None
