from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, current_app
from flask_babel import gettext as _
from flask_login import login_required
from ...security import role_required
from ...extensions import db, mail
from ...models import (
    Vehicle,
    Shipment,
    Invoice,
    InvoiceItem,
    Payment,
    InternationalCost,
    BillOfLading,
    Customer,
    Setting,
    VehicleShipment,
)
from ...utils_pdf import render_invoice_pdf, render_bol_pdf
from flask_mail import Message
from datetime import datetime
from decimal import Decimal

acct_bp = Blueprint("acct", __name__, template_folder="templates/accounting")

@acct_bp.route("/dashboard")
@role_required("accountant", "admin")
def dashboard():
    # summary metrics
    counts = {
        "invoices": db.session.query(Invoice).count(),
        "vehicles_priced": db.session.query(InternationalCost).count(),
    }

    usd_to_omr = float(current_app.config.get('OMR_EXCHANGE_RATE', 0.385))
    totals = {
        "revenue_omr": float(db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).scalar() or 0),
        "expenses_omr": float(((db.session.query(db.func.coalesce(db.func.sum(Shipment.cost_freight_usd), 0)).scalar() or 0)
                                + (db.session.query(db.func.coalesce(db.func.sum(InternationalCost.auction_fees_usd), 0)).scalar() or 0)) * usd_to_omr),
    }
    totals["net_omr"] = totals["revenue_omr"] - totals["expenses_omr"]

    # monthly revenue series (last 12 months)
    now = datetime.utcnow()
    months = []
    revenue_series = []
    for i in range(12):
        month_start = datetime(now.year - (1 if now.month - i <= 0 else 0), ((now.month - i - 1) % 12) + 1, 1)
        if month_start.month == 12:
            month_end = datetime(month_start.year + 1, 1, 1)
        else:
            month_end = datetime(month_start.year, month_start.month + 1, 1)
        total = db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).\
            filter(Invoice.created_at >= month_start, Invoice.created_at < month_end).scalar() or 0
        months.append(month_start.strftime('%b'))
        revenue_series.append(float(total))
    months = list(reversed(months))
    revenue_series = list(reversed(revenue_series))

    # expenses by category (freight, customs, vat, local transport, misc)
    exp = {
        "Freight": float(db.session.query(db.func.coalesce(db.func.sum(Shipment.cost_freight_usd), 0)).scalar() or 0) * usd_to_omr,
        "Customs": float(db.session.query(db.func.coalesce(db.func.sum(InternationalCost.customs_omr), 0)).scalar() or 0),
        "VAT": float(db.session.query(db.func.coalesce(db.func.sum(InternationalCost.vat_omr), 0)).scalar() or 0),
        "Local Transport": float(db.session.query(db.func.coalesce(db.func.sum(InternationalCost.local_transport_omr), 0)).scalar() or 0),
        "Misc": float(db.session.query(db.func.coalesce(db.func.sum(InternationalCost.misc_omr), 0)).scalar() or 0),
    }

    return render_template("accounting/dashboard.html", counts=counts, totals=totals, chart={
        "months": months, "revenue": revenue_series, "exp_labels": list(exp.keys()), "exp_values": list(exp.values())
    })


# International Costs Management
@acct_bp.route('/costs')
@role_required('accountant', 'admin')
def costs_list():
    q = db.session.query(Vehicle).order_by(Vehicle.created_at.desc())
    vehicles = q.limit(50).all()
    return render_template('accounting/costs_list.html', vehicles=vehicles)


