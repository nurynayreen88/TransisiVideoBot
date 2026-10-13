"""Private server-side Supabase REST access for Klippo subscriptions."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

def configured():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def request(path, method="GET", payload=None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    url = base + "/rest/v1/" + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Content-Type": "application/json", "Prefer": "return=representation"}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8") or "[]")

def submit_receipt(user_id, name, file_id, kind):
    rows = request("klippo_payment_receipts", "POST", {
        "telegram_user_id": user_id, "telegram_name": name,
        "telegram_file_id": file_id, "telegram_file_type": kind
    })
    return rows[0]

def pending_receipts():
    return request("klippo_payment_receipts?status=eq.pending&select=id,telegram_user_id,telegram_name,submitted_at&order=submitted_at.asc&limit=10")

def review(receipt_id, admin_id, approve):
    rows = request("rpc/klippo_review_receipt", "POST", {
        "p_receipt_id": receipt_id, "p_admin_id": admin_id, "p_approve": approve
    })
    return rows[0]

def subscription(user_id):
    rows = request("klippo_subscriptions?telegram_user_id=eq." + str(int(user_id)) +
                   "&select=status,expires_at&limit=1")
    return rows[0] if rows else None
