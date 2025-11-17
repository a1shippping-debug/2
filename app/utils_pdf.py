import io
from flask import render_template
from .utils.storage import save_file_to_storage


def _render_pdf_bytes(html_string: str) -> bytes:
    try:
        from weasyprint import HTML  # type: ignore
        return HTML(string=html_string).write_pdf()
    except Exception:
        return html_string.encode("utf-8")


def _upload_pdf(filename: str, html_string: str) -> str:
    pdf_bytes = _render_pdf_bytes(html_string)
    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)
    buffer.name = filename
    buffer.filename = filename
    return save_file_to_storage(buffer, folder="pdfs")


def render_invoice_pdf(invoice, items, template="pdf/invoice.html"):
    html = render_template(template, invoice=invoice, items=items)
    filename = f"invoice_{invoice.invoice_number}.pdf"
    return _upload_pdf(filename, html)


def render_bol_pdf(bol, vehicles, template="pdf/bol.html"):
    html = render_template(template, bol=bol, vehicles=vehicles)
    filename = f"bol_{bol.bol_number}.pdf"
    return _upload_pdf(filename, html)


def render_vehicle_statement_pdf(vehicle, statement, totals, template="pdf/vehicle_statement.html"):
    html = render_template(template, vehicle=vehicle, statement=statement, totals=totals)
    filename = f"vehicle_statement_{vehicle.vin or vehicle.id}.pdf"
    return _upload_pdf(filename, html)
