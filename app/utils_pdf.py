from flask import render_template, current_app
import os

def _write_pdf(outpath: str, html_string: str) -> None:
    """Best-effort PDF writer using WeasyPrint if available; otherwise write HTML.

    This keeps the app importable even if binary deps for WeasyPrint are missing.
    """
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string=html_string).write_pdf(outpath)
    except Exception:
        # Fallback: save the HTML so users still get a file; name remains .pdf
        try:
            with open(outpath, 'wb') as f:
                f.write(html_string.encode('utf-8'))
        except Exception:
            # Last resort: ensure directory exists, but ignore write failures silently
            try:
                os.makedirs(os.path.dirname(outpath), exist_ok=True)
            except Exception:
                pass

def render_invoice_pdf(invoice, items, template='pdf/invoice.html'):
    html = render_template(template, invoice=invoice, items=items)
    outdir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'pdfs')
    os.makedirs(outdir, exist_ok=True)
    filename = f"invoice_{invoice.invoice_number}.pdf"
    outpath = os.path.join(outdir, filename)
    _write_pdf(outpath, html)
    return outpath


def render_bol_pdf(bol, vehicles, template='pdf/bol.html'):
    html = render_template(template, bol=bol, vehicles=vehicles)
    outdir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'pdfs')
    os.makedirs(outdir, exist_ok=True)
    filename = f"bol_{bol.bol_number}.pdf"
    outpath = os.path.join(outdir, filename)
    _write_pdf(outpath, html)
    return outpath
