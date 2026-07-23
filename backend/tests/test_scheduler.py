"""Scheduler startup-safety tests (FIX 8 + FIX A).

No real timers are awaited: jobs are registered with far-future first-run times
(10 min / 30 min / daily), so start_scheduler() returns immediately and any
started scheduler is shut down before a job fires.
"""

import importlib
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
THREE_JOB_IDS = {
    "process_overdue_confirmations_interval",
    "process_payments_daily",
    "apply_penalties_interval",
}


@pytest.fixture
def sched(monkeypatch):
    """Import the scheduler module with a clean per-test singleton + env, and
    always shut down any instance the test started."""
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


# ---- env truth parsing ----------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " On ", "Yes"])
def test_env_flag_true_spellings(sched, monkeypatch, value):
    monkeypatch.setenv("X_FLAG", value)
    assert sched.env_flag("X_FLAG", default=False) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  ", "FALSE", "Off"])
def test_env_flag_false_spellings(sched, monkeypatch, value):
    monkeypatch.setenv("X_FLAG", value)
    assert sched.env_flag("X_FLAG", default=True) is False


def test_env_flag_absent_uses_default(sched, monkeypatch):
    monkeypatch.delenv("X_FLAG", raising=False)
    assert sched.env_flag("X_FLAG", default=False) is False
    assert sched.env_flag("X_FLAG", default=True) is True


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("yes", True), ("on", True), ("ON", True),
    ("0", False), ("false", False), ("no", False), ("off", False), ("", False),
])
def test_scheduler_enabled_parsing(sched, monkeypatch, value, expected):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", value)
    assert sched.scheduler_enabled() is expected


# ---- default OFF: web import must not start jobs --------------------------

def test_unset_flag_does_not_start_scheduler(sched):
    assert sched.scheduler_enabled() is False          # default OFF
    assert sched.start_scheduler() is None
    assert sched._scheduler is None


def test_app_import_path_does_not_auto_start(sched):
    """The web-app import path calls start_scheduler() (no force). Prove (a) the
    default-off gate makes that a no-op, and (b) app.py uses exactly that call."""
    assert sched.start_scheduler() is None and sched._scheduler is None
    app_src = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
    assert "start_scheduler()" in app_src            # gated, no force
    assert "start_scheduler(force=True)" not in app_src


# ---- Werkzeug reloader detection uses real truth parsing ------------------

def test_flask_debug_zero_is_not_reloader_parent(sched, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "1")
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert sched._in_reloader_parent() is False
    s = sched.start_scheduler()                        # must START (0 != debug)
    assert s is not None and s.running


def test_flask_debug_false_is_not_reloader_parent(sched, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "1")
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    assert sched._in_reloader_parent() is False
    assert sched.start_scheduler() is not None


def test_true_debug_parent_is_skipped(sched, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "1")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)   # the parent
    assert sched._in_reloader_parent() is True
    assert sched.start_scheduler() is None


def test_true_debug_child_runs(sched, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "1")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")          # the serving child
    assert sched._in_reloader_parent() is False
    assert sched.start_scheduler() is not None


# ---- singleton reuse + dedicated worker -----------------------------------

def test_repeated_starts_reuse_one_scheduler(sched, monkeypatch):
    monkeypatch.setenv("DIGITRANSX_ENABLE_SCHEDULER", "1")
    s1 = sched.start_scheduler()
    assert s1 is not None and s1.running
    assert {j.id for j in s1.get_jobs()} == THREE_JOB_IDS
    s2 = sched.start_scheduler()
    assert s2 is s1 and len(s2.get_jobs()) == 3         # no duplicate jobs


def test_dedicated_worker_force_starts_all_three_jobs(sched):
    # Flag is UNSET (default off). The dedicated worker forces the single owner.
    assert sched.scheduler_enabled() is False
    s = sched.start_scheduler(force=True)
    assert s is not None and s.running
    assert {j.id for j in s.get_jobs()} == THREE_JOB_IDS


def test_force_bypasses_reloader_parent(sched, monkeypatch):
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    s = sched.start_scheduler(force=True)
    assert s is not None and s.running


def test_run_scheduler_module_importable(sched):
    # The dedicated worker entry point imports cleanly (does not run main()).
    import importlib
    mod = importlib.import_module("scripts.run_scheduler")
    assert hasattr(mod, "main")
