"""Export-first, admin-only purging of retained DEMO chat and closed ride records.

The frontend requires a confirmed local Save As, then supplies the short-lived
grant. Server-side integrity is enforced by a fresh snapshot comparison.
An HTTP request alone cannot prove a local file exists; this mirrors the
existing account deletion contract and intentionally fails closed in browsers
without a verified file-save API.
"""
import hashlib
import json
import time

import demo_chatham_rides


KINDS = frozenset(("chat", "rides"))


def any_open_rides(store):
    return any(ride.get("status") not in ("completed", "cancelled")
               for ride in (store.get("rides") or {}).values())


def snapshot(store, kind, generated_at):
    if kind not in KINDS:
        raise ValueError("Unknown archive type.")
    common = {
        "archive_type": "NightRider " + kind + " history deletion audit",
        "version": 1,
        "generated_at_unix": generated_at,
        "warnings": [
            "Sensitive records: store this archive securely.",
            "Only records currently retained by this software demo are included.",
            "Account logins, authentication credentials and payment records are excluded.",
            "After deletion the server cannot restore this data without this saved file.",
            "Operational transportation record-retention obligations must be reviewed before live use."
        ]
    }
    if kind == "chat":
        common.update({
            "team_and_private_driver_messages": store.get("messages") or [],
            "ride_messages": store.get("ride_messages") or [],
            "rider_account_messages": store.get("account_messages") or {},
        })
    else:
        rides = store.get("rides") or {}
        ride_ids = set(rides)
        common.update({
            "rides": rides,
            "dispatch_only_fictional_demo_rides": demo_chatham_rides.samples(store),
            "ride_messages_for_deleted_rides": [
                m for m in store.get("ride_messages", []) if m.get("ride_id") in ride_ids
            ],
            "rider_history_refs": {
                rid: {
                    "rides": [ride_id for ride_id in rec.get("rides", []) if ride_id in ride_ids],
                    "ratings": [entry for entry in rec.get("ratings", [])
                                if entry.get("ride") in ride_ids]
                }
                for rid, rec in (store.get("riders") or {}).items()
                if any(ride_id in ride_ids for ride_id in rec.get("rides", [])) or
                any(entry.get("ride") in ride_ids for entry in rec.get("ratings", []))
            },
        })
    return common


def serialise(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def sha256(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def filename(kind, generated_at):
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(generated_at))
    return "NightRider-" + kind + "-history-" + stamp + ".json"


def purge(store, kind):
    """Mutate only relevant persisted collections, preserving logins and drivers.

    Caller must hold the same lock protecting snapshots and saves and check
    any_open_rides() before calling. No active ride is ever eligible.
    """
    if kind == "chat":
        counts = {"messages": len(store.get("messages") or []) +
                              len(store.get("ride_messages") or []) +
                              sum(len(thread) for thread in
                                  (store.get("account_messages") or {}).values())}
        store["messages"] = []
        store["ride_messages"] = []
        store["account_messages"] = {}
        return counts
    if kind != "rides":
        raise ValueError("Unknown archive type.")
    if any_open_rides(store):
        raise ValueError("Finish or cancel all active rides before clearing history.")
    ids = set(store.get("rides") or {})
    count = len(ids)
    preview_count = len(demo_chatham_rides.samples(store))
    # This flag survives a restart; deleted examples do NOT regenerate.
    store["demo_chatham_samples_cleared"] = True
    store["rides"] = {}
    store["ride_messages"] = [
        m for m in store.get("ride_messages", []) if m.get("ride_id") not in ids
    ]
    for rider in (store.get("riders") or {}).values():
        rider["rides"] = [ride_id for ride_id in rider.get("rides", []) if ride_id not in ids]
        rider["ratings"] = [entry for entry in rider.get("ratings", [])
                            if entry.get("ride") not in ids]
    return {"rides": count, "demo_rides": preview_count}
