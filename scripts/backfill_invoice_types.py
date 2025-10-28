#!/usr/bin/env python3
"""
Backfill existing invoices so accountant dashboard updates correctly:
- Set invoice_type = 'CAR' if any invoice item links to a vehicle and type is empty
- Set invoice.vehicle_id from the first vehicle-linked item if missing

Safe to run multiple times.
"""
import sys
from decimal import Decimal
import os

# Ensure project root and vendored site-packages are importable when run directly
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    venv_site = os.path.join(ROOT, 'venv', 'Lib', 'site-packages')
    if os.path.isdir(venv_site) and venv_site not in sys.path:
        sys.path.insert(0, venv_site)
except Exception:
    pass

from app import create_app  # type: ignore
from app.extensions import db  # type: ignore
from app.models import Invoice, InvoiceItem  # type: ignore
from sqlalchemy import or_, func  # type: ignore


def main() -> int:
    app = create_app()
    updated = 0
    examined = 0
    with app.app_context():
        # Identify invoices with missing/blank type
        rows = (
            db.session.query(Invoice)
            .filter(or_(Invoice.invoice_type.is_(None), func.trim(Invoice.invoice_type) == ''))
            .order_by(Invoice.created_at.asc())
            .all()
        )
        for inv in rows:
            examined += 1
            item = (
                db.session.query(InvoiceItem)
                .filter(InvoiceItem.invoice_id == inv.id, InvoiceItem.vehicle_id.isnot(None))
                .order_by(InvoiceItem.created_at.asc())
                .first()
            )
            if not item:
                continue
            changed = False
            # Set type to CAR when tied to a vehicle
            if not inv.invoice_type or str(inv.invoice_type).strip() == '':
                inv.invoice_type = 'CAR'
                changed = True
            # Link primary vehicle_id if absent
            if not getattr(inv, 'vehicle_id', None):
                inv.vehicle_id = item.vehicle_id
                changed = True
            if changed:
                updated += 1
        if updated:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                print("Backfill failed during commit", file=sys.stderr)
                return 1
    print(f"Examined: {examined} | Updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
