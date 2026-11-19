"""'Import expense report' tab on the Record expense page.

Upload one or more Emburse expense-report exports; every purchase line is read,
compared with what's already recorded, and only the missing ones are offered for
saving. Uploading the same report again adds nothing, because each line is matched
against existing rows by date + category + amount before it is saved.
"""
import hashlib
from dataclasses import replace

import pandas as pd
import streamlit as st

from utils.auth import current_username
from utils.db import add_expenses_bulk, expense_extra_columns, get_expenses_in_range
from utils.expense_report import (
    NEW, POSSIBLE, RECORDED, ReportParseError, compare_with_existing, date_window,
    normalize_vendor, parse_expense_report, resolve_categories, suggest_category,
)
from utils.helpers import get_device

_STATUS_LABEL = {NEW: "New", POSSIBLE: "Possible duplicate", RECORDED: "Already recorded"}


@st.cache_data(show_spinner=False, max_entries=20)
def _parse_cached(data: bytes, name: str):
    return parse_expense_report(data, name)


def _describe(e: dict | None, code_to_label: dict) -> str:
    if not e:
        return ""
    cat = code_to_label.get(e["category_code"], e["category_code"])
    note = (e.get("notes") or "").strip().replace("\n", " ")
    note = f" · {note[:40]}" if note else ""
    by = f" · by {e['created_by']}" if e.get("created_by") else ""
    return f"{e['txn_date']} · {cat} · ${float(e['amount']):,.2f} · {e.get('vendor') or '-'}{note}{by}"


def _report_label(report) -> str:
    """'Emburse Sep 2026' - from the report's period, since report names are typed
    by hand in Emburse and can be wrong (the Sep 2026 report is named 'October 2026')."""
    if report.start_date:
        return f"Emburse {report.start_date:%b %Y}"
    return f"Emburse {report.report_name or report.file_name}"


def _notes_for(item, report) -> str:
    parts = [item.reason or "Expense report item"]
    if item.reimbursable:
        parts.append("reimbursable to employee")
    tag = f"[{_report_label(report)}"
    tag += f" - {report.employee}]" if report.employee else "]"
    return " · ".join(parts) + " " + tag


