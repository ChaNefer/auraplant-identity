# Migrations

Schema is defined in `identity_core.models`. For local/dev:

```bash
python -c "from identity_core.db import make_engine, create_all; create_all(make_engine())"
```

Or run the bootstrap script:

```bash
python -m migrations.env
```

`versions/001_initial.py` documents the initial tables (`users`, `email_tokens`, `login_logs`).
