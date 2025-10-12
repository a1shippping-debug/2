from weasyprint import HTML
from flask import render_template, current_app
import os

def render_invoice_pdf(invoice, items, template='pdf/invoice.html'):
    html = render_template(template, invoice=invoice, items=items)
    outdir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'pdfs')
    os.makedirs(outdir, exist_ok=True)
    filename = f"invoice_{invoice.invoice_number}.pdf"
    outpath = os.path.join(outdir, filename)
    HTML(string=html).write_pdf(outpath)
    return outpath
