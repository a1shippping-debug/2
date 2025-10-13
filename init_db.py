from app import create_app
from app.extensions import db
from app.models import Role, User, Customer, Auction, Vehicle, Shipment, Invoice, Setting
from datetime import datetime, timedelta


def seed():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Roles
        roles = {r.name: r for r in Role.query.all()}
        for name in ["admin", "staff", "accountant", "customer"]:
            if name not in roles:
                db.session.add(Role(name=name))
        db.session.commit()

        # Admin user
        if not User.query.filter_by(email="admin@example.com").first():
            admin_role = Role.query.filter_by(name="admin").first()
            admin = User(name="Admin", email="admin@example.com", role=admin_role, active=True)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

        # Settings
        if not Setting.query.first():
            db.session.add(Setting(customs_rate=5.0, vat_rate=5.0, shipping_fee=100.000))
            db.session.commit()

        # Sample customer
        if not Customer.query.first():
            c = Customer(account_number="CUST-001", company_name="Gulf Motors LLC")
            db.session.add(c)
            db.session.commit()

        # Sample auctions / vehicles
        if not Auction.query.first():
            auc = Auction(provider="Copart", auction_date=datetime.utcnow(), lot_number="LOT123", location="Texas")
            db.session.add(auc)
            db.session.commit()
            v1 = Vehicle(vin="1FTFW1EG1JFC00001", make="Ford", model="F-150", year=2019, auction_id=auc.id, status="New", purchase_price_usd=15000)
            v2 = Vehicle(vin="WDDGF8AB9EA000002", make="Mercedes", model="C300", year=2014, auction_id=auc.id, status="In Shipping", purchase_price_usd=8000)
            db.session.add_all([v1, v2])
            db.session.commit()

        # Sample shipment
        if not Shipment.query.first():
            sh = Shipment(shipment_number="SHIP-001", type="Container", origin_port="Newark", destination_port="Sohar",
                          departure_date=datetime.utcnow() - timedelta(days=7), arrival_date=None, status="Open", cost_freight_usd=1200)
            db.session.add(sh)
            db.session.commit()

        # Sample invoice
        if not Invoice.query.first():
            inv = Invoice(invoice_number="INV-001", customer_id=Customer.query.first().id, total_omr=2500.000, status="Paid")
            db.session.add(inv)
            db.session.commit()


if __name__ == "__main__":
    seed()
