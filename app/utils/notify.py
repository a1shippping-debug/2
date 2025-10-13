from typing import Optional
from ..extensions import db
from ..models import Notification


def create_notification(message: str, url: Optional[str] = None, audience_role: str = "employee", recipient_user_id: Optional[int] = None, level: str = "info") -> None:
    n = Notification(message=message[:300], url=url, audience_role=audience_role, recipient_user_id=recipient_user_id, level=level)
    db.session.add(n)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
