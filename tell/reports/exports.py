"""Export helpers: JSON, CSV (formula-injection safe) and PDF (ReportLab)."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import pandas as pd

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection by prefixing risky strings with a quote."""
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        # negative numbers formatted as strings are fine: only guard non-numeric
        try:
            float(value)
            return value
        except ValueError:
            return "'" + value
    return value


def df_to_csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(df.columns))
    for row in df.itertuples(index=False):
        writer.writerow([safe_cell(v) for v in row])
    return buf.getvalue()


def findings_csv(report: dict) -> str:
    rows = [{"finding_key": f["finding_key"], "severity": f["severity"], "classification": f["classification"], "status": f["status"],
             "category": f["category"], "title": f["title"], "summary": f["summary"], "period_start": f["period_start"], "period_end": f["period_end"],
             "estimated_impact": f["estimated_impact"], "confidence": f["confidence"], "evidence_rows": len(f["evidence"]), "next_action": f["next_action"]}
            for f in report["findings"]]
    return df_to_csv(pd.DataFrame(rows))


def questions_csv(report: dict) -> str:
    return df_to_csv(pd.DataFrame(report["questions"]))


def reconciliation_csv(report: dict) -> str:
    return df_to_csv(pd.DataFrame(report["reconciliation"]["monthly"]))


def evidence_csv(evidence: pd.DataFrame) -> str:
    return df_to_csv(evidence)


def report_json(report: dict) -> str:
    return json.dumps(report, indent=2, default=str)


