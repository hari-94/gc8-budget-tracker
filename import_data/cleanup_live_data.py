"""
One-time cleanup of the live expenses table:
  1. Removes exact-duplicate transactions (keeps the earliest of each set).
  2. Cleans the invoice_number field:
       - pure numbers / invoice-like IDs stay
       - names/descriptions move to notes
       - "Name 12345" -> invoice=12345, note gets "Name"
       - blanks / n/a  -> "NA"

Run ONCE, locally, with your service_role key. Nothing is committed.

Usage:
    python cleanup_live_data.py
"""
import re
import getpass
from supabase import create_client


def clean_invoice(raw):
    """Return (invoice, extracted_note)."""
    if raw is None:
        return "NA", ""
    v = str(raw).strip()
    if not v or v.lower() in ("n/a", "na", "none", "-"):
        return "NA", ""
    if re.fullmatch(r"[0-9]+", v):
        return v, ""
    if re.fullmatch(r"[A-Za-z0-9\-/#]+", v) and any(c.isdigit() for c in v):
        return v, ""
    nums = re.findall(r"[0-9]{3,}", v)
    if nums:
        inv = max(nums, key=len)
        note = v.replace(inv, "").strip(" -/#,")
        return inv, note
    return "NA", v


def merge_notes(existing, extracted):
    existing = (existing or "").strip()
    if not extracted:
        return existing
    if not existing:
        return extracted
    if extracted.lower() in existing.lower():
        return existing
    return f"{existing} · {extracted}"


def main():
    url = input("Supabase Project URL: ").strip()
    key = getpass.getpass("Supabase service_role key (hidden): ").strip()
    client = create_client(url, key)

    print("\nFetching all expenses...")
    rows = []
    page = 0
    while True:
        res = client.table("expenses").select("*").is_("deleted_at", "null") \
            .range(page * 1000, page * 1000 + 999).execute()
        if not res.data:
            break
        rows.extend(res.data)
        if len(res.data) < 1000:
            break
        page += 1
    print(f"  {len(rows)} active expenses")

    # ---- 1. De-duplicate ----
    seen = {}
    to_delete = []
    for r in sorted(rows, key=lambda x: x.get("created_at") or ""):
        key = (
            r["category_code"], r["txn_date"], str(r["amount"]),
            (r.get("vendor") or "").strip().lower(),
            (r.get("invoice_number") or "").strip().lower(),
        )
        if key in seen:
            to_delete.append(r["id"])
        else:
            seen[key] = r["id"]
    print(f"\n{len(to_delete)} duplicate rows will be removed (keeping earliest of each).")
    if to_delete and input("Proceed with deletion? (yes/no): ").strip().lower() == "yes":
        for i in range(0, len(to_delete), 100):
            batch = to_delete[i:i + 100]
            client.table("expenses").delete().in_("id", batch).execute()
        print("  duplicates removed.")
        rows = [r for r in rows if r["id"] not in set(to_delete)]

    # ---- 2. Clean invoice / notes ----
    print("\nCleaning invoice / notes fields...")
    updated = 0
    for r in rows:
        new_inv, extracted = clean_invoice(r.get("invoice_number"))
        new_notes = merge_notes(r.get("notes"), extracted)
        if new_inv != (r.get("invoice_number") or "") or new_notes != (r.get("notes") or ""):
            client.table("expenses").update(
                {"invoice_number": new_inv, "notes": new_notes}
            ).eq("id", r["id"]).execute()
            updated += 1
    print(f"  {updated} rows cleaned.")
    print("\nDone.")


if __name__ == "__main__":
    main()
