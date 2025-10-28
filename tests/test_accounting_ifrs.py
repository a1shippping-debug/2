import os
import unittest

# Ensure in-memory DB for tests BEFORE importing app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app
from app.extensions import db
from app.models import Account, JournalEntry, JournalLine
from app.blueprints.accounting.routes import _post_journal


class IFRSAccountingTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        # Seed minimal COA
        db.session.add(Account(code="A100", name="Bank", type="ASSET"))
        db.session.add(Account(code="L200", name="Client Deposits", type="LIABILITY"))
        db.session.add(Account(code="R300", name="Service Fees", type="REVENUE"))
        db.session.commit()

    def tearDown(self):
        try:
            db.session.remove()
            db.drop_all()
        finally:
            self.ctx.pop()

    def _sum_revenue(self) -> float:
        # Sum R* credits minus debits, excluding client funds
        total = (
            db.session.query(db.func.coalesce(db.func.sum(JournalLine.credit - JournalLine.debit), 0))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .filter(Account.code.like("R%"), JournalEntry.is_client_fund.is_(False))
            .scalar()
            or 0
        )
        return float(total)

    def _client_deposits_balance(self) -> float:
        # L200* liability credit balance
        total = (
            db.session.query(db.func.coalesce(db.func.sum(JournalLine.debit - JournalLine.credit), 0))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .filter(Account.code.like("L200%"))
            .scalar()
            or 0
        )
        return -float(total)

    def test_client_fund_excluded_from_revenue(self):
        # Dr Bank 1000 / Cr Client Deposits 1000 (client fund)
        _post_journal(
            description="Deposit",
            reference="T1",
            lines=[("A100", 1000.0, 0.0), ("L200", 0.0, 1000.0)],
            is_client_fund=True,
        )
        db.session.commit()
        self.assertAlmostEqual(self._sum_revenue(), 0.0, places=3)
        self.assertAlmostEqual(self._client_deposits_balance(), 1000.0, places=3)

    def test_commission_recognition(self):
        # Dr Bank 150 / Cr Revenue 150 (not client fund)
        _post_journal(
            description="Commission",
            reference="C1",
            lines=[("A100", 150.0, 0.0), ("R300", 0.0, 150.0)],
            is_client_fund=False,
        )
        db.session.commit()
        self.assertAlmostEqual(self._sum_revenue(), 150.0, places=3)

    def test_commission_deducted_from_deposit(self):
        # First receive deposit
        _post_journal(
            description="Deposit",
            reference="D1",
            lines=[("A100", 500.0, 0.0), ("L200", 0.0, 500.0)],
            is_client_fund=True,
        )
        # Then deduct commission from deposit: Dr L200 / Cr R300
        _post_journal(
            description="Commission from deposit",
            reference="D1-COMM",
            lines=[("L200", 200.0, 0.0), ("R300", 0.0, 200.0)],
            is_client_fund=True,
        )
        db.session.commit()
        # Revenue should still exclude client-fund flagged entries (so 0)
        self.assertAlmostEqual(self._sum_revenue(), 0.0, places=3)
        # Liability should now be 300
        self.assertAlmostEqual(self._client_deposits_balance(), 300.0, places=3)


if __name__ == "__main__":
    unittest.main()