@acct_bp.route('/costs/<int:vehicle_id>', methods=['GET','POST'])
@role_required('accountant', 'admin')
def costs_edit(vehicle_id: int):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        flash(_('Vehicle not found'), 'danger')
        return redirect(url_for('acct.costs_list'))
    cost = db.session.query(InternationalCost).filter_by(vehicle_id=vehicle.id).first()
    if request.method == 'POST':
        def f(name):
            try:
                return float(request.form.get(name) or 0)
            except Exception:
                return 0
        if not cost:
            cost = InternationalCost(vehicle_id=vehicle.id)
            db.session.add(cost)
        cost.freight_usd = f('freight_usd')
        cost.insurance_usd = f('insurance_usd')
        cost.auction_fees_usd = f('auction_fees_usd')
        cost.customs_omr = f('customs_omr')
        cost.vat_omr = f('vat_omr')
        cost.local_transport_omr = f('local_transport_omr')
        cost.misc_omr = f('misc_omr')
        try:
            db.session.commit()
            flash(_('Costs saved'), 'success')
            return redirect(url_for('acct.costs_list'))
        except Exception:
            db.session.rollback()
            flash(_('Failed to save costs'), 'danger')
    return render_template('accounting/costs_edit.html', vehicle=vehicle, cost=cost)


# Invoices CRUD
@acct_bp.route('/invoices')
@role_required('accountant', 'admin')
def invoices_list():
    invoices = db.session.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return render_template('accounting/invoices_list.html', invoices=invoices)


@acct_bp.route('/invoices/new', methods=['GET','POST'])
@role_required('accountant', 'admin')
def invoices_new():
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    vehicles = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(100).all()
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        items = []
        descriptions = request.form.getlist('item_description')
        amounts = request.form.getlist('item_amount')
        for d, a in zip(descriptions, amounts):
            if d.strip():
                try:
                    items.append((d.strip(), float(a or 0)))
                except Exception:
                    items.append((d.strip(), 0.0))
        inv = Invoice(invoice_number=f"INV-{int(datetime.utcnow().timestamp())}", customer_id=int(customer_id) if customer_id else None, status='Draft', total_omr=0)
        db.session.add(inv)
        db.session.flush()
        total = Decimal('0')
        for d, a in items:
            db.session.add(InvoiceItem(invoice_id=inv.id, description=d, amount_omr=a))
            total += Decimal(str(a))
        inv.total_omr = total
        try:
            db.session.commit()
            flash(_('Invoice created'), 'success')
            return redirect(url_for('acct.invoices_edit', invoice_id=inv.id))
        except Exception:
            db.session.rollback()
            flash(_('Failed to create invoice'), 'danger')
    return render_template('accounting/invoices_form.html', customers=customers, vehicles=vehicles)


@acct_bp.route('/invoices/<int:invoice_id>/edit', methods=['GET','POST'])
@role_required('accountant', 'admin')
def invoices_edit(invoice_id: int):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        flash(_('Invoice not found'), 'danger')
        return redirect(url_for('acct.invoices_list'))
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    if request.method == 'POST':
        status = request.form.get('status') or 'Draft'
        invoice.status = status
        # replace items
        db.session.query(InvoiceItem).filter_by(invoice_id=invoice.id).delete()
        descriptions = request.form.getlist('item_description')
        amounts = request.form.getlist('item_amount')
        total = Decimal('0')
        for d, a in zip(descriptions, amounts):
            if d.strip():
                val = Decimal(str(a or 0))
                db.session.add(InvoiceItem(invoice_id=invoice.id, description=d.strip(), amount_omr=val))
                total += val
        invoice.total_omr = total
        try:
            db.session.commit()
            flash(_('Invoice updated'), 'success')
        except Exception:
            db.session.rollback()
            flash(_('Failed to update invoice'), 'danger')
    return render_template('accounting/invoices_edit.html', invoice=invoice, customers=customers)


@acct_bp.route('/invoices/<int:invoice_id>/delete', methods=['POST'])
@role_required('accountant', 'admin')
def invoices_delete(invoice_id: int):
    inv = db.session.get(Invoice, invoice_id)
    if not inv:
        flash(_('Not found'), 'danger')
        return redirect(url_for('acct.invoices_list'))
    db.session.delete(inv)
    try:
        db.session.commit()
        flash(_('Invoice deleted'), 'success')
    except Exception:
        db.session.rollback()
        flash(_('Failed to delete invoice'), 'danger')
    return redirect(url_for('acct.invoices_list'))


