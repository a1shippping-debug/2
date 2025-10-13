from typing import Optional, Any, Dict
from flask_login import current_user
from ..extensions import db
from ..models import AuditLog


def log_action(action: str, target_type: str, target_id: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> None:
    user_id = getattr(current_user, 'id', None)
    entry = AuditLog(user_id=user_id, action=action, target_type=target_type, target_id=target_id, meta=meta or {})
    db.session.add(entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
