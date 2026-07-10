"""
Pushes categories, budget_allocations, and expenses CSVs straight into Supabase.
Uses the service_role key so it bypasses RLS (no login needed) - run this ONCE, locally,
then don't commit the key anywhere.

Usage:
    python push_to_supabase.py
"""
import csv
import getpass
from supabase import create_client

SUPABASE_URL = input("Supabase Project URL (e.g. https://xxxx.supabase.co): ").strip()
SERVICE_ROLE_KEY = getpass.getpass("Supabase service_role key (input hidden): ").strip()

client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def push(table, rows, on_conflict=None):
    if not rows:
        print(f'  no rows for {table}, skipping')
        return
    # supabase-py batches well up to a few hundred rows at a time
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        if on_conflict:
            client.table(table).upsert(batch, on_conflict=on_conflict).execute()
        else:
            client.table(table).insert(batch).execute()
    print(f'  pushed {len(rows)} rows -> {table}')


if __name__ == '__main__':
    print('Pushing extra_categories.csv -> categories ...')
    cats = load_csv('extra_categories.csv')
    push('categories', cats, on_conflict='code')

    print('Pushing budget_allocations.csv -> budget_allocations ...')
    budget = load_csv('budget_allocations.csv')
    for r in budget:
        r['fiscal_year'] = int(r['fiscal_year'])
        r['month'] = int(r['month'])
        r['budgeted_amount'] = float(r['budgeted_amount'])
    push('budget_allocations', budget, on_conflict='category_code,fiscal_year,month')

    print('Pushing expenses.csv -> expenses ...')
    expenses = load_csv('expenses.csv')
    for r in expenses:
        r['amount'] = float(r['amount'])
        # drop empty strings so blank invoice_number/vendor don't overwrite defaults oddly
        for k in ('vendor', 'invoice_number', 'notes'):
            if r.get(k) == '':
                r[k] = None
    push('expenses', expenses)

    print('\nDone. Go double-check row counts in Supabase Table Editor.')