def report_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    meta, cur = report["meta"], report["meta"]["currency"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Tell - {meta['brand']} diligence report", author="Tell")
    ss = getSampleStyleSheet()
    ink, accent, muted = colors.HexColor("#24262B"), colors.HexColor("#2F5D50"), colors.HexColor("#6B6F76")
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=ink, alignment=TA_LEFT, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=accent, spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, textColor=ink, spaceBefore=8, spaceAfter=2)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13, textColor=ink)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=11, textColor=muted)

    def esc(s: Any) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def money(v: Any) -> str:
        return "n/a" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{cur} {float(v):,.0f}"

    def table(data: list[list[Any]], widths: list[float] | None = None, header: bool = True) -> Table:
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
        style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("TEXTCOLOR", (0, 0), (-1, -1), ink), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, 0), 0.6, accent), ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E4E1D8")),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4)]
        if header:
            style.append(("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8))
        t.setStyle(TableStyle(style))
        return t

    story: list[Any] = [Paragraph("Tell", ParagraphStyle("brand", parent=small, textColor=accent, fontName="Helvetica-Bold", fontSize=9)),
                        Paragraph(f"{esc(meta['brand'])} - Acquisition diligence report", h1),
                        Paragraph(f"Analysis run {meta['run_id']} | data hash {meta['data_hash']} | engine {meta['engine_version']} | generated {meta['generated_at'][:19]} UTC", small),
                        Spacer(1, 6), Paragraph(esc(meta["disclaimer"]), small), Spacer(1, 10)]

    story.append(Paragraph("1. Executive summary", h2))
    story.append(Paragraph(f"<b>{esc(report['executive_summary']['headline'])}</b>", body))
    for b in report["executive_summary"]["bullets"]:
        story.append(Paragraph("- " + esc(b), body))

    t = report["performance"]["totals"]
    if t:
        story.append(Paragraph("2. Business performance overview", h2))
        story.append(table([["Metric", "Value"], ["Period", f"{t['period_start']} to {t['period_end']}"], ["Completed orders", f"{t['orders_completed']:,}"],
                            ["GMS", money(t["gms"])], ["Discounts", money(t["discounts"])], ["Gross sales", money(t["gross_sales"])], ["Refunds posted", money(t["refunds_posted"])],
                            ["Net sales", money(t["net_sales"])], ["COGS", money(t["cogs"])], ["Gross profit", money(t["gross_profit"])], ["Gross margin", f"{t['gross_margin_pct']:.1f}%"],
                            ["Advertising spend", money(t["ad_spend"])], ["Contribution proxy (GP - ads)", money(t["contribution_proxy"])]], [70 * mm, 90 * mm]))
        story.append(Paragraph("Contribution proxy excludes fulfilment, payroll, payment fees and overheads. It is not EBITDA.", small))
        monthly = report["performance"]["monthly"]
        if monthly:
            rows = [["Month", "Orders", "Gross sales", "Refunds", "Net sales", "GM %", "Ad spend"]]
            rows += [[m["period"], f"{int(m['orders_completed'])}", f"{m['gross_sales']:,.0f}", f"{m['refunds_posted']:,.0f}", f"{m['net_sales']:,.0f}",
                      f"{m['gross_margin_pct']:.1f}" if m.get("gross_margin_pct") is not None else "", f"{m['ad_spend']:,.0f}"] for m in monthly]
            story.append(Spacer(1, 6))
            story.append(table(rows, [22 * mm, 18 * mm, 28 * mm, 24 * mm, 28 * mm, 18 * mm, 26 * mm]))

    rec = report["reconciliation"]
    story.append(Paragraph("3. Revenue reconciliation", h2))
    if rec["monthly"]:
        story.append(Paragraph(f"{rec['months_reported']} months reported by the seller; {rec['months_breaching_threshold']} breach the 2% variance threshold. "
                               f"Reported {money(rec['reported_revenue_total'])} vs supported {money(rec['net_sales_total'])} (variance {money(rec['variance_total'])}).", body))
        rows = [["Month", "Reported", "Gross sales", "Refunds", "Net sales", "Variance", "Var %"]]
        rows += [[m["period"], f"{m['reported_revenue']:,.0f}", f"{m['gross_sales']:,.0f}", f"{m['refunds_posted']:,.0f}", f"{m['net_sales']:,.0f}", f"{m['revenue_variance']:+,.0f}", f"{m['revenue_variance_pct']:+.1f}"] for m in rec["monthly"]]
        story.append(table(rows, [22 * mm, 26 * mm, 26 * mm, 22 * mm, 26 * mm, 24 * mm, 18 * mm]))
    else:
        story.append(Paragraph("No seller-reported revenue available; reconciliation not performed.", body))

    story.append(PageBreak())
    story.append(Paragraph("4. Material findings", h2))
    material = [f for f in report["findings"] if f["classification"] != "observation"]
    observations = [f for f in report["findings"] if f["classification"] == "observation"]
    if not material:
        story.append(Paragraph("No material findings.", body))
    for f in material:
        story.append(Paragraph(f"[{f['severity'].upper()}] {esc(f['title'])}", h3))
        story.append(Paragraph(f"{esc(f['finding_key'])} | {esc(f['category'])} | {esc(f['classification'].replace('_', ' '))} | status: {esc(f['status'].replace('_', ' '))} | impact: {money(f['estimated_impact'])} | confidence: {f['confidence']}", small))
        story.append(Paragraph(esc(f["explanation"]), body))
        story.append(Paragraph(f"<b>Method.</b> {esc(f['method'])}", small))
        if f["impact_basis"]:
            story.append(Paragraph(f"<b>Impact basis.</b> {esc(f['impact_basis'])}", small))
        story.append(Paragraph(f"<b>Evidence.</b> {len(f['evidence'])} record(s): " + esc("; ".join(e["description"] for e in f["evidence"][:4])) + (" ..." if len(f["evidence"]) > 4 else ""), small))
        if f["next_action"]:
            story.append(Paragraph(f"<b>Next step.</b> {esc(f['next_action'])}", small))
    if observations:
        story.append(Paragraph("Observations (informational)", h3))
        for f in observations:
            story.append(Paragraph(f"- {esc(f['title'])}: {esc(f['summary'])}", small))

    story.append(Paragraph("5. Open questions for the seller", h2))
    qs = [q for q in report["questions"] if q.get("status") != "resolved"]
    if qs:
        rows = [["Priority", "Question", "Requested items"]] + [[q["priority"], Paragraph(esc(q["question"]), small), Paragraph(esc(q["requested_items"] or ""), small)] for q in qs]
        story.append(table(rows, [18 * mm, 96 * mm, 60 * mm]))
    else:
        story.append(Paragraph("No open questions.", body))

    story.append(Paragraph("6. Methodology and definitions", h2))
    for k, v in report["methodology"]["definitions"].items():
        story.append(Paragraph(f"<b>{esc(k)}.</b> {esc(v)}", small))

    story.append(Paragraph("7. Data limitations", h2))
    lim = report["data_limitations"]
    story.append(Paragraph(f"Data coverage: {lim['coverage_score']}/100 ({lim['coverage_label']}).", body))
    for s in lim["skipped_analyses"]:
        story.append(Paragraph("- Skipped: " + esc(s), small))
    for s in lim["general"]:
        story.append(Paragraph("- " + esc(s), small))

    story.append(Paragraph("8. Recommended next steps", h2))
    for i, s in enumerate(report["next_steps"], 1):
        story.append(Paragraph(f"{i}. {esc(s)}", body))

    doc.build(story)
    return buf.getvalue()
