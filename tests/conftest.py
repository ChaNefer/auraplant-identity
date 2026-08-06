from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from identity_core.db import create_all, make_engine, make_session_factory
from identity_core.mailer import MemoryMailer
from identity_core.service import IdentityService


@pytest.fixture()
def engine():
    eng = make_engine("sqlite:///:memory:")
    create_all(eng)
    return eng


@pytest.fixture()
def db_session(engine) -> Session:
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def mailer() -> MemoryMailer:
    return MemoryMailer()


@pytest.fixture()
def svc(db_session, mailer) -> IdentityService:
    return IdentityService(db_session, mailer=mailer, base_url="http://test")
