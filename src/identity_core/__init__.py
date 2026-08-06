"""identity-core: framework-agnostic identity service.

Flask is optional. Import ``identity_core.service`` without installing Flask.
Use ``identity_core.flask_ext.register_blueprint`` only in Flask apps.
"""

from identity_core.service import (
    AuthResult,
    IdentityError,
    IdentityService,
    is_profile_complete,
)

__all__ = [
    "AuthResult",
    "IdentityError",
    "IdentityService",
    "is_profile_complete",
]

__version__ = "0.1.0"
