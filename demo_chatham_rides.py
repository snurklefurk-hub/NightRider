"""Ten fictional, read-only Chatham County ride examples for Dispatch.

These are *presentation samples*, NOT ride requests. Never insert them into
store['rides'], push them to drivers, charge money, allow assignment, or expose
them via rider/driver endpoints. A saved flag allows the administrator's
archive-before-delete Recent rides action to remove them permanently.

Addresses point to real PUBLIC venues in Chatham County, not private homes.
Names, routes, estimates, fares, and status histories are entirely invented.
"""
import time

# Anchored once per server process: repeated requests and archive snapshots
# have identical bytes. A server restart invalidates any in-memory grants.
REFERENCE_TIME = time.time()

# ID, passenger, pickup, destination, distance miles, simulated fare, status,
# minutes before REFERENCE_TIME. All names and trips are fictional.
_ROWS = (
    ("NR-DEMO-001", "Naomi Whitaker",
     "2 E Bay St, Savannah, GA 31401",
     "7804 Abercorn St, Savannah, GA 31406", 7.4, 18.40, "requested", 5),
    ("NR-DEMO-002", "Luis Bennett",
     "200 Tanger Outlets Blvd, Pooler, GA 31322",
     "100 US Highway 80 SW, Pooler, GA 31322", 3.1, 12.75, "requested", 12),
    ("NR-DEMO-003", "Tessa Monroe",
     "301 Martin Luther King Jr Blvd, Savannah, GA 31401",
     "330 Bonaventure Rd, Savannah, GA 31404", 5.8, 17.20, "requested", 21),
    ("NR-DEMO-004", "Adrian Fields",
     "207 W York St, Savannah, GA 31401",
     "121 Barnard St, Savannah, GA 31401", 0.8, 9.50, "completed", 93),
    ("NR-DEMO-005", "Kiara Vaughn",
     "175 Bourne Ave, Pooler, GA 31322",
     "200 Tanger Outlets Blvd, Pooler, GA 31322", 4.2, 14.60, "completed", 228),
    ("NR-DEMO-006", "Marcus Delgado",
     "7804 Abercorn St, Savannah, GA 31406",
     "301 W Oglethorpe Ave, Savannah, GA 31401", 7.5, 21.10, "completed", 510),
    ("NR-DEMO-007", "Celeste Morgan",
     "330 Bonaventure Rd, Savannah, GA 31404",
     "30 Meddin Dr, Tybee Island, GA 31328", 14.2, 34.80, "completed", 1270),
    ("NR-DEMO-008", "Owen Blake",
     "200 Preston Stokes Dr, Pooler, GA 31322",
     "301 Martin Luther King Jr Blvd, Savannah, GA 31401", 12.1, 27.90, "completed", 1590),
    ("NR-DEMO-009", "Priya Foster",
     "307 W Julian St, Savannah, GA 31401",
     "124 Abercorn St, Savannah, GA 31401", 1.2, 0.00, "cancelled", 330),
    ("NR-DEMO-010", "Eli Mercer",
     "30 Meddin Dr, Tybee Island, GA 31328",
     "207 W York St, Savannah, GA 31401", 18.1, 0.00, "cancelled", 2400),
)


def samples(store):
    """Show a deterministic sample set until an archive-backed deletion."""
    if store.get("demo_chatham_samples_cleared"):
        return []
    out = []
    for ride_id, name, origin, destination, miles, fare, status, minutes_ago in _ROWS:
        created = round(REFERENCE_TIME - minutes_ago * 60, 3)
        log = [{"status": "requested", "at": created}]
        if status != "requested":
            log.append({"status": status, "at": created + (12 if status == "completed" else 3) * 60})
        out.append({
            "id": ride_id, "rider_name": name, "rider_id": "DEMO-" + ride_id[-3:],
            "pickup": origin, "dropoff": destination, "distance_mi": miles,
            "fare": fare, "status": status, "driver": "Fictional demo driver"
                if status == "completed" else None,
            "created": created, "status_log": log,
            "simulated": True, "transportation_service": False,
            "payment_method": "Simulation only — no payment collected",
            "demo_preview": True,
        })
    return out
