"""Generates a formatted PDF budget report (in-memory) from dashboard data."""
import io
from datetime import datetime
import pandas as pd

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTHS_FULL = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

# Palette (match the app)
GREEN = colors.HexColor("#1B4D3E")
INK = colors.HexColor("#1A1A17")
INK_SOFT = colors.HexColor("#5C5A52")
INK_FAINT = colors.HexColor("#8A887E")
SAND = colors.HexColor("#F2F0EB")
LINE = colors.HexColor("#E4E1D9")
CLAY = colors.HexColor("#B44C3C")
GREEN_OK = colors.HexColor("#1B7A4B")


def _money(v):
    return f"${v:,.0f}"


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("GC8Title", parent=ss["Title"], fontName="Helvetica-Bold",
                          fontSize=22, textColor=INK, spaceAfter=2, leading=26))
    ss.add(ParagraphStyle("GC8Sub", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, textColor=INK_FAINT, spaceAfter=2))
    ss.add(ParagraphStyle("GC8H2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                          fontSize=13, textColor=INK, spaceBefore=16, spaceAfter=6))
    ss.add(ParagraphStyle("GC8Body", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, textColor=INK_SOFT, leading=15, spaceAfter=4))
    ss.add(ParagraphStyle("GC8Bullet", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, textColor=INK_SOFT, leading=15, leftIndent=14,
                          spaceAfter=3, bulletIndent=2))
    ss.add(ParagraphStyle("GC8Small", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=8, textColor=INK_FAINT))
    return ss


def _metric_cards(data, styles):
    """A 4-up row of headline figures rendered as a table."""
    cells = [
        ("BUDGET", _money(data["budget"])),
        ("SPENT", _money(data["spent"])),
        ("REMAINING", _money(data["remaining"])),
        ("UTILISATION", f"{data['pct']:.0f}%"),
    ]
    label_style = ParagraphStyle("cl", fontName="Helvetica-Bold", fontSize=7.5,
                                 textColor=INK_FAINT, leading=10)
    value_style = ParagraphStyle("cv", fontName="Helvetica-Bold", fontSize=15,
                                 textColor=INK, leading=18)
    row = []
    for label, value in cells:
        inner = Table([[Paragraph(label, label_style)], [Paragraph(value, value_style)]],
                      colWidths=[1.55 * inch])
        inner.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        row.append(inner)
    t = Table([row], colWidths=[1.7 * inch] * 4)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _table(headers, rows, col_widths, right_cols=(), highlight_over=False, over_col=None):
    header_style = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5,
                                  textColor=colors.white)
    cell_style = ParagraphStyle("td", fontName="Helvetica", fontSize=8.5, textColor=INK_SOFT)
    cell_r = ParagraphStyle("tdr", parent=cell_style, alignment=TA_RIGHT)

    data = [[Paragraph(h, header_style) for h in headers]]
    for r in rows:
        line = []
        for i, val in enumerate(r):
            st = cell_r if i in right_cols else cell_style
            line.append(Paragraph(str(val), st))
        data.append(line)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SAND]),
    ]
    t.setStyle(TableStyle(style))
    return t


