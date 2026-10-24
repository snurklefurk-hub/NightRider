"""NightRider basic server: static pages + JSON ride API. Standard library only."""
import json, math, os, threading, time, uuid

# A stand-in driver permanently parked at Savannah City Hall, so the
# driver -> pickup leg of the fare can be exercised without a real driver.
# Coords are 2 E Bay St, Savannah, GA (32.08111, -81.09111).
DEMO_DRIVER = {
    "name": "Test Driver",
    "label": "Savannah City Hall",
    "coords": [32.08111, -81.09111],
}

# CARTO basemap key used for the rider map's Dark Matter tiles. This is a public,
# client-side basemap key -- it ships in every tile URL the browser requests --
# so a working default is included to make the map work out of the box. Set the
# CARTO_API_KEY environment variable on the host to override/rotate it without
# touching this file.
DEFAULT_CARTO_KEY = "cb1_4ty9_1_b9153d194e9b53019d1d5bbe"
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(BASE, "public")
DATA_FILE = os.path.join(BASE, "rides.json")
LOCK = threading.Lock()
STATUSES = ["requested", "accepted", "arrived", "in_progress", "completed", "cancelled"]
NEXT = {"accepted": "arrived", "arrived": "in_progress", "in_progress": "completed"}


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"rides": {}}


def save(store):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, DATA_FILE)


STORE = load()


def clean_text(v, n=120):
    return str(v or "").strip()[:n]


# ---- Fares -------------------------------------------------------------
# $5.00 flag drop, plus $1.00 per mile of the trip (pickup -> drop-off),
# plus $0.25 per mile the driver spends getting to the pickup.
FLAG_DROP = 5.00
TRIP_PER_MILE = 1.00
APPROACH_PER_MILE = 0.25

def _miles(value):
    """Coerce a distance to a non-negative float; bad input counts as 0."""
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def fare(distance_mi, driver_to_pickup_mi=0.0):
    """$5 flag drop + $1.00/mi trip + $0.25/mi driver -> pickup."""
    total = FLAG_DROP + TRIP_PER_MILE * _miles(distance_mi) + APPROACH_PER_MILE * _miles(driver_to_pickup_mi)
    return round(total, 2)


def fare_breakdown(distance_mi, driver_to_pickup_mi=0.0):
    """The itemised fare so the client never has to re-derive the formula."""
    trip = _miles(distance_mi)
    approach = _miles(driver_to_pickup_mi)
    return {
        "flag_drop": FLAG_DROP,
        "trip_mi": round(trip, 1),
        "trip_fare": round(TRIP_PER_MILE * trip, 2),
        "driver_to_pickup_mi": round(approach, 1),
        "approach_fare": round(APPROACH_PER_MILE * approach, 2),
        "total": fare(trip, approach),
    }


