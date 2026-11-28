"""A generated two-page sample PDF for the e-signing demo (synthetic text only; reportlab in invariant mode, so the
same inputs give the same bytes). Page 2 carries the line "Accepted by (customer)" with a ruled line beside it: that
printed text is what `AnchorRule` finds to place the signature."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ANCHOR_TEXT = "Accepted by (customer)"


def sample_pdf(title: str = "Sample Service Agreement") -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    width, height = letter
    pdf.setTitle(title)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(72, height - 96, title)
    pdf.setFont("Helvetica", 11)
    lines = [
        "This is a synthetic document made for a demonstration. It describes no real work, person or place.",
        "",
        "1. Scope. The contractor will perform the sample services listed on the next page.",
        "2. Price. The sample price is 1,000.00 and is payable on completion.",
        "3. Changes. Any change to this agreement must be in writing.",
    ]
    for number, line in enumerate(lines):
        pdf.drawString(72, height - 140 - 18 * number, line)
    pdf.showPage()
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(72, height - 96, "Acceptance")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(72, height - 124, "By signing below the customer accepts the sample agreement on the previous page.")
    y = 190
    pdf.drawString(72, y, ANCHOR_TEXT)
    pdf.line(72 + pdf.stringWidth(ANCHOR_TEXT, "Helvetica", 11) + 8, y - 2, width - 72, y - 2)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
