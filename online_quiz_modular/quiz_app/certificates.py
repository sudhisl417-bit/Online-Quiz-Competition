"""PDF certificate generation and the on-screen certificate preview.

``generate_certificate_pdf`` is a pure function: it receives everything it
needs as arguments (it no longer reads ``st.session_state``), so the same code
can issue a certificate right after an exam *or* later from the history page.
"""

from __future__ import annotations

import io
import math
from typing import Any, Dict

import streamlit as st
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import config
from .ui import html as render_html
from .utils import esc, grade_label, pretty_date, safe_filename

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
NAVY = HexColor("#1B1F4B")
INDIGO = HexColor("#4F46E5")
GOLD = HexColor("#B8892B")
GOLD_LIGHT = HexColor("#E3C77A")
CREAM = HexColor("#FFFDF7")
GREY = HexColor("#5B6475")
LIGHT_GREY = HexColor("#C9CED8")


# --------------------------------------------------------------------------
# Low-level drawing helpers
# --------------------------------------------------------------------------
def _pdf_text(value: Any) -> str:
    """Make text safe for the built-in PDF fonts (Latin-1 / Windows-1252 only).

    Characters the standard fonts cannot draw (e.g. Devanagari, Malayalam,
    Chinese) are replaced by ``?`` instead of printing garbage.
    """
    return str(value or "").encode("cp1252", "replace").decode("cp1252")


def _result_text(percentage: float) -> str:
    """``PASSED`` or ``PASSED - MERIT`` / ``PASSED - DISTINCTION``."""
    level = grade_label(percentage)
    return "PASSED" if level == "Pass" else f"PASSED  -  {level.upper()}"


def _fit_size(pdf: canvas.Canvas, text: str, font: str, max_size: float,
              max_width: float, min_size: float = 12) -> float:
    """Largest font size (<= ``max_size``) at which ``text`` fits ``max_width``."""
    size = max_size
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _tracked(pdf: canvas.Canvas, x_center: float, y: float, text: str,
             font: str, size: float, spacing: float) -> None:
    """Draw letter-spaced text centred on ``x_center``."""
    width = pdf.stringWidth(text, font, size) + spacing * (len(text) - 1)
    obj = pdf.beginText(x_center - width / 2, y)
    obj.setFont(font, size)
    obj.setCharSpace(spacing)
    obj.textOut(text)
    obj.setCharSpace(0)          # character spacing is sticky - always reset it
    pdf.drawText(obj)


def _diamond(pdf: canvas.Canvas, cx: float, cy: float, r: float) -> None:
    path = pdf.beginPath()
    path.moveTo(cx, cy + r)
    path.lineTo(cx + r, cy)
    path.lineTo(cx, cy - r)
    path.lineTo(cx - r, cy)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)


def _star_points(cx: float, cy: float, outer: float, inner: float, points: int):
    """Vertices of a star / starburst polygon."""
    coords = []
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = math.pi / 2 + i * math.pi / points
        coords.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return coords


def _polygon(pdf: canvas.Canvas, coords, fill=1, stroke=0) -> None:
    path = pdf.beginPath()
    path.moveTo(*coords[0])
    for point in coords[1:]:
        path.lineTo(*point)
    path.close()
    pdf.drawPath(path, fill=fill, stroke=stroke)


def _divider(pdf: canvas.Canvas, cx: float, y: float, half_width: float) -> None:
    """Thin gold rule with a diamond in the middle."""
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.8)
    pdf.line(cx - half_width, y, cx - 4 * mm, y)
    pdf.line(cx + 4 * mm, y, cx + half_width, y)
    pdf.setFillColor(GOLD)
    _diamond(pdf, cx, y, 1.8 * mm)


def _seal(pdf: canvas.Canvas, cx: float, cy: float) -> None:
    """Gold rosette with ribbon tails and a star."""
    # ribbon tails (drawn first so the rosette overlaps them)
    pdf.setFillColor(NAVY)
    _polygon(pdf, [(cx - 9 * mm, cy - 8 * mm), (cx - 2 * mm, cy - 11 * mm),
                   (cx - 5 * mm, cy - 20 * mm), (cx - 8 * mm, cy - 17 * mm),
                   (cx - 12 * mm, cy - 19 * mm)])
    pdf.setFillColor(INDIGO)
    _polygon(pdf, [(cx + 9 * mm, cy - 8 * mm), (cx + 2 * mm, cy - 11 * mm),
                   (cx + 5 * mm, cy - 20 * mm), (cx + 8 * mm, cy - 17 * mm),
                   (cx + 12 * mm, cy - 19 * mm)])
    # scalloped rosette
    pdf.setFillColor(GOLD)
    _polygon(pdf, _star_points(cx, cy, 16 * mm, 14 * mm, 28))
    pdf.setFillColor(GOLD_LIGHT)
    pdf.circle(cx, cy, 12.5 * mm, fill=1, stroke=0)
    pdf.setFillColor(NAVY)
    pdf.circle(cx, cy, 10.5 * mm, fill=1, stroke=0)
    pdf.setStrokeColor(GOLD_LIGHT)
    pdf.setLineWidth(0.8)
    pdf.circle(cx, cy, 8.8 * mm, fill=0, stroke=1)
    # star
    pdf.setFillColor(GOLD_LIGHT)
    _polygon(pdf, _star_points(cx, cy, 6.2 * mm, 2.6 * mm, 5))


