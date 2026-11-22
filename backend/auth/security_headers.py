"""Global HTTP security headers and nonce-bound CSP installation."""

import os
import secrets

from flask import current_app, g, has_request_context, request

from shared.rate_limit import trusted_proxy_hops


API_DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"


def ensure_csp_nonce():
    """Return a cryptographic per-request CSP nonce for HTML bootstrap scripts."""
    if not has_request_context():
        return ""
    nonce = getattr(g, "_dtx_csp_nonce", None)
    if not nonce:
        nonce = secrets.token_urlsafe(24)
        g._dtx_csp_nonce = nonce
    return nonce


def build_html_csp(nonce):
    """Build strict SPA Content-Security-Policy without unsafe-inline scripts."""
    script_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
        "connect-src 'self' https://nominatim.openstreetmap.org; "
        "frame-src 'self' https://www.openstreetmap.org; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )


def _request_uses_https():
    if os.environ.get("DIGITRANSX_FORCE_HSTS", "").strip().lower() == "true":
        return True
    if not has_request_context():
        return False
    if getattr(request, "is_secure", False):
        return True
    hops = trusted_proxy_hops()
    if hops <= 0:
        return False
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").strip()
    if not forwarded_proto:
        return False
    parts = [part.strip().lower() for part in forwarded_proto.split(",") if part.strip()]
    if len(parts) < hops:
        return False
    return parts[-hops] == "https"


def apply_security_headers(response):
    """Attach global security headers while preserving stricter endpoint policies."""
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    if "Content-Security-Policy" not in response.headers:
        mimetype = (response.mimetype or "").lower()
        if mimetype == "text/html":
            response.headers["Content-Security-Policy"] = build_html_csp(ensure_csp_nonce())
        else:
            response.headers["Content-Security-Policy"] = API_DEFAULT_CSP

    if current_app.config.get("SESSION_COOKIE_SECURE") and _request_uses_https():
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    else:
        response.headers.pop("Strict-Transport-Security", None)
    return response


def install_security_headers(app):
    """Register the global security header hook idempotently on a Flask app."""
    if app.extensions.get("dtx_security_headers_installed"):
        return app

    @app.after_request
    def _dtx_apply_security_headers(response):
        return apply_security_headers(response)

    app.extensions["dtx_security_headers_installed"] = True
    return app
