# CarTrade - Flask project skeleton

This is a starter Flask project for managing import/export of cars between US auctions and Oman.

## What's included
- Flask app skeleton with blueprints for auth/admin/operations/accounting/customer
- SQLAlchemy models
- Tailwind-based simple templates
- PDF utility using WeasyPrint (requires system deps)
- SQL init script (sql/init_db.sql)
- requirements.txt and .env.example
- scripts/backup_db.sh

## Run locally (recommended)
1. Create venv and install:
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and adjust variables.

3. Initialize DB (SQLite default shown):
```bash
export FLASK_APP=run.py
flask db init
flask db migrate -m "init"
flask db upgrade
```
Alternatively run:
```bash
python -c "from app import create_app; app=create_app(); from app.extensions import db; db.create_all(app=app)"
```

4. Run:
```bash
flask run
```

## Accounting & Finance

This project includes an IFRS/GAAP‑aligned accountant portal and general ledger.

Key points:
- Client Deposits are treated as liabilities (not revenue). Journals tagged as client funds are excluded from P&L.
- Service commissions are recognized only when earned/paid into Bank (Revenue R* accounts).
- Balance Sheet presents Client Deposits under Current Liabilities.
- Reports available: Profit & Loss, Balance Sheet, Trial Balance, General Ledger, Cash Flow, Taxes.

Workflows:
- Client sends funds: Dr Bank (A100) / Cr Client Deposits (L200) [client fund].
- Company pays auction (on client behalf): Dr Client Deposits / Cr Bank [client fund].
- Company earns commission: Dr Bank (or Client) / Cr Revenue (R300) [not client fund].
- Commission deducted from deposit: Dr Client Deposits / Cr Revenue (R300) [client fund].

Manual Journals:
- Accounting → Journals lets accountants post, approve, and flag entries as client funds.

## Notes
- WeasyPrint requires system packages (libpango, libcairo). If you can't install them, remove WeasyPrint and use ReportLab or plain HTML downloads.
- To use PostgreSQL, update DATABASE_URL in `.env`.
- Add SMTP settings to send emails and integrate WhatsApp gateway for notifications.

