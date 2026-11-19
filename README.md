# GC8 Budget Tracker

A Streamlit + Supabase app to track budget vs. actual spend, log expenses (including
upcoming/planned ones), and keep a full audit trail with notes on every line item.

## What's in this package

```
budget_app/
├── app.py                       # Dashboard (main page)
├── pages/
│   ├── 1_Add_Expense.py         # Log a new paid/pending/planned expense
│   ├── 2_Expense_Log.py         # Browse, filter, edit, note, and view history on any line item
│   ├── 3_Budget_Setup.py        # Set monthly budget $ per category
│   └── 4_Admin.py               # Manage user roles (admin only)
├── utils/
│   ├── db.py                    # All Supabase data-access functions
│   └── auth.py                  # Login/session/role handling
├── import_data/
│   ├── extract_from_excel.py    # Converts your workbook into import-ready CSVs
│   └── *.csv / insert_*.sql     # generated data files - kept LOCAL only (gitignored,
│                                #   they contain real financial data)
├── supabase_schema.sql          # Run this once in Supabase SQL Editor
├── requirements.txt
└── .streamlit/secrets.toml.example
```

## 1. Set up Supabase

1. Create a project at [supabase.com](https://supabase.com) (free tier is plenty to start).
2. Go to **SQL Editor → New Query**, paste the entire contents of `supabase_schema.sql`, and run it.
   This creates all tables, views, triggers, and Row Level Security policies, and seeds your
   chart of accounts from `Budget_26`.
3. Go to **Authentication → Providers** and make sure Email is enabled (it is by default).
4. Sign up your own account through the app once it's running (see step 3 below), then in the
   SQL Editor run:
   ```sql
   update public.profiles set role = 'admin' where email = 'you@example.com';
   ```
   That makes you an admin so you can promote your teammates from the **Admin** page instead of SQL.

## 2. Import your existing data

The three CSVs in `import_data/` were already generated from your uploaded workbook. In Supabase Studio:

1. **Table Editor → categories → Insert → Import data from CSV** → upload `extra_categories.csv`
   (this adds 5 one-off codes — Spa Infinity, Parts & Supplies, etc. — found in your transaction
   log that weren't in the `Budget_26` chart of accounts).
2. **Table Editor → budget_allocations → Insert → Import data from CSV** → upload `budget_allocations.csv`.
3. **Table Editor → expenses → Insert → Import data from CSV** → upload `expenses.csv`.

If you ever need to re-run the extraction (e.g. a new export), run:
```bash
cd import_data
python3 extract_from_excel.py /path/to/your/workbook.xlsx
```

## 3. Run the app

**Locally:**
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit secrets.toml with your Supabase URL + anon key (Project Settings -> API)
streamlit run app.py
```

**Online (Streamlit Community Cloud, free):**
1. Push this folder to a GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → point it at `app.py`.
3. In the app's **Settings → Secrets**, paste the same two keys from `secrets.toml.example`.
4. Deploy — you'll get a public URL to share with your team.

## How roles work

| Role   | Can view | Add/edit expenses & budget | Delete (soft) | Permanently delete | Manage users |
|--------|:---:|:---:|:---:|:---:|:---:|
| viewer | ✅ | | | | |
| editor | ✅ | ✅ | ✅ | | |
| admin  | ✅ | ✅ | ✅ | ✅ | ✅ |

New sign-ups default to **viewer** — promote them from the Admin page.

## Importing Emburse expense reports

**Record expense → Import expense report** takes the monthly Emburse export (`.xls`/`.xlsx`;
several files at once is fine) and adds only the purchases not already recorded.

- Line items come from the report's **Details** section (date, amount, category, department,
  reimbursable), enriched with vendor + description from **Expense Comments**. Sections are found
  by their headings, so it doesn't matter how many category rows the weekly grids have. The sum
  of the lines is checked against *Total Company Expenses*.
- Category = account number + department, e.g. `75000-Meals-Prop Mgmt` in `P8P-570-…` → `75000-570`.
- A line counts as **already recorded** when an expense with the same date, category and amount
  exists (vendor/invoice are ignored, since manual entries spell vendors differently). Each recorded
  row covers one line only, so two identical purchases need two rows. Re-uploading a report adds nothing.
- **Possible duplicates** (same category + amount within 3 days, or same day + amount in another
  category) are shown unticked for a person to decide.
- Raw card vendors are mapped to existing vendors (`AMAZON MARK` → `Amazon`); notes get a
  `[Emburse Sep 2026 - Employee Name]` tag; the invoice # is the report's approval code
  (`Emburse 14838`).
- Nothing is saved until the reviewer approves lines (step 1) and confirms the final list (step 2).
- **Suggested category:** Emburse offers only a few accounts, so keywords in the reason suggest a
  more specific app category (e.g. "HSP Spiff" under Entertainment → Employee Incentive). It's a
  hint only — tick *Use suggested* to apply it; the Emburse category stays the default because
  that's what accounting charged.
- After running `migration_expense_report_fields.sql`, imports also store **Spent by** (the report's
  employee), **Location** and the **Receipt** link (Emburse receipts + approval trail), shown in
  Transactions.

Code: `utils/expense_report.py` (parsing/matching, no Streamlit), `utils/import_ui.py` (the tab).
Tests: `python -m pytest tests`.

---

## Feature brainstorm (beyond what's built)

**Already built:** budget vs. actual dashboard, monthly trend chart, spend-by-group breakdown,
add expenses with paid/pending/planned status, full editable expense log with filters,
threaded notes per line item, automatic audit trail (every insert/edit/delete logged with
before/after values), soft delete + admin hard delete, role-based access, monthly budget editor.

**Natural next additions, roughly in order of value:**

1. **Receipt/invoice attachments** — Supabase Storage bucket + file upload on the Add Expense
   form, linked to the expense row. Handy for anything over a threshold amount.
2. **Recurring expense templates** — e.g. "Telephone – AT&T – $45/mo" that auto-creates a
   `pending` line item each month so you're not re-entering the same vendor over and over.
3. **Budget alerts** — email/Slack notification (via a Supabase Edge Function + cron) when a
   category crosses 80%/100% of its monthly or annual budget.
4. **CSV/Excel export** — a "Download filtered results" button on the Expense Log page, for
   sending a slice to accounting or an owner.
5. **Approval workflow** — a `pending_approval` status + approve/reject buttons, useful if
   editors submit expenses that an admin sign off on before they count as "actual."
6. **Vendor spend view** — a page that groups all-time spend by vendor, useful for negotiating
   contracts or spotting a vendor whose costs are creeping up.
7. **Building-level breakdown** — you already have a `building` field on expenses (B1/B2/B3);
   add a dashboard filter/toggle to see spend split by building, similar to how your cleaning
   scheduler already thinks about the property.
8. **Year-over-year comparison** — since the schema is already keyed by fiscal_year, a page
   comparing 2025 actuals vs 2026 budget vs 2026 actuals side by side.
9. **Mobile-friendly quick-add** — a stripped-down single-field "log an expense fast" view,
   useful for entering something on your phone right after a purchase.
10. **Bulk import for future years** — reuse `extract_from_excel.py` as a template for whatever
    format next year's budget planning spreadsheet takes.

Happy to build out any of these next — just say which one and I'll add it.
