"""Phase 0: extract notification triggers and component configurations.

Extracts:
1. Standard frontend notification component config (Notification.jsx, NotificationBell.jsx).
2. Ad-hoc frontend notification/toast mechanisms and their configurations.
3. Every trigger/usage in the frontend (Notification, custom toast, window.alert).
4. Backend notification writers (shared/notifications.py, DB triggers, API endpoints).
5. All backend events that call notify() or notify_admins().
"""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend-react" / "src"
BACKEND = ROOT / "backend"
OUT = ROOT / "inventory" / "notifications.json"

# 1. Standard Notification Config
standard_config = {
    "standard_component": "frontend-react/src/components/common/Notification.jsx",
    "css_selector": ".app-notification",
    "css_file": "frontend-react/src/styles/pages/auth.css",
    "position": "fixed; top: 22px; right: 22px",
    "duration_ms": {"success": 5000, "error": 8000, "info": 8000},
    "dismissible": True,
    "has_close_button": True,
    "notes": "Requires onClose prop to function. If caller omits onClose, button click does nothing and auto-close timer fails.",
}

notification_bell_config = {
    "component": "frontend-react/src/components/common/NotificationBell.jsx",
    "poll_interval_ms": 45000,
    "fetch_endpoint": "GET /api/notifications",
    "read_endpoint": "POST /api/notifications/<id>/read",
    "read_all_endpoint": "POST /api/notifications/read-all",
    "used_in": [
        "frontend-react/src/components/client/ClientLayout.jsx",
        "frontend-react/src/components/everyday/EverydayLayout.jsx",
        "frontend-react/src/components/transporter/TransporterLayout.jsx",
    ],
}

# 2. Frontend Triggers & Usages
frontend_triggers = []

for f in sorted(SRC.rglob("*")):
    if f.suffix not in {".js", ".jsx"} or ".test." in f.name:
        continue
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    content = f.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    # <Notification ... />
    for m in re.finditer(r'<Notification\b([^>]*)/?>', content):
        ln = content.count("\n", 0, m.start()) + 1
        props = m.group(1)
        has_on_close = "onClose" in props
        frontend_triggers.append({
            "type": "standard_notification_component",
            "file": rel,
            "line": ln,
            "has_on_close": has_on_close,
            "snippet": lines[ln - 1].strip(),
            "inconsistent": not has_on_close,
            "issue": "Missing onClose callback; notification cannot be dismissed manually and auto-close fails" if not has_on_close else None
        })

    # showToast(...)
    for m in re.finditer(r'\bshowToast\(([^)]*)\)', content):
        ln = content.count("\n", 0, m.start()) + 1
        frontend_triggers.append({
            "type": "custom_toast",
            "file": rel,
            "line": ln,
            "args": m.group(1).strip()[:100],
            "snippet": lines[ln - 1].strip(),
        })

    # window.alert or alert(...)
    for m in re.finditer(r'\b(?:window\.)?alert\(([^)]*)\)', content):
        ln = content.count("\n", 0, m.start()) + 1
        frontend_triggers.append({
            "type": "window_alert",
            "file": rel,
            "line": ln,
            "args": m.group(1).strip()[:100],
            "snippet": lines[ln - 1].strip(),
            "inconsistent": True,
            "issue": "Raw browser alert() blocks UI thread and violates design system"
        })

# 3. Ad-hoc toast configurations found in frontend
ad_hoc_configs = [
    {
        "file": "frontend-react/src/pages/transporter/settings.jsx",
        "function": "showToast",
        "position": "fixed; top: 92px; right: 28px (.transporter-settings__toast)",
        "duration_ms": 3500,
        "dismissible": False,
        "has_close_button": False,
        "issue": "Ad-hoc toast instead of Notification component; cannot be dismissed manually"
    },
    {
        "file": "frontend-react/src/pages/transporter/truck_configuration.jsx",
        "function": "showToast",
        "position": "fixed bottom-6 right-6 (inline Tailwind)",
        "duration_ms": 3500,
        "dismissible": False,
        "has_close_button": False,
        "issue": "Ad-hoc toast instead of Notification component; cannot be dismissed manually"
    },
    {
        "file": "frontend-react/src/pages/transporter/ac_history.jsx",
        "function": "showToast",
        "position": "fixed; bottom: 24; right: 24 (inline style)",
        "duration_ms": 3000,
        "dismissible": False,
        "has_close_button": False,
        "issue": "Ad-hoc toast instead of Notification component; cannot be dismissed manually"
    },
    {
        "file": "frontend-react/src/pages/transporter/future_features/*.jsx",
        "function": "showToast",
        "position": "fixed; bottom: 24; right: 24 (inline style)",
        "duration_ms": 2500,
        "dismissible": False,
        "has_close_button": False,
        "issue": "Ad-hoc toast in unimported future_features modules; cannot be dismissed manually"
    }
]

# 4. Backend Notification Triggers
backend_triggers = []
for f in sorted(BACKEND.rglob("*.py")):
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    if "/tests/" in rel or "/scripts/" in rel or "__pycache__" in rel:
        continue
    content = f.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    for m in re.finditer(r'\b(notify|notify_admins)\s*\(([^)]*)\)', content):
        ln = content.count("\n", 0, m.start()) + 1
        fn_name = m.group(1)
        args = [a.strip() for a in m.group(2).split(",")]
        backend_triggers.append({
            "function": fn_name,
            "file": rel,
            "line": ln,
            "args_snippet": m.group(2).strip()[:140],
            "snippet": lines[ln - 1].strip(),
        })

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({
    "standard_config": standard_config,
    "notification_bell_config": notification_bell_config,
    "ad_hoc_toast_configs": ad_hoc_configs,
    "frontend_trigger_count": len(frontend_triggers),
    "frontend_triggers": frontend_triggers,
    "backend_trigger_count": len(backend_triggers),
    "backend_triggers": backend_triggers,
}, indent=2), encoding="utf-8")

print(f"Extracted {len(frontend_triggers)} frontend triggers and {len(backend_triggers)} backend triggers.")