@acct_bp.route('/invoices/<int:invoice_id>/export')
@role_required('accountant', 'admin')
def invoices_export(invoice_id: int):
    inv = db.session.get(Invoice, invoice_id)
    if not inv:
        abort(404)
    items = db.session.query(InvoiceItem).filter_by(invoice_id=inv.id).all()
    path = render_invoice_pdf(inv, items)
    inv.pdf_path = path
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=f"{inv.invoice_number}.pdf")


@acct_bp.route('/invoices/<int:invoice_id>/export.xlsx')
@role_required('accountant', 'admin')
def invoices_export_xlsx(invoice_id: int):
    from openpyxl import Workbook
    inv = db.session.get(Invoice, invoice_id)
    if not inv:
        abort(404)
    items = db.session.query(InvoiceItem).filter_by(invoice_id=inv.id).all()
    wb = Workbook(); ws = wb.active; ws.title = inv.invoice_number or 'Invoice'
    ws.append(['Invoice #', inv.invoice_number])
    ws.append(['Date', inv.created_at.strftime('%Y-%m-%d') if inv.created_at else ''])
    ws.append(['Client', inv.customer.company_name if inv.customer else '-'])
    ws.append([])
    ws.append(['Description', 'Amount (OMR)'])
    for it in items:
        ws.append([it.description, float(it.amount_omr or 0)])
    ws.append([])
    ws.append(['Total', float(inv.total_omr or 0)])
    from io import BytesIO
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f"{inv.invoice_number}.xlsx")

@acct_bp.route('/invoices/<int:invoice_id>/email', methods=['POST'])
@role_required('accountant', 'admin')
def invoices_email(invoice_id: int):
    inv = db.session.get(Invoice, invoice_id)
    if not inv or not inv.customer or not inv.customer.user:
        flash(_('Missing customer email'), 'danger')
        return redirect(url_for('acct.invoices_list'))
    email = inv.customer.user.email
    # ensure pdf exists
    items = db.session.query(InvoiceItem).filter_by(invoice_id=inv.id).all()
    path = inv.pdf_path or render_invoice_pdf(inv, items)
    try:
        msg = Message(subject=_('Invoice %(n)s', n=inv.invoice_number), recipients=[email])
        msg.body = _('Please find attached invoice %(n)s.', n=inv.invoice_number)
        with open(path, 'rb') as f:
            msg.attach(filename=f"{inv.invoice_number}.pdf", content_type='application/pdf', data=f.read())
        mail.send(msg)
        flash(_('Email sent'), 'success')
    except Exception:
        flash(_('Failed to send email'), 'danger')
    return redirect(url_for('acct.invoices_edit', invoice_id=inv.id))


# Payments
@acct_bp.route('/payments')
@role_required('accountant', 'admin')
def payments_list():
    payments = db.session.query(Payment).order_by(Payment.created_at.desc()).limit(100).all()
    invoices = db.session.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return render_template('accounting/payments_list.html', payments=payments, invoices=invoices)


@acct_bp.route('/payments/new', methods=['POST'])
@role_required('accountant', 'admin')
def payments_new():
    invoice_id = request.form.get('invoice_id')
    amount = request.form.get('amount')
    method = request.form.get('method')
    reference = request.form.get('reference')
    inv = db.session.get(Invoice, int(invoice_id)) if invoice_id else None
    if not inv:
        flash(_('Invalid invoice'), 'danger')
        return redirect(url_for('acct.payments_list'))
    try:
        amt = Decimal(str(amount or 0))
    except Exception:
        amt = Decimal('0')
    p = Payment(invoice_id=inv.id, amount_omr=amt, method=method, reference=reference)
    db.session.add(p)
    # update status
    paid = inv.paid_total() + amt
    if paid >= (inv.total_omr or 0):
        inv.status = 'Paid'
    else:
        inv.status = 'Partial'
    try:
        db.session.commit()
        flash(_('Payment recorded'), 'success')
    except Exception:
        db.session.rollback()
        flash(_('Failed to save payment'), 'danger')
    return redirect(url_for('acct.payments_list'))


