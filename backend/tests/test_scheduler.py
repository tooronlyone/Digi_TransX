"""Scheduler startup-safety tests (FIX 8).

No real timers are awaited: jobs are registered with far-future first-run times
(10 min / 30 min / daily), so start_scheduler() returns immediately and the
scheduler is shut down before any job fires.
"""

import importlib

import pytest


@pytest.fixture
def scheduler_mod(monkeypatch):
    """Import the scheduler module with a clean per-test singleton, and always
    shut down any instance the test started."""
    monkeypatch.delenv("DIGITRANSX_ENABLE_SCHEDULER", raising=False)
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    import scheduler as scheduler_mod
    importlib.reload(scheduler_mod)
    scheduler_mod._scheduler = None
    yield scheduler_mod
    inst = scheduler_mod._scheduler
    if inst is not None:
        try:
            inst.shutdown(wait=False)
        except Exception:
            pass
    scheduler_mod._scheduler = None


def test_scheduler_enabled_default(scheduler_mod):
    assert scheduler_mod.scheduler_enabled() is True


def test_scheduler_disabled_via_env(scheduler_mod, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "0")
    assert scheduler_mod.scheduler_enabled() is False
    assert scheduler_mod.start_scheduler() is None
    assert scheduler_mod._scheduler is None


def test_scheduler_singleton_reuse_no_duplicate_jobs(scheduler_mod):
    s1 = scheduler_mod.start_scheduler()
    assert s1 is not None and s1.running
    # All three production jobs registered exactly once.
    assert {j.id for j in s1.get_jobs()} == {
        "process_overdue_confirmations_interval",
        "process_payments_daily",
        "apply_penalties_interval",
    }
    # A repeated call reuses the SAME instance — no second scheduler, no dup jobs.
    s2 = scheduler_mod.start_scheduler()
    assert s2 is s1
    assert len(s2.get_jobs()) == 3


def test_scheduler_skipped_in_reloader_parent(scheduler_mod, monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)   # the reloader PARENT
    assert scheduler_mod._in_reloader_parent() is True
    assert scheduler_mod.start_scheduler() is None
    assert scheduler_mod._scheduler is None


def test_scheduler_runs_in_reloader_child(scheduler_mod, monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")          # the serving CHILD
    assert scheduler_mod._in_reloader_parent() is False
    s = scheduler_mod.start_scheduler()
    assert s is not None and s.running