def haversine_miles(lat1, lng1, lat2, lng2):
    """Straight-line distance, used for the driver -> pickup leg."""
    r = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_coords(value):
    """Accept {lat,lng} or its JSON string form; return [lat, lng] or None."""
    try:
        if isinstance(value, str):
            value = json.loads(value or "{}")
        lat, lng = float(value["lat"]), float(value["lng"])
        return [lat, lng] if -90 <= lat <= 90 and -180 <= lng <= 180 else None
    except (TypeError, KeyError, ValueError):
        return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PUBLIC, **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.startswith("/api/"):
            if self.path == "/api/config":
                # Host environment variable wins (lets you rotate the key
                # without a code change); otherwise use the built-in key.
                key = os.environ.get("CARTO_API_KEY", DEFAULT_CARTO_KEY).strip()
                return self.send_json(200, {
                    "cartoKey": key,
                    # One source of truth: the client prices the preview with
                    # these rates instead of hard-coding its own copy.
                    "rates": {
                        "flag_drop": FLAG_DROP,
                        "trip_per_mile": TRIP_PER_MILE,
                        "approach_per_mile": APPROACH_PER_MILE,
                    },
                    "demoDriver": DEMO_DRIVER,
                })
            if self.path == "/api/rides":
                with LOCK:
                    rides = sorted(STORE["rides"].values(), key=lambda r: r["created"], reverse=True)
                return self.send_json(200, {"rides": rides})
            if self.path.startswith("/api/rides/"):
                rid = self.path.split("/")[3].split("?")[0]
                with LOCK:
                    ride = STORE["rides"].get(rid)
                return self.send_json(200 if ride else 404, ride or {"error": "not found"})
            return self.send_json(404, {"error": "not found"})
        return super().do_GET()

    def do_POST(self):
        try:
            data = self.read_json()
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "invalid JSON"})

        if self.path == "/api/rides":
            pickup = clean_text(data.get("pickup"))
            dropoff = clean_text(data.get("dropoff"))
            name = clean_text(data.get("rider_name"), 60)
            try:
                miles = float(data.get("distance_mi", 0))
            except (TypeError, ValueError):
                return self.send_json(400, {"error": "distance_mi must be a number"})
            if not pickup or not dropoff or not name:
                return self.send_json(400, {"error": "pickup, dropoff and rider_name are required"})
            if not (0 < miles <= 500):
                return self.send_json(400, {"error": "distance_mi must be between 0 and 500"})
            pickup_coords = parse_coords(data.get("pickup_coords"))
            # The rider's preview sends the distance it computed from the test
            # driver; otherwise fall back to pricing it from City Hall.
            if data.get("driver_to_pickup_mi") is not None:
                approach = _miles(data.get("driver_to_pickup_mi"))
            elif DEMO_DRIVER and pickup_coords:
                approach = haversine_miles(DEMO_DRIVER["coords"][0], DEMO_DRIVER["coords"][1],
                                           pickup_coords[0], pickup_coords[1])
            else:
                approach = 0.0
            if not (0 <= approach <= 200):
                return self.send_json(400, {"error": "driver_to_pickup_mi must be between 0 and 200"})
            ride = {
                "id": uuid.uuid4().hex[:8], "rider_name": name, "pickup": pickup, "dropoff": dropoff,
                "pickup_coords": pickup_coords,
                "dropoff_coords": parse_coords(data.get("dropoff_coords")),
                "distance_mi": round(miles, 1), "driver_to_pickup_mi": round(approach, 1),
                "fare": fare(miles, approach), "status": "requested",
                "driver": None, "created": time.time(),
            }
            with LOCK:
                STORE["rides"][ride["id"]] = ride
                save(STORE)
            return self.send_json(201, ride)

        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rides":
            rid, action = parts[2], parts[3]
            with LOCK:
                ride = STORE["rides"].get(rid)
                if not ride:
                    return self.send_json(404, {"error": "not found"})
                if action == "accept":
                    if ride["status"] != "requested":
                        return self.send_json(409, {"error": "ride is no longer available"})
                    driver = clean_text(data.get("driver"), 60)
                    if not driver:
                        return self.send_json(400, {"error": "driver name required"})
                    ride["driver"] = driver
                    ride["status"] = "accepted"
                    # Price the driver -> pickup leg now that we know who is
                    # coming and (when the driver's page shares it) where from.
                    approach = None
                    dcoords = parse_coords(data.get("driver_coords"))
                    if not dcoords and data.get("demo") and DEMO_DRIVER:
                        dcoords = list(DEMO_DRIVER["coords"])
                    if dcoords and ride.get("pickup_coords"):
                        approach = haversine_miles(dcoords[0], dcoords[1],
                                                   ride["pickup_coords"][0], ride["pickup_coords"][1])
                    elif data.get("driver_to_pickup_mi") is not None:
                        approach = _miles(data.get("driver_to_pickup_mi"))
                    if approach is not None:
                        ride["driver_to_pickup_mi"] = round(approach, 1)
                        ride["driver_coords"] = dcoords
                        ride["fare"] = fare(ride["distance_mi"], ride["driver_to_pickup_mi"])
                elif action == "advance":
                    nxt = NEXT.get(ride["status"])
                    if not nxt:
                        return self.send_json(409, {"error": "ride cannot advance"})
                    ride["status"] = nxt
                elif action == "cancel":
                    if ride["status"] in ("completed", "cancelled"):
                        return self.send_json(409, {"error": "ride already closed"})
                    ride["status"] = "cancelled"
                else:
                    return self.send_json(404, {"error": "unknown action"})
                save(STORE)
                return self.send_json(200, ride)
        return self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"NightRider listening on http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