# Bill of Lading
@acct_bp.route('/bol')
@role_required('accountant', 'admin')
def bol_list():
    bols = db.session.query(BillOfLading).order_by(BillOfLading.created_at.desc()).all()
    shipments = db.session.query(Shipment).order_by(Shipment.created_at.desc()).all()
    return render_template('accounting/bol_list.html', bols=bols, shipments=shipments)


@acct_bp.route('/bol/new', methods=['POST'])
@role_required('accountant', 'admin')
def bol_new():
    shipment_id = request.form.get('shipment_id')
    bol_number = request.form.get('bol_number') or f"BOL-{int(datetime.utcnow().timestamp())}"
    bol = BillOfLading(bol_number=bol_number, shipment_id=int(shipment_id) if shipment_id else None)
    db.session.add(bol)
    try:
        db.session.commit()
        flash(_('BOL created'), 'success')
    except Exception:
        db.session.rollback()
        flash(_('Failed to create BOL'), 'danger')
    return redirect(url_for('acct.bol_list'))


@acct_bp.route('/bol/<int:bol_id>/export')
@role_required('accountant', 'admin')
def bol_export(bol_id: int):
    bol = db.session.get(BillOfLading, bol_id)
    if not bol:
        abort(404)
    vehicles = db.session.query(Vehicle).join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id).\
        filter(VehicleShipment.shipment_id == bol.shipment_id).all()
    path = render_bol_pdf(bol, vehicles)
    bol.pdf_path = path
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=f"{bol.bol_number}.pdf")


@acct_bp.route('/bol/<int:bol_id>/email', methods=['POST'])
@role_required('accountant', 'admin')
def bol_email(bol_id: int):
    recipient = (request.form.get('email') or '').strip()
    if not recipient:
        flash(_('Recipient email required'), 'danger'); return redirect(url_for('acct.bol_list'))
    bol = db.session.get(BillOfLading, bol_id)
    if not bol:
        flash(_('BOL not found'), 'danger'); return redirect(url_for('acct.bol_list'))
    vehicles = db.session.query(Vehicle).join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id).\
        filter(VehicleShipment.shipment_id == bol.shipment_id).all()
    path = bol.pdf_path or render_bol_pdf(bol, vehicles)
    try:
        msg = Message(subject=_('BOL %(n)s', n=bol.bol_number), recipients=[recipient])
        msg.body = _('Please find attached Bill of Lading %(n)s.', n=bol.bol_number)
        with open(path, 'rb') as f:
            msg.attach(filename=f"{bol.bol_number}.pdf", content_type='application/pdf', data=f.read())
        mail.send(msg)
        flash(_('Email sent'), 'success')
    except Exception:
        flash(_('Failed to send email'), 'danger')
    return redirect(url_for('acct.bol_list'))


@acct_bp.route('/bol/<int:bol_id>/upload', methods=['POST'])
@role_required('accountant', 'admin')
def bol_upload(bol_id: int):
    bol = db.session.get(BillOfLading, bol_id)
    if not bol:
        flash(_('BOL not found'), 'danger'); return redirect(url_for('acct.bol_list'))
    f = request.files.get('file')
    if not f:
        flash(_('No file uploaded'), 'danger'); return redirect(url_for('acct.bol_list'))
    import os
    outdir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'bols')
    os.makedirs(outdir, exist_ok=True)
    filename = f"{bol.bol_number}.pdf"
    path = os.path.join(outdir, filename)
    f.save(path)
    bol.pdf_path = path
    db.session.commit()
    flash(_('BOL uploaded'), 'success')
    return redirect(url_for('acct.bol_list'))


