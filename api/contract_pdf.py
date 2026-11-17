import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def fmt_date(val):
    if not val:
        return '—'
    try:
        dt = datetime.fromisoformat(str(val).replace('Z', '+00:00'))
        return dt.strftime('%d %b %Y')
    except Exception:
        return str(val)


def make_contract_pdf(input_data) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=35,
        rightMargin=35,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    navy = colors.HexColor('#09173b')
    blue = colors.HexColor('#0852dc')
    pale = colors.HexColor('#f0f7ff')
    border_color = colors.HexColor('#d0e3f8')

    title_style = ParagraphStyle(
        'ContractTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        textColor=navy,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'ContractSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#4a5568'),
        spaceAfter=15
    )

    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=colors.white,
        spaceBefore=10,
        spaceAfter=10
    )

    body_style = ParagraphStyle(
        'ContractBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1a202c')
    )

    bold_label = ParagraphStyle(
        'BoldLabel',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    story = []

    # Title Banner
    story.append(Paragraph("REWAN TECH SOLUTIONS PVT. LTD.", ParagraphStyle('Brand', fontName='Helvetica-Bold', fontSize=14, textColor=blue)))
    story.append(Paragraph("Social Media Services Agreement", title_style))

    c = input_data.get('customer', {})
    t = input_data.get('terms', {})
    gen_at = input_data.get('generatedAt', '')

    story.append(Paragraph(f"Agreement prepared for <b>{c.get('name') or 'Client'}</b> | Generated: {fmt_date(gen_at)}", subtitle_style))
    story.append(Spacer(1, 10))

    # Section 1: Customer Information
    def make_section_header(title):
        t_data = [[Paragraph(title.upper(), section_style)]]
        t = Table(t_data, colWidths=[525])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), blue),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        return t

    story.append(make_section_header("01  Customer & Business Information"))
    story.append(Spacer(1, 6))

    info_rows = [
        [Paragraph("Client / Business", bold_label), Paragraph(str(c.get('name') or '—'), body_style)],
        [Paragraph("Business Category", bold_label), Paragraph(str(c.get('businessCategory') or '—'), body_style)],
        [Paragraph("Status", bold_label), Paragraph(str(c.get('status') or '—'), body_style)],
        [Paragraph("Account Manager", bold_label), Paragraph(str(c.get('handledBy') or '—'), body_style)],
        [Paragraph("Service Plan", bold_label), Paragraph(str(c.get('planDetails') or '—'), body_style)],
    ]
    info_table = Table(info_rows, colWidths=[150, 375])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), pale),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # Section 2: Commercial Terms
    story.append(make_section_header("02  Contract Period & Commercial Terms"))
    story.append(Spacer(1, 6))

    amount_val = input_data.get('amount', '0.00')
    try:
        formatted_amount = f"INR {float(amount_val):,.2f}"
    except Exception:
        formatted_amount = f"INR {amount_val}"

    comm_rows = [
        [Paragraph("Start Date", bold_label), Paragraph(fmt_date(input_data.get('start')), body_style)],
        [Paragraph("End Date", bold_label), Paragraph(fmt_date(input_data.get('end')), body_style)],
        [Paragraph("Service Fee", bold_label), Paragraph(formatted_amount, body_style)],
        [Paragraph("Billing Frequency", bold_label), Paragraph(str(input_data.get('frequency', '')).upper(), body_style)],
    ]
    comm_table = Table(comm_rows, colWidths=[150, 375])
    comm_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), pale),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(comm_table)
    story.append(Spacer(1, 15))

    # Section 3: Terms & Conditions
    story.append(make_section_header(f"03  Terms & Conditions (Version {t.get('version', 1)})"))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"<b>{t.get('title', '')}</b>", bold_label))
    story.append(Spacer(1, 4))
    for p_line in str(t.get('body', '')).splitlines():
        if p_line.strip():
            story.append(Paragraph(p_line.strip(), body_style))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 25))

    # Signatures
    sig_data = [
        [Paragraph("<b>FOR THE CLIENT</b>", bold_label), Paragraph("<b>FOR REWAN TECH SOLUTIONS</b>", bold_label)],
        [Paragraph("<br/><br/>Signature: ______________________<br/>Name: __________________________<br/>Date: __________________________", body_style),
         Paragraph("<br/><br/>Signature: ______________________<br/>Authorized Signatory: ___________<br/>Date: __________________________", body_style)]
    ]
    sig_table = Table(sig_data, colWidths=[260, 265])
    sig_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), pale),
        ('BOX', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(KeepTogether([sig_table]))

    doc.build(story)
    return buffer.getvalue()
