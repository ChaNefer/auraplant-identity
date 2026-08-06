"""Twitter/X OAuth 2.0 PKCE helpers. Requires optional ``requests``."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Any
from urllib.parse import urlencode

TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_ME_URL = "https://api.twitter.com/2/users/me"


def _require_requests():
    try:
        import requests
    except ImportError as exc:
        raise ImportError("Install identity-core[flask] for OAuth helpers") from exc
    return requests


def twitter_config() -> dict[str, str]:
    client_id = os.environ.get("TWITTER_CLIENT_ID") or os.environ.get("TWITTER_API_KEY") or ""
    client_secret = os.environ.get("TWITTER_CLIENT_SECRET") or os.environ.get("TWITTER_API_SECRET") or ""
    redirect_uri = os.environ.get("TWITTER_REDIRECT_URI") or ""
    if not client_id or not redirect_uri:
        raise RuntimeError("TWITTER_CLIENT_ID and TWITTER_REDIRECT_URI required")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(state: str, code_challenge: str, *, scope: str = "users.read tweet.read offline.access") -> str:
    cfg = twitter_config()
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{TWITTER_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, code_verifier: str) -> dict[str, Any]:
    requests = _require_requests()
    cfg = twitter_config()
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "code_verifier": code_verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = None
    if cfg["client_secret"]:
        auth = (cfg["client_id"], cfg["client_secret"])
    resp = requests.post(TWITTER_TOKEN_URL, data=data, headers=headers, auth=auth, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_me(access_token: str) -> dict[str, Any]:
    requests = _require_requests()
    resp = requests.get(
        TWITTER_ME_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"user.fields": "id,name,username,profile_image_url"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def profile_from_me(payload: dict[str, Any]) -> dict[str, str | None]:
    data = payload.get("data") or {}
    return {
        "provider_user_id": str(data.get("id") or ""),
        "email": None,  # X API typically does not return email
        "name": data.get("name") or data.get("username"),
        "avatar": data.get("profile_image_url"),
    }
