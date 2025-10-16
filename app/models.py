from .extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
from typing import Optional

class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(180), unique=True, index=True)
    phone = db.Column(db.String(50))
    password_hash = db.Column(db.String(200))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    role = db.relationship("Role")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return bool(self.active)

    def get_id(self):
        return str(self.id)

class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    account_number = db.Column(db.String(50), unique=True)
    company_name = db.Column(db.String(200))
    full_name = db.Column(db.String(200))
    email = db.Column(db.String(180))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    country = db.Column(db.String(100))
    user = db.relationship("User", backref="customer_profile")

class Buyer(db.Model):
    __tablename__ = "buyers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    # Optional credentials and association for buyer accounts used in auctions
    buyer_number = db.Column(db.String(100))
    password = db.Column(db.String(200))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    customer = db.relationship("Customer")

class Auction(db.Model):
    __tablename__ = "auctions"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50))
    auction_date = db.Column(db.DateTime)
    lot_number = db.Column(db.String(100))
    location = db.Column(db.String(200))
    notes = db.Column(db.Text)
    auction_url = db.Column(db.Text)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyers.id"))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))

    buyer = db.relationship("Buyer")
    customer = db.relationship("Customer")

class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)
    vin = db.Column(db.String(30), unique=True, index=True)
    make = db.Column(db.String(100))
    model = db.Column(db.String(100))
    year = db.Column(db.Integer)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"))
    owner_customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    status = db.Column(db.String(50), default="New car")
    current_location = db.Column(db.String(200))
    purchase_price_usd = db.Column(db.Numeric(12,2))
    purchase_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Public sharing fields
    share_token: Optional[str] = db.Column(db.String(64), unique=True, index=True)
    share_enabled: bool = db.Column(db.Boolean, default=False, nullable=False)

    auction = db.relationship("Auction")
    owner = db.relationship("Customer")
    cost_items = db.relationship("CostItem", backref="vehicle")

class Shipment(db.Model):
    __tablename__ = "shipments"
    id = db.Column(db.Integer, primary_key=True)
    shipment_number = db.Column(db.String(100), unique=True)
    type = db.Column(db.String(50))
    origin_port = db.Column(db.String(200))
    destination_port = db.Column(db.String(200))
    departure_date = db.Column(db.DateTime)
    arrival_date = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    cost_freight_usd = db.Column(db.Numeric(12,2))
    cost_insurance_usd = db.Column(db.Numeric(12,2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    shipping_company = db.Column(db.String(200))
    container_number = db.Column(db.String(100))

class VehicleShipment(db.Model):
    __tablename__ = "vehicle_shipments"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"))
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"))

class CostItem(db.Model):
    __tablename__ = "cost_items"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"))
    type = db.Column(db.String(100))
    amount_usd = db.Column(db.Numeric(12,2))
    description = db.Column(db.Text)

class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(100), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    total_omr = db.Column(db.Numeric(12,3))
    status = db.Column(db.String(50))
    pdf_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer")
    items = db.relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="invoice", cascade="all, delete-orphan")

    def calculate_total(self) -> Decimal:
        total = Decimal("0")
        for it in self.items or []:
            total += Decimal(it.amount_omr or 0)
        return total

    def paid_total(self) -> Decimal:
        paid = Decimal("0")
        for p in self.payments or []:
            paid += Decimal(p.amount_omr or 0)
        return paid


class Setting(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    customs_rate = db.Column(db.Numeric(5,2))
    vat_rate = db.Column(db.Numeric(5,2))
    shipping_fee = db.Column(db.Numeric(12,3))
    insurance_rate = db.Column(db.Numeric(5,2))

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(200))
    target_type = db.Column(db.String(100))
    target_id = db.Column(db.Integer)
    meta = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Backup(db.Model):
    __tablename__ = "backups"
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True)
    description = db.Column(db.String(255))
    amount_omr = db.Column(db.Numeric(12,3))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), index=True)
    amount_omr = db.Column(db.Numeric(12,3))
    method = db.Column(db.String(50))  # Cash / Bank Transfer / Card
    reference = db.Column(db.String(100))
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class InternationalCost(db.Model):
    __tablename__ = "international_costs"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), unique=True)
    freight_usd = db.Column(db.Numeric(12,2))
    insurance_usd = db.Column(db.Numeric(12,2))
    auction_fees_usd = db.Column(db.Numeric(12,2))
    customs_omr = db.Column(db.Numeric(12,3))
    vat_omr = db.Column(db.Numeric(12,3))
    local_transport_omr = db.Column(db.Numeric(12,3))
    misc_omr = db.Column(db.Numeric(12,3))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship("Vehicle", backref=db.backref("international_cost", uselist=False))

    @property
    def cif_usd(self) -> Decimal:
        cost = Decimal(self.vehicle.purchase_price_usd or 0)
        freight = Decimal(self.freight_usd or 0)
        insurance = Decimal(self.insurance_usd or 0)
        return cost + insurance + freight


class BillOfLading(db.Model):
    __tablename__ = "bills_of_lading"
    id = db.Column(db.Integer, primary_key=True)
    bol_number = db.Column(db.String(100), unique=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"))
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    pdf_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shipment = db.relationship("Shipment")


class Document(db.Model):
    __tablename__ = "documents"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"), nullable=True, index=True)
    doc_type = db.Column(db.String(100))
    file_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255))
    level = db.Column(db.String(20), default="info")
    target_type = db.Column(db.String(50))  # Vehicle / Shipment / Document
    target_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False, nullable=False)


class VehicleSaleListing(db.Model):
    __tablename__ = "vehicle_sale_listings"
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    asking_price_omr = db.Column(db.Numeric(12, 3), nullable=False)
    status = db.Column(db.String(20), default="Pending")  # Pending / Approved / Rejected
    note_admin = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    vehicle = db.relationship("Vehicle")
    customer = db.relationship("Customer")
    decided_by = db.relationship("User")