# Reports
@acct_bp.route('/reports')
@role_required('accountant', 'admin')
def reports():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from openpyxl import Workbook
    report_type = request.args.get('type', 'monthly')
    export = request.args.get('export')

    now = datetime.utcnow()
    if report_type == 'monthly':
        labels, revenue, expenses = [], [], []
        dt = datetime(now.year, now.month, 1)
        usd_to_omr = float(current_app.config.get('OMR_EXCHANGE_RATE', 0.385))
        for _ in range(12):
            start = dt
            end = datetime(dt.year + 1, 1, 1) if dt.month == 12 else datetime(dt.year, dt.month + 1, 1)
            labels.append(dt.strftime('%b %Y'))
            rev = db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).filter(Invoice.created_at >= start, Invoice.created_at < end).scalar() or 0
            freight = db.session.query(db.func.coalesce(db.func.sum(Shipment.cost_freight_usd), 0)).filter(Shipment.created_at >= start, Shipment.created_at < end).scalar() or 0
            customs = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.customs_omr), 0)).filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            vat = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.vat_omr), 0)).filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            local_t = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.local_transport_omr), 0)).filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            misc = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.misc_omr), 0)).filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            exp = float(freight) * usd_to_omr + float(customs or 0) + float(vat or 0) + float(local_t or 0) + float(misc or 0)
            revenue.append(float(rev)); expenses.append(float(exp))
            if dt.month == 1: dt = datetime(dt.year - 1, 12, 1)
            else: dt = datetime(dt.year, dt.month - 1, 1)
        labels, revenue, expenses = list(reversed(labels)), list(reversed(revenue)), list(reversed(expenses))

        if export == 'pdf':
            buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4; y = height - 40
            c.setFont('Helvetica-Bold', 16); c.drawString(40, y, _('Monthly Profit & Loss'))
            y -= 25; c.setFont('Helvetica-Bold', 11);
            c.drawString(40, y, _('Month')); c.drawString(200, y, _('Revenue')); c.drawString(320, y, _('Expenses')); c.drawString(440, y, _('Profit'))
            y -= 14; c.setFont('Helvetica', 10)
            for m, r, e in zip(labels, revenue, expenses):
                if y < 40:
                    c.showPage(); y = height - 40; c.setFont('Helvetica-Bold', 11)
                    c.drawString(40, y, _('Month')); c.drawString(200, y, _('Revenue')); c.drawString(320, y, _('Expenses')); c.drawString(440, y, _('Profit'))
                    y -= 14; c.setFont('Helvetica', 10)
                c.drawString(40, y, m); c.drawRightString(300, y, f"{r:,.3f}"); c.drawRightString(420, y, f"{e:,.3f}"); c.drawRightString(540, y, f"{(r-e):,.3f}"); y -= 12
            c.showPage(); c.save(); buf.seek(0)
            return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='monthly_pl.pdf')
        
        
    if report_type == 'monthly' and export == 'xlsx':
        wb = Workbook(); ws = wb.active; ws.title = 'Monthly P&L'; ws.append([_('Month'),_('Revenue'),_('Expenses'),_('Profit')])
        for m, r, e in zip(labels, revenue, expenses): ws.append([m, r, e, r-e])
        buf = BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='monthly_pl.xlsx')

    if report_type == 'by_client':
        # Aggregate invoices by client
        rows = db.session.query(Customer.company_name, db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).\
            join(Invoice, Invoice.customer_id == Customer.id, isouter=True).group_by(Customer.company_name).order_by(Customer.company_name.asc()).all()
        data = [(name or '-', float(total or 0)) for name, total in rows]
        if export == 'xlsx':
            wb = Workbook(); ws = wb.active; ws.title = 'Invoices by Client'; ws.append([_('Client'), _('Total (OMR)')])
            for n, t in data: ws.append([n, t])
            buf = BytesIO(); wb.save(buf); buf.seek(0)
            return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='invoices_by_client.xlsx')
        if export == 'pdf':
            buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4; y = height - 40
            c.setFont('Helvetica-Bold', 16); c.drawString(40, y, _('Invoices by Client')); y -= 20; c.setFont('Helvetica', 10)
            for n, t in data:
                if y < 40: c.showPage(); y = height - 40; c.setFont('Helvetica', 10)
                c.drawString(40, y, n); c.drawRightString(550, y, f"{t:,.3f}"); y -= 14
            c.showPage(); c.save(); buf.seek(0)
            return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='invoices_by_client.pdf')
        return render_template('accounting/reports.html', report_type='by_client', table=data)

    if report_type == 'taxes':
        # Monthly customs and VAT
        labels, customs_m, vat_m = [], [], []
        dt = datetime(now.year, now.month, 1)
        for _ in range(12):
            start = dt
            end = datetime(dt.year + 1, 1, 1) if dt.month == 12 else datetime(dt.year, dt.month + 1, 1)
            labels.append(dt.strftime('%b %Y'))
            customs = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.customs_omr), 0)).\
                filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            vat = db.session.query(db.func.coalesce(db.func.sum(InternationalCost.vat_omr), 0)).\
                filter(InternationalCost.created_at >= start, InternationalCost.created_at < end).scalar() or 0
            customs_m.append(float(customs)); vat_m.append(float(vat))
            if dt.month == 1: dt = datetime(dt.year - 1, 12, 1)
            else: dt = datetime(dt.year, dt.month - 1, 1)
        labels, customs_m, vat_m = list(reversed(labels)), list(reversed(customs_m)), list(reversed(vat_m))
        if export == 'xlsx':
            wb = Workbook(); ws = wb.active; ws.title = 'Taxes'; ws.append([_('Month'), _('Customs (OMR)'), _('VAT (OMR)')])
            for m, cst, vt in zip(labels, customs_m, vat_m): ws.append([m, cst, vt])
            buf = BytesIO(); wb.save(buf); buf.seek(0)
            return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='taxes.xlsx')
        if export == 'pdf':
            buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4; y = height - 40
            c.setFont('Helvetica-Bold', 16); c.drawString(40, y, _('Customs & VAT by Month')); y -= 20; c.setFont('Helvetica', 10)
            for m, cst, vt in zip(labels, customs_m, vat_m):
                if y < 40: c.showPage(); y = height - 40; c.setFont('Helvetica', 10)
                c.drawString(40, y, m); c.drawRightString(320, y, f"{cst:,.3f}"); c.drawRightString(560, y, f"{vt:,.3f}"); y -= 14
            c.showPage(); c.save(); buf.seek(0)
            return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name='taxes.pdf')
        return render_template('accounting/reports.html', report_type='taxes', chart={"months": labels, "customs": customs_m, "vat": vat_m})

    # default monthly
    return render_template('accounting/reports.html', report_type='monthly', chart={"months": labels, "revenue": revenue, "expenses": expenses})


# Accounting Settings (Accountant scope)
@acct_bp.route('/settings', methods=['GET','POST'])
@role_required('accountant', 'admin')
def settings():
    settings_row = db.session.query(Setting).first()
    if not settings_row:
        settings_row = Setting(customs_rate=0, vat_rate=0, shipping_fee=0, insurance_rate=0)
        db.session.add(settings_row)
        db.session.commit()
    if request.method == 'POST':
        try:
            settings_row.customs_rate = float(request.form.get('customs_rate') or 0)
            settings_row.vat_rate = float(request.form.get('vat_rate') or 0)
            settings_row.shipping_fee = float(request.form.get('shipping_fee') or 0)
            settings_row.insurance_rate = float(request.form.get('insurance_rate') or 0)
            db.session.commit(); flash('Settings saved', 'success')
        except Exception:
            db.session.rollback(); flash('Failed to save', 'danger')
    return render_template('accounting/settings.html', settings=settings_row)
