"""Optional Flask Blueprint implementing the /auth HTTP contract."""

from __future__ import annotations

import secrets
from functools import wraps

from identity_core.mailer import mailer_from_env
from identity_core.rate_limit import login_limiter, register_limiter
from identity_core.service import (
    AuthRejected,
    ConflictError,
    IdentityError,
    IdentityService,
    LockedError,
    NotFoundError,
    is_profile_complete,
)


def _json_error(message: str, status: int = 400):
    from flask import jsonify

    return jsonify({"error": message}), status


def create_auth_blueprint(
    *,
    session_factory,
    login_manager=None,
    url_prefix: str = "/auth",
):
    """Build a Flask Blueprint. Lazy-imports Flask so core stays optional."""
    try:
        from flask import Blueprint, jsonify, redirect, request, session
        from flask_login import current_user, login_required, login_user, logout_user
    except ImportError as exc:
        raise ImportError("Install identity-core[flask] to use the auth blueprint") from exc

    bp = Blueprint("identity_auth", __name__, url_prefix=url_prefix)

    def _svc() -> IdentityService:
        db_session = session_factory()
        # stash on request ctx via flask.g
        from flask import g

        g.identity_db = db_session
        return IdentityService(db_session, mailer=mailer_from_env())

    def _close_db(response=None):
        from flask import g

        db = getattr(g, "identity_db", None)
        if db is not None:
            db.close()
        return response

    bp.after_request(_close_db)

    def _client_ip() -> str:
        return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

    def _user_to_dict(user):
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "is_active": user.is_active,
            "email_confirmed_at": user.email_confirmed_at.isoformat() if user.email_confirmed_at else None,
            "google_id": user.google_id,
            "twitter_id": user.twitter_id,
            "profile_complete": is_profile_complete(user),
        }

    @bp.post("/register")
    def register():
        if not register_limiter.hit(f"reg:{_client_ip()}"):
            return _json_error("Rate limit exceeded", 429)
        data = request.get_json(silent=True) or {}
        email = data.get("email")
        password = data.get("password")
        name = data.get("name")
        try:
            svc = _svc()
            user = svc.create_user(email, password, name)
            return jsonify({"user": _user_to_dict(user), "message": "Check email to verify"}), 201
        except ConflictError as exc:
            return _json_error(str(exc), 409)
        except (IdentityError, ValueError) as exc:
            return _json_error(str(exc), 400)

    @bp.get("/verify-email/<token>")
    def verify_email(token: str):
        try:
            svc = _svc()
            user = svc.verify_email(token)
            login_user(user)
            return jsonify({"user": _user_to_dict(user)})
        except (IdentityError, ValueError) as exc:
            return _json_error(str(exc), 400)

    @bp.post("/login")
    def login():
        if not login_limiter.hit(f"login:{_client_ip()}"):
            return _json_error("Rate limit exceeded", 429)
        data = request.get_json(silent=True) or {}
        try:
            svc = _svc()
            user = svc.authenticate(
                data.get("email") or "",
                data.get("password") or "",
                ip=_client_ip(),
                user_agent=request.headers.get("User-Agent"),
            )
            if user is None:
                return _json_error("Invalid credentials", 401)
            login_user(user, remember=bool(data.get("remember_me")))
            return jsonify({"user": _user_to_dict(user)})
        except LockedError as exc:
            return _json_error(str(exc), 423)
        except AuthRejected as exc:
            return _json_error(str(exc), 403)

    @bp.post("/logout")
    def logout():
        logout_user()
        return jsonify({"ok": True})

    @bp.post("/forgot-password")
    def forgot_password():
        data = request.get_json(silent=True) or {}
        svc = _svc()
        svc.start_password_reset(data.get("email") or "")
        return jsonify({"message": "If the email exists, a reset link was sent"})

    @bp.post("/reset-password/<token>")
    def reset_password(token: str):
        data = request.get_json(silent=True) or {}
        try:
            svc = _svc()
            user = svc.reset_password(token, data.get("password") or "")
            login_user(user)
            return jsonify({"user": _user_to_dict(user)})
        except (IdentityError, ValueError) as exc:
            return _json_error(str(exc), 400)

    @bp.get("/me")
    @login_required
    def me():
        return jsonify({"user": _user_to_dict(current_user)})

    @bp.patch("/me")
    @login_required
    def patch_me():
        data = request.get_json(silent=True) or {}
        svc = _svc()
        try:
            if "email" in data and data["email"]:
                result = svc.complete_profile(
                    current_user.id,
                    data["email"],
                    name=data.get("name", current_user.name),
                )
                return jsonify({"user": _user_to_dict(result.user), "profile_complete": result.profile_complete})
            user = svc.update_me(
                current_user.id,
                name=data.get("name"),
                avatar_url=data.get("avatar_url"),
            )
            return jsonify({"user": _user_to_dict(user), "profile_complete": is_profile_complete(user)})
        except ConflictError as exc:
            return _json_error(str(exc), 409)
        except (IdentityError, NotFoundError, ValueError) as exc:
            return _json_error(str(exc), 400)

    @bp.get("/oauth/google")
    def oauth_google_start():
        from identity_core.oauth_google import build_authorize_url

        state = secrets.token_urlsafe(24)
        session["oauth_google_state"] = state
        return redirect(build_authorize_url(state))

    @bp.get("/oauth/google/callback")
    def oauth_google_callback():
        from identity_core.oauth_google import exchange_code, fetch_userinfo, profile_from_userinfo

        if request.args.get("state") != session.pop("oauth_google_state", None):
            return _json_error("Invalid OAuth state", 400)
        code = request.args.get("code")
        if not code:
            return _json_error("Missing code", 400)
        tokens = exchange_code(code)
        info = fetch_userinfo(tokens["access_token"])
        profile = profile_from_userinfo(info)
        if not profile["provider_user_id"]:
            return _json_error("Google profile missing id", 400)
        svc = _svc()
        result = svc.upsert_oauth(
            "google",
            profile["provider_user_id"],
            email=profile.get("email"),
            name=profile.get("name"),
            avatar=profile.get("avatar"),
        )
        login_user(result.user)
        return jsonify({"user": _user_to_dict(result.user), "profile_complete": result.profile_complete})

    @bp.get("/oauth/twitter")
    def oauth_twitter_start():
        from identity_core.oauth_twitter import build_authorize_url, generate_pkce

        state = secrets.token_urlsafe(24)
        verifier, challenge = generate_pkce()
        session["oauth_twitter_state"] = state
        session["oauth_twitter_verifier"] = verifier
        return redirect(build_authorize_url(state, challenge))

    @bp.get("/oauth/twitter/callback")
    def oauth_twitter_callback():
        from identity_core.oauth_twitter import exchange_code, fetch_me, profile_from_me

        if request.args.get("state") != session.pop("oauth_twitter_state", None):
            return _json_error("Invalid OAuth state", 400)
        verifier = session.pop("oauth_twitter_verifier", None)
        code = request.args.get("code")
        if not code or not verifier:
            return _json_error("Missing code", 400)
        tokens = exchange_code(code, verifier)
        me_payload = fetch_me(tokens["access_token"])
        profile = profile_from_me(me_payload)
        if not profile["provider_user_id"]:
            return _json_error("Twitter profile missing id", 400)
        svc = _svc()
        result = svc.upsert_oauth(
            "twitter",
            profile["provider_user_id"],
            email=profile.get("email"),
            name=profile.get("name"),
            avatar=profile.get("avatar"),
        )
        login_user(result.user)
        return jsonify({"user": _user_to_dict(result.user), "profile_complete": result.profile_complete})

    # silence unused import when login_manager not passed
    _ = login_manager
    _ = wraps
    return bp
