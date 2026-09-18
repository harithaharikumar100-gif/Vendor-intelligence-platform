"""
pdf_generator.py - DRiskify NIVETA SK-VDD-001 Summary Report Generator
-----------------------------------------------------------------------
Features:
- Conforms to DRiskify - NIVETA Skill Document (SK-VDD-001)
- Two-pass NumberedCanvas for "Page X of Y" and running headers/footers
- Cover page with a visual risk meter, entity snapshot, and scope/escalation notices
- 5-Dimension Weighted Score Matrix with tier-colored severity bars
- Full point-by-point risk factor breakdown per dimension (not truncated) with
  source attributions, matching the web UI's risk-factor list format
- Data gaps, licensed-source disclosures, mitigations, and human-in-the-loop sign-off
"""

from xml.sax.saxutils import escape as _xml_escape

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def _esc(text) -> str:
    """
    Escapes &, <, > before interpolating free text (AI-generated summaries,
    headlines, person names, etc.) into a ReportLab Paragraph's mini-XML
    markup. Without this, text containing "R&D", "M&A", "AT&T", or any
    literal '<'/'>' would break the parser and crash PDF generation entirely.
    """
    if text is None:
        return ""
    return _xml_escape(str(text))

# ── Design tokens — same monochrome-with-severity-accent language as the web UI ──
INK_900 = colors.HexColor("#0a0a0a")
INK_700 = colors.HexColor("#3a3a3a")
INK_500 = colors.HexColor("#6b6b6b")
INK_300 = colors.HexColor("#a3a3a3")
BORDER = colors.HexColor("#e5e5e5")
SURFACE_TINT = colors.HexColor("#fafafa")

TIER_COLORS = {
    "Low": colors.HexColor("#16a34a"),
    "Medium": colors.HexColor("#ca8a04"),
    "High": colors.HexColor("#ea580c"),
    "Critical": colors.HexColor("#dc2626"),
}

SEVERITY_COLORS = {
    "Low": INK_500,
    "Elevated": colors.HexColor("#ca8a04"),
    "High": colors.HexColor("#ea580c"),
    "Critical": colors.HexColor("#dc2626"),
}


