"""Local runner for AuraPlant work against MonoIdentity.

Uses MemoryMailer so verify/reset links are available without SMTP.
Dev-only helper: GET /auth/dev/last-email
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from flask import Flask, jsonify  # noqa: E402
from identity_core.flask_ext import register_blueprint  # noqa: E402
from identity_core.mailer import MemoryMailer  # noqa: E402
import identity_core.routes as routes_mod  # noqa: E402

mailer = MemoryMailer()
routes_mod.mailer_from_env = lambda: mailer  # type: ignore[assignment]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
register_blueprint(app)


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "MonoIdentity", "module": "identity-core"})


@app.get("/auth/dev/last-email")
def last_email():
    """Return last MemoryMailer message (verify / reset links in html)."""
    if os.environ.get("NODE_ENV") == "production" or os.environ.get("FLASK_ENV") == "production":
        return jsonify({"error": "Not found"}), 404
    if not mailer.outbox:
        return jsonify({"error": "No emails yet"}), 404
    return jsonify(mailer.outbox[-1])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"MonoIdentity listening on http://127.0.0.1:{port}")
    print("Auth: POST /auth/register | /auth/login | GET /auth/me")
    print("Dev:  GET /auth/dev/last-email  (verify link without SMTP)")
    app.run(host="127.0.0.1", port=port, debug=True)
