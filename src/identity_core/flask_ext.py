"""Optional Flask integration. Importing identity_core does NOT load this module."""

from __future__ import annotations

from typing import Any


def register_blueprint(
    app: Any,
    *,
    session_factory=None,
    engine=None,
    url_prefix: str = "/auth",
    secret_key: str | None = None,
) -> Any:
    """Attach identity auth blueprint + Flask-Login to an existing Flask app.

    Does not run automatically. Call explicitly from Flask apps only.
    """
    try:
        from flask_login import LoginManager, UserMixin
    except ImportError as exc:
        raise ImportError("Install identity-core[flask] to use register_blueprint") from exc

    from identity_core.db import create_all, make_engine, make_session_factory
    from identity_core.models import User
    from identity_core.routes import create_auth_blueprint

    if secret_key and not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secret_key

    if engine is None:
        engine = make_engine()
        create_all(engine)
    if session_factory is None:
        session_factory = make_session_factory(engine)

    # Flask-Login needs UserMixin methods; our SQLAlchemy User already has id.
    if not issubclass(User, UserMixin):
        # Duck-type: patch get_id onto instances via mixin-style helpers
        if not hasattr(User, "get_id"):
            User.get_id = lambda self: str(self.id)  # type: ignore[attr-defined]
        if not hasattr(User, "is_authenticated"):
            User.is_authenticated = property(lambda self: True)  # type: ignore[attr-defined]
        if not hasattr(User, "is_anonymous"):
            User.is_anonymous = property(lambda self: False)  # type: ignore[attr-defined]
        # is_active already exists as a column — Flask-Login reads it

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = None

    @login_manager.user_loader
    def load_user(user_id: str):
        db = session_factory()
        try:
            return db.get(User, user_id)
        finally:
            db.close()

    bp = create_auth_blueprint(session_factory=session_factory, login_manager=login_manager, url_prefix=url_prefix)
    app.register_blueprint(bp)
    app.extensions["identity_core"] = {
        "engine": engine,
        "session_factory": session_factory,
        "login_manager": login_manager,
    }
    return bp


# Alias kept for docs; init_app is optional and identical entrypoint.
init_app = register_blueprint
