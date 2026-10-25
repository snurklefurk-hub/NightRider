"""NightRider basic server: static pages + JSON ride API. Standard library only."""
import datetime, hmac, json, math, os, threading, time, urllib.parse, uuid
import auth

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
STATUSES = ["requested", "accepted", "to_pickup", "at_pickup", "to_dropoff",
            "at_dropoff", "completed", "cancelled"]
# The driver's ride workflow: each press moves the ride to the next stage.
NEXT = {
    "accepted": "to_pickup",
    "to_pickup": "at_pickup",
    "at_pickup": "to_dropoff",
    "to_dropoff": "at_dropoff",
    "at_dropoff": "completed",
}
# The label shown on the driver's next button, keyed by the ride's current stage.
STAGE_ACTION = {
    "accepted": "Head to pickup",
    "to_pickup": "Arrive at pickup",
    "at_pickup": "Head to destination",
    "to_dropoff": "Arrive at destination",
    "at_dropoff": "Complete ride",
}
# Human labels for every status, shared by the driver and dispatch boards.
STATUS_LABELS = {
    "requested": "Requested",
    "accepted": "Assigned",
    "to_pickup": "Heading to pickup",
    "at_pickup": "At pickup",
    "to_dropoff": "Heading to destination",
    "at_dropoff": "At destination",
    "completed": "Completed",
    "cancelled": "Cancelled",
}


def load():
    if os.environ.get("DATABASE_URL", "").strip():
        return auth.load_app_state(DATA_FILE)
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"rides": {}}


def ensure_store(store):
    """Guarantee every collection the API writes to exists."""
    store.setdefault("rides", {})
    store.setdefault("riders", {})
    store.setdefault("drivers", {})
    store.setdefault("messages", [])
    return store


def save(store):
    if os.environ.get("DATABASE_URL", "").strip():
        auth.save_app_state(store, DATA_FILE)
        return
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, DATA_FILE)


if os.environ.get("NIGHTRIDER_REQUIRE_DATABASE", "true").lower() == "true" and not os.environ.get("DATABASE_URL", "").strip():
    raise RuntimeError("DATABASE_URL is required; set it in the Render environment before deploying")
if os.environ.get("DATABASE_URL", "").strip():
    auth.initialize()
STORE = ensure_store(load())
LOGIN_FAILURES = {}
LOGIN_FAILURES_LOCK = threading.Lock()
SIGNUP_ATTEMPTS = {}


def clean_text(v, n=120):
    return str(v or "").strip()[:n]


def _first(qs, key, default=""):
    return (qs.get(key) or [default])[0]


def _num(qs, key, default=0.0):
    try:
        return float(_first(qs, key, default))
    except (TypeError, ValueError):
        return float(default)


# ---- Push events (long-poll) -------------------------------------------
# Dispatch no longer watches the clock. It holds one open request on
# /api/events and the server answers the instant something happens, so a new
# request appears on the dispatch screen immediately. The log lives in memory,
# so a server restart simply resets the cursor to 0.
EVENTS = []
EVENT_SEQ = 0
EVENT_LIMIT = 400
EVENT_COND = threading.Condition()
EVENT_FOR = {"accept": "ride_accepted", "advance": "ride_status", "cancel": "ride_cancelled"}


def record_event(kind, ride=None, **extra):
    """Append to the event log and wake every client that is waiting."""
    global EVENT_SEQ
    with EVENT_COND:
        EVENT_SEQ += 1
        ev = {"seq": EVENT_SEQ, "type": kind, "at": time.time()}
        if ride is not None:
            ev["ride"] = ride
        ev.update(extra)
        EVENTS.append(ev)
        if len(EVENTS) > EVENT_LIMIT:
            del EVENTS[:-EVENT_LIMIT]
        EVENT_COND.notify_all()
        return ev


def read_events(since, ride=None, timeout=25.0):
    """Long-poll: return events newer than `since`, or time out with none."""
    deadline = time.time() + max(0.0, timeout)
    with EVENT_COND:
        while True:
            found = [e for e in EVENTS if e["seq"] > since and (ride is None or e.get("ride") == ride)]
            if found or time.time() >= deadline:
                return {"events": found, "cursor": EVENT_SEQ, "now": time.time(), "timed_out": not found}
            EVENT_COND.wait(min(1.0, max(0.05, deadline - time.time())))


# ---- Active drivers + dispatch/driver texting --------------------------
# A driver page pings with its name (and, when it shares it, its location).
# Anything seen inside DRIVER_ACTIVE_WINDOW counts as "active" on dispatch.
DRIVER_ACTIVE_WINDOW = 90.0
MESSAGE_LIMIT = 500
# A driver is available/idle/offline, or reports the ride stage they are in
# ("accepted", "to_pickup", ...) so dispatch sees live stage status.
DRIVER_STATUSES = ("available", "busy", "offline", "accepted", "to_pickup",
                   "at_pickup", "to_dropoff", "at_dropoff", "completed")


