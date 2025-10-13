from functools import wraps
from typing import Callable
from flask import abort
from flask_login import login_required, current_user


def role_required(*allowed_roles: str) -> Callable:
    """Decorator to require one of the given roles for a view.

    Usage: @role_required("admin") or @role_required("admin", "accountant")
    """

    normalized = {r.lower() for r in allowed_roles}

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        @login_required
        def wrapper(*args, **kwargs):
            user_role = getattr(getattr(current_user, "role", None), "name", None)
            if not user_role or user_role.lower() not in normalized:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
