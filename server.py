"""NightRider basic server: static pages + JSON ride API. Standard library only."""
import json, os, threading, time, uuid
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


def fare(distance_mi):
    # Basic placeholder fare: base + per-mile, minimum applied.
    return round(max(7.0, 3.0 + 1.6 * float(distance_mi)), 2)


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
            if self.path == "/api/rides":
                with LOCK:
                    rides = sorted(STORE["rides"].values(), key=lambda r: r["created"], reverse=True)
                return self.send_json(200, {"rides": rides})
            if self.path.startswith("/api/rides/"):
                rid = self.path.split("/")[3].split("?")[0]
                with LOCK:
                    ride = STORE["rides"].get(rid)
                return self.send_json(200 if ride else 404, ride or {"error": "not found"})
            if self.path == "/api/config":
                return self.send_json(200, {"googleMapsKey": os.environ.get("GOOGLE_MAPS_API_KEY", "")})
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
            def coord(v):
                try:
                    if isinstance(v, str):
                        v = json.loads(v or "{}")
                    lat, lng = float(v["lat"]), float(v["lng"])
                    return [lat, lng] if -90 <= lat <= 90 and -180 <= lng <= 180 else None
                except (TypeError, KeyError, ValueError):
                    return None
            ride = {
                "id": uuid.uuid4().hex[:8], "rider_name": name, "pickup": pickup, "dropoff": dropoff,
                "pickup_coords": coord(data.get("pickup_coords")),
                "dropoff_coords": coord(data.get("dropoff_coords")),
                "distance_mi": round(miles, 1), "fare": fare(miles), "status": "requested",
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
