# identity-core (MonoIdentity)

Minimal, **service-first** identity library extracted from Science40 / research-4.0.

- Email register / verify / login
- Forgot / reset password (anti-enumeration)
- Google + X/Twitter OAuth upsert
- Optional Flask Blueprint + Flask-Login adapter
- **No** RBAC, 2FA, org/project, ELIXIR, LinkedIn, ORCID

## Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"         # core + Flask + pytest
# or library-only:
pip install -e .
```

## Library usage (no Flask)

```python
from identity_core.db import make_engine, create_all, make_session_factory
from identity_core.mailer import MemoryMailer
from identity_core.service import IdentityService

engine = make_engine("sqlite:///identity.db")
create_all(engine)
session = make_session_factory(engine)()
svc = IdentityService(session, mailer=MemoryMailer(), base_url="http://localhost:5000")

user = svc.create_user("a@example.com", "password123", name="Ada")
# read verify token from DB / mailer, then:
# svc.verify_email(token)
# svc.authenticate("a@example.com", "password123")

result = svc.upsert_oauth("twitter", "tw-1", name="Bird")
if not result.profile_complete:
    svc.complete_profile(result.user.id, "bird@example.com")
```

Public service surface:

| Function | Role |
|---|---|
| `create_user` | inactive user + verify token email |
| `verify_email` | activate |
| `authenticate` | email/password → `User \| None` (lockout aware) |
| `start_password_reset` | always OK (anti-enum) |
| `reset_password` | set new password (min 8) |
| `upsert_oauth` | → `AuthResult(user, profile_complete)` |
| `is_profile_complete` / `complete_profile` | force email completion (X) |
| `get_user` / `get_user_by_email` | lookups |

## Optional Flask adapter

```python
from flask import Flask
from identity_core.flask_ext import register_blueprint

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me"
register_blueprint(app)   # mounts /auth/*
```

Endpoints: `POST /auth/register`, `GET /auth/verify-email/:token`, `POST /auth/login|logout`, `POST /auth/forgot-password`, `POST /auth/reset-password/:token`, `GET|PATCH /auth/me`, Google/X OAuth start+callback.

Importing `identity_core` or `identity_core.service` **does not** require Flask.

## Env

Copy `.env.example`:

```
DATABASE_URL=
SECRET_KEY=
BASE_URL=
SENDGRID_API_KEY=          # or MAIL_* SMTP
SENDGRID_FROM_EMAIL=
MAIL_SERVER=
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
TWITTER_CLIENT_ID=
TWITTER_CLIENT_SECRET=
TWITTER_REDIRECT_URI=
```

## Tests

```bash
pytest -q
```

Smoke covered: register → verify → login → me → logout (service + Flask).

## Schema

See `migrations/versions/001_initial.py` and `src/identity_core/models.py`.

Bootstrap tables:

```bash
python -m migrations.env
```
