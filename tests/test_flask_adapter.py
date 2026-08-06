"""Optional Flask blueprint smoke (skipped if Flask not installed)."""

from __future__ import annotations

import pytest

flask = pytest.importorskip("flask")
pytest.importorskip("flask_login")

from sqlalchemy import select

from identity_core.db import create_all, make_engine, make_session_factory
from identity_core.flask_ext import register_blueprint
from identity_core.mailer import MemoryMailer
from identity_core.models import EmailToken
from identity_core.tokens import PURPOSE_VERIFY


@pytest.fixture()
def app(monkeypatch):
    engine = make_engine("sqlite:///:memory:")
    create_all(engine)
    factory = make_session_factory(engine)
    mailer = MemoryMailer()

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    # Force MemoryMailer via patching mailer_from_env
    import identity_core.routes as routes_mod

    monkeypatch.setattr(routes_mod, "mailer_from_env", lambda: mailer)

    application = flask.Flask(__name__)
    application.config["SECRET_KEY"] = "test-secret"
    application.config["TESTING"] = True
    register_blueprint(application, session_factory=factory, engine=engine)
    application.extensions["identity_mailer"] = mailer
    application.extensions["identity_factory"] = factory
    return application


def test_http_register_verify_login_me_logout(app):
    client = app.test_client()
    factory = app.extensions["identity_factory"]

    r = client.post("/auth/register", json={"email": "web@example.com", "password": "password123", "name": "Web"})
    assert r.status_code == 201

    session = factory()
    token = session.scalars(select(EmailToken).where(EmailToken.purpose == PURPOSE_VERIFY)).first()
    assert token is not None
    raw = token.token
    session.close()

    r = client.get(f"/auth/verify-email/{raw}")
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "web@example.com"

    client.post("/auth/logout")
    r = client.post("/auth/login", json={"email": "web@example.com", "password": "password123"})
    assert r.status_code == 200

    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "web@example.com"

    r = client.post("/auth/logout")
    assert r.status_code == 200
    r = client.get("/auth/me")
    assert r.status_code in (401, 302)
