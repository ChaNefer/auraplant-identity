"""Initial identity-core schema.

Revision ID: 001_initial
Creates: users, email_tokens, login_logs
"""

REVISION = "001_initial"
DOWN_REVISION = None

TABLES = {
    "users": [
        "id UUID/TEXT PK",
        "email TEXT UNIQUE NULL",
        "password_hash TEXT NULL",
        "name TEXT NULL",
        "avatar_url TEXT NULL",
        "is_active BOOL NOT NULL DEFAULT false",
        "email_confirmed_at TIMESTAMPTZ NULL",
        "google_id TEXT UNIQUE NULL",
        "twitter_id TEXT UNIQUE NULL",
        "failed_login_count INT NOT NULL DEFAULT 0",
        "locked_until TIMESTAMPTZ NULL",
        "created_at TIMESTAMPTZ NOT NULL",
        "updated_at TIMESTAMPTZ NOT NULL",
    ],
    "email_tokens": [
        "id UUID/TEXT PK",
        "user_id FK users",
        "token TEXT UNIQUE NOT NULL",
        "purpose TEXT NOT NULL  -- verify | reset",
        "expires_at TIMESTAMPTZ NOT NULL",
        "used_at TIMESTAMPTZ NULL",
        "created_at TIMESTAMPTZ NOT NULL",
    ],
    "login_logs": [
        "id UUID/TEXT PK",
        "user_id FK users NULL",
        "ip TEXT NULL",
        "user_agent TEXT NULL",
        "success BOOL NOT NULL",
        "created_at TIMESTAMPTZ NOT NULL",
    ],
}


def upgrade(engine) -> None:
    from identity_core.db import create_all

    create_all(engine)


def downgrade(engine) -> None:
    from identity_core.models import Base

    Base.metadata.drop_all(engine)
