"""Parse Emburse expense-report exports (.xls / .xlsx) into individual line items,
and compare them against expenses already recorded in the app.

The export is a single sheet split into labelled sections. Row positions shift
from month to month (the weekly grid has one row per category used that month),
so every section is located by its heading text, never by a fixed row number:

    Statement Information   report name, start/end date, department
    Week 1..5 grids         per-category daily totals (summary only - not used)
    Expense Comments        one row per purchase: Date | Category | Amount | Reason
                            (Reason holds "Reason: ...\\nVendor: ...\\nLocation: ...")
    Details                 one row per purchase: Date | Reimb. Amt | Non Reimb. Amt |
                            Curr. | Reimbursable | Billable | Exp Type | Category | Department
    Total Company Expenses  grand total, used to verify nothing was missed

"Details" is the authoritative list of line items; "Expense Comments" supplies the
vendor and description for each one.

This module has no Streamlit dependency so it can be tested on its own.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


class ReportParseError(ValueError):
    """The file isn't an Emburse expense report we can read."""


@dataclass
class ReportItem:
    txn_date: date
    account: str               # "75000"
    category_label: str        # "75000-Meals-Prop Mgmt"
    department: str            # "P8P-570-GC8 Housekeeping"
    amount: float
    reimbursable: bool = False
    reason: str = ""
    vendor_raw: str = ""
    location: str = ""
    category_code: str | None = None   # resolved app category, e.g. "75000-570"


