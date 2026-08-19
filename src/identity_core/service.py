"""Framework-agnostic identity service — main public contract."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from identity_core.mailer import EmailSender, LoggingMailer
from identity_core.models import LoginLog, User
from identity_core.passwords import hash_password, validate_password, verify_password
from identity_core.tokens import PURPOSE_RESET, PURPOSE_VERIFY, consume_token, create_token

Provider = Literal["google", "twitter"]

LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_MINUTES = 15
LOCKOUT_DURATION_MINUTES = 30

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def is_profile_complete(user: User) -> bool:
    """Profile is complete when a real email is present."""
    email = (user.email or "").strip()
    return bool(email) and bool(_EMAIL_RE.match(email))


class IdentityError(Exception):
    """Base error for identity operations."""


class ConflictError(IdentityError):
    pass


class NotFoundError(IdentityError):
    pass


class AuthRejected(IdentityError):
    pass


class LockedError(AuthRejected):
    pass


@dataclass
class AuthResult:
    user: User
    profile_complete: bool


class IdentityService:
    """Session-bound identity operations. No Flask imports."""

    def __init__(
        self,
        session: Session,
        *,
        mailer: EmailSender | None = None,
        base_url: str | None = None,
        record_login_logs: bool = True,
    ) -> None:
        self.session = session
        self.mailer = mailer or LoggingMailer()
        self.base_url = (base_url or os.environ.get("BASE_URL") or "http://localhost:5000").rstrip("/")
        self.record_login_logs = record_login_logs

    # ----- queries -----

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        norm = _normalize_email(email)
        if not norm:
            return None
        return self.session.scalar(select(User).where(func.lower(User.email) == norm))

    # ----- register / verify -----

    def create_user(
        self,
        email: str,
        password: str | None = None,
        name: str | None = None,
        *,
        send_email: bool = True,
    ) -> User:
        norm = _normalize_email(email)
        if not norm or not _EMAIL_RE.match(norm):
            raise IdentityError("Valid email is required")
        if self.get_user_by_email(norm):
            raise ConflictError("Email already registered")

        user = User(
            email=norm,
            name=(name or "").strip() or None,
            is_active=False,
            password_hash=hash_password(password) if password else None,
        )
        if password:
            validate_password(password)

        self.session.add(user)
        self.session.flush()

        token = create_token(self.session, user, PURPOSE_VERIFY)
        self.session.commit()

        if send_email:
            link = f"{self.base_url}/auth/verify-email/{token.token}"
            try:
                self.mailer.send(
                    norm,
                    "Confirm your email",
                    f"<p>Confirm your account:</p><p><a href=\"{link}\">{link}</a></p>",
                )
            except Exception as exc:
                raise IdentityError(
                    "Nie udało się wysłać maila weryfikacyjnego. Sprawdź SendGrid."
                ) from exc
        return user

    def verify_email(self, token: str) -> User:
        row = consume_token(self.session, token, PURPOSE_VERIFY)
        user = self.get_user(row.user_id)
        if user is None:
            raise NotFoundError("User not found")
        user.is_active = True
        user.email_confirmed_at = _utcnow()
        self.session.commit()
        return user

    # ----- authenticate / lockout -----

    def authenticate(
        self,
        email: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> User | None:
        user = self.get_user_by_email(email)
        if user is None:
            self._log_login(None, ip, user_agent, success=False)
            self.session.commit()
            return None

        if user.is_locked():
            self._log_login(user.id, ip, user_agent, success=False)
            self.session.commit()
            raise LockedError("Account temporarily locked")

        if not user.is_active or user.email_confirmed_at is None:
            self._register_failure(user)
            self._log_login(user.id, ip, user_agent, success=False)
            self.session.commit()
            raise AuthRejected("Email not confirmed")

        if not verify_password(user.password_hash, password):
            self._register_failure(user)
            self._log_login(user.id, ip, user_agent, success=False)
            self.session.commit()
            return None

        user.failed_login_count = 0
        user.locked_until = None
        self._log_login(user.id, ip, user_agent, success=True)
        self.session.commit()
        return user

    def _register_failure(self, user: User) -> None:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= LOCKOUT_THRESHOLD:
            user.locked_until = _utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            user.failed_login_count = 0

    def _log_login(
        self,
        user_id: str | None,
        ip: str | None,
        user_agent: str | None,
        *,
        success: bool,
    ) -> None:
        if not self.record_login_logs:
            return
        self.session.add(
            LoginLog(user_id=user_id, ip=ip, user_agent=user_agent, success=success)
        )

    # ----- password reset -----

    def start_password_reset(self, email: str) -> None:
        """Always succeeds (anti-enumeration)."""
        user = self.get_user_by_email(email)
        if user is None or not user.email:
            return
        token = create_token(self.session, user, PURPOSE_RESET)
        self.session.commit()
        link = f"{self.base_url}/auth/reset-password/{token.token}"
        self.mailer.send(
            user.email,
            "Reset your password",
            f"<p>Reset your password:</p><p><a href=\"{link}\">{link}</a></p>",
        )

    def reset_password(self, token: str, new_password: str) -> User:
        validate_password(new_password)
        row = consume_token(self.session, token, PURPOSE_RESET)
        user = self.get_user(row.user_id)
        if user is None:
            raise NotFoundError("User not found")
        user.password_hash = hash_password(new_password)
        user.is_active = True
        if user.email_confirmed_at is None:
            user.email_confirmed_at = _utcnow()
        user.failed_login_count = 0
        user.locked_until = None
        self.session.commit()
        if user.email:
            self.mailer.send(
                user.email,
                "Password changed",
                "<p>Your password was changed. If this was not you, contact support.</p>",
            )
        return user

    # ----- OAuth -----

    def upsert_oauth(
        self,
        provider: Provider,
        provider_user_id: str,
        email: str | None = None,
        name: str | None = None,
        avatar: str | None = None,
    ) -> AuthResult:
        if provider not in ("google", "twitter"):
            raise IdentityError(f"Unsupported provider: {provider}")
        if not provider_user_id:
            raise IdentityError("provider_user_id is required")

        id_field = "google_id" if provider == "google" else "twitter_id"
        norm_email = _normalize_email(email)

        user = self.session.scalar(select(User).where(getattr(User, id_field) == provider_user_id))
        if user is None and norm_email:
            user = self.get_user_by_email(norm_email)

        if user is None:
            user = User(
                email=norm_email,
                name=(name or "").strip() or None,
                avatar_url=avatar,
                password_hash=None,
                # Provider already authenticated the user; email may still be missing (X).
                is_active=True,
                email_confirmed_at=_utcnow() if norm_email else None,
            )
            setattr(user, id_field, provider_user_id)
            self.session.add(user)
        else:
            setattr(user, id_field, provider_user_id)
            if norm_email and not user.email:
                other = self.get_user_by_email(norm_email)
                if other and other.id != user.id:
                    raise ConflictError("Email already registered")
                user.email = norm_email
            if norm_email and user.email_confirmed_at is None:
                user.email_confirmed_at = _utcnow()
            user.is_active = True
            if name and not user.name:
                user.name = name.strip()
            if avatar:
                user.avatar_url = avatar

        self.session.commit()
        return AuthResult(user=user, profile_complete=is_profile_complete(user))

    def complete_profile(
        self,
        user_id: str,
        email: str,
        name: str | None = None,
        *,
        send_verification: bool = True,
    ) -> AuthResult:
        user = self.get_user(user_id)
        if user is None:
            raise NotFoundError("User not found")
        norm = _normalize_email(email)
        if not norm or not _EMAIL_RE.match(norm):
            raise IdentityError("Valid email is required")
        existing = self.get_user_by_email(norm)
        if existing and existing.id != user.id:
            raise ConflictError("Email already registered")

        email_changed = user.email != norm
        user.email = norm
        if name is not None:
            user.name = name.strip() or None

        if email_changed or user.email_confirmed_at is None:
            user.is_active = False
            user.email_confirmed_at = None
            token = create_token(self.session, user, PURPOSE_VERIFY)
            self.session.commit()
            if send_verification:
                link = f"{self.base_url}/auth/verify-email/{token.token}"
                self.mailer.send(
                    norm,
                    "Confirm your email",
                    f"<p>Confirm your account:</p><p><a href=\"{link}\">{link}</a></p>",
                )
        else:
            self.session.commit()

        return AuthResult(user=user, profile_complete=is_profile_complete(user))

    def update_me(
        self,
        user_id: str,
        *,
        name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        user = self.get_user(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if name is not None:
            user.name = name.strip() or None
        if avatar_url is not None:
            user.avatar_url = avatar_url.strip() or None
        self.session.commit()
        return user


# Module-level helpers matching the brief surface --------------------------

def create_user(session: Session, email: str, password: str | None = None, name: str | None = None, **kw) -> User:
    return IdentityService(session, **{k: v for k, v in kw.items() if k in ("mailer", "base_url")}).create_user(
        email, password, name
    )


def verify_email(session: Session, token: str) -> User:
    return IdentityService(session).verify_email(token)


def authenticate(session: Session, email: str, password: str) -> User | None:
    return IdentityService(session).authenticate(email, password)


def start_password_reset(session: Session, email: str, **kw) -> None:
    IdentityService(session, **{k: v for k, v in kw.items() if k in ("mailer", "base_url")}).start_password_reset(email)


def reset_password(session: Session, token: str, new_password: str) -> User:
    return IdentityService(session).reset_password(token, new_password)


def upsert_oauth(
    session: Session,
    provider: Provider,
    provider_user_id: str,
    email: str | None = None,
    name: str | None = None,
    avatar: str | None = None,
) -> AuthResult:
    return IdentityService(session).upsert_oauth(provider, provider_user_id, email, name, avatar)


def get_user(session: Session, user_id: str) -> User | None:
    return IdentityService(session).get_user(user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return IdentityService(session).get_user_by_email(email)
