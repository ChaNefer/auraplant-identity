"""Smoke: register → verify → login → me → logout (+ reset)."""

from __future__ import annotations

from sqlalchemy import select

from identity_core.models import EmailToken, User
from identity_core.service import AuthRejected, IdentityService, is_profile_complete
from identity_core.tokens import PURPOSE_VERIFY


def _latest_token(session, purpose: str) -> EmailToken:
    return session.scalars(
        select(EmailToken).where(EmailToken.purpose == purpose).order_by(EmailToken.created_at.desc())
    ).first()


def test_register_verify_login_me_logout(svc: IdentityService, db_session, mailer):
    user = svc.create_user("alice@example.com", "password123", name="Alice")
    assert user.is_active is False
    assert user.email_confirmed_at is None
    assert len(mailer.outbox) == 1
    assert "verify-email" in mailer.outbox[0]["html"]

    # login before verify must fail
    try:
        svc.authenticate("alice@example.com", "password123")
        assert False, "expected AuthRejected"
    except AuthRejected:
        pass

    token = _latest_token(db_session, PURPOSE_VERIFY)
    assert token is not None
    verified = svc.verify_email(token.token)
    assert verified.is_active is True
    assert verified.email_confirmed_at is not None

    authed = svc.authenticate("alice@example.com", "password123")
    assert authed is not None
    assert authed.id == user.id

    me = svc.get_user(authed.id)
    assert me is not None
    assert me.email == "alice@example.com"
    assert is_profile_complete(me) is True

    updated = svc.update_me(me.id, name="Alice Updated", avatar_url="https://example.com/a.png")
    assert updated.name == "Alice Updated"
    assert updated.avatar_url == "https://example.com/a.png"

    # "logout" is session-layer; service has no server session — assert user still fetchable
    assert svc.get_user(me.id) is not None


def test_forgot_reset_password_anti_enum(svc: IdentityService, db_session, mailer):
    svc.create_user("bob@example.com", "password123")
    token = _latest_token(db_session, PURPOSE_VERIFY)
    svc.verify_email(token.token)
    mailer.outbox.clear()

    # unknown email — no error, no mail
    svc.start_password_reset("nobody@example.com")
    assert mailer.outbox == []

    svc.start_password_reset("bob@example.com")
    assert len(mailer.outbox) == 1
    assert "reset-password" in mailer.outbox[0]["html"]

    from identity_core.tokens import PURPOSE_RESET

    reset_token = _latest_token(db_session, PURPOSE_RESET)
    user = svc.reset_password(reset_token.token, "newpassword99")
    assert svc.authenticate("bob@example.com", "newpassword99").id == user.id
    assert svc.authenticate("bob@example.com", "password123") is None


def test_password_min_length(svc: IdentityService):
    try:
        svc.create_user("short@example.com", "short")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "8" in str(exc)


def test_oauth_google_complete_and_twitter_incomplete(svc: IdentityService):
    google = svc.upsert_oauth(
        "google",
        "g-123",
        email="g@example.com",
        name="G User",
        avatar="https://example.com/g.png",
    )
    assert google.profile_complete is True
    assert google.user.is_active is True
    assert google.user.google_id == "g-123"
    assert google.user.password_hash is None

    twitter = svc.upsert_oauth("twitter", "tw-999", email=None, name="X User")
    assert twitter.profile_complete is False
    assert twitter.user.twitter_id == "tw-999"
    assert twitter.user.email is None
    assert twitter.user.is_active is True

    completed = svc.complete_profile(twitter.user.id, "xuser@example.com", name="X User")
    assert completed.user.email == "xuser@example.com"
    assert completed.profile_complete is True
    # email change requires verify
    assert completed.user.is_active is False


def test_module_level_api(db_session, mailer):
    from identity_core import service as api

    user = api.create_user(db_session, "mod@example.com", "password123", mailer=mailer, base_url="http://test")
    token = db_session.scalars(select(EmailToken).where(EmailToken.user_id == user.id)).first()
    api.verify_email(db_session, token.token)
    assert api.authenticate(db_session, "mod@example.com", "password123") is not None
    assert api.get_user_by_email(db_session, "mod@example.com").id == user.id
