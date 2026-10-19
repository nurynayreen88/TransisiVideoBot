"""Private server-side Supabase REST access for Klippo subscriptions."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

def configured():
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

def request(path, method="GET", payload=None, prefer="return=representation"):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    url = base + "/rest/v1/" + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Content-Type": "application/json", "Prefer": prefer}
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


def register_user(user_id, name):
    """Create a minimal user record without overwriting an existing subscription."""
    rows = request(
        "klippo_subscriptions?on_conflict=telegram_user_id",
        "POST",
        {"telegram_user_id": int(user_id), "telegram_name": (name or "")[:255]},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return rows[0] if rows else None


def users(query="", status="all", offset=0, limit=10):
    """Return a filtered admin list. Status 'expired' is derived from expires_at."""
    from datetime import datetime, timezone

    rows = request(
        "klippo_subscriptions?select=telegram_user_id,telegram_name,status,started_at,expires_at,updated_at"
        "&order=updated_at.desc.nullslast&limit=1000"
    )
    needle = (query or "").strip().casefold()
    now = datetime.now(timezone.utc)
    matched = []
    for row in rows:
        name = (row.get("telegram_name") or "").casefold()
        user_id = str(row.get("telegram_user_id", ""))
        if needle and needle not in name and needle not in user_id:
            continue
        current = (row.get("status") or "inactive").casefold()
        expiry = row.get("expires_at")
        if current == "active" and expiry:
            try:
                parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                if parsed <= now:
                    current = "expired"
            except (ValueError, TypeError):
                pass
        row["display_status"] = current
        if status != "all" and current != status:
            continue
        matched.append(row)
    start = max(0, int(offset))
    size = max(1, min(20, int(limit)))
    return {"total": len(matched), "items": matched[start:start + size], "offset": start, "limit": size}


def user_details(user_id):
    """Return subscription record and recent payment receipt history for one Telegram user."""
    uid = int(user_id)
    subscriptions = request(
        "klippo_subscriptions?telegram_user_id=eq." + str(uid)
        + "&select=telegram_user_id,telegram_name,status,started_at,expires_at,updated_at&limit=1"
    )
    receipts = request(
        "klippo_payment_receipts?telegram_user_id=eq." + str(uid)
        + "&select=id,status,amount_myr,submitted_at,reviewed_at,reviewed_by,review_note"
        + "&order=submitted_at.desc&limit=10"
    )
    return {"user": subscriptions[0] if subscriptions else None, "receipts": receipts}
