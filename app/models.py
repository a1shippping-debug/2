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
    # Customer-specific pricing category used to filter shipping region prices
    # One of: normal, container, vip, vvip
    price_category = db.Column(db.String(20), nullable=False, default="normal")
    user = db.relationship("User", backref="customer_profile")

    @property
    def display_name(self) -> str:
        """Return the most appropriate display name for the customer.

        Preference order:
        1) company_name
        2) full_name
        3) linked user.name
        Fallback to '-' when nothing available.
        """
        try:
            name = (self.company_name or self.full_name or (self.user.name if getattr(self, 'user', None) else None))
            name = (name or "").strip()
            return name if name else "-"
        except Exception:
            return "-"


class ClientAccountStructure(db.Model):
    __tablename__ = "client_account_structures"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), unique=True, nullable=False, index=True)
    # Per-client sub-ledger accounts (codes must exist in accounts table)
    deposit_account_code = db.Column(db.String(20), nullable=False)  # L200C{customer_id}
    auction_account_code = db.Column(db.String(20))  # A150C{customer_id}
    service_revenue_account_code = db.Column(db.String(20), nullable=False)  # R300C{customer_id}
    logistics_expense_account_code = db.Column(db.String(20), nullable=False)  # E200C{customer_id}
    receivable_account_code = db.Column(db.String(20), nullable=False)  # A300C{customer_id}
    currency_code = db.Column(db.String(3), default="OMR", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer")


class VehicleAccountStructure(db.Model):
    __tablename__ = "vehicle_account_structures"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), unique=True, nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    # Per-vehicle sub-ledger accounts (codes must exist in accounts table)
    deposit_account_code = db.Column(db.String(20), nullable=False)      # L200-V{vehicle_id}
    auction_account_code = db.Column(db.String(20), nullable=False)      # A150-V{vehicle_id}
    freight_account_code = db.Column(db.String(20), nullable=False)      # E200-V{vehicle_id}
    customs_account_code = db.Column(db.String(20), nullable=False)      # E220-V{vehicle_id}
    commission_account_code = db.Column(db.String(20), nullable=False)   # R300-V{vehicle_id}
    storage_account_code = db.Column(db.String(20), nullable=False)      # E230-V{vehicle_id}
    currency_code = db.Column(db.String(3), default="OMR", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship("Vehicle")
    client = db.relationship("Customer")

class Buyer(db.Model):
    __tablename__ = "buyers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    # Optional credentials and association for buyer accounts used in auctions
    buyer_number = db.Column(db.String(100))
    password = db.Column(db.String(200))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="SET NULL"))
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
    # CAR or SHIPPING
    invoice_type = db.Column(db.String(20))
    # Optional primary vehicle reference for per-deal tracking
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=True, index=True)
    total_omr = db.Column(db.Numeric(12,3))
    status = db.Column(db.String(50))
    pdf_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer")
    vehicle = db.relationship("Vehicle")
    items = db.relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="invoice", cascade="all, delete-orphan")
    # Optional exchange rate used for this invoice (e.g., fines converted from USD)
    exchange_rate_id = db.Column(db.Integer, db.ForeignKey("exchange_rates.id"), nullable=True)

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
    # Books lock date: prevent posting entries on or before this date
    books_locked_until = db.Column(db.DateTime)
    # Accounting basis: 'accrual' or 'cash'
    accounting_method = db.Column(db.String(10), default="accrual")

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
    # Optional direct linkage for reporting/traceability
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), index=True)
    amount_omr = db.Column(db.Numeric(12,3))
    method = db.Column(db.String(50))  # Cash / Bank Transfer / Card
    reference = db.Column(db.String(100))
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships for convenient access in templates and reports
    customer = db.relationship("Customer")
    vehicle = db.relationship("Vehicle")


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


class Testimonial(db.Model):
    __tablename__ = "testimonials"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(150))  # e.g., تاجر سيارات
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)  # 1-5 stars
    approved = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def display_initials(self) -> str:
        try:
            parts = (self.name or "").strip().split()
            if not parts:
                return ""
            if len(parts) == 1:
                return parts[0][:2]
            return f"{parts[0][:1]}.{parts[-1][:1]}"
        except Exception:
            return ""


