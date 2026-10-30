"""Deterministic, restricted account-history archives for Dispatch deletion flow.

Export only retained application records. The server never receives evidence of
filesystem state; the web client waits for its local file save to complete.
"""
import hashlib
import json
import re
import time


def _rider_id(account_id):
    return "NR-" + str(account_id)[:10].upper()


def account_has_active_ride(store, user):
    """Never remove a login while its rider or driver has an unfinished trip."""
    for ride in (store.get("rides") or {}).values():
        if ride.get("status") in ("completed", "cancelled"):
            continue
        if user["role"] == "rider" and ride.get("rider_account_id") == user["id"]:
            return True
        if user["role"] == "driver" and ride.get("driver_account_id") == user["id"]:
            return True
    return False


def build_archive(store, user, generated_at):
    """Snapshot every CURRENTLY RETAINED record associated with this login.

    The account is not deleted here. Do not archive authentication credentials
    or unrelated riders' private account conversations.
    """
    role = user["role"]
    if role not in ("rider", "driver"):
        raise ValueError("Only Rider and Driver accounts can be archived.")
    identity = {
        key: user.get(key) for key in
        ("id", "username", "display_name", "role", "enabled", "created_at")
    }
    account_id = user["id"]
    name = user["display_name"]
    rid = _rider_id(account_id) if role == "rider" else None

    def matches(ride):
        if role == "rider":
            return ride.get("rider_account_id") == account_id or (
                not ride.get("rider_account_id") and ride.get("rider_id") == rid)
        if ride.get("driver_account_id") == account_id:
            return True
        if not ride.get("driver_account_id") and ride.get("driver") == name:
            return True
        if any(log.get("from_driver") == name or log.get("to_driver") == name
               for log in ride.get("assignment_log", [])):
            return True
        return (ride.get("last_driver_release") or {}).get("driver") == name

    rides = sorted(
        (dict(ride) for ride in (store.get("rides") or {}).values() if matches(ride)),
        key=lambda ride: (ride.get("created") or 0, str(ride.get("id") or "")),
    )
    # Do not include any in-memory conversations in an operator-saved file.
    data = {
        "archive_type": "NightRider account deletion audit",
        "version": 1,
        "generated_at_unix": generated_at,
        "account": identity,
        "rides": rides,
        "ride_messages": [],
        "chat_retention": "Temporary chats are excluded from this archive.",
        "notes": [
            "Contains non-chat operational records currently retained for this account.",
            "Older records already purged by retention limits cannot be recovered.",
            "Password hashes, authentication tokens, and session cookies are never exported.",
            "Deleting the login does not erase NightRider's operational trip ledger.",
            "This archive includes sensitive personal information; store it securely.",
        ],
    }
    if role == "rider":
        data["rider_history"] = (store.get("riders") or {}).get(rid)
        data["account_messages"] = []
        data["driver_records"] = []
        data["team_messages"] = []
    else:
        data["rider_history"] = None
        data["account_messages"] = []
        data["driver_chat_color"] = (store.get("driver_colors") or {}).get(account_id)
        data["driver_records"] = [
            dict(record) for record in (store.get("drivers") or {}).values()
            if record.get("account_id") == account_id or (
                not record.get("account_id") and record.get("name") == name)
        ]
        data["team_messages"] = []
    return data


def serialise_archive(data):
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def archive_sha256(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def archive_filename(user, generated_at):
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(user.get("username") or "account"))
    slug = slug.strip("-")[:35] or "account"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(generated_at))
    return "NightRider-%s-%s-%s-%s.json" % (
        user["role"], slug, str(user["id"])[:10], stamp)