def _corner_ornaments(pdf: canvas.Canvas, w: float, h: float, inset: float) -> None:
    """Small diamonds and double lines in each corner of the frame."""
    pdf.setFillColor(GOLD)
    for x, y in ((inset, inset), (w - inset, inset), (inset, h - inset), (w - inset, h - inset)):
        _diamond(pdf, x, y, 3.2 * mm)
        pdf.setFillColor(CREAM)
        _diamond(pdf, x, y, 1.4 * mm)
        pdf.setFillColor(GOLD)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def generate_certificate_pdf(
    result: Dict[str, Any],
    student_name: str,
    organization: str = config.DEFAULT_ORGANIZATION,
) -> bytes:
    """Render a landscape A4 certificate and return the PDF bytes.

    ``result`` must contain: subject, score, total, percentage, date and
    certificate_id.
    """
    buffer = io.BytesIO()
    page_w, page_h = landscape(A4)
    cx = page_w / 2

    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"Certificate - {_pdf_text(student_name)}")
    pdf.setAuthor(_pdf_text(organization))
    pdf.setSubject(f"Certificate of Achievement - {_pdf_text(result.get('subject'))}")

    # ---- background ------------------------------------------------------
    pdf.setFillColor(CREAM)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    # faint concentric watermark rings behind the text
    pdf.setStrokeColor(Color(0.72, 0.54, 0.17, alpha=0.07))
    pdf.setLineWidth(1)
    for radius in (30, 48, 66, 84, 102):
        pdf.circle(cx, page_h / 2 - 4 * mm, radius * mm, fill=0, stroke=1)

    # ---- triple frame ----------------------------------------------------
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(5)
    pdf.rect(8 * mm, 8 * mm, page_w - 16 * mm, page_h - 16 * mm, fill=0, stroke=1)
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(1.4)
    pdf.rect(12 * mm, 12 * mm, page_w - 24 * mm, page_h - 24 * mm, fill=0, stroke=1)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(0.6)
    pdf.rect(14.5 * mm, 14.5 * mm, page_w - 29 * mm, page_h - 29 * mm, fill=0, stroke=1)
    _corner_ornaments(pdf, page_w, page_h, 12 * mm)

    # ---- heading ---------------------------------------------------------
    pdf.setFillColor(GREY)
    _tracked(pdf, cx, page_h - 30 * mm, _pdf_text(organization).upper()[:60],
             "Helvetica-Bold", 10.5, 3)

    pdf.setFillColor(NAVY)
    pdf.setFont("Times-Bold", 46)
    pdf.drawCentredString(cx, page_h - 48 * mm, "CERTIFICATE")

    pdf.setFillColor(GOLD)
    _tracked(pdf, cx, page_h - 58 * mm, "OF ACHIEVEMENT", "Helvetica-Bold", 14, 6)
    _divider(pdf, cx, page_h - 64 * mm, 45 * mm)

    # ---- recipient -------------------------------------------------------
    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 14)
    pdf.drawCentredString(cx, page_h - 76 * mm, "This certificate is proudly presented to")

    name = _pdf_text(student_name)[:60]
    name_font = "Times-BoldItalic"
    name_size = _fit_size(pdf, name, name_font, 40, page_w - 80 * mm)
    pdf.setFillColor(NAVY)
    pdf.setFont(name_font, name_size)
    pdf.drawCentredString(cx, page_h - 92 * mm, name)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.line(cx - 75 * mm, page_h - 96 * mm, cx + 75 * mm, page_h - 96 * mm)

    # ---- achievement -----------------------------------------------------
    pdf.setFillColor(GREY)
    pdf.setFont("Times-Italic", 13)
    pdf.drawCentredString(cx, page_h - 108 * mm, "for successfully passing the examination in")

    subject = _pdf_text(result.get("subject"))
    subject_size = _fit_size(pdf, subject, "Helvetica-Bold", 22, page_w - 90 * mm)
    pdf.setFillColor(INDIGO)
    pdf.setFont("Helvetica-Bold", subject_size)
    pdf.drawCentredString(cx, page_h - 120 * mm, subject)

    # ---- three result "chips" -------------------------------------------
    percentage = float(result.get("percentage") or 0)
    chips = [
        ("SCORE", f"{result.get('score')} / {result.get('total')}"),
        ("PERCENTAGE", f"{percentage:.2f}%"),
        ("RESULT", _result_text(percentage)),
    ]
    centers = (cx - 72 * mm, cx, cx + 72 * mm)
    for (label, value), x in zip(chips, centers):
        pdf.setFillColor(GREY)
        _tracked(pdf, x, page_h - 134 * mm, label, "Helvetica-Bold", 8, 2)
        pdf.setFillColor(NAVY)
        font_size = _fit_size(pdf, value, "Helvetica-Bold", 14, 62 * mm, 9)
        pdf.setFont("Helvetica-Bold", font_size)
        pdf.drawCentredString(x, page_h - 142 * mm, value)
    pdf.setStrokeColor(LIGHT_GREY)
    pdf.setLineWidth(0.6)
    for x in (cx - 36 * mm, cx + 36 * mm):
        pdf.line(x, page_h - 146 * mm, x, page_h - 131 * mm)

    # ---- footer: signature | seal | date ---------------------------------
    sig_cx, date_cx = page_w * 0.22, page_w * 0.78
    line_y = 36 * mm
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.8)
    for x in (sig_cx, date_cx):
        pdf.line(x - 28 * mm, line_y, x + 28 * mm, line_y)

    pdf.setFillColor(NAVY)
    pdf.setFont("Times-BoldItalic", 17)
    pdf.drawCentredString(sig_cx, line_y + 2.5 * mm, "Quiz Administrator")
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(date_cx, line_y + 2.5 * mm, pretty_date(result.get("date")))

    pdf.setFillColor(GREY)
    _tracked(pdf, sig_cx, line_y - 5 * mm, "AUTHORIZED SIGNATURE", "Helvetica-Bold", 7, 1.5)
    _tracked(pdf, date_cx, line_y - 5 * mm, "DATE OF ISSUE", "Helvetica-Bold", 7, 1.5)

    _seal(pdf, cx, 44 * mm)

    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawCentredString(cx, 18 * mm, "Certificate ID: " + _pdf_text(result.get("certificate_id")))

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def certificate_filename(student_name: str, subject: str) -> str:
    """File name used for the download button."""
    return f"Certificate_{safe_filename(student_name)}_{safe_filename(subject)}.pdf"


