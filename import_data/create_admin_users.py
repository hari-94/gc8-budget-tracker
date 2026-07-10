"""
Creates Supabase auth users in bulk and sets their role to 'admin'.
Uses the service_role key (admin API), so it bypasses email confirmation and RLS.

Run this ONCE locally. Never commit the service_role key anywhere.

Usage:
    python create_admin_users.py
"""
import getpass
from supabase import create_client

USERS = [
    {"email": "jpimentel@Grandtimber.com", "password": "Jaz@123", "full_name": "Jazmin"},
    {"email": "lsalazar@Grandtimber.com", "password": "Liz@123", "full_name": "Liz Salazar"},
    {"email": "rgarcia@Grandtimber.com", "password": "Rig@123", "full_name": "Rigo Garcia"},
    {"email": "hari@Grandtimber.com", "password": "Har@123", "full_name": "Hari"},
]

SUPABASE_URL = input("Supabase Project URL (e.g. https://xxxx.supabase.co): ").strip()
SERVICE_ROLE_KEY = getpass.getpass("Supabase service_role key (input hidden): ").strip()

client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

created_emails = []

for u in USERS:
    try:
        resp = client.auth.admin.create_user({
            "email": u["email"],
            "password": u["password"],
            "email_confirm": True,   # skip email verification
            "user_metadata": {"full_name": u["full_name"]},
        })
        print(f'Created: {u["email"]}')
        created_emails.append(u["email"])
    except Exception as e:
        # Most common case: user already exists - that's fine, we'll still set their role below
        print(f'Skipped {u["email"]}: {e}')
        created_emails.append(u["email"])

print("\nPromoting all four to admin...")
for email in created_emails:
    try:
        client.table("profiles").update({"role": "admin"}).eq("email", email).execute()
        print(f'  admin -> {email}')
    except Exception as e:
        print(f'  FAILED to set admin for {email}: {e}')

print("\nDone. Everyone can log in now with the email/password above.")
print("Recommend each person changes their password after first login, since these were shared in plain text.")
