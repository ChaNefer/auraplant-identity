"""Google OAuth helpers. Requires optional ``requests`` (flask extra)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def _require_requests():
    try:
        import requests  # noqa: WPS433
    except ImportError as exc:
        raise ImportError("Install identity-core[flask] for OAuth helpers") from exc
    return requests


def google_config() -> dict[str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or ""
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or ""
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI") or ""
    if not client_id or not client_secret or not redirect_uri:
        raise RuntimeError("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI required")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def build_authorize_url(state: str, *, scope: str = "openid email profile") -> str:
    cfg = google_config()
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": scope,
        "access_type": "online",
        "include_granted_scopes": "true",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict[str, Any]:
    requests = _require_requests()
    cfg = google_config()
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"],
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    requests = _require_requests()
    resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def profile_from_userinfo(info: dict[str, Any]) -> dict[str, str | None]:
    return {
        "provider_user_id": str(info.get("id") or ""),
        "email": info.get("email"),
        "name": info.get("name"),
        "avatar": info.get("picture"),
    }