def touch_driver(store, name, coords=None, status=None):
    """Record a driver heartbeat and return the stored record."""
    name = clean_text(name, 60)
    if not name:
        return None
    rec = store.setdefault("drivers", {}).setdefault(
        name, {"name": name, "first_seen": time.time()})
    rec["last_seen"] = time.time()
    if coords:
        rec["coords"] = coords
    if status in DRIVER_STATUSES:
        rec["status"] = status
    rec.setdefault("status", "available")
    return rec


def driver_is_active(rec, now=None):
    now = time.time() if now is None else now
    return (now - float(rec.get("last_seen") or 0)) <= DRIVER_ACTIVE_WINDOW


def dispatch_driver(rec, now=None):
    """Public driver shape for the dispatch screen."""
    now = time.time() if now is None else now
    return {
        "name": rec.get("name"),
        "status": rec.get("status") or "available",
        "active": driver_is_active(rec, now),
        "last_seen": rec.get("last_seen"),
        "idle_s": round(max(0.0, now - float(rec.get("last_seen") or 0)), 1),
        "coords": rec.get("coords"),
    }


def add_message(store, sender, text, driver=None, private=False):
    """Append one text to the shared conversation and return it.

    A group text (private=False) is seen by dispatch and every driver. A
    private text belongs to one dispatch<->driver pair and is seen only by
    those two; it still lives in the same conversation window, colour-coded.
    """
    text = clean_text(text, 1000)
    if not text:
        return None
    sender = clean_text(sender, 60) or "dispatch"
    private = bool(private)
    msg = {"id": uuid.uuid4().hex[:8], "from": sender,
           "role": "dispatch" if sender == "dispatch" else "driver",
           "channel": "private" if private else "group",
           "driver": clean_text(driver, 60) if private else None,
           "text": text, "at": time.time()}
    thread = store.setdefault("messages", [])
    thread.append(msg)
    if len(thread) > MESSAGE_LIMIT:
        del thread[:-MESSAGE_LIMIT]
    return msg


def thread_messages(store, viewer, since=0.0):
    """The conversation as one viewer is allowed to see it.

    Everyone sees group texts. A private text is visible only to dispatch and
    the named driver, so a driver's fetch is filtered to their own pair.
    """
    viewer = clean_text(viewer, 60)
    out = []
    for m in store.get("messages", []):
        if m.get("channel") == "private":
            if viewer != "dispatch" and m.get("driver") != viewer:
                continue
        out.append(m)
    if since:
        out = [m for m in out if float(m.get("at") or 0) > float(since)]
    return out


def touch_rider(store, rid, signals, name):
    """Create or update the backend record for this hidden rider id."""
    riders = store.setdefault("riders", {})
    rec = riders.get(rid)
    now = time.time()
    if not rec:
        rec = {"id": rid, "first_seen": now, "rides": [], "ratings": []}
        riders[rid] = rec
    rec["last_seen"] = now
    if signals:
        rec["signals"] = signals
    names = rec.setdefault("names", [])
    if name and name not in names:
        names.append(name)
    del names[:-5]
    return rec


def rider_summary(store, rid):
    """Counts and average score a driver may see. Never the identity."""
    rec = (store.get("riders") or {}).get(rid)
    if not rec:
        return {"rides": 0, "ratings": 0, "avg": None, "issues": 0}
    ratings = rec.get("ratings") or []
    scored = [r["stars"] for r in ratings if isinstance(r.get("stars"), (int, float))]
    return {
        "rides": len(rec.get("rides") or []),
        "ratings": len(ratings),
        "avg": round(sum(scored) / len(scored), 2) if scored else None,
        "issues": sum(1 for r in ratings if r.get("issues")),
    }


def log_status(ride, status):
    """Record a status change with a timestamp so stage timing can be shown."""
    ride.setdefault("status_log", []).append({"status": status, "at": time.time()})
    return ride


def public_ride(ride, store=None):
    """A ride any client may see. The hidden rider id is never included."""
    if not ride:
        return ride
    out = {k: v for k, v in ride.items() if k != "rider_id"}
    out["rider_summary"] = rider_summary(store or {}, ride.get("rider_id"))
    return out


def dispatch_ride(ride, store):
    """Dispatch's view: the same ride plus the hidden rider id."""
    out = dict(ride)
    out["rider_summary"] = rider_summary(store, ride.get("rider_id"))
    return out


def dispatch_rider(rec, store, detail=False):
    out = {
        "id": rec.get("id"),
        "first_seen": rec.get("first_seen"),
        "last_seen": rec.get("last_seen"),
        "names": rec.get("names") or [],
        "summary": rider_summary(store, rec.get("id")),
    }
    if detail:
        rides = store["rides"]
        out["rides"] = [
            {"id": i, "created": rides[i]["created"], "status": rides[i]["status"],
             "pickup": rides[i]["pickup"], "dropoff": rides[i]["dropoff"],
             "fare": rides[i]["fare"], "driver": rides[i].get("driver"),
             "ratings": rides[i].get("ratings") or []}
            for i in rec.get("rides") or [] if i in rides
        ]
        out["ratings"] = rec.get("ratings") or []
    return out


