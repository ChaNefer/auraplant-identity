"""Create identity-core tables from models (Alembic-lite bootstrap)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from identity_core.db import create_all, make_engine  # noqa: E402


def main() -> None:
    url = os.environ.get("DATABASE_URL", "sqlite:///identity.db")
    engine = make_engine(url)
    create_all(engine)
    print(f"Created tables on {url}")


if __name__ == "__main__":
    main()
