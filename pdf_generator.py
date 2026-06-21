import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


# TWO-PASS CANVAS FOR PROFESSIONAL PAGE NUMBERING ("Page X of Y")

class NumberedCanvas(canvas.Canvas):
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
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Draw Running Header
        self.drawString(54, 750, "VendorIQ Intelligence Platform — Confidential Report")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Draw Running Footer
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        self.restoreState()



# MAIN GENERATOR FUNCTION

def generate_pdf(result, filename="vendor_report.pdf"):
    # Target standard printing dimensions with clean 0.75 in margins
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=72,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Define cohesive, high-end design palette styling rules
    PRIMARY_COLOR = colors.HexColor("#0F172A")    # Slate 900
    SECONDARY_COLOR = colors.HexColor("#0284C7")  # Sky 600
    TEXT_COLOR = colors.HexColor("#334155")       # Slate 700
    
    # Custom Typography Layout Hierarchies 
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=PRIMARY_COLOR,
        alignment=0,
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=PRIMARY_COLOR,
        spaceBefore=16,
        spaceAfter=8,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=TEXT_COLOR,
        spaceAfter=4
    )
    
    bold_label_style = ParagraphStyle(
        'BoldLabel',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=PRIMARY_COLOR
    )

    elements = []

    # 1. DOCUMENT TITLE & IDENTIFIER
    elements.append(Paragraph("Vendor Intelligence Report", title_style))
    elements.append(Spacer(1, 10))

    # 2. COMPANY PROFILE SECTION
    profile = result.get("company_profile", {})
    elements.append(Paragraph("Company Profile", h2_style))
    
    profile_data = [
        [Paragraph("Vendor Entity Name:", bold_label_style), Paragraph(str(profile.get('industry', 'N/A')), body_style)],
        [Paragraph("Executive Leadership (CEO):", bold_label_style), Paragraph(str(profile.get('ceo', 'N/A')), body_style)],
        [Paragraph("Corporate Origins / Founder:", bold_label_style), Paragraph(str(profile.get('founder', 'N/A')), body_style)],
        [Paragraph("Incorporation Calendar Year:", bold_label_style), Paragraph(str(profile.get('founded', 'N/A')), body_style)],
        [Paragraph("Global Administrative Hub:", bold_label_style), Paragraph(str(profile.get('headquarters', 'N/A')), body_style)]
    ]
    
    profile_table = Table(profile_data, colWidths=[180, 324])
    profile_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
    ]))
    elements.append(profile_table)
    elements.append(Spacer(1, 10))

    # 3. RISK METRICS SUMMARY TABLE
    risk_scores = result.get("risk_scores", {})
    elements.append(Paragraph("Risk Scores Assessment", h2_style))
    
    score_headers = [Paragraph("Risk Dimension Category", bold_label_style), Paragraph("Evaluated Metric Score", bold_label_style)]
    score_rows = [score_headers]
    
    for category, val in risk_scores.items():
        score_rows.append([
            Paragraph(category.replace('_', ' ').capitalize(), body_style),
            Paragraph(f"<b>{val}</b> / 100", body_style)
        ])
        
    score_table = Table(score_rows, colWidths=[250, 254])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    elements.append(score_table)
    elements.append(Spacer(1, 10))

 # 4. COMPREHENSIVE RISK ANALYSIS EXPLANATIONS WITH AUDIT LINKS
    explanations = result.get("explanations", {})
    evidence_links = result.get("evidence_links", {})
    
    if explanations:
        elements.append(Paragraph("Granular Risk Analysis & Sources", h2_style))
        for category, detail in explanations.items():
            elements.append(Paragraph(f"<b>{category.replace('_', ' ').capitalize()} Analysis</b>", bold_label_style))
            elements.append(Paragraph(str(detail), body_style))
            
            # Extract links and append directly beneath the paragraph block
            links = evidence_links.get(category, [])
            if links:
                links_str = "<b>Verified Evidence Sources:</b> " + ", ".join(links)
                elements.append(Paragraph(links_str, ParagraphStyle('LinkStyle', parent=body_style, fontSize=8, textColor=SECONDARY_COLOR)))
                
            elements.append(Spacer(1, 8))

    # 5. ACTIONABLE MITIGATION RECOMMENDATIONS
    recommendations = result.get("recommendations", [])
    if recommendations:
        elements.append(Paragraph("Strategic Risk Mitigation Actions", h2_style))
        rec_rows = []
        for index, item in enumerate(recommendations, 1):
            rec_rows.append([
                Paragraph(f"<b>{index}.</b>", bold_label_style),
                Paragraph(str(item), body_style)
            ])
            
        rec_table = Table(rec_rows, colWidths=[20, 484])
        rec_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(rec_table)

    # Build document via our dynamic numbering tracking canvas
    doc.build(elements, canvasmaker=NumberedCanvas)
    return filename