@dataclass
class ExpenseReport:
    file_name: str
    report_name: str = ""
    employee: str = ""
    department: str = ""
    start_date: date | None = None
    end_date: date | None = None
    status: str = ""
    report_total: float | None = None   # "Total Company Expenses"
    disapproved_total: float = 0.0
    items: list[ReportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def items_total(self) -> float:
        return round(sum(i.amount for i in self.items), 2)

    @property
    def total_matches(self) -> bool:
        return self.report_total is None or abs(self.items_total - self.report_total) < 0.01


# ---------------------------------------------------------------------------
# Low-level cell helpers
# ---------------------------------------------------------------------------

def _load_grid(data: bytes, file_name: str) -> list[list]:
    """Return the first sheet as a list of rows of raw cell values ('' for empty)."""
    name = file_name.lower()
    if data[:4] == b"PK\x03\x04" or name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:
            raise ReportParseError(f"Couldn't open {file_name} as an Excel workbook ({e}).") from e
        ws = wb.worksheets[0]
        return [["" if v is None else v for v in row] for row in ws.iter_rows(values_only=True)]

    import xlrd
    try:
        wb = xlrd.open_workbook(file_contents=data)
    except Exception as e:
        raise ReportParseError(f"Couldn't open {file_name} as an Excel workbook ({e}).") from e
    sh = wb.sheet_by_index(0)
    grid = []
    for r in range(sh.nrows):
        row = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                row.append(xlrd.xldate_as_datetime(cell.value, wb.datemode))
            elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                row.append("")
            else:
                row.append(cell.value)
        grid.append(row)
    return grid


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _parse_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _text(v)
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


_NUM_RE = re.compile(r"[-+]?\(?\$?\s*[\d,]*\.?\d+\)?")


def _parse_amount(v) -> float | None:
    """'1,114.07 USD' -> 1114.07, '(12.50)' -> -12.5, 45.0 -> 45.0, '' -> None."""
    if isinstance(v, (int, float)):
        return float(v)
    s = _text(v)
    if not s:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    tok = m.group(0)
    neg = tok.startswith("-") or (tok.startswith("(") and tok.endswith(")"))
    num = re.sub(r"[^\d.]", "", tok)
    if not num:
        return None
    val = float(num)
    return -val if neg else val


def _find_row(grid, label: str, col: int | None = 0, start: int = 0) -> int | None:
    """Index of the first row (from `start`) with a cell equal to `label` (case-insensitive)."""
    want = label.lower()
    for r in range(start, len(grid)):
        cells = grid[r] if col is None else grid[r][col:col + 1]
        if any(_text(c).lower() == want for c in cells):
            return r
    return None


def _header_map(row) -> dict:
    """{'date': 0, 'category': 1, ...} from a header row."""
    return {_text(v).lower(): i for i, v in enumerate(row) if _text(v)}


def _value_right_of(grid, label: str) -> object:
    """Value of the first non-empty cell to the right of a cell whose text is `label`."""
    want = label.lower()
    for row in grid:
        for i, v in enumerate(row):
            if _text(v).lower() == want:
                for nxt in row[i + 1:]:
                    if _text(nxt):
                        return nxt
                return ""
    return ""


def _is_blank(row) -> bool:
    return not any(_text(v) for v in row)


def _account_of(category_label: str) -> str:
    m = re.match(r"\s*(\d{4,6})", category_label)
    return m.group(1) if m else ""


def _dept_number(department: str) -> str:
    """'P8P-570-GC8 Housekeeping' -> '570'."""
    m = re.search(r"(?:^|-)(\d{3})(?:-|$|\s)", department or "")
    return m.group(1) if m else ""


def _split_reason(text: str) -> tuple[str, str, str]:
    """'Reason: x\\nVendor: y\\nLocation: z' -> (x, y, z). Tolerates missing parts."""
    reason = vendor = location = ""
    other = []
    for line in str(text).replace("\r", "").split("\n"):
        line = line.strip()
        low = line.lower()
        if low.startswith("reason:"):
            reason = line[7:].strip()
        elif low.startswith("vendor:"):
            vendor = line[7:].strip()
        elif low.startswith("location:"):
            location = line[9:].strip()
        elif line:
            other.append(line)
    if not reason and other:
        reason = " ".join(other)
    return reason, vendor, location


def clean_reason(reason: str) -> str:
    """Drop receipt file extensions ('Brushes.png' -> 'Brushes') and squeeze spaces."""
    r = re.sub(r"\.(png|jpe?g|pdf|heic|gif)\b", "", reason or "", flags=re.I)
    return re.sub(r"\s{2,}", " ", r).strip(" ,")


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _rows_after_header(grid, title: str, required: tuple[str, ...]):
    """Find section `title`, then the header row containing all `required` columns
    (within the next few rows). Yields (header_map, data_rows) or None."""
    r0 = _find_row(grid, title)
    if r0 is None:
        return None
    for h in range(r0, min(r0 + 4, len(grid))):
        hm = _header_map(grid[h])
        if all(k in hm for k in required):
            rows = []
            for r in range(h + 1, len(grid)):
                row = grid[r]
                if _is_blank(row):
                    break
                if _parse_date(row[hm["date"]]) is None:
                    break   # reached the next section
                rows.append(row)
            return hm, rows
    return None


def _parse_details(grid) -> list[dict] | None:
    found = _rows_after_header(grid, "Details", ("date", "category"))
    if not found:
        return None
    hm, rows = found
    out = []
    for row in rows:
        reimb = _parse_amount(row[hm["reimb. amt"]]) if "reimb. amt" in hm else None
        non = _parse_amount(row[hm["non reimb. amt"]]) if "non reimb. amt" in hm else None
        amt = round((reimb or 0.0) + (non or 0.0), 2)
        flag = _text(row[hm["reimbursable"]]).lower() if "reimbursable" in hm else ""
        out.append({
            "date": _parse_date(row[hm["date"]]),
            "category": _text(row[hm["category"]]),
            "department": _text(row[hm["department"]]) if "department" in hm else "",
            "amount": amt,
            "reimbursable": flag == "yes" or bool(reimb),
        })
    return out


def _parse_comments(grid) -> list[dict]:
    found = _rows_after_header(grid, "Expense Comments", ("date", "category", "amount"))
    if not found:
        return []
    hm, rows = found
    reason_col = hm.get("reason")
    out = []
    for row in rows:
        reason, vendor, location = _split_reason(row[reason_col] if reason_col is not None else "")
        out.append({
            "date": _parse_date(row[hm["date"]]),
            "category": _text(row[hm["category"]]),
            "amount": _parse_amount(row[hm["amount"]]),
            "reason": reason, "vendor": vendor, "location": location,
        })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_expense_report(data: bytes, file_name: str = "report.xls") -> ExpenseReport:
    grid = _load_grid(data, file_name)
    if not grid:
        raise ReportParseError(f"{file_name} is empty.")
    width = max(len(r) for r in grid)
    grid = [list(r) + [""] * (width - len(r)) for r in grid]

    rep = ExpenseReport(file_name=file_name)
    rep.report_name = _text(_value_right_of(grid, "Expense Report Name"))
    rep.department = _text(_value_right_of(grid, "Department"))
    rep.start_date = _parse_date(_value_right_of(grid, "Start Date"))
    rep.end_date = _parse_date(_value_right_of(grid, "End Date"))
    rep.status = _text(_value_right_of(grid, "Status"))
    emp = _text(_value_right_of(grid, "Name"))
    rep.employee = re.sub(r"\s*\(.*?\)\s*$", "", emp)
    rep.report_total = _parse_amount(_value_right_of(grid, "Total Company Expenses"))
    rep.disapproved_total = _parse_amount(_value_right_of(grid, "Disapproved Expenses")) or 0.0

    details = _parse_details(grid)
    comments = _parse_comments(grid)
    if details is None and not comments:
        raise ReportParseError(
            f"{file_name} doesn't look like an Emburse expense report - couldn't find "
            "the 'Details' or 'Expense Comments' sections.")

    # Index comments by (date, account, amount) so each Details row can pick up its
    # vendor/description even if the two sections are ever ordered differently.
    pool = defaultdict(list)
    for c in comments:
        pool[(c["date"], _account_of(c["category"]), round(c["amount"] or 0, 2))].append(c)

    base = details if details is not None else [
        {"date": c["date"], "category": c["category"], "department": rep.department,
         "amount": round(c["amount"] or 0, 2), "reimbursable": False} for c in comments]
    if details is None:
        rep.warnings.append("No 'Details' section found - used 'Expense Comments' only.")

    for d in base:
        key = (d["date"], _account_of(d["category"]), d["amount"])
        c = pool[key].pop(0) if pool.get(key) else None
        rep.items.append(ReportItem(
            txn_date=d["date"],
            account=_account_of(d["category"]),
            category_label=d["category"],
            department=d["department"] or rep.department,
            amount=d["amount"],
            reimbursable=d["reimbursable"],
            reason=clean_reason(c["reason"]) if c else "",
            vendor_raw=c["vendor"] if c else "",
            location=c["location"] if c else "",
        ))
        if c is None and comments:
            rep.warnings.append(
                f"No description found for {d['date']:%m/%d/%Y} {d['category']} ${d['amount']:,.2f}.")

    leftovers = [c for lst in pool.values() for c in lst]
    for c in leftovers:
        rep.warnings.append(
            f"Comment for {c['date']} {c['category']} ${c['amount']:,.2f} has no matching "
            "line in the Details section - it was not imported.")

    if not rep.total_matches:
        rep.warnings.append(
            f"Line items add up to ${rep.items_total:,.2f} but the report total is "
            f"${rep.report_total:,.2f}. Some rows may not have been read.")
    if rep.disapproved_total:
        rep.warnings.append(
            f"The report lists ${rep.disapproved_total:,.2f} of disapproved expenses - "
            "check none of them were included.")
    return rep


def resolve_categories(report: ExpenseReport, category_codes: list[str]) -> None:
    """Fill item.category_code from the app's chart of accounts.

    Emburse gives '75000-Meals-Prop Mgmt' + department 'P8P-570-...'; the app code is
    '75000-570'. Falls back to the only app code starting with the account number."""
    codes = set(category_codes)
    by_account = defaultdict(list)
    for c in category_codes:
        by_account[c.split("-")[0]].append(c)
    for it in report.items:
        dept = _dept_number(it.department) or _dept_number(report.department)
        guess = f"{it.account}-{dept}" if dept else None
        if guess in codes:
            it.category_code = guess
        elif len(by_account.get(it.account, [])) == 1:
            it.category_code = by_account[it.account][0]
        else:
            it.category_code = None


# ---------------------------------------------------------------------------
# Vendor normalisation
# ---------------------------------------------------------------------------

_VENDOR_NOISE = re.compile(
    r"\b(www|com|llc|inc|co|corp|ltd|the|store|stores|retail|reta|mark|mktp|marketplace)\b|#\s*\d+",
    re.I)


def _vkey(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _VENDOR_NOISE.sub(" ", (name or "").lower()))


def normalize_vendor(raw: str, known_vendors: list[str]) -> str:
    """Map raw card-statement text to an existing vendor where it clearly matches
    ('AMAZON MARK  B' -> 'Amazon', 'WWW COSTCO COM' -> 'Costco', 'Robbies Breckenridge'
    -> 'Robbies'); otherwise return a tidied version of the raw text."""
    raw = (raw or "").strip()
    if not raw:
        return "Others" if "Others" in known_vendors else ""
    rk = _vkey(raw)
    best, best_len = None, 0
    for v in known_vendors:
        vk = _vkey(v)
        if len(vk) < 4:
            continue
        if rk == vk:
            return v
        if rk.startswith(vk) and len(vk) > best_len:
            best, best_len = v, len(vk)
    if best:
        return best
    tidy = re.sub(r"\s*#\s*\d+\s*$", "", re.sub(r"\s{2,}", " ", raw)).strip()
    if tidy.isupper():
        tidy = tidy.title()
    return tidy


# ---------------------------------------------------------------------------
# Comparison with recorded expenses
# ---------------------------------------------------------------------------

NEW, RECORDED, POSSIBLE = "new", "recorded", "possible"


def compare_with_existing(items: list[ReportItem], existing: list[dict],
                          near_days: int = 3) -> list[dict]:
    """Classify each item against existing expense rows (dicts with id, txn_date,
    category_code, amount, vendor, notes).

    - RECORDED: an unclaimed existing row with the same date, category and amount.
    - POSSIBLE: no exact match, but an unclaimed row with the same category and amount
      within `near_days`, or the same date and amount in another category.
    - NEW: nothing similar.

    Each existing row can satisfy only one report line, so two identical purchases on
    the same day need two recorded rows to both count as recorded."""
    ex = []
    for e in existing:
        d = e["txn_date"]
        ex.append({**e, "_d": d if isinstance(d, date) else date.fromisoformat(str(d)[:10]),
                   "_a": round(float(e["amount"]), 2)})
    claimed: set = set()
    results = [None] * len(items)

    # Pass 1: exact matches first, so a near-match never steals an exact one.
    for i, it in enumerate(items):
        for e in ex:
            if (e["id"] not in claimed and e["_d"] == it.txn_date
                    and e["category_code"] == it.category_code and e["_a"] == round(it.amount, 2)):
                claimed.add(e["id"])
                results[i] = {"status": RECORDED, "match": e}
                break

    # Pass 2: near matches for whatever is left.
    for i, it in enumerate(items):
        if results[i]:
            continue
        best = None
        for e in ex:
            if e["id"] in claimed or e["_a"] != round(it.amount, 2):
                continue
            gap = abs((e["_d"] - it.txn_date).days)
            if e["category_code"] == it.category_code and gap <= near_days:
                score = gap
            elif gap == 0:
                score = near_days + 1
            else:
                continue
            if best is None or score < best[0]:
                best = (score, e)
        if best:
            claimed.add(best[1]["id"])
            results[i] = {"status": POSSIBLE, "match": best[1]}
        else:
            results[i] = {"status": NEW, "match": None}
    return results


def date_window(items: list[ReportItem], pad_days: int = 3) -> tuple[date, date]:
    ds = [i.txn_date for i in items]
    return min(ds) - timedelta(days=pad_days), max(ds) + timedelta(days=pad_days)