def show_certificate(
    result: Dict[str, Any],
    student_name: str,
    organization: str = config.DEFAULT_ORGANIZATION,
    key: str = "cert",
) -> None:
    """On-screen certificate preview with a PDF download button."""
    percentage = float(result.get("percentage") or 0)

    st.markdown("### 🏆 Your Achievement Certificate")
    render_html(
        f"""
        <div class="qp-cert">
          <div class="qp-cert-inner">
            <div class="qp-cert-org">{esc(organization)}</div>
            <div class="qp-cert-title">Certificate</div>
            <div class="qp-cert-sub">OF ACHIEVEMENT</div>
            <div class="qp-cert-line"></div>
            <div class="qp-cert-small">This certificate is proudly presented to</div>
            <div class="qp-cert-name">{esc(student_name)}</div>
            <div class="qp-cert-small">for successfully passing the examination in</div>
            <div class="qp-cert-subject">{esc(result.get("subject"))}</div>
            <div class="qp-cert-meta">
              <span><b>Score</b> {esc(result.get("score"))} / {esc(result.get("total"))}</span>
              <span><b>Percentage</b> {percentage:.2f}%</span>
              <span><b>Result</b> {esc(_result_text(percentage).replace("  ", " "))}</span>
            </div>
            <div class="qp-cert-foot">
              Issued {esc(pretty_date(result.get("date")))} &nbsp;•&nbsp;
              ID {esc(result.get("certificate_id"))}
            </div>
          </div>
        </div>
        """
    )

    st.download_button(
        label="📜  Download PDF Certificate",
        data=generate_certificate_pdf(result, student_name, organization),
        file_name=certificate_filename(student_name, str(result.get("subject"))),
        mime="application/pdf",
        type="primary",
        key=f"download_{key}",
    )