def build_report(scope_label, fiscal_year, generated_by, data) -> bytes:
    """
    data = {
      budget, spent, remaining, pct,
      over_rows: [(name, budget, actual, over, pct_over)],   # sorted worst first
      top_rows:  [(name, budget, actual, variance)],         # largest spend lines
      group_rows:[(group, spent)],                            # spend by group
      spent_prev, prev_month_name (optional),
      n_over, n_budgeted, top_name, top_amt, worst_name, worst_over,
    }
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            title=f"GC8 Budget Report — {scope_label} {fiscal_year}")
    ss = _styles()
    story = []

    # Header
    story.append(Paragraph("GC8 Budget Report", ss["GC8Title"]))
    story.append(Paragraph("Grand Colorado on Peak 8 · Housekeeping Operations", ss["GC8Sub"]))
    story.append(Paragraph(f"{scope_label} {fiscal_year}", ss["GC8Sub"]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=LINE))
    story.append(Spacer(1, 12))

    # Headline cards
    story.append(_metric_cards(data, ss))
    story.append(Spacer(1, 6))

    # Executive summary / inferences
    story.append(Paragraph("Summary &amp; findings", ss["GC8H2"]))
    findings = _build_findings(scope_label, data)
    for f in findings:
        story.append(Paragraph(f"• {f}", ss["GC8Bullet"]))

    # Over budget section
    story.append(Paragraph("Categories over budget", ss["GC8H2"]))
    if data["over_rows"]:
        rows = [(n, _money(b), _money(a), _money(o), f"{p:.0f}%")
                for (n, b, a, o, p) in data["over_rows"]]
        story.append(_table(
            ["Category", "Budget", "Actual", "Over by", "% over"],
            rows, [2.3 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 0.75 * inch],
            right_cols=(1, 2, 3, 4)))
    else:
        story.append(Paragraph("No categories are over budget for this period.", ss["GC8Body"]))

    # Largest spend lines
    story.append(Paragraph("Largest spend lines", ss["GC8H2"]))
    if data["top_rows"]:
        rows = [(n, _money(b), _money(a), _money(v))
                for (n, b, a, v) in data["top_rows"]]
        story.append(_table(
            ["Category", "Budget", "Actual", "Variance"],
            rows, [2.6 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch],
            right_cols=(1, 2, 3)))
    else:
        story.append(Paragraph("No spend recorded for this period.", ss["GC8Body"]))

    # Spend by group
    if data["group_rows"]:
        story.append(Paragraph("Spend by group", ss["GC8H2"]))
        rows = [(g, _money(s)) for (g, s) in data["group_rows"]]
        story.append(_table(["Group", "Spent"], rows,
                            [3.5 * inch, 1.5 * inch], right_cols=(1,)))

    # Footer
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 4))
    ts = datetime.now().strftime("%b %d, %Y %I:%M %p")
    story.append(Paragraph(
        f"Generated {ts} MT by {generated_by} · GC8 Budget Tracker", ss["GC8Small"]))

    doc.build(story)
    return buf.getvalue()


def _build_findings(scope_label, data):
    """Turn the numbers into plain-language observations."""
    out = []
    budget, spent, remaining, pct = data["budget"], data["spent"], data["remaining"], data["pct"]

    # Utilisation
    if budget <= 0:
        out.append(f"No budget was set for {scope_label.lower()}.")
    elif remaining < 0:
        out.append(f"Spending is <b>over budget</b> by {_money(abs(remaining))} "
                   f"({pct:.0f}% of the {_money(budget)} budget used).")
    else:
        out.append(f"{_money(spent)} of the {_money(budget)} budget has been used "
                   f"({pct:.0f}%), leaving {_money(remaining)} remaining.")

    # Over-budget categories
    n_over = data.get("n_over", 0)
    n_budgeted = data.get("n_budgeted", 0)
    if n_budgeted:
        if n_over == 0:
            out.append(f"All {n_budgeted} budgeted categories are within budget.")
        else:
            out.append(f"<b>{n_over} of {n_budgeted}</b> budgeted categories are over budget.")
            if data.get("worst_name"):
                out.append(f"The largest overspend is <b>{data['worst_name']}</b>, "
                           f"{_money(data['worst_over'])} over its budget.")

    # Top spend line
    if data.get("top_name") and data.get("top_amt"):
        out.append(f"The highest-spend category is <b>{data['top_name']}</b> "
                   f"at {_money(data['top_amt'])}.")

    # Month-over-month
    if data.get("prev_month_name") and data.get("spent_prev") is not None:
        delta = spent - data["spent_prev"]
        if abs(delta) > 0.01 * max(spent, 1):
            direction = "down" if delta < 0 else "up"
            out.append(f"Spend is <b>{direction} {_money(abs(delta))}</b> "
                       f"versus {data['prev_month_name']}.")

    # Concentration
    if data.get("group_rows"):
        total_grp = sum(s for _, s in data["group_rows"])
        if total_grp > 0:
            top_g, top_s = max(data["group_rows"], key=lambda x: x[1])
            share = top_s / total_grp * 100
            if share >= 40:
                out.append(f"Spending is concentrated in <b>{top_g}</b>, which accounts for "
                           f"{share:.0f}% of the total.")

    return out