def _tier_for(score: int) -> str:
    return "Low" if score <= 24 else ("Medium" if score <= 49 else ("High" if score <= 74 else "Critical"))


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for dynamic page numbers and running header/footer."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # cover page carries its own footer, drawn separately
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(INK_500)
        self.drawString(54, 750, "CONFIDENTIAL  ·  DRiskify — NIVETA Platform  ·  Skill SK-VDD-001")
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        self.drawString(54, 36, "FOR INTERNAL DUE DILIGENCE USE ONLY")
        self.drawRightString(558, 36, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _draw_score_meter(c, x, y, width, height, score, tier_color):
    """A horizontal risk meter: track + filled bar + numeric label, drawn directly on canvas."""
    c.saveState()
    radius = height / 2
    c.setFillColor(colors.HexColor("#e5e5e5"))
    c.roundRect(x, y, width, height, radius, stroke=0, fill=1)
    fill_w = max(height, width * (score / 100.0))
    c.setFillColor(tier_color)
    c.roundRect(x, y, fill_w, height, radius, stroke=0, fill=1)
    c.restoreState()


def _cover_page(c, doc_width, doc_height, result, display_vendor, overall_score, risk_level, traffic_light, conf, query_date):
    tier_color = TIER_COLORS.get(risk_level, TIER_COLORS["Low"])
    page_w, page_h = letter

    # Top accent band
    c.setFillColor(INK_900)
    c.rect(0, page_h - 8, page_w, 8, stroke=0, fill=1)

    c.setFillColor(INK_900)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(54, page_h - 60, "DRiskify")
    c.setFont("Helvetica", 9)
    c.setFillColor(INK_500)
    c.drawString(54, page_h - 74, "NIVETA Platform  ·  Skill SK-VDD-001  ·  Vendor Intelligence Scraping for Due Diligence")

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.75)
    c.line(54, page_h - 92, 558, page_h - 92)

    # Title block
    c.setFillColor(INK_900)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(54, page_h - 150, "Vendor Due Diligence Report")
    c.setFont("Helvetica", 15)
    c.setFillColor(INK_700)
    c.drawString(54, page_h - 176, str(display_vendor))
    c.setFont("Helvetica", 9.5)
    c.setFillColor(INK_500)
    c.drawString(54, page_h - 194, f"Report generated {query_date}  ·  Canada Vendor Due Diligence  ·  Confidential")

    # Score meter block
    meter_y = page_h - 280
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(tier_color)
    c.drawString(54, meter_y, f"{overall_score}")
    c.setFont("Helvetica", 13)
    c.setFillColor(INK_500)
    c.drawString(54 + c.stringWidth(f"{overall_score}", "Helvetica-Bold", 48) + 4, meter_y + 10, "/ 100")

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(tier_color)
    c.drawString(54, meter_y - 22, f"{risk_level.upper()} RISK  ·  {traffic_light.upper()}")

    _draw_score_meter(c, 54, meter_y - 42, 300, 8, overall_score, tier_color)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(INK_500)
    c.drawString(54, meter_y - 56, f"Data confidence: {conf}%  ·  36-month lookback horizon")

    action = result.get("recommended_action", "")
    if action:
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(INK_900)
        c.drawString(54, meter_y - 84, "Recommended action")
        c.setFont("Helvetica", 9.5)
        c.setFillColor(INK_700)
        _wrap_text_on_canvas(c, action, 54, meter_y - 98, 500, 12)

    # Scope / jurisdiction notice (only if not a clean confirmed-Canadian run)
    jurisdiction_gate = result.get("jurisdiction_gate", "confirmed_canadian")
    run_status = result.get("run_status", "complete")
    y_cursor = meter_y - 140
    if jurisdiction_gate != "confirmed_canadian" or run_status != "complete":
        c.setFillColor(colors.HexColor("#fef2f2"))
        c.roundRect(54, y_cursor - 34, 504, 40, 4, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#dc2626"))
        c.setFont("Helvetica-Bold", 8.5)
        gate_label = {
            "out_of_scope_non_canada": "OUT OF SKILL SCOPE — this vendor's jurisdiction is outside SK-VDD-001 Section 2.2's Canadian scope.",
            "unconfirmed_canadian_registration": "JURISDICTION UNCONFIRMED — no CBCA or provincial registry evidence found (Section 10.2).",
        }.get(jurisdiction_gate, "RUN INCOMPLETE — see automatic escalations below.")
        c.drawString(64, y_cursor - 15, gate_label)
        y_cursor -= 50

    # Automatic escalations on cover
    escalations = result.get("automatic_escalations", [])
    if escalations:
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColor(INK_900)
        c.drawString(54, y_cursor, f"Automatic senior review escalations ({len(escalations)})  ·  Section 10.1")
        y_cursor -= 16
        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.HexColor("#dc2626"))
        for esc in escalations[:6]:
            c.drawString(64, y_cursor, "•")
            _wrap_text_on_canvas(c, esc, 74, y_cursor, 480, 11)
            lines = max(1, len(esc) // 105 + 1)
            y_cursor -= 11 * lines + 3

    # Footer for cover page
    c.setFont("Helvetica", 8)
    c.setFillColor(INK_500)
    c.drawString(54, 36, "FOR INTERNAL DUE DILIGENCE USE ONLY")
    c.drawRightString(558, 36, "Page 1")


def _wrap_text_on_canvas(c, text, x, y, max_width, line_height):
    words = text.split()
    line = ""
    cy = y
    for w in words:
        trial = f"{line} {w}".strip()
        if c.stringWidth(trial, c._fontname, c._fontsize) > max_width and line:
            c.drawString(x, cy, line)
            cy -= line_height
            line = w
        else:
            line = trial
    if line:
        c.drawString(x, cy, line)


def generate_pdf(result: dict, filename: str = "vendor_report.pdf", vendor_name: str = "") -> str:
    styles = getSampleStyleSheet()

    h2_style = ParagraphStyle(
        'SectionHeader', parent=styles['Heading2'], fontName='Helvetica-Bold',
        fontSize=13, leading=16, textColor=INK_900, spaceBefore=16, spaceAfter=6, keepWithNext=True
    )
    h3_style = ParagraphStyle(
        'SubHeader', parent=styles['Heading3'], fontName='Helvetica-Bold',
        fontSize=10.5, leading=13, textColor=INK_900, spaceBefore=10, spaceAfter=3, keepWithNext=True
    )
    body_style = ParagraphStyle(
        'BodyTextCustom', parent=styles['Normal'], fontName='Helvetica',
        fontSize=9, leading=13, textColor=INK_700, spaceAfter=3
    )
    muted_style = ParagraphStyle('Muted', parent=body_style, textColor=INK_500, fontSize=8.5)
    bold_label_style = ParagraphStyle('BoldLabel', parent=body_style, fontName='Helvetica-Bold', textColor=INK_900)
    link_style = ParagraphStyle('LinkStyle', parent=body_style, fontSize=7.5, leading=10, textColor=INK_500)

    elements = []

    display_vendor = vendor_name or result.get("vendor_name") or "Target Entity"
    overall_score = result.get("overall_score", 20)
    risk_level = result.get("overall_risk_rating", "Low")
    traffic_light = result.get("traffic_light", "Green")
    conf = result.get("confidence_score", 85)
    query_date = result.get("query_date", "")
    risk_scores = result.get("risk_scores", {})
    profile = result.get("company_profile", {})

    # Cover page is drawn directly on the canvas via onFirstPage (below) rather
    # than as a Platypus flowable — a flowable's draw() runs in a coordinate
    # frame already translated to its position on the page, so absolute
    # page-coordinate drawing (used for the full-bleed cover layout) would be
    # misplaced if done that way. A leading PageBreak keeps page 1 empty of
    # normal flowable content while still triggering the onFirstPage callback.
    elements.append(PageBreak())

    # ── 1. CORPORATE REGISTRY & ENTITY INFORMATION ──
    elements.append(Paragraph("1. Corporate Registry &amp; Entity Information", h2_style))
    profile_data = [
        [Paragraph("Legal entity name", muted_style), Paragraph(_esc(display_vendor), bold_label_style),
         Paragraph("Jurisdiction", muted_style), Paragraph(_esc(result.get('registration_country', 'Canada')), bold_label_style)],
        [Paragraph("Executive leadership (CEO)", muted_style), Paragraph(_esc(profile.get('ceo', 'Not Available')), body_style),
         Paragraph("Founder", muted_style), Paragraph(_esc(profile.get('founder', 'Not Available')), body_style)],
        [Paragraph("Incorporation year", muted_style), Paragraph(_esc(profile.get('founded', 'Not Available')), body_style),
         Paragraph("Headquarters", muted_style), Paragraph(_esc(profile.get('headquarters', 'Not Available')), body_style)],
        [Paragraph("Estimated employees", muted_style), Paragraph(_esc(profile.get('employees', 'Not Available')), body_style),
         Paragraph("CRA business number", muted_style), Paragraph(_esc(result.get('business_number') or 'Not provided'), body_style)],
    ]
    if result.get("duns_number") or result.get("naics_code"):
        profile_data.append([
            Paragraph("D&amp;B D-U-N-S number", muted_style), Paragraph(_esc(result.get('duns_number') or 'Not provided'), body_style),
            Paragraph("NAICS code", muted_style), Paragraph(_esc(result.get('naics_code') or 'Not provided'), body_style),
        ])
    profile_table = Table(profile_data, colWidths=[110, 142, 110, 142])
    profile_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f1f1")),
    ]))
    elements.append(profile_table)

    fm = profile.get("financial_metrics")
    if fm:
        elements.append(Paragraph("Verified financial ratios (yfinance / public disclosures)", h3_style))
        fm_rows = [[Paragraph(_esc(k.replace('_', ' ').title()), muted_style), Paragraph(_esc(v), body_style)] for k, v in fm.items()]
        fm_table = Table(fm_rows, colWidths=[130, 374])
        fm_table.setStyle(TableStyle([
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3), ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f1f1")),
        ]))
        elements.append(fm_table)

    # ── 2. RISK MATRIX ──
    elements.append(Paragraph("2. SK-VDD-001 Multi-Dimensional Risk Matrix", h2_style))
    dim_rows = [[
        Paragraph("Risk dimension", bold_label_style), Paragraph("Weight", bold_label_style),
        Paragraph("Score", bold_label_style), Paragraph("Rating", bold_label_style),
    ]]
    dims = [
        ("financial", "Financial Viability", "30%"),
        ("reputation", "Reputational Risk", "20%"),
        ("key_person", "Key-Person & Governance", "20%"),
        ("cyber", "Technology & Cybersecurity", "20%"),
        ("compliance", "Regulatory Compliance", "10%"),
    ]
    row_colors = [colors.white]
    for k, name, wt in dims:
        val = int(risk_scores.get(k, 20))
        tier = _tier_for(val)
        tier_color = TIER_COLORS[tier]
        dim_rows.append([
            Paragraph(name, body_style), Paragraph(wt, body_style),
            Paragraph(f"<b>{val}</b> /100", body_style),
            Paragraph(f"<font color='{_hexstr(tier_color)}'><b>{tier}</b></font>", body_style),
        ])
        row_colors.append(colors.Color(tier_color.red, tier_color.green, tier_color.blue, alpha=0.06))

    score_table = Table(dim_rows, colWidths=[224, 60, 90, 130])
    tstyle = [
        ('BACKGROUND', (0, 0), (-1, 0), SURFACE_TINT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, BORDER),
    ]
    for i, rc in enumerate(row_colors[1:], start=1):
        tstyle.append(('BACKGROUND', (0, i), (-1, i), rc))
        tstyle.append(('LINEBEFORE', (0, i), (0, i), 3, TIER_COLORS[_tier_for(int(risk_scores.get(dims[i-1][0], 20)))]))
    score_table.setStyle(TableStyle(tstyle))
    elements.append(score_table)
    elements.append(PageBreak())

    # ── 3. FULL RISK FACTOR BREAKDOWN (point by point, not truncated) ──
    explanations = result.get("explanations", {})
    evidence_links = result.get("evidence_links", {})

    elements.append(Paragraph("3. Detailed Risk Factor Breakdown", h2_style))
    elements.append(Paragraph(
        "Every risk factor identified for each dimension, listed point by point with severity and source, "
        "per SK-VDD-001 Section 9.1 (source attribution).", muted_style
    ))

    for cat_k, name, wt in dims:
        detail = explanations.get(cat_k, {})
        score_val = int(risk_scores.get(cat_k, 20))
        tier = _tier_for(score_val)
        tier_color = TIER_COLORS[tier]

        block = []
        block.append(Paragraph(
            f"{name} <font color='{_hexstr(tier_color)}'><b>&nbsp;&nbsp;{score_val}/100 · {tier}</b></font>"
            f"&nbsp;&nbsp;<font color='{_hexstr(INK_500)}' size=8>({wt} weight · source: {detail.get('source', 'n/a').replace('_', ' ')})</font>",
            h3_style
        ))

        if isinstance(detail, dict):
            summary = detail.get("summary", "")
            if summary:
                block.append(Paragraph(f"<b>Assessment —</b> {_esc(summary)}", body_style))
                block.append(Spacer(1, 3))

            items = detail.get("signals") or detail.get("articles") or []
            item_kind = "signals" if detail.get("signals") else ("articles" if detail.get("articles") else None)

            if item_kind == "signals" and items:
                for i, s in enumerate(items, 1):
                    sev = s.get("severity", "Low")
                    sev_color = _hexstr(SEVERITY_COLORS.get(sev, INK_500))
                    label = s.get("category") or s.get("authority") or "Signal"
                    text = s.get("indicator") or s.get("action") or ""
                    block.append(Paragraph(
                        f"{i}.&nbsp; <font color='{_hexstr(INK_500)}'>[{_esc(label)}]</font> {_esc(text)} "
                        f"<font color='{sev_color}'><b>{_esc(str(sev).upper())}</b></font>",
                        body_style
                    ))
            elif item_kind == "articles" and items:
                for i, a in enumerate(items, 1):
                    sev = a.get("severity", "Low")
                    sev_color = _hexstr(SEVERITY_COLORS.get(sev, INK_500))
                    block.append(Paragraph(
                        f"{i}.&nbsp; {_esc(a.get('headline', ''))} "
                        f"<font color='{_hexstr(INK_500)}'>— {_esc(a.get('source', 'News'))}, {_esc(a.get('date', 'Recent'))}</font> "
                        f"<font color='{sev_color}'><b>{_esc(str(sev).upper())}</b></font>",
                        body_style
                    ))

            persons = detail.get("persons", [])
            if persons:
                for i, p in enumerate(persons, 1):
                    flags = ', '.join(str(f) for f in p.get('flags', ['Clean']))
                    block.append(Paragraph(
                        f"{i}.&nbsp; <b>{_esc(p.get('name', 'Executive'))}</b> "
                        f"<font color='{_hexstr(INK_500)}'>— {_esc(p.get('role', 'Role'))}</font>: {_esc(flags)}",
                        body_style
                    ))

            links = evidence_links.get(cat_k, [])
            if links:
                block.append(Spacer(1, 2))
                block.append(Paragraph(f"Sources: {_esc(' | '.join(links[:3]))}", link_style))

        else:
            block.append(Paragraph(_esc(detail), body_style))

        block.append(Spacer(1, 8))
        elements.append(KeepTogether(block))

    # ── 4. DATA SOURCES, GAPS & LICENSED-SOURCE DISCLOSURE ──
    elements.append(Paragraph("4. Data Sources, Gaps &amp; Confidence Disclosure", h2_style))

    sources = result.get("data_sources_used", [])
    if sources:
        elements.append(Paragraph("Sources queried this run (Section 5)", h3_style))
        for src in sources:
            elements.append(Paragraph(f"✓ {_esc(src)}", body_style))

    gaps = result.get("data_gaps", [])
    if gaps:
        elements.append(Paragraph("Data gaps &amp; verification items (Section 9.2)", h3_style))
        for i, g in enumerate(gaps, 1):
            elements.append(Paragraph(f"{i}.&nbsp; {_esc(g)}", body_style))

    # ── 5. MITIGATIONS ──
    recs = result.get("recommendations", [])
    if recs:
        elements.append(Paragraph("5. Recommended Risk Mitigations &amp; Actions", h2_style))
        for i, r in enumerate(recs, 1):
            elements.append(Paragraph(f"{i}.&nbsp; {_esc(r)}", body_style))

    # ── 6. SIGN-OFF ──
    elements.append(Paragraph("6. Human-in-the-Loop Review &amp; Governance Sign-Off", h2_style))
    elements.append(Paragraph(
        "This report is advisory. Per SK-VDD-001 Section 9.3, NIVETA does not autonomously approve or "
        "reject a vendor — final onboarding decisions must be made by a qualified human risk analyst.",
        muted_style
    ))
    sign_data = [
        [Paragraph("Reviewing analyst", muted_style), Paragraph("_____________________________", body_style),
         Paragraph("Review date", muted_style), Paragraph("_____________________________", body_style)],
        [Paragraph("Senior risk sign-off", muted_style), Paragraph("_____________________________", body_style),
         Paragraph("Onboarding decision", muted_style), Paragraph("[ ] Approved   [ ] Conditional   [ ] Escalated", body_style)],
    ]
    sign_table = Table(sign_data, colWidths=[110, 142, 110, 142])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(sign_table)

    doc = SimpleDocTemplate(
        filename, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=72, bottomMargin=52
    )

    def _on_first_page(c, _doc):
        page_w, page_h = letter
        _cover_page(c, page_w, page_h, result, display_vendor, overall_score, risk_level, traffic_light, conf, query_date)

    doc.build(elements, canvasmaker=NumberedCanvas, onFirstPage=_on_first_page)
    return filename


def _hexstr(c) -> str:
    return '#%02x%02x%02x' % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))
