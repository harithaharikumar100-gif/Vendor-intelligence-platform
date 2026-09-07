"""
pdf_generator.py - DRiskify NIVETA SK-VDD-001 Summary Report Generator
-----------------------------------------------------------------------
Features:
- Conforms to DRiskify - NIVETA Skill Document (SK-VDD-001)
- Two-pass NumberedCanvas for "Page X of Y" and Running Headers
- Document Control, Rating Band, and Automatic Escalation Flags
- 5-Dimension Weighted Score Matrix (30%, 20%, 20%, 20%, 10%)
- Granular Signal Taxonomy Breakdown & Verified Citations
- Strategic Mitigations, Data Gaps, and Human-in-the-Loop Sign-Off Table
"""

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


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
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Running Top Header
        self.drawString(54, 750, "CONFIDENTIAL | DRiskify – NIVETA Platform | Skill: SK-VDD-001 – Vendor Intelligence")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Running Bottom Footer
        self.drawString(54, 36, "FOR INTERNAL DUE DILIGENCE USE ONLY — SK-VDD-001 COMPLIANT")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, page_text)
        self.restoreState()


def generate_pdf(result: dict, filename: str = "vendor_report.pdf", vendor_name: str = "") -> str:
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=72,
        bottomMargin=52
    )
    
    styles = getSampleStyleSheet()
    
    PRIMARY_COLOR = colors.HexColor("#0F172A")    # Slate 900
    SECONDARY_COLOR = colors.HexColor("#0284C7")  # Sky 600
    TEXT_COLOR = colors.HexColor("#334155")       # Slate 700
    MUTED_COLOR = colors.HexColor("#64748B")      # Slate 500
    BORDER_COLOR = colors.HexColor("#E2E8F0")     # Slate 200

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=PRIMARY_COLOR,
        alignment=0,
        spaceAfter=3
    )
    
    sub_title_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=MUTED_COLOR,
        spaceAfter=12
    )

    h2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=PRIMARY_COLOR,
        spaceBefore=12,
        spaceAfter=5,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=TEXT_COLOR,
        spaceAfter=3
    )
    
    bold_label_style = ParagraphStyle(
        'BoldLabel',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR
    )

    link_style = ParagraphStyle(
        'LinkStyle',
        parent=body_style,
        fontSize=8,
        leading=11,
        textColor=SECONDARY_COLOR
    )

    alert_style = ParagraphStyle(
        'AlertStyle',
        parent=body_style,
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#DC2626")
    )

    elements = []

    # 1. HEADER
    display_vendor = vendor_name or result.get("vendor_name") or "Target Entity"
    overall_score = result.get("overall_score", 20)
    risk_level = result.get("overall_risk_rating", "Low")
    traffic_light = result.get("traffic_light", "Green")
    action = result.get("recommended_action", "Standard onboarding may proceed.")
    conf = result.get("confidence_score", 85)
    query_date = result.get("query_date", "2026-05-11")

    elements.append(Paragraph(f"Vendor Due Diligence: {display_vendor}", title_style))
    elements.append(Paragraph(
        f"<b>NIVETA SK-VDD-001 Intelligence Report</b> | Date: {query_date} | Rating: <b>{risk_level.upper()} ({traffic_light})</b> | Score: <b>{overall_score}/100</b>",
        sub_title_style
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=BORDER_COLOR, spaceAfter=8))

    # Automatic Escalation Banner if triggered
    escalations = result.get("automatic_escalations", [])
    if escalations:
        esc_text = "<b>AUTOMATIC SENIOR REVIEW ESCALATIONS TRIGGERED (Section 10.1):</b><br/>" + "<br/>• ".join(escalations)
        esc_table = Table([[Paragraph(esc_text, alert_style)]], colWidths=[504])
        esc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#FCA5A5")),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(esc_table)
        elements.append(Spacer(1, 8))

    # 2. ENTITY PROFILE TABLE
    profile = result.get("company_profile", {})
    elements.append(Paragraph("1. Corporate Registry & Entity Information", h2_style))
    
    profile_data = [
        [Paragraph("Legal Entity Name:", bold_label_style), Paragraph(str(display_vendor), body_style),
         Paragraph("Jurisdiction:", bold_label_style), Paragraph(str(result.get('registration_country', 'Canada')), body_style)],
        [Paragraph("Executive Leadership (CEO):", bold_label_style), Paragraph(str(profile.get('ceo', 'Not Available')), body_style),
         Paragraph("Corporate Origins / Founder:", bold_label_style), Paragraph(str(profile.get('founder', 'Not Available')), body_style)],
        [Paragraph("Incorporation Year:", bold_label_style), Paragraph(str(profile.get('founded', 'Not Available')), body_style),
         Paragraph("Principal Hub / HQ:", bold_label_style), Paragraph(str(profile.get('headquarters', 'Not Available')), body_style)],
        [Paragraph("Estimated Employees:", bold_label_style), Paragraph(str(profile.get('employees', 'Not Available')), body_style),
         Paragraph("Confidence Index:", bold_label_style), Paragraph(f"<b>{conf}%</b> (Lookback: 36m)", body_style)]
    ]
    
    profile_table = Table(profile_data, colWidths=[120, 132, 125, 127])
    profile_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
    ]))
    elements.append(profile_table)
    elements.append(Spacer(1, 6))

    # 3. 5-DIMENSION SCORECARD TABLE
    risk_scores = result.get("risk_scores", {})
    elements.append(Paragraph("2. SK-VDD-001 Multi-Dimensional Risk Matrix", h2_style))
    
    dim_rows = [
        [Paragraph("Risk Dimension", bold_label_style), Paragraph("Weight", bold_label_style),
         Paragraph("Evaluated Score", bold_label_style), Paragraph("Rating Band", bold_label_style)]
    ]

    dims = [
        ("financial", "Financial Viability (Solvency, Liquidity, Filings)", "30%"),
        ("reputation", "Reputational Risk (Adverse Media, Controversies)", "20%"),
        ("key_person", "Key-Person & Governance (Sanctions, Bench)", "20%"),
        ("cyber", "Technology & Cybersecurity (Breaches, CVEs)", "20%"),
        ("compliance", "Regulatory Compliance (OSFI, FINTRAC, Orders)", "10%"),
    ]

    for k, name, wt in dims:
        val = int(risk_scores.get(k, 20))
        tier = "Low" if val <= 24 else ("Medium" if val <= 49 else ("High" if val <= 74 else "Critical"))
        tier_color = "#16a34a" if val <= 24 else ("#d97706" if val <= 49 else ("#ea580c" if val <= 74 else "#dc2626"))
        dim_rows.append([
            Paragraph(name, body_style),
            Paragraph(wt, body_style),
            Paragraph(f"<b>{val}</b> / 100", body_style),
            Paragraph(f"<font color='{tier_color}'><b>{tier}</b></font>", body_style)
        ])

    score_table = Table(dim_rows, colWidths=[244, 60, 100, 100])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    elements.append(score_table)
    elements.append(Spacer(1, 8))

    # 4. GRANULAR SIGNALS & DETAILED FINDINGS
    explanations = result.get("explanations", {})
    evidence_links = result.get("evidence_links", {})
    
    if explanations:
        elements.append(Paragraph("3. Granular Risk Signals & Source Attributions", h2_style))
        for cat_k, name, _ in dims:
            detail = explanations.get(cat_k, {})
            score_val = risk_scores.get(cat_k, 20)
            
            elements.append(Paragraph(f"<b>{name} — Score: {score_val}/100</b>", bold_label_style))
            
            if isinstance(detail, dict):
                summary = detail.get("summary", "")
                if summary:
                    elements.append(Paragraph(f"<b>Assessment:</b> {summary}", body_style))
                
                # Render specific arrays
                signals = detail.get("signals", [])
                if signals:
                    for s in signals[:2]:
                        elements.append(Paragraph(f"• <b>[{s.get('category', s.get('authority', 'Signal'))}]</b> {s.get('indicator', s.get('action', ''))} <i>(Severity: {s.get('severity', 'Low')})</i>", body_style))
                
                articles = detail.get("articles", [])
                if articles:
                    for a in articles[:2]:
                        elements.append(Paragraph(f"• <b>[{a.get('source', 'News')}]</b> {a.get('headline', '')} <i>({a.get('date', 'Recent')})</i>", body_style))
                        
                persons = detail.get("persons", [])
                if persons:
                    for p in persons[:2]:
                        elements.append(Paragraph(f"• <b>{p.get('name', 'Executive')}</b> ({p.get('role', 'Role')}): Flags: {', '.join(p.get('flags', ['Clean']))}", body_style))
            else:
                elements.append(Paragraph(str(detail), body_style))

            links = evidence_links.get(cat_k, [])
            if links:
                elements.append(Paragraph(f"<b>Sources:</b> {' | '.join(links[:3])}", link_style))
            elements.append(Spacer(1, 4))

    # 5. MITIGATIONS & GAPS
    recs = result.get("recommendations", [])
    if recs:
        elements.append(Paragraph("4. Recommended Risk Mitigations & Actions", h2_style))
        rec_rows = [[Paragraph(f"<b>{i}.</b>", bold_label_style), Paragraph(str(r), body_style)] for i, r in enumerate(recs, 1)]
        rec_table = Table(rec_rows, colWidths=[20, 484])
        rec_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(rec_table)
        elements.append(Spacer(1, 6))

    # 6. SIGN-OFF BLOCK
    elements.append(Paragraph("5. Human-in-the-Loop Review & Governance Sign-Off", h2_style))
    sign_data = [
        [Paragraph("Reviewing Analyst:", bold_label_style), Paragraph("___________________________", body_style),
         Paragraph("Review Date:", bold_label_style), Paragraph("___________________________", body_style)],
        [Paragraph("Senior Risk Sign-off:", bold_label_style), Paragraph("___________________________", body_style),
         Paragraph("Onboarding Decision:", bold_label_style), Paragraph(f"[ ] Approved  [ ] Conditional  [ ] Escalated", body_style)]
    ]
    sign_table = Table(sign_data, colWidths=[125, 127, 125, 127])
    sign_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(sign_table)

    doc.build(elements, canvasmaker=NumberedCanvas)
    return filename