from .extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal

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
    address = db.Column(db.Text)
    user = db.relationship("User", backref="customer_profile")

class Auction(db.Model):
    __tablename__ = "auctions"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50))
    auction_date = db.Column(db.DateTime)
    lot_number = db.Column(db.String(100))
    location = db.Column(db.String(200))
    notes = db.Column(db.Text)

class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)
    vin = db.Column(db.String(30), unique=True, index=True)
    make = db.Column(db.String(100))
    model = db.Column(db.String(100))
    year = db.Column(db.Integer)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"))
    owner_customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    status = db.Column(db.String(50), default="New")
    purchase_price_usd = db.Column(db.Numeric(12,2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
