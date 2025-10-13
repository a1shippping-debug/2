from functools import wraps
from typing import Callable
from flask import abort
from flask_login import login_required, current_user


def _canonicalize_role(role_name: str | None) -> str | None:
    """Normalize role names to canonical identifiers.

    This allows supporting legacy/synonym role names without changing DB data.
    """
    if not role_name:
        return None
    name = role_name.strip().lower()
    synonyms = {
        # Treat legacy "staff" as the same as "employee"
        "staff": "employee",
        # Accept common pluralization mistakes
        "employees": "employee",
    }
    return synonyms.get(name, name)


def role_required(*allowed_roles: str) -> Callable:
    """Decorator to require one of the given roles for a view.

    Usage: @role_required("admin") or @role_required("admin", "accountant")
    """

    normalized_allowed = {
        r for r in (_canonicalize_role(r) for r in allowed_roles) if r is not None
    }

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(*args, **kwargs):
            user_role = getattr(getattr(current_user, "role", None), "name", None)
            user_role_norm = _canonicalize_role(user_role)
            if not user_role_norm or user_role_norm not in normalized_allowed:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
