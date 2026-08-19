"""Production WSGI entry for AuraPlant Identity on Render.

Uses env mailer (SendGrid / SMTP). No dev mailbox routes.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify
from identity_core.flask_ext import register_blueprint
from werkzeug.middleware.proxy_fix import ProxyFix


def normalize_database_url(url: str) -> str:
    raw = url.strip()
    if not raw or raw.startswith("sqlite"):
        return raw
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+psycopg2" not in raw and "+psycopg" not in raw:
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in raw:
        raw = f"{raw}{'&' if '?' in raw else '?'}sslmode=require"
    return raw


def create_app() -> Flask:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        os.environ["DATABASE_URL"] = normalize_database_url(database_url)

    secret = os.environ.get("SECRET_KEY", "").strip()
    if not secret:
        raise RuntimeError("SECRET_KEY is required")

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SECRET_KEY=secret,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("RENDER") == "true",
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("RENDER") == "true",
    )
    register_blueprint(app)

    @app.get("/health")
    def health():
        return jsonify(
            {"ok": True, "service": "auraplant-identity", "module": "identity-core"}
        )

    return app


app = create_app()
