"""Unit tests for OAuth upsert without live providers."""

from __future__ import annotations

from identity_core.service import ConflictError, IdentityService, is_profile_complete


def test_google_links_existing_email(svc: IdentityService):
    user = svc.create_user("link@example.com", "password123")
    from identity_core.models import EmailToken
    from sqlalchemy import select

    token = svc.session.scalars(select(EmailToken)).first()
    svc.verify_email(token.token)

    result = svc.upsert_oauth("google", "google-42", email="link@example.com", name="Linked")
    assert result.user.id == user.id
    assert result.user.google_id == "google-42"
    assert result.profile_complete is True


def test_twitter_no_placeholder_email(svc: IdentityService):
    result = svc.upsert_oauth("twitter", "tw-1", name="Bird")
    assert result.user.email is None
    assert "@" not in (result.user.email or "")
    assert is_profile_complete(result.user) is False


def test_email_conflict_on_complete_profile(svc: IdentityService):
    a = svc.upsert_oauth("twitter", "tw-a", name="A")
    svc.upsert_oauth("google", "g-b", email="taken@example.com", name="B")
    try:
        svc.complete_profile(a.user.id, "taken@example.com")
        assert False, "expected ConflictError"
    except ConflictError:
        pass
