"""Email verification and password-reset tokens."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from identity_core.models import EmailToken, User

PURPOSE_VERIFY = "verify"
PURPOSE_RESET = "reset"
DEFAULT_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_token(
    session: Session,
    user: User,
    purpose: str,
    *,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> EmailToken:
    if purpose not in (PURPOSE_VERIFY, PURPOSE_RESET):
        raise ValueError(f"Unknown token purpose: {purpose}")

    # Invalidate prior unused tokens of same purpose
    existing = session.scalars(
        select(EmailToken).where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
    ).all()
    for row in existing:
        row.used_at = _utcnow()

    token = EmailToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose=purpose,
        expires_at=_utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(token)
    session.flush()
    return token


def consume_token(session: Session, raw_token: str, purpose: str) -> EmailToken:
    row = session.scalar(
        select(EmailToken).where(
            EmailToken.token == raw_token,
            EmailToken.purpose == purpose,
        )
    )
    if row is None:
        raise ValueError("Invalid or expired token")
    if row.used_at is not None:
        raise ValueError("Token already used")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _utcnow():
        raise ValueError("Invalid or expired token")
    row.used_at = _utcnow()
    session.flush()
    return row
