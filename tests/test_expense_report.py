"""Tests for utils/expense_report.py. Run: python -m pytest tests"""
import io
import os
import sys
from datetime import date

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.expense_report import (  # noqa: E402
    NEW, POSSIBLE, RECORDED, ReportItem, ReportParseError, compare_with_existing,
    normalize_vendor, parse_expense_report, resolve_categories,
)


def _report_bytes(lines, total=None, extra_week_rows=0):
    """Build a minimal Emburse-style sheet. `lines` = (m/d/Y, category, amount, vendor, reimb)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    rows = [
        ["Employee Information"],
        ["Name", "Pat Example (Direct Deposit)", "Email", "x@example.com"],
        [],
        ["Statement Information"],
        ["Expense Report Name", "Test Report", "Start Date", "9/1/2026"],
        ["Client Billable Status", "Billable Items: 0", "End Date", "9/30/2026"],
        ["Department", "P8P-570-GC8 Housekeeping", "Status", "Completed"],
        [],
        ["Week 1"],
        ["Expense Category", "Sunday", "Monday"],
    ]
    rows += [[f"7{i:04d}-Filler-Prop Mgmt", "", "", "", "", "", "", "", "0.00"]
             for i in range(extra_week_rows)]
    total = sum(a for _, _, a, _, _ in lines) if total is None else total
    rows += [[], ["", "", "", "", "Total Company Expenses", "", "", "", f"${total:,.2f}"], [],
             ["Expense Comments"], ["Date", "Category", "Amount", "Reason"]]
    rows += [[d, c, f"{a:,.2f} USD", f"Reason: thing {i}\nVendor: {v}\nLocation: Here"]
             for i, (d, c, a, v, _) in enumerate(lines)]
    rows += [[], ["Details"],
             ["Date", "Reimb. Amt", "Non Reimb. Amt", "Curr.", "Reimbursable", "Billable",
              "Exp Type", "Category", "Department"]]
    rows += [[d, a if r else "", "" if r else a, "USD", "Yes" if r else "No", "No",
              "Cash Expense", c, "P8P-570-GC8 Housekeeping"] for d, c, a, _, r in lines]
    rows += [[], ["Receipt Report Link: https://example.invalid"]]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


LINES = [
    ("9/9/2026", "73400-Hskpg Tools-Prop Mgmt", 49.27, "AMAZON RETA", False),
    ("9/11/2026", "74690-Telephone Exp-Prop Mgmt", 45.00, "T-Mobile", True),
    ("9/22/2026", "75030-Entertainment-Prop Mgmt", 1000.00, "Adventure Times Rental", False),
]
CODES = ["73400-570", "74690-570", "75030-570", "75000-570"]


@pytest.mark.parametrize("extra", [0, 7])  # layout shifts with the number of categories
def test_parses_lines_regardless_of_row_positions(extra):
    rep = parse_expense_report(_report_bytes(LINES, extra_week_rows=extra), "r.xlsx")
    resolve_categories(rep, CODES)
    assert rep.employee == "Pat Example"
    assert rep.start_date == date(2026, 9, 1) and rep.end_date == date(2026, 9, 30)
    assert [(i.txn_date, i.category_code, i.amount) for i in rep.items] == [
        (date(2026, 9, 9), "73400-570", 49.27),
        (date(2026, 9, 11), "74690-570", 45.00),
        (date(2026, 9, 22), "75030-570", 1000.00),
    ]
    assert rep.items[1].reimbursable and not rep.items[0].reimbursable
    assert rep.items[0].vendor_raw == "AMAZON RETA" and rep.items[0].reason == "thing 0"
    assert rep.total_matches and not rep.warnings


def test_total_mismatch_is_flagged():
    rep = parse_expense_report(_report_bytes(LINES, total=9999.0), "r.xlsx")
    assert not rep.total_matches
    assert any("report total" in w for w in rep.warnings)


def test_rejects_non_report():
    wb = openpyxl.Workbook()
    wb.active["A1"] = "hello"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ReportParseError):
        parse_expense_report(buf.getvalue(), "x.xlsx")


def _item(d, code, amt):
    return ReportItem(txn_date=d, account=code[:5], category_label="", department="",
                      amount=amt, category_code=code)


def _row(i, d, code, amt):
    return {"id": i, "txn_date": d.isoformat(), "category_code": code, "amount": amt}


def test_compare_exact_near_and_new():
    d = date(2026, 9, 22)
    items = [_item(d, "75030-570", 200.0),            # exact
             _item(d, "75000-570", 305.9),            # recorded 2 days later -> possible
             _item(d, "73400-570", 50.0),             # same day+amount, other category -> possible
             _item(d, "75030-570", 1000.0)]           # nothing similar ($10,000 typo) -> new
    existing = [_row(1, d, "75030-570", 200.0),
                _row(2, date(2026, 9, 24), "75000-570", 305.9),
                _row(3, d, "72500-570", 50.0),
                _row(4, d, "75030-570", 10000.0)]
    res = compare_with_existing(items, existing)
    assert [r["status"] for r in res] == [RECORDED, POSSIBLE, POSSIBLE, NEW]
    assert [r["match"]["id"] if r["match"] else None for r in res] == [1, 2, 3, None]


def test_identical_purchases_need_one_recorded_row_each():
    d = date(2026, 10, 13)
    items = [_item(d, "73400-570", 19.89), _item(d, "73400-570", 19.89)]
    res = compare_with_existing(items, [_row(1, d, "73400-570", 19.89)])
    assert [r["status"] for r in res] == [RECORDED, NEW]


def test_exact_match_beats_earlier_near_match():
    d = date(2026, 10, 1)
    items = [_item(d, "75000-570", 10.0), _item(date(2026, 10, 2), "75000-570", 10.0)]
    res = compare_with_existing(items, [_row(1, date(2026, 10, 2), "75000-570", 10.0)])
    assert [r["status"] for r in res] == [NEW, RECORDED]


@pytest.mark.parametrize("raw,expected", [
    ("AMAZON RETA", "Amazon"), ("AMAZON MARK  B", "Amazon"), ("WWW COSTCO COM", "Costco"),
    ("Robbies Breckenridge", "Robbies"), ("DOS CHILES LLC", "Dos chiles"),
    ("ZORO TOOLS INC", "Zoro"), ("LOWES #122", "Lowes"), ("Soupz On", "Soupz On"),
])
def test_vendor_normalisation(raw, expected):
    known = ["Amazon", "Costco", "Robbies", "Dos chiles", "Zoro", "City Market", "N/A"]
    assert normalize_vendor(raw, known) == expected
