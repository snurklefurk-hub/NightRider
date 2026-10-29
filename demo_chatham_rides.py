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
     "7804 Abercorn St, Savannah, GA 31406", 7.4, 18.40, "to_pickup", 5),
    ("NR-DEMO-002", "Luis Bennett",
     "200 Tanger Outlets Blvd, Pooler, GA 31322",
     "100 US Highway 80 SW, Pooler, GA 31322", 3.1, 12.75, "at_pickup", 12),
    ("NR-DEMO-003", "Tessa Monroe",
     "301 Martin Luther King Jr Blvd, Savannah, GA 31401",
     "330 Bonaventure Rd, Savannah, GA 31404", 5.8, 17.20, "to_dropoff", 21),
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



# Positions are intentionally fixed, APPROXIMATE example locations, not live GPS.
# A shared coordinate means an illustrative driver/passenger meeting point.
_ACTIVE_GEO = {
    "NR-DEMO-001": {"pickup": [32.0814, -81.0912], "dropoff": [31.9970, -81.1161],
                    "rider": [32.0814, -81.0912], "driver": [32.0766, -81.0871],
                    "driver_name": "Harper Reed", "driver_id": "NR-FAKE-DRIVER-01"},
    "NR-DEMO-002": {"pickup": [32.1378, -81.2470], "dropoff": [32.1217, -81.2452],
                    "rider": [32.1378, -81.2470], "driver": [32.1378, -81.2470],
                    "driver_name": "Damon Ellis", "driver_id": "NR-FAKE-DRIVER-02"},
    "NR-DEMO-003": {"pickup": [32.0763, -81.1001], "dropoff": [32.0460, -81.0488],
                    "rider": [32.0631, -81.0856], "driver": [32.0631, -81.0856],
                    "driver_name": "Sydney Brooks", "driver_id": "NR-FAKE-DRIVER-03"},
}
_EXTRA_DRIVERS = (
    ("NR-FAKE-DRIVER-04", "Devon Price", [32.0854, -81.1671]),
    ("NR-FAKE-DRIVER-05", "Jules Carter", [31.9991, -81.1080]),
)


def demo_drivers(store):
    """Show fixed, nondispatchable demo drivers on Dispatch map only."""
    if store.get("demo_chatham_samples_cleared"):
        return []
    drivers = []
    for ride_id, geo in _ACTIVE_GEO.items():
        drivers.append({
            "id": geo["driver_id"], "name": geo["driver_name"],
            "coords": list(geo["driver"]), "ride_id": ride_id,
            "status": {"NR-DEMO-001": "to_pickup",
                       "NR-DEMO-002": "at_pickup",
                       "NR-DEMO-003": "to_dropoff"}[ride_id],
            "demo_preview": True, "location_kind": "fixed_demonstration_point",
        })
    for driver_id, name, coords in _EXTRA_DRIVERS:
        drivers.append({"id": driver_id, "name": name, "coords": list(coords),
                        "ride_id": None, "status": "available",
                        "demo_preview": True,
                        "location_kind": "fixed_demonstration_point"})
    return drivers


def map_rides(store):
    """Only 3 staged examples; fictional coords never enter operational map state."""
    if store.get("demo_chatham_samples_cleared"):
        return []
    return [{
        "id": ride["id"], "rider_name": ride["rider_name"],
        "driver": ride["driver"], "status": ride["status"],
        "pickup": ride["pickup"], "dropoff": ride["dropoff"],
        "pickup_coords": list(_ACTIVE_GEO[ride["id"]]["pickup"]),
        "dropoff_coords": list(_ACTIVE_GEO[ride["id"]]["dropoff"]),
        "rider_location": {"coords": list(_ACTIVE_GEO[ride["id"]]["rider"]),
                           "simulated": True, "live": False, "sharing": False,
                           "location_kind": "fixed_demonstration_point"},
        "demo_preview": True, "location_kind": "fixed_demonstration_point",
    } for ride in samples(store) if ride["id"] in _ACTIVE_GEO]

def samples(store):
    """Show a deterministic sample set until an archive-backed deletion."""
    if store.get("demo_chatham_samples_cleared"):
        return []
    out = []
    for ride_id, name, origin, destination, miles, fare, status, minutes_ago in _ROWS:
        created = round(REFERENCE_TIME - minutes_ago * 60, 3)
        log = [{"status": "requested", "at": created}]
        if status in ("to_pickup", "at_pickup", "to_dropoff"):
            stages = {"to_pickup": ("accepted", "to_pickup"),
                      "at_pickup": ("accepted", "to_pickup", "at_pickup"),
                      "to_dropoff": ("accepted", "to_pickup", "at_pickup", "to_dropoff")}[status]
            for index, step in enumerate(stages):
                log.append({"status": step, "at": created + (index + 1) * 60})
        elif status != "requested":
            log.append({"status": status, "at": created + (12 if status == "completed" else 3) * 60})
        out.append({
            "id": ride_id, "rider_name": name, "rider_id": "DEMO-" + ride_id[-3:],
            "pickup": origin, "dropoff": destination, "distance_mi": miles,
            "fare": fare, "status": status,
            "driver": _ACTIVE_GEO[ride_id]["driver_name"] if ride_id in _ACTIVE_GEO
                else "Fictional demo driver" if status == "completed" else None,
            "created": created, "status_log": log,
            "simulated": True, "transportation_service": False,
            "payment_method": "Simulation only — no payment collected",
            "demo_preview": True,
        })
    return out