def render_report_import(categories: pd.DataFrame, vendors: list[str]):
    st.markdown(
        "Upload the monthly **Emburse expense report** export (.xls or .xlsx). Each purchase "
        "on it is read automatically and checked against what's already recorded, so only "
        "the **missing** ones are added. Uploading the same report again is safe; anything "
        "already recorded is skipped."
    )

    seq = st.session_state.get("imp_seq", 0)
    if msg := st.session_state.pop("imp_done_msg", None):
        st.success(msg)

    files = st.file_uploader("Expense report files", type=["xls", "xlsx"],
                             accept_multiple_files=True, key=f"imp_files_{seq}")
    if not files:
        return

    exp_cats = categories[categories["type"] == "expense"]
    code_to_label = dict(zip(exp_cats["code"], exp_cats["name"] + "  (" + exp_cats["code"] + ")"))
    label_to_code = {v: k for k, v in code_to_label.items()}
    all_codes = list(categories["code"])

    # ---- Parse every file; drop files that are the same report uploaded twice ----
    reports, seen = [], {}
    for f in files:
        data = f.getvalue()
        try:
            rep = _parse_cached(data, f.name)
        except ReportParseError as e:
            st.error(str(e))
            continue
        except Exception as e:  # unexpected layout - never crash the page
            st.error(f"Couldn't read {f.name}: {e}")
            continue
        ident = (rep.employee, rep.report_name, rep.start_date, rep.end_date,
                 hashlib.sha1(data).hexdigest() if not rep.report_name else "")
        if ident in seen:
            st.info(f"**{f.name}** is the same report as **{seen[ident]}** - skipped.")
            continue
        seen[ident] = f.name
        rep = replace(rep, items=[replace(i) for i in rep.items])  # don't mutate the cache
        resolve_categories(rep, all_codes)
        reports.append(rep)

    reports = [r for r in reports if r.items]
    if not reports:
        st.warning("No expense lines found in the uploaded file(s).")
        return

    # ---- Summary per report ----
    for rep in reports:
        period = (f"{rep.start_date:%b %d} - {rep.end_date:%b %d, %Y}"
                  if rep.start_date and rep.end_date else "")
        check = "✓ matches report total" if rep.total_matches else "⚠ doesn't match report total"
        st.markdown(
            f"**{_report_label(rep)}** ({rep.report_name or rep.file_name}) · "
            f"{rep.employee or 'Unknown employee'}"
            f"{' · ' + period if period else ''}  \n"
            f"{len(rep.items)} lines · ${rep.items_total:,.2f} {check}"
            + (f" · approval code {rep.approval_code}" if rep.approval_code else "")
            + (f" · [receipts in Emburse]({rep.receipt_url})" if rep.receipt_url else ""))
        for w in rep.warnings:
            st.warning(w)

    # ---- Compare with recorded expenses (one combined pass, so overlapping reports
    #      can't both claim the same existing row) ----
    items = [(rep, it) for rep in reports for it in rep.items]
    lo, hi = date_window([it for _, it in items])
    existing = get_expenses_in_range(lo, hi)
    results = compare_with_existing([it for _, it in items], existing)

    extra_cols = expense_extra_columns()
    rows, extras, recorded = [], [], []
    for (rep, it), res in zip(items, results):
        if res["status"] == RECORDED:
            recorded.append({
                "Date": it.txn_date, "Category": code_to_label.get(it.category_code, it.category_label),
                "Amount": it.amount, "Report vendor": it.vendor_raw,
                "Recorded as": _describe(res["match"], code_to_label),
            })
            continue
        sugg = suggest_category(it.reason, it.category_code, all_codes)
        extras.append({
            "invoice_number": f"Emburse {rep.approval_code}" if rep.approval_code else "NA",
            "spent_by": rep.employee or None,
            "location": it.location or None,
            "receipt_url": rep.receipt_url or None,
            "suggested": sugg,
        })
        rows.append({
            "Add": res["status"] == NEW,
            "Status": _STATUS_LABEL[res["status"]],
            "Date": it.txn_date,
            "Category": code_to_label.get(it.category_code),
            "Use suggested": False,
            "Suggested category": code_to_label.get(sugg, "") if sugg else "",
            "Vendor": normalize_vendor(it.vendor_raw, vendors),
            "Amount": it.amount,
            "Notes": _notes_for(it, rep),
            "Similar recorded entry": _describe(res["match"], code_to_label),
            "_src": f"{rep.report_name or rep.file_name}",
        })

    n_new = sum(r["Status"] == "New" for r in rows)
    n_pos = len(rows) - n_new
    c1, c2, c3 = st.columns(3)
    c1.metric("Already recorded", len(recorded))
    c2.metric("New", n_new)
    c3.metric("Possible duplicates", n_pos)

    money = {"Amount": st.column_config.NumberColumn(format="$%.2f")}

    if recorded:
        with st.expander(f"Already recorded ({len(recorded)}) - will be skipped",
                         expanded=not rows):
            st.dataframe(pd.DataFrame(recorded), hide_index=True, use_container_width=True,
                         column_config=money)

    if not rows:
        st.success("Everything on this report is already recorded. Nothing to add.")
        return

    # ---------------------------------------------------------------------------
    # Step 1 - review. Nothing is saved until step 2 is confirmed.
    # ---------------------------------------------------------------------------
    pending_key = f"imp_pending_{seq}"
    pending = st.session_state.get(pending_key)

    st.markdown("#### Step 1 · Review the lines to add")
    st.caption("Tick **Approve** for each line you want captured. You can change the category, "
               "vendor or notes before approving. Nothing is saved until you confirm in step 2.")
    n_sugg = sum(bool(r["Suggested category"]) for r in rows)
    if n_sugg:
        st.caption(f"**{n_sugg} line(s) have a suggested category** based on the reason. Tick "
                   "**Use suggested** to file a line there instead of the Emburse category.")
    if n_pos:
        st.caption("**Possible duplicates** look like something already recorded (same amount "
                   "within a few days, or same day in another category). They start unticked; "
                   "approve one only if it's a separate purchase.")

    df = pd.DataFrame(rows).rename(columns={"Add": "Approve"})
    editor_key = "imp_editor_" + hashlib.sha1(
        ("|".join(sorted(seen.values())) + str(seq)).encode()).hexdigest()[:12]
    edited = st.data_editor(
        df.drop(columns=["_src"]),
        key=editor_key, hide_index=True, use_container_width=True,
        # Locked while waiting for confirmation, so what's confirmed is what's saved.
        disabled=True if pending else ["Status", "Date", "Amount", "Suggested category",
                                       "Similar recorded entry"],
        column_config={
            "Approve": st.column_config.CheckboxColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
            "Date": st.column_config.DateColumn(format="MM/DD/YYYY", width="small"),
            "Category": st.column_config.SelectboxColumn(
                options=sorted(code_to_label.values()), required=True, width="medium"),
            "Use suggested": st.column_config.CheckboxColumn(
                width="small", help="Tick to file this line under the suggested category instead."),
            "Suggested category": st.column_config.TextColumn(
                width="medium", help="A more specific app category suggested by the reason text. "
                "Emburse's category is what accounting charged, so it stays the default."),
            "Vendor": st.column_config.TextColumn(required=True, width="medium"),
            "Amount": st.column_config.NumberColumn(format="$%.2f", width="small"),
            "Notes": st.column_config.TextColumn(width="large"),
            "Similar recorded entry": st.column_config.TextColumn(width="large"),
        },
    )

    chosen = edited[edited["Approve"]]
    total = float(chosen["Amount"].sum()) if len(chosen) else 0.0
    plural = "s" if len(chosen) != 1 else ""

    if not pending:
        st.write("")
        if st.button(f"Review {len(chosen)} approved line{plural} (${total:,.2f})",
                     type="primary", use_container_width=True, disabled=chosen.empty,
                     key=f"imp_review_{seq}"):
            # Apply "Use suggested" before validating
            chosen = chosen.copy()
            use = chosen["Use suggested"] & (chosen["Suggested category"] != "")
            chosen.loc[use, "Category"] = chosen.loc[use, "Suggested category"]
            missing_cat = chosen[chosen["Category"].isna()
                                 | ~chosen["Category"].isin(label_to_code)]
            if len(missing_cat):
                st.error("Choose a category for every approved line "
                         f"({len(missing_cat)} line(s) have none - their account isn't in the app).")
                return
            if (chosen["Vendor"].fillna("").str.strip() == "").any():
                st.error("Every approved line needs a vendor.")
                return
            pend = []
            for idx, r in chosen.iterrows():
                ex = extras[idx]
                row = {
                    "category_code": label_to_code[r["Category"]],
                    "vendor": r["Vendor"].strip(),
                    "invoice_number": ex["invoice_number"],
                    "txn_date": r["Date"],
                    "amount": round(float(r["Amount"]), 2),
                    "status": "paid",
                    "notes": (r["Notes"] or "").strip(),
                }
                if extra_cols:
                    row.update(spent_by=ex["spent_by"], location=ex["location"],
                               receipt_url=ex["receipt_url"])
                pend.append(row)
            st.session_state[pending_key] = pend
            st.rerun()
        return

    # ---------------------------------------------------------------------------
    # Step 2 - confirm exactly what will be written.
    # ---------------------------------------------------------------------------
    p_total = sum(r["amount"] for r in pending)
    p_plural = "s" if len(pending) != 1 else ""
    st.markdown("#### Step 2 · Confirm")
    st.info(f"**{len(pending)} expense{p_plural} totalling ${p_total:,.2f}** will be added to "
            f"the app as **paid**, recorded by **{current_username()}**. Please check them below.")
    st.dataframe(pd.DataFrame([{
        "Date": r["txn_date"], "Category": code_to_label.get(r["category_code"], r["category_code"]),
        "Vendor": r["vendor"], "Amount": r["amount"], "Invoice #": r["invoice_number"],
        **({"Spent by": r.get("spent_by"), "Location": r.get("location")} if extra_cols else {}),
        "Notes": r["notes"],
    } for r in pending]), hide_index=True, use_container_width=True, column_config=money)

    b1, b2 = st.columns(2)
    with b1:
        confirm = st.button(f"Confirm and add {len(pending)} expense{p_plural}", type="primary",
                            use_container_width=True, key=f"imp_confirm_{seq}")
    with b2:
        if st.button("Go back and change", use_container_width=True, key=f"imp_back_{seq}"):
            st.session_state.pop(pending_key, None)
            st.rerun()
    if not confirm:
        return

    # ---- Final duplicate check against live data (another user may have just added
    #      these, or the button was pressed twice) ----
    fresh = get_expenses_in_range(lo, hi)
    probe = [replace(items[0][1], txn_date=r["txn_date"], category_code=r["category_code"],
                     amount=r["amount"]) for r in pending]
    fresh_res = compare_with_existing(probe, fresh)
    final = [r for r, fr in zip(pending, fresh_res) if fr["status"] != RECORDED]
    skipped = len(pending) - len(final)

    user, device = current_username(), get_device()
    source = ", ".join(sorted({_report_label(r) for r in reports}))
    added = 0
    try:
        added = add_expenses_bulk(final, user, device, source)
    except ValueError:
        # A row collided with the database's duplicate guard - save the rest one by one.
        for r in final:
            try:
                added += add_expenses_bulk([r], user, device, source)
            except ValueError:
                skipped += 1

    msg = f"Added {added} expense{'s' if added != 1 else ''} from {source}."
    if skipped:
        msg += f" {skipped} skipped because they were already recorded."
    st.session_state.pop(pending_key, None)
    st.session_state["imp_done_msg"] = msg
    st.session_state["imp_seq"] = seq + 1
    st.rerun()