class ShippingRegionPrice(db.Model):
    __tablename__ = "shipping_region_prices"

    id = db.Column(db.Integer, primary_key=True)
    # Short code or identifier for the region (e.g., MCT, SLL, IBRA)
    # Note: uniqueness is enforced together with category via a composite constraint
    region_code = db.Column(db.String(50), index=True, nullable=False)
    # Pricing category: normal, container, vip, vvip
    category = db.Column(db.String(20), nullable=False, default="normal")
    # Human-friendly name in any language (Arabic recommended for admin UI)
    region_name = db.Column(db.String(200))
    # Price stored in OMR with 3 fractional digits
    price_omr = db.Column(db.Numeric(12, 3), nullable=False)
    effective_from = db.Column(db.DateTime)
    effective_to = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("region_code", "category", name="uq_shipping_region_code_category"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ShippingRegionPrice {self.region_code} [{self.category}] {self.price_omr}>"


# --- General Ledger & Accounting ---

class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, index=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    # One of: ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
    type = db.Column(db.String(20), nullable=False)
    currency_code = db.Column(db.String(3), default="OMR", nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Optional linkage for client-specific sub-accounts
    client_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    # Optional linkage for vehicle-specific sub-accounts
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), index=True)


class ExchangeRate(db.Model):
    __tablename__ = "exchange_rates"

    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.String(3), nullable=False)  # e.g., USD
    quote_currency = db.Column(db.String(3), nullable=False)  # e.g., OMR
    rate = db.Column(db.Numeric(12, 6), nullable=False)
    effective_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JournalEntry(db.Model):
    __tablename__ = "journal_entries"

    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    description = db.Column(db.String(255))
    reference = db.Column(db.String(100))
    # Linkage for reporting & traceability
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), index=True)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"), index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), index=True)
    # Compliance & workflow
    is_client_fund: bool = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(20), default="approved", nullable=False)  # pending/approved/rejected
    notes = db.Column(db.Text)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer")
    vehicle = db.relationship("Vehicle")
    auction = db.relationship("Auction")
    invoice = db.relationship("Invoice")
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])
    lines = db.relationship("JournalLine", backref="entry", cascade="all, delete-orphan")


class JournalLine(db.Model):
    __tablename__ = "journal_lines"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id"), index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)
    debit = db.Column(db.Numeric(14, 3), default=0)
    credit = db.Column(db.Numeric(14, 3), default=0)
    currency_code = db.Column(db.String(3), default="OMR")

    account = db.relationship("Account")


class OperationalExpense(db.Model):
    __tablename__ = "operational_expenses"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), index=True)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"), index=True)
    category = db.Column(db.String(50), nullable=False)  # international_shipping, customs, internal_shipping, misc
    # Store both original amount/currency and converted OMR for reporting consistency
    original_amount = db.Column(db.Numeric(12, 3))
    original_currency = db.Column(db.String(3), default="OMR")
    amount_omr = db.Column(db.Numeric(12, 3), nullable=False)
    exchange_rate_id = db.Column(db.Integer, db.ForeignKey("exchange_rates.id"), nullable=True)
    paid = db.Column(db.Boolean, default=False, nullable=False)
    paid_at = db.Column(db.DateTime)
    description = db.Column(db.String(255))
    supplier = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vehicle = db.relationship("Vehicle")
    auction = db.relationship("Auction")
    exchange_rate = db.relationship("ExchangeRate")


class CustomerDeposit(db.Model):
    __tablename__ = "customer_deposits"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), index=True)
    auction_id = db.Column(db.Integer, db.ForeignKey("auctions.id"), index=True)
    amount_omr = db.Column(db.Numeric(12, 3), nullable=False)
    method = db.Column(db.String(50))  # Cash / Bank Transfer / Card
    reference = db.Column(db.String(100))
    status = db.Column(db.String(20), default="held")  # held / refunded / applied
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    refunded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer")
    vehicle = db.relationship("Vehicle")
    auction = db.relationship("Auction")