def build_rating(data):
    """Build a rating entry, or return an error string."""
    by = clean_text(data.get("by"), 20)
    if by not in ("driver", "dispatch"):
        return "by must be driver or dispatch"
    try:
        stars = float(data.get("stars"))
    except (TypeError, ValueError):
        return "stars must be a number from 1 to 5"
    if not (stars == int(stars) and 1 <= stars <= 5):
        return "stars must be a number from 1 to 5"
    issues = data.get("issues")
    if isinstance(issues, str):
        issues = [issues]
    if not isinstance(issues, list):
        issues = []
    cleaned = [clean_text(i, 60) for i in issues[:6]]
    return {
        "by": by,
        "by_name": clean_text(data.get("by_name"), 60),
        "stars": int(stars),
        "issues": [i for i in cleaned if i],
        "note": clean_text(data.get("note"), 400),
        "at": time.time(),
    }


# ---- Plain-text log export ---------------------------------------------
def fmt_ts(ts):
    return datetime.datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_when(value, end_of_day=False):
    """Epoch seconds, YYYY-MM-DD, or an ISO timestamp. None means no bound."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        if len(s) == 10:
            d = datetime.datetime.strptime(s, "%Y-%m-%d")
            if end_of_day:
                d = d.replace(hour=23, minute=59, second=59, microsecond=999999)
            return d.timestamp()
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def export_log(store, start=None, end=None):
    """Every ride in the period as plain text, newest last, with hidden ids."""
    rides = [r for r in store["rides"].values()
             if (start is None or r["created"] >= start) and (end is None or r["created"] <= end)]
    rides.sort(key=lambda r: r["created"])
    if start is not None and end is not None:
        period = fmt_ts(start) + " to " + fmt_ts(end)
    elif start is not None:
        period = "from " + fmt_ts(start)
    elif end is not None:
        period = "through " + fmt_ts(end)
    else:
        period = "all rides"
    lines = [
        "NightRider ride log",
        "Period:    " + period,
        "Generated: " + fmt_ts(time.time()),
        "Rides:     " + str(len(rides)),
        "",
    ]
    if not rides:
        lines.append("No rides in this period." + chr(10))
        return chr(10).join(lines)
    for r in rides:
        ack = r.get("dispatch_ack")
        lines.append("-" * 68)
        lines.append(fmt_ts(r["created"]) + "  ride " + str(r["id"]) + "  rider " + str(r.get("rider_id") or "-"))
        lines.append("  Name:     " + str(r.get("rider_name") or "-"))
        lines.append("  Route:    " + str(r.get("pickup")) + "  ->  " + str(r.get("dropoff")))
        lines.append("  Distance: " + str(r.get("distance_mi")) + " mi (driver leg "
                     + str(r.get("driver_to_pickup_mi")) + " mi)")
        lines.append("  Payment:  " + str(r.get("payment_method") or "Unspecified"))
        lines.append("  Fare:     $" + "%.2f" % r.get("fare", 0))
        lines.append("  Driver:   " + str(r.get("driver") or "-"))
        lines.append("  Status:   " + str(r.get("status"))
                     + ("   (dispatch ack " + fmt_ts(ack["at"]) + " by " + str(ack.get("by"))
                        + ", " + str(ack.get("latency_s")) + "s)" if ack else "   (no dispatch ack)"))
        for entry in r.get("ratings") or []:
            lines.append("  Rating:   " + str(entry.get("by")) + " " + str(entry.get("stars")) + "/5"
                         + ("  by " + str(entry["by_name"]) if entry.get("by_name") else "")
                         + ("  issues: " + ", ".join(entry["issues"]) if entry.get("issues") else "")
                         + ("  note: " + str(entry["note"]) if entry.get("note") else ""))
    lines.append("-" * 68)
    lines.append("")
    return chr(10).join(lines)


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

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        if os.environ.get("NIGHTRIDER_COOKIE_SECURE", "true").lower() == "true":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def send_json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def set_session_cookie(self, token):
        secure = os.environ.get("NIGHTRIDER_COOKIE_SECURE", "true").lower() == "true"
        parts = ["nr_session=" + urllib.parse.quote(token), "Path=/", "HttpOnly", "SameSite=Strict",
                 "Max-Age=" + str(auth.SESSION_DAYS * 86400)]
        if secure:
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def clear_session_cookie(self):
        secure = os.environ.get("NIGHTRIDER_COOKIE_SECURE", "true").lower() == "true"
        parts = ["nr_session=", "Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=0"]
        if secure:
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def user(self):
        if not os.environ.get("DATABASE_URL", "").strip():
            return None
        token = ""
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:].strip()
        if not token:
            cookie = self.headers.get("Cookie", "")
            for item in cookie.split(";"):
                key, sep, value = item.strip().partition("=")
                if sep and key == "nr_session":
                    token = urllib.parse.unquote(value)
                    break
        return auth.get_session(token)

    def require_role(self, *roles):
        user = self.user()
        if user and (not roles or user["role"] in roles):
            return user
        self.send_json(401 if not user else 403,
                       {"error": "sign in required" if not user else "not allowed"})
        return None

    def account_endpoint(self, path, data=None):
        """NightRider-only signup, login, logout and account setup."""
        if path == "/api/auth/me":
            return self.send_json(200, {"user": self.user()})
        if path == "/api/auth/register":
            now = time.time()
            ip = self.client_address[0]
            recent = [stamp for stamp in SIGNUP_ATTEMPTS.get(ip, []) if now - stamp < 3600]
            if len(recent) >= 10:
                SIGNUP_ATTEMPTS[ip] = recent
                return self.send_json(429, {"error": "Too many accounts created from this connection. Try again later."})
            recent.append(now)
            SIGNUP_ATTEMPTS[ip] = recent
            user, error = auth.create_user(data.get("username"), data.get("display_name"),
                                           data.get("password"), "rider")
            if error:
                return self.send_json(400, {"error": error})
            token = auth.create_session(user["id"])
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.set_session_cookie(token)
            body = json.dumps({"user": user}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/auth/login":
            key = (self.client_address[0], auth.normalize_username(data.get("username")))
            now = time.time()
            with LOGIN_FAILURES_LOCK:
                failures = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < 900]
                LOGIN_FAILURES[key] = failures
                if len(failures) >= 8:
                    return self.send_json(429, {"error": "Too many sign-in attempts. Wait 15 minutes and try again."})
            user = auth.authenticate(data.get("username"), data.get("password"))
            if not user:
                with LOGIN_FAILURES_LOCK:
                    LOGIN_FAILURES.setdefault(key, []).append(now)
                return self.send_json(401, {"error": "Username or password is incorrect."})
            with LOGIN_FAILURES_LOCK:
                LOGIN_FAILURES.pop(key, None)
            token = auth.create_session(user["id"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.set_session_cookie(token)
            body_data = {"user": user}
            if self.headers.get("X-NightRider-Client") == "android":
                body_data["token"] = token
            body = json.dumps(body_data).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/auth/logout":
            user = self.user()
            token = ""
            header = self.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                token = header[7:].strip()
            if not token:
                for item in self.headers.get("Cookie", "").split(";"):
                    key, sep, value = item.strip().partition("=")
                    if sep and key == "nr_session":
                        token = urllib.parse.unquote(value)
            auth.delete_session(token)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.clear_session_cookie()
            body = b'{"ok":true}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/auth/setup-dispatch":
            setup = os.environ.get("NIGHTRIDER_SETUP_TOKEN", "")
            if not setup or auth.has_dispatch_user() or not self.secrets_compare(data.get("setup_token"), setup):
                return self.send_json(403, {"error": "Initial setup is unavailable."})
            user, error = auth.create_user(data.get("username"), data.get("display_name"),
                                           data.get("password"), "dispatch")
            if error:
                return self.send_json(400, {"error": error})
            token = auth.create_session(user["id"])
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.set_session_cookie(token)
            body = json.dumps({"user": user}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/auth/change-password":
            user = self.require_role("rider", "driver", "dispatch")
            if not user:
                return
            if not auth.authenticate(user["username"], data.get("current_password")):
                return self.send_json(401, {"error": "Current password is incorrect."})
            if not auth.change_password(user["id"], data.get("new_password")):
                return self.send_json(400, {"error": "New password must be at least 8 characters."})
            token = auth.create_session(user["id"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.set_session_cookie(token)
            body = json.dumps({"ok": True, "user": user}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return self.send_json(404, {"error": "not found"})

    def page_access(self, path):
        if not os.environ.get("DATABASE_URL", "").strip():
            return True
        roles = {"/": ("rider",), "/index.html": ("rider",),
                 "/driver.html": ("driver",), "/dispatch.html": ("dispatch",)}
        allowed = roles.get(path)
        if not allowed:
            return True
        user = self.user()
        if not user:
            self.send_response(302)
            self.send_header("Location", "/account.html?next=" + urllib.parse.quote(path, safe="/"))
            self.end_headers()
            return False
        if user["role"] not in allowed:
            destinations = {"rider": "/", "driver": "/driver.html", "dispatch": "/dispatch.html"}
            self.send_response(302)
            self.send_header("Location", destinations[user["role"]])
            self.end_headers()
            return False
        return True

    def secrets_compare(self, value, expected):
        return hmac.compare_digest(str(value or "").encode(), str(expected or "").encode())

    def send_text(self, code, text, filename=None):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def driver_message(self, name, data):
        """Store one text from a driver page: a group text, or private to
        dispatch when the driver marks it private."""
        name = clean_text(name, 60)
        if not name:
            return self.send_json(400, {"error": "driver name required"})
        text = clean_text(data.get("text"), 1000)
        if not text:
            return self.send_json(400, {"error": "text required"})
        private = bool(data.get("private"))
        with LOCK:
            touch_driver(STORE, name)
            msg = add_message(STORE, name, text, driver=name, private=private)
            save(STORE)
        record_event("driver_message", driver=name, message=msg)
        return self.send_json(201, {"ok": True, "message": msg})

    def dispatch_message(self, data):
        """Store one text from dispatch: a group text for everyone, or a
        private text when `to` names a single driver."""
        text = clean_text(data.get("text"), 1000)
        if not text:
            return self.send_json(400, {"error": "text required"})
        to = clean_text(data.get("to"), 60)
        private = bool(to) and to != "all"
        with LOCK:
            if private:
                touch_driver(STORE, to)
            msg = add_message(STORE, "dispatch", text,
                              driver=to if private else None, private=private)
            save(STORE)
        record_event("dispatch_message", message=msg)
        return self.send_json(201, {"ok": True, "message": msg})

    def ack_ride(self, rid, data, dispatcher_name=None):
        """The handshake: dispatch confirms it really received the request."""
        by = clean_text(dispatcher_name, 60) or clean_text(data.get("by"), 40) or "dispatch"
        now = time.time()
        with LOCK:
            ride = STORE["rides"].get(rid)
            if not ride:
                return self.send_json(404, {"error": "not found"})
            ride["dispatch_ack"] = {"by": by, "at": now,
                                    "latency_s": round(max(0.0, now - ride["created"]), 2)}
            save(STORE)
            snapshot = public_ride(ride, STORE)
            ack = dict(ride["dispatch_ack"])
        # Tells the waiting rider screen that dispatch has the request in hand.
        record_event("ride_acknowledged", ride=rid, ack=ack, snapshot=snapshot)
        return self.send_json(200, {"ok": True, "ack": ack, "ride": snapshot})

    def dispatch_assign(self, ride_id, data):
        """Push a ride to a driver or recall it to the open queue."""
        driver_id = clean_text((data or {}).get("driver_account_id"), 80)
        driver = None
        if driver_id:
            driver = next((u for u in auth.list_users("driver")
                           if u["id"] == driver_id and u["enabled"]), None)
            if not driver:
                return self.send_json(400, {"error": "Choose an enabled driver account."})

        with LOCK:
            ride = STORE["rides"].get(ride_id)
            if not ride:
                return self.send_json(404, {"error": "ride not found"})
            if ride.get("status") in ("completed", "cancelled"):
                return self.send_json(409, {"error": "Closed rides cannot be assigned."})
            previous_id = ride.get("driver_account_id")
            previous_name = ride.get("driver")
            if driver and previous_id == driver_id:
                return self.send_json(200, public_ride(ride, STORE))
            if not driver and not previous_id:
                return self.send_json(409, {"error": "This ride is already in the open queue."})

            now = time.time()
            if driver:
                ride["driver"] = driver["display_name"]
                ride["driver_account_id"] = driver_id
                ride["status"] = "accepted"
                ride.pop("driver_coords", None)
                ride["driver_to_pickup_mi"] = 0.0
                ride["fare"] = fare(ride["distance_mi"], 0.0)
                log_status(ride, "accepted")
                action = "assigned" if not previous_id else "reassigned"
                new_name = driver["display_name"]
            else:
                ride["driver"] = None
                ride["driver_account_id"] = None
                ride["status"] = "requested"
                ride.pop("driver_coords", None)
                ride["driver_to_pickup_mi"] = 0.0
                ride["fare"] = fare(ride["distance_mi"], 0.0)
                log_status(ride, "requested")
                action = "recalled"
                new_name = None

            ride.setdefault("assignment_log", []).append({
                "action": action, "at": now,
                "from_driver": previous_name, "to_driver": new_name,
            })
            save(STORE)
            snapshot = public_ride(ride, STORE)

        record_event("ride_" + action, ride=ride_id, status=snapshot.get("status"),
                     snapshot=snapshot)
        return self.send_json(200, snapshot)

    def dispatch_get(self, path, qs):
        if path == "/api/dispatch/users":
            return self.send_json(200, {"users": auth.list_users("driver")})
        if path == "/api/dispatch/rider-accounts":
            return self.send_json(200, {"users": auth.list_users("rider")})
        if path == "/api/dispatch/events":
            since = int(_num(qs, "since", 0))
            wait = min(55.0, max(0.0, _num(qs, "wait", 25)))
            return self.send_json(200, read_events(since, None, wait))
        if path == "/api/dispatch/rides":
            with LOCK:
                rides = sorted(STORE["rides"].values(), key=lambda r: r["created"], reverse=True)
                return self.send_json(200, {"rides": [dispatch_ride(r, STORE) for r in rides]})
        if path == "/api/dispatch/riders":
            with LOCK:
                out = [dispatch_rider(rec, STORE) for rec in (STORE.get("riders") or {}).values()]
            out.sort(key=lambda r: r.get("last_seen") or 0, reverse=True)
            return self.send_json(200, {"riders": out})
        if path.startswith("/api/dispatch/riders/"):
            rid = path.split("/")[4]
            with LOCK:
                rec = (STORE.get("riders") or {}).get(rid)
                if not rec:
                    return self.send_json(404, {"error": "not found"})
                return self.send_json(200, dispatch_rider(rec, STORE, detail=True))
        if path == "/api/dispatch/drivers":
            now = time.time()
            with LOCK:
                out = [dispatch_driver(rec, now) for rec in STORE.get("drivers", {}).values()]
            out.sort(key=lambda d: (not d["active"], -float(d.get("last_seen") or 0)))
            return self.send_json(200, {"drivers": out, "window_s": DRIVER_ACTIVE_WINDOW, "now": now})
        if path == "/api/dispatch/messages":
            since = _num(qs, "since", 0)
            with LOCK:
                msgs = thread_messages(STORE, "dispatch", since)
            return self.send_json(200, {"viewer": "dispatch", "messages": msgs,
                                        "now": time.time()})
        if path == "/api/dispatch/export":
            start = parse_when(_first(qs, "from"), end_of_day=False)
            end = parse_when(_first(qs, "to"), end_of_day=True)
            with LOCK:
                text = export_log(STORE, start, end)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
            return self.send_text(200, text, filename="nightrider-log-%s.txt" % stamp)
        return self.send_json(404, {"error": "not found"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path == "/healthz":
            try:
                if os.environ.get("DATABASE_URL", "").strip():
                    auth.database_healthy()
                return self.send_json(200, {"ok": True})
            except Exception:
                return self.send_json(503, {"ok": False})
        if not self.page_access(path):
            return
        if path.startswith("/api/"):
            if path == "/api/auth/me":
                return self.account_endpoint(path)
            if path == "/api/dispatch/":
                return self.send_json(404, {"error": "not found"})
            if path.startswith("/api/dispatch/"):
                if os.environ.get("DATABASE_URL", "").strip() and not self.require_role("dispatch"):
                    return
                return self.dispatch_get(path, qs)
            if path == "/api/config":
                # Host environment variable wins (lets you rotate the key
                # without a code change); otherwise use the built-in key.
                key = os.environ.get("CARTO_API_KEY", DEFAULT_CARTO_KEY).strip()
                return self.send_json(200, {
                    "cartoKey": key,
                    # Country filter for address lookup, so results stay local.
                    "country": os.environ.get("ADDRESS_COUNTRY", "us").strip().lower(),
                    # One source of truth: the client prices the preview with
                    # these rates instead of hard-coding its own copy.
                    "rates": {
                        "flag_drop": FLAG_DROP,
                        "trip_per_mile": TRIP_PER_MILE,
                        "approach_per_mile": APPROACH_PER_MILE,
                    },
                    "demoDriver": DEMO_DRIVER if os.environ.get("NIGHTRIDER_ENABLE_DEMO_DRIVER", "false").lower() == "true" else None,
                    # Shared status labels + driver stage actions so the
                    # driver and dispatch boards never drift apart.
                    "statusLabels": STATUS_LABELS,
                    "stageAction": STAGE_ACTION,
                })
            if path == "/api/events":
                user = self.require_role("rider", "driver", "dispatch")
                if os.environ.get("DATABASE_URL", "").strip() and not user:
                    return
                since = int(_num(qs, "since", 0))
                ride = _first(qs, "ride") or None
                if user and user["role"] == "rider":
                    with LOCK:
                        owned = STORE["rides"].get(ride) if ride else None
                    if not owned or owned.get("rider_account_id") != user["id"]:
                        return self.send_json(404, {"error": "not found"})
                if user and user["role"] == "driver":
                    with LOCK:
                        visible = STORE["rides"].get(ride) if ride else None
                    if not visible or (visible.get("status") != "requested" and
                                       visible.get("driver_account_id") != user["id"]):
                        return self.send_json(404, {"error": "not found"})
                wait = min(55.0, max(0.0, _num(qs, "wait", 25)))
                return self.send_json(200, read_events(since, ride, wait))
            if path.startswith("/api/drivers/") and path.endswith("/messages"):
                user = self.require_role("driver", "dispatch")
                if os.environ.get("DATABASE_URL", "").strip() and not user:
                    return
                name = urllib.parse.unquote(path.split("/")[3])
                if user and user["role"] == "driver":
                    name = user["display_name"]
                since = _num(qs, "since", 0)
                with LOCK:
                    msgs = thread_messages(STORE, name, since)
                return self.send_json(200, {"driver": name, "messages": msgs, "now": time.time()})
            if path == "/api/rides":
                user = self.require_role("rider", "driver", "dispatch")
                if os.environ.get("DATABASE_URL", "").strip() and not user:
                    return
                with LOCK:
                    rides = sorted(STORE["rides"].values(), key=lambda r: r["created"], reverse=True)
                    if user and user["role"] == "rider":
                        rides = [r for r in rides if r.get("rider_account_id") == user["id"]]
                    elif user and user["role"] == "driver":
                        rides = [r for r in rides if r.get("status") == "requested" or
                                 r.get("driver_account_id") == user["id"]]
                    return self.send_json(200, {"rides": [public_ride(r, STORE) for r in rides]})
            if path.startswith("/api/rides/"):
                user = self.require_role("rider", "driver", "dispatch")
                if os.environ.get("DATABASE_URL", "").strip() and not user:
                    return
                rid = path.split("/")[3]
                with LOCK:
                    ride = STORE["rides"].get(rid)
                    if not ride:
                        return self.send_json(404, {"error": "not found"})
                    if user and user["role"] == "rider" and ride.get("rider_account_id") != user["id"]:
                        return self.send_json(404, {"error": "not found"})
                    if user and user["role"] == "driver" and ride.get("status") != "requested" and ride.get("driver_account_id") != user["id"]:
                        return self.send_json(404, {"error": "not found"})
                    if path.endswith("/ratings"):
                        if user and user["role"] == "rider":
                            return self.send_json(403, {"error": "not allowed"})
                        return self.send_json(200, {"ratings": ride.get("ratings") or []})
                    return self.send_json(200, public_ride(ride, STORE))
            return self.send_json(404, {"error": "not found"})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            data = self.read_json()
        except (ValueError, json.JSONDecodeError):
            return self.send_json(400, {"error": "invalid JSON"})

        origin = self.headers.get("Origin")
        if origin and self.headers.get("Cookie"):
            origin_host = urllib.parse.urlparse(origin).netloc.lower()
            request_host = self.headers.get("Host", "").lower()
            if origin_host != request_host:
                return self.send_json(403, {"error": "request origin is not allowed"})

        if path.startswith("/api/auth/"):
            return self.account_endpoint(path, data)

        if path == "/api/rides":
            user = self.require_role("rider")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            pickup = clean_text(data.get("pickup"))
            dropoff = clean_text(data.get("dropoff"))
            name = user["display_name"] if user else clean_text(data.get("rider_name"), 60)
            # The rider picks a payment method in the popup before the request
            # is sent; store it with the ride so dispatch and the driver see it.
            payment = clean_text(data.get("payment_method"), 30) or "Unspecified"
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
                "payment_method": payment, "rider_account_id": user["id"] if user else None,
                "driver": None, "created": time.time(),
                "status_log": [{"status": "requested", "at": time.time()}],
            }
            with LOCK:
                signals = {}
                rid = "NR-" + user["id"][:10].upper() if user else None
                if not rid:
                    return self.send_json(401, {"error": "sign in required"})
                ride["rider_id"] = rid
                STORE["rides"][ride["id"]] = ride
                rec = touch_rider(STORE, rid, signals, name)
                if ride["id"] not in rec["rides"]:
                    rec["rides"].append(ride["id"])
                save(STORE)
                reply = public_ride(ride, STORE)
            # The push: every dispatch screen waiting on /api/events wakes with
            # this request at once and has to acknowledge it (see ack_ride).
            record_event("ride_requested", ride=ride["id"], ack_required=True,
                         status="requested", snapshot=reply)
            return self.send_json(201, reply)

        if path == "/api/drivers/ping":
            user = self.require_role("driver")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            name = user["display_name"] if user else clean_text(data.get("name"), 60)
            if not name:
                return self.send_json(400, {"error": "name required"})
            coords = parse_coords(data.get("coords"))
            with LOCK:
                rec = touch_driver(STORE, name, coords, clean_text(data.get("status"), 20))
                save(STORE)
                out = dispatch_driver(rec)
            return self.send_json(200, {"ok": True, "driver": out})

        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "dispatch":
            user = self.require_role("dispatch")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            if len(parts) == 3 and parts[2] == "users":
                created, error = auth.create_user(data.get("username"), data.get("display_name"),
                                                  data.get("password"), "driver")
                if error:
                    return self.send_json(400, {"error": error})
                return self.send_json(201, {"user": created})
            if len(parts) == 5 and parts[2] == "users" and parts[4] == "delete":
                user_id = parts[3]
                with LOCK:
                    active_ride = any(
                        ride.get("driver_account_id") == user_id and
                        ride.get("status") not in ("completed", "cancelled")
                        for ride in STORE["rides"].values()
                    )
                    if active_ride:
                        return self.send_json(409, {"error": "This driver has an active ride. Complete or cancel it before deleting the account."})
                    if not auth.delete_driver_user(user_id):
                        return self.send_json(404, {"error": "Driver account not found."})
                return self.send_json(200, {"ok": True})
            if len(parts) == 4 and parts[2] == "users" and parts[3]:
                auth.set_user_enabled(parts[3], data.get("enabled") is True)
                return self.send_json(200, {"ok": True})
            if len(parts) == 5 and parts[2] == "users" and parts[4] == "password":
                if not auth.reset_password(parts[3], data.get("password")):
                    return self.send_json(400, {"error": "Password must be at least 8 characters."})
                return self.send_json(200, {"ok": True})
            if len(parts) == 5 and parts[2] == "rides" and parts[4] == "assign":
                return self.dispatch_assign(parts[3], data)
            if len(parts) == 5 and parts[2] == "rides" and parts[4] == "ack":
                return self.ack_ride(parts[3], data, user["display_name"] if user else None)
            if len(parts) == 3 and parts[2] == "message":
                return self.dispatch_message(data)
            if len(parts) == 5 and parts[2] == "drivers" and parts[4] == "message":
                # Kept as an alias: an old per-driver text is now private.
                data = dict(data or {})
                data["to"] = urllib.parse.unquote(parts[3])
                return self.dispatch_message(data)
            return self.send_json(404, {"error": "not found"})

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "drivers" and parts[3] == "message":
            user = self.require_role("driver")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            name = user["display_name"] if user else urllib.parse.unquote(parts[2])
            return self.driver_message(name, data)

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "rides":
            rid, action = parts[2], parts[3]
            user = self.require_role("rider", "driver", "dispatch")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            with LOCK:
                ride = STORE["rides"].get(rid)
                if not ride:
                    return self.send_json(404, {"error": "not found"})
                if user and user["role"] == "rider" and action != "cancel":
                    return self.send_json(403, {"error": "not allowed"})
                if user and user["role"] == "driver" and action not in ("accept", "advance", "rating", "cancel"):
                    return self.send_json(403, {"error": "not allowed"})
                if action == "rating":
                    if user and user["role"] not in ("driver", "dispatch"):
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "driver" and ride.get("driver_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    # A driver or dispatcher rates this ride; the score is filed
                    # against the hidden rider id behind it, never the name.
                    rating_data = dict(data)
                    if user:
                        rating_data["by"] = user["role"]
                        rating_data["by_name"] = user["display_name"]
                    entry = build_rating(rating_data)
                    if isinstance(entry, str):
                        return self.send_json(400, {"error": entry})
                    ride.setdefault("ratings", []).append(entry)
                    rec = (STORE.get("riders") or {}).get(ride.get("rider_id"))
                    if rec is not None:
                        rec.setdefault("ratings", []).append(dict(entry, ride=rid))
                    save(STORE)
                    snapshot = public_ride(ride, STORE)
                    record_event("ride_rated", ride=rid, rating=entry, snapshot=snapshot)
                    return self.send_json(201, {"ok": True, "rating": entry, "ride": snapshot})
                if action == "accept":
                    if user and user["role"] != "driver":
                        return self.send_json(403, {"error": "not allowed"})
                    if ride["status"] != "requested":
                        return self.send_json(409, {"error": "ride is no longer available"})
                    driver = user["display_name"] if user else clean_text(data.get("driver"), 60)
                    if not driver:
                        return self.send_json(400, {"error": "driver name required"})
                    ride["driver"] = driver
                    ride["driver_account_id"] = user["id"] if user else None
                    ride["status"] = "accepted"
                    log_status(ride, "accepted")
                    # Price the driver -> pickup leg now that we know who is
                    # coming and (when the driver's page shares it) where from.
                    approach = None
                    dcoords = parse_coords(data.get("driver_coords"))
                    demo_enabled = os.environ.get("NIGHTRIDER_ENABLE_DEMO_DRIVER", "false").lower() == "true"
                    if not dcoords and data.get("demo") and DEMO_DRIVER and demo_enabled:
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
                    if user and (user["role"] != "driver" or ride.get("driver_account_id") != user["id"]):
                        return self.send_json(403, {"error": "not allowed"})
                    nxt = NEXT.get(ride["status"])
                    if not nxt:
                        return self.send_json(409, {"error": "ride cannot advance"})
                    ride["status"] = nxt
                    log_status(ride, nxt)
                elif action == "cancel":
                    if user and user["role"] == "rider" and ride.get("rider_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "driver" and ride.get("driver_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    if ride["status"] in ("completed", "cancelled"):
                        return self.send_json(409, {"error": "ride already closed"})
                    actor = user["role"] if user else "rider"
                    ride["cancelled_by"] = actor
                    ride["cancelled_by_name"] = user["display_name"] if user else ride.get("rider_name")
                    ride["cancelled_at"] = time.time()
                    ride["status"] = "cancelled"
                    log_status(ride, "cancelled")
                else:
                    return self.send_json(404, {"error": "unknown action"})
                save(STORE)
                snapshot = public_ride(ride, STORE)
            # Status changes are pushed the same way, so the rider's screen
            # updates the moment a driver accepts instead of on a timer.
            record_event(EVENT_FOR.get(action, "ride_status"), ride=rid,
                         status=snapshot.get("status"), snapshot=snapshot)
            return self.send_json(200, snapshot)
        return self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"NightRider listening on http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

