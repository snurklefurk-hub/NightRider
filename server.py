"""NightRider basic server: static pages + JSON ride API. Standard library only."""
import copy, datetime, hmac, json, math, os, random, secrets, threading, time, urllib.parse, uuid
import auth
import account_archive
import history_purge
import demo_chatham_rides
import partner_desk

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
# Ephemeral one-time archive grants: never grant deletion from the legacy API.
ACCOUNT_ARCHIVE_GRANTS = {}
ACCOUNT_ARCHIVE_TTL = 600
HISTORY_PURGE_GRANTS = {}
HISTORY_PURGE_TTL = 600
STATUSES = ["requested", "accepted", "to_pickup", "at_pickup", "to_dropoff",
            "at_dropoff", "completed", "cancelled"]
DEFAULT_PRICING = {
    "flag_drop": 5.00,
    "approach_per_mile": 0.25,
    "trip_per_mile": 1.00,
    "multiplier": 1.00,
}


def normalize_pricing(saved):
    """Normalize persisted fare settings and keep older ride stores safe."""
    saved = saved if isinstance(saved, dict) else {}
    limits = {"flag_drop": 10000.0, "approach_per_mile": 10000.0,
              "trip_per_mile": 10000.0, "multiplier": 100.0}
    rates = {}
    for key, default in DEFAULT_PRICING.items():
        try:
            value = float(saved.get(key, default))
        except (TypeError, ValueError):
            value = default
        if not math.isfinite(value) or value < 0 or value > limits[key]:
            value = default
        rates[key] = round(value, 2)
    if rates["multiplier"] < 0.01:
        rates["multiplier"] = DEFAULT_PRICING["multiplier"]
    return rates
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
    store.setdefault("ride_messages", [])
    store.setdefault("account_messages", {})
    store.setdefault("chat_epoch", 0)
    partner_desk.collections(store)
    store.setdefault("driver_colors", {})
    store["pricing"] = normalize_pricing(store.get("pricing"))
    for ride in (store.get("rides") or {}).values():
        if isinstance(ride, dict):
            ride.setdefault("fare_rates", dict(store["pricing"]))
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
    auth.ensure_demo_users()
STORE = ensure_store(load())

DRIVER_CHAT_COLORS = [
    "#ff6b6b", "#ffa94d", "#ffd43b", "#a9e34b", "#38d9a9", "#3bc9db",
    "#4dabf7", "#748ffc", "#9775fa", "#da77f2", "#f783ac", "#ff8787",
]
PASSENGER_CHAT_COLOR = "#45e0c2"
DISPATCH_CHAT_COLOR = "#ffffff"


def driver_chat_color(user_id):
    """Persist a distinct bright chat color for each driver login."""
    user_id = str(user_id or "")
    if not user_id:
        return "#8dd3ff"
    with LOCK:
        colors = STORE.setdefault("driver_colors", {})
        color = colors.get(user_id)
        if not color:
            used = set(colors.values())
            choices = [value for value in DRIVER_CHAT_COLORS if value not in used]
            if choices:
                color = random.SystemRandom().choice(choices)
            else:
                rng = random.SystemRandom()
                color = "#%02x%02x%02x" % tuple(rng.randint(128, 255) for _ in range(3))
                while color in used:
                    color = "#%02x%02x%02x" % tuple(rng.randint(128, 255) for _ in range(3))
            colors[user_id] = color
            save(STORE)
        return color


def driver_chat_color_map():
    out = {}
    for account in auth.list_users("driver"):
        out[account["display_name"]] = driver_chat_color(account["id"])
    return out


def add_account_message(store, rider_account_id, user, data):
    """Permanent account-to-Dispatch conversation, hidden from drivers."""
    text = clean_text((data or {}).get("text"), 1000)
    if not text:
        return None, "Message text is required."
    if user["role"] not in ("dispatch", "rider"):
        return None, "Only riders and Dispatch can use account messages."
    if user["role"] == "rider" and user["id"] != rider_account_id:
        return None, "Account conversation not found."
    thread = store.setdefault("account_messages", {}).setdefault(rider_account_id, [])
    client_id = clean_text((data or {}).get("client_id"), 80)
    if client_id:
        for prior in reversed(thread):
            if prior.get("client_id") == client_id and prior.get("sender_id") == user["id"]:
                return prior, None
    message = {
        "id": uuid.uuid4().hex[:12], "rider_account_id": rider_account_id,
        "from": user["display_name"], "role": user["role"],
        "text": text, "at": time.time(),
    }
    if client_id:
        message["client_id"] = client_id
        message["sender_id"] = user["id"]
    thread.append(message)
    return message, None


def visible_account_messages(store, user, since=0.0):
    """Dispatch sees all account conversations; a rider sees only their own."""
    if user["role"] == "driver":
        return []
    threads = store.get("account_messages", {})
    if not isinstance(threads, dict):
        return []
    selected = threads.values() if user["role"] == "dispatch" else [threads.get(user["id"], [])]
    return [dict(message, message_kind="account") for thread in selected
            for message in thread if float(message.get("at") or 0) > since]


def unified_chat_messages(user, since=0.0):
    role = user["role"]
    account_id = user["id"]
    name = user["display_name"]
    colors = driver_chat_color_map()
    with LOCK:
        if role == "dispatch":
            messages = [dict(m, message_kind="team") for m in thread_messages(STORE, "dispatch", since)]
            rides = list(STORE["rides"].values())
        elif role == "driver":
            messages = [dict(m, message_kind="team") for m in thread_messages(STORE, name, since)]
            rides = [r for r in STORE["rides"].values() if r.get("driver_account_id") == account_id]
        else:
            messages = []
            rides = [r for r in STORE["rides"].values() if r.get("rider_account_id") == account_id]
        messages.extend(visible_account_messages(STORE, user, since))
        for ride in rides:
            for message in visible_ride_messages(STORE, ride["id"], role, since):
                item = dict(message, message_kind="ride")
                item.setdefault("audience", "shared")
                messages.append(item)
    for message in messages:
        if message.get("message_kind") in ("ride", "account"):
            message["mine"] = (
                (role == "dispatch" and message.get("role") == "dispatch") or
                (role == "driver" and message.get("role") == "driver") or
                (role == "rider" and message.get("role") == "rider" and message.get("from") == name)
            )
        else:
            message["mine"] = (
                (role == "dispatch" and message.get("role") == "dispatch") or
                (role == "driver" and message.get("role") == "driver" and message.get("from") == name)
            )
        if message.get("role") == "dispatch":
            message["chat_color"] = DISPATCH_CHAT_COLOR
            if message.get("channel") == "private":
                message["audience"] = "dispatch"
        elif message.get("role") == "rider":
            message["chat_color"] = PASSENGER_CHAT_COLOR
        else:
            driver_name = message.get("from") or ""
            # Preserve the original sender color when the ride changes drivers.
            message["chat_color"] = colors.get(driver_name, "#8dd3ff")
    messages.sort(key=lambda message: float(message.get("at") or 0))
    return messages


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
# Live rider fixes stay in memory, outside ride history and database snapshots.
LOCATION_FRESH_SECONDS = 120.0
RIDER_LOCATIONS = {}
RIDER_REVOKED_SHARES = {}
# A driver is available/idle/offline, or reports the ride stage they are in
# ("accepted", "to_pickup", ...) so dispatch sees live stage status.
DRIVER_STATUSES = ("available", "busy", "offline", "accepted", "to_pickup",
                   "at_pickup", "to_dropoff", "at_dropoff", "completed")


def touch_driver(store, name, coords=None, status=None, location_at=None, accuracy=None):
    """Record a driver heartbeat and return the stored record."""
    name = clean_text(name, 60)
    if not name:
        return None
    rec = store.setdefault("drivers", {}).setdefault(
        name, {"name": name, "first_seen": time.time()})
    rec["last_seen"] = time.time()
    if coords:
        rec["coords"] = coords
        rec["location_at"] = location_at if location_at is not None else time.time()
        rec["location_accuracy"] = accuracy
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
        "location_at": rec.get("location_at"),
        "location_accuracy": rec.get("location_accuracy"),
    }


def read_location(data, now=None):
    """Accept a recent device fix; never turn a cached old fix into a live one."""
    now = time.time() if now is None else now
    if not isinstance(data, dict):
        return None, "Send a location object."
    coords = parse_coords(data.get("coords"))
    if coords is None:
        return None, "A valid latitude and longitude are required."
    try:
        at = float(data.get("location_at", now))
        accuracy = data.get("accuracy")
        accuracy = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError, OverflowError):
        return None, "Invalid location timestamp or accuracy."
    if not math.isfinite(at) or not now - LOCATION_FRESH_SECONDS <= at <= now + 30:
        return None, "This location is too old. Request a new location fix."
    if accuracy is not None and (not math.isfinite(accuracy) or not 0 <= accuracy <= 100000):
        return None, "Invalid location accuracy."
    return {"coords": coords, "at": min(at, now), "accuracy": accuracy}, None


def dispatch_map_snapshot(store, now=None):
    """Only dispatch receives live rider positions, and only during active rides."""
    now = time.time() if now is None else now
    for key, revoked_at in list(RIDER_REVOKED_SHARES.items()):
        if now - revoked_at > 300:
            RIDER_REVOKED_SHARES.pop(key, None)
    for ride_id, fix in list(RIDER_LOCATIONS.items()):
        ride = store.get("rides", {}).get(ride_id)
        if not ride or ride.get("status") in ("completed", "cancelled"):
            RIDER_LOCATIONS.pop(ride_id, None)
    active_rides = [r for r in store.get("rides", {}).values()
                    if r.get("status") not in ("completed", "cancelled")]
    active_rides.sort(key=lambda r: r.get("created") or 0, reverse=True)
    drivers = []
    for rec in store.get("drivers", {}).values():
        item = dispatch_driver(rec, now)
        item["color"] = store.get("driver_colors", {}).get(rec.get("account_id"), "#8bbcff")
        item["location_fresh"] = bool(item.get("location_at") and
            now - float(item["location_at"]) <= LOCATION_FRESH_SECONDS)
        current = next((r for r in active_rides if r.get("driver") == rec.get("name")), None)
        if current:
            item["ride_id"] = current["id"]
            item["status"] = current["status"]
        drivers.append(item)
    rides = []
    for ride in active_rides:
        item = {key: ride.get(key) for key in (
            "id", "rider_name", "driver", "status", "pickup", "dropoff",
            "pickup_coords", "dropoff_coords", "distance_mi", "created")}
        fix = RIDER_LOCATIONS.get(ride["id"])
        if fix:
            item["rider_location"] = {key: fix[key] for key in ("coords", "at", "accuracy")}
            item["rider_location"]["sharing"] = fix.get("sharing", True)
            item["rider_location"]["live"] = bool(fix.get("sharing", True) and
                now - fix["at"] <= LOCATION_FRESH_SECONDS)
        else:
            item["rider_location"] = None
        rides.append(item)
    return {"rides": rides, "drivers": drivers,
            "demo_rides": demo_chatham_rides.map_rides(store),
            "demo_drivers": demo_chatham_rides.demo_drivers(store), "now": now,
            "location_fresh_seconds": LOCATION_FRESH_SECONDS}


def add_message(store, sender, text, driver=None, private=False, role=None, client_id=None, sender_id=None):
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
    thread = store.setdefault("messages", [])
    client_id = clean_text(client_id, 80)
    if client_id and sender_id:
        for prior in reversed(thread):
            if prior.get("client_id") == client_id and prior.get("sender_id") == sender_id:
                return prior
    msg = {"id": uuid.uuid4().hex[:8], "from": sender,
           "role": role or ("dispatch" if sender == "dispatch" else "driver"),
           "channel": "private" if private else "group",
           "driver": clean_text(driver, 60) if private else None,
           "text": text, "at": time.time()}
    if client_id and sender_id:
        msg["client_id"] = client_id
        msg["sender_id"] = sender_id
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


def add_ride_message(store, ride_id, user, data):
    """Save a ride conversation message with a rider/dispatch privacy boundary."""
    text = clean_text((data or {}).get("text"), 1000)
    if not text:
        return None, "Message text is required."
    audience = clean_text((data or {}).get("audience"), 20) or "shared"
    role = user["role"] if user else "rider"
    # Riders cannot make a private Dispatch-only conversation. Existing rider
    # messages are treated as shared history when a driver gets assigned.
    if role == "rider":
        audience = "shared"
    if audience not in ("shared", "rider"):
        return None, "Choose the rider conversation."
    if role == "driver" and audience != "shared":
        return None, "Driver-to-rider messages also go to Dispatch."
    sender = user["display_name"] if user else "Rider"
    sender_id = user["id"] if user else ""
    client_id = clean_text((data or {}).get("client_id"), 80)
    thread = store.setdefault("ride_messages", [])
    if client_id and sender_id:
        for prior in reversed(thread):
            if prior.get("client_id") == client_id and prior.get("sender_id") == sender_id:
                return prior, None
    message = {
        "id": uuid.uuid4().hex[:12], "ride_id": ride_id,
        "from": sender, "role": role, "audience": audience,
        "text": text, "at": time.time(),
    }
    if client_id and sender_id:
        message["client_id"] = client_id
        message["sender_id"] = sender_id
    thread.append(message)
    if len(store["ride_messages"]) > 2000:
        del store["ride_messages"][:-2000]
    return message, None


def visible_ride_messages(store, ride_id, viewer, since=0.0):
    out = []
    for message in store.get("ride_messages", []):
        if message.get("ride_id") != ride_id:
            continue
        if viewer == "driver" and message.get("audience") != "shared" and message.get("role") != "rider":
            # Dispatch-to-rider-only messages stay private. Rider-originated
            # legacy Dispatch-only messages follow the new shared-history rule.
            continue
        try:
            if since and float(message.get("at") or 0) <= float(since):
                continue
        except (TypeError, ValueError):
            continue
        out.append(message)
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


def dispatch_rider(rec, store, detail=False, account_created=None):
    out = {
        "id": rec.get("id"),
        "account_created": account_created,
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
    if by not in ("driver", "dispatch", "rider"):
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
        timeline = r.get("status_log") or []
        if timeline:
            lines.append("  Stage timeline:")
            for entry in timeline:
                stage = entry.get("status") or "unknown"
                stage_label = {
                    "requested": "Ride requested",
                    "accepted": "Driver accepted",
                    "to_pickup": "Driver heading to pickup",
                    "at_pickup": "Arrived at pickup",
                    "to_dropoff": "Departed pickup for drop-off",
                    "at_dropoff": "Arrived at destination",
                    "completed": "Ride completed",
                    "cancelled": "Ride cancelled",
                }.get(stage, STATUS_LABELS.get(stage, stage.replace("_", " ").title()))
                if entry.get("at") is not None:
                    lines.append("    " + stage_label + ": " + fmt_ts(entry["at"]))
        for entry in r.get("ratings") or []:
            lines.append("  Rating:   " + str(entry.get("by")) + " " + str(entry.get("stars")) + "/5"
                         + ("  by " + str(entry["by_name"]) if entry.get("by_name") else "")
                         + ("  issues: " + ", ".join(entry["issues"]) if entry.get("issues") else "")
                         + ("  note: " + str(entry["note"]) if entry.get("note") else ""))
    lines.append("-" * 68)
    lines.append("")
    return chr(10).join(lines)


# ---- Fares -------------------------------------------------------------
# Dispatch rates are read from the current store for each fare calculation.
def current_pricing():
    """Return a safe copy of persisted dispatch fare settings."""
    saved = STORE.get("pricing", {}) if "STORE" in globals() else {}
    return normalize_pricing(saved)


def validate_pricing(data):
    """Validate the four dispatch-editable fare inputs."""
    if not isinstance(data, dict):
        return None, "Enter a valid number for every price."
    limits = {
        "flag_drop": 10000.0,
        "approach_per_mile": 10000.0,
        "trip_per_mile": 10000.0,
        "multiplier": 100.0,
    }
    rates = {}
    for key, maximum in limits.items():
        try:
            value = float(data.get(key))
        except (TypeError, ValueError):
            return None, "Enter a valid number for every price."
        if not math.isfinite(value) or value < 0 or value > maximum:
            return None, "Prices must be between $0 and $10,000; multiplier must be between 0.01 and 100."
        rates[key] = round(value, 2)
    if rates["multiplier"] < 0.01:
        return None, "Multiplier must be between 0.01 and 100."
    return rates, None


def _miles(value):
    """Coerce a distance to a non-negative float; bad input counts as 0."""
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def fare(distance_mi, driver_to_pickup_mi=0.0, rates=None):
    """Flag drop plus the two per-mile legs, all adjusted by the multiplier."""
    rates = rates or current_pricing()
    trip = _miles(distance_mi)
    approach = _miles(driver_to_pickup_mi)
    subtotal = (rates["flag_drop"] + rates["trip_per_mile"] * trip +
                rates["approach_per_mile"] * approach)
    return round(subtotal * rates["multiplier"], 2)


def fare_breakdown(distance_mi, driver_to_pickup_mi=0.0, rates=None):
    """The itemised fare so the client never has to re-derive the formula."""
    rates = rates or current_pricing()
    trip = _miles(distance_mi)
    approach = _miles(driver_to_pickup_mi)
    multiplier = rates["multiplier"]
    return {
        "flag_drop": round(rates["flag_drop"] * multiplier, 2),
        "trip_mi": round(trip, 1),
        "trip_fare": round(rates["trip_per_mile"] * trip * multiplier, 2),
        "driver_to_pickup_mi": round(approach, 1),
        "approach_fare": round(rates["approach_per_mile"] * approach * multiplier, 2),
        "multiplier": multiplier,
        "total": fare(trip, approach, rates),
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
            return self.send_json(403, {"error": "Public Rider account creation is paused. Use the demo account to explore this software preview."})
        if path == "/api/auth/login":
            key = (self.client_address[0], auth.normalize_username(data.get("username")))
            now = time.time()
            with LOGIN_FAILURES_LOCK:
                failures = [stamp for stamp in LOGIN_FAILURES.get(key, []) if now - stamp < 900]
                LOGIN_FAILURES[key] = failures
                if len(failures) >= 8:
                    return self.send_json(429, {"error": "Too many sign-in attempts. Wait 15 minutes and try again."})
            if auth.normalize_username(data.get("username")) == "demo":
                demo_role = data.get("demo_role")
                if not demo_role and self.headers.get("X-NightRider-Client") == "android":
                    demo_role = "driver"
                user = auth.authenticate_demo(demo_role, data.get("password"))
            else:
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
            actor = self.user()
            if actor and actor.get("is_demo"):
                return self.send_json(403, {"error": "Demo accounts cannot manage accounts or initial setup."})
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
            if user.get("is_demo"):
                return self.send_json(403, {"error": "Demo accounts cannot change passwords."})
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
        roles = {"/rider": ("rider",), "/rider/": ("rider",), "/index.html": ("rider",),
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
            destinations = {"rider": "/rider", "driver": "/driver.html", "dispatch": "/dispatch.html"}
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

    def post_chat_message(self, user, data):
        text = clean_text((data or {}).get("text"), 1000)
        if not text:
            return self.send_json(400, {"error": "Message text is required."})
        role = user["role"]
        ride_id = clean_text((data or {}).get("ride_id"), 80)
        audience = clean_text((data or {}).get("audience"), 20) or "shared"
        to_driver = clean_text((data or {}).get("to_driver"), 60)
        account_chat = (data or {}).get("account_chat") is True
        target_rider = clean_text((data or {}).get("rider_account_id"), 80)
        if account_chat or target_rider:
            if role == "driver":
                return self.send_json(403, {"error": "Drivers cannot access account conversations."})
            if ride_id or to_driver or (data or {}).get("private"):
                return self.send_json(400, {"error": "Choose one conversation type."})
            if role == "rider":
                target_rider = user["id"]
            else:
                rider_accounts = auth.list_users("rider")
                if not any(account["id"] == target_rider and account["enabled"] for account in rider_accounts):
                    return self.send_json(404, {"error": "Rider account not found."})
            with LOCK:
                message, error = add_account_message(STORE, target_rider, user, data)
                if error:
                    return self.send_json(400, {"error": error})
                save(STORE)
            record_event("account_message", message_id=message["id"])
            return self.send_json(201, {"ok": True, "message": message})
        if ride_id:
            with LOCK:
                ride = STORE["rides"].get(ride_id)
                if not ride:
                    return self.send_json(404, {"error": "Ride not found."})
                if role == "rider" and ride.get("rider_account_id") != user["id"]:
                    return self.send_json(404, {"error": "Ride not found."})
                if role == "driver" and ride.get("driver_account_id") != user["id"]:
                    return self.send_json(403, {"error": "You are not assigned to this ride."})
                message, error = add_ride_message(STORE, ride_id, user, {
                    "text": text, "audience": audience,
                    "client_id": (data or {}).get("client_id"),
                })
                if error:
                    return self.send_json(400, {"error": error})
                save(STORE)
            record_event("ride_message", ride=ride_id, message=message)
            return self.send_json(201, {"ok": True, "message": message})

        if role == "rider":
            return self.send_json(400, {"error": "A ride is required to message."})
        private = bool((data or {}).get("private")) if role == "driver" else bool(to_driver)
        if role == "dispatch" and to_driver:
            accounts = auth.list_users("driver")
            target = next((account for account in accounts
                           if account["id"] == to_driver or account["display_name"] == to_driver), None)
            if not target:
                return self.send_json(404, {"error": "Driver not found."})
            to_driver = target["display_name"]
        elif role == "dispatch":
            to_driver = ""
        elif role == "driver":
            to_driver = user["display_name"] if private else ""
        with LOCK:
            message = add_message(
                STORE,
                user["display_name"] if role != "dispatch" else "dispatch",
                text,
                driver=to_driver or None,
                private=private,
                role=role,
                client_id=(data or {}).get("client_id"),
                sender_id=user["id"],
            )
            save(STORE)
        record_event("driver_message" if role == "driver" else "dispatch_message",
                     driver=user["display_name"] if role == "driver" else None,
                     message=message)
        return self.send_json(201, {"ok": True, "message": message})

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
            already_acknowledged = bool(ride.get("dispatch_ack"))
            if not already_acknowledged:
                ride["dispatch_ack"] = {"by": by, "at": now,
                                        "latency_s": round(max(0.0, now - ride["created"]), 2)}
                save(STORE)
            snapshot = public_ride(ride, STORE)
            ack = dict(ride["dispatch_ack"])
        # Multiple dispatch screens may acknowledge simultaneously; first ack wins.
        if not already_acknowledged:
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
                ride["fare"] = fare(ride["distance_mi"], 0.0, ride.get("fare_rates"))
                log_status(ride, "accepted")
                action = "assigned" if not previous_id else "reassigned"
                new_name = driver["display_name"]
            else:
                ride["driver"] = None
                ride["driver_account_id"] = None
                ride["status"] = "requested"
                ride.pop("driver_coords", None)
                ride["driver_to_pickup_mi"] = 0.0
                ride["fare"] = fare(ride["distance_mi"], 0.0, ride.get("fare_rates"))
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

    def prepare_account_archive(self, qs):
        """Issue an expiring export token. Never delete before a local save."""
        actor = self.user()
        if not actor or actor.get("is_demo") or actor["role"] != "dispatch" or not actor.get("dispatch_admin"):
            return self.send_json(403, {"error": "Dispatch administrator required."})
        role = _first(qs, "role")
        account_id = _first(qs, "id")
        if role not in ("rider", "driver") or not account_id:
            return self.send_json(400, {"error": "Select a Rider or Driver account."})
        user = auth.get_account_for_archive(account_id, role)
        if not user:
            return self.send_json(404, {"error": "Account not found."})
        with LOCK:
            if account_archive.account_has_active_ride(STORE, user):
                return self.send_json(409, {"error": "Account has an unfinished ride. Close the ride before archiving and deleting."})
            now = time.time()
            content = account_archive.serialise_archive(
                account_archive.build_archive(STORE, user, now))
            digest = account_archive.archive_sha256(content)
            token = secrets.token_urlsafe(32)
            for key, grant in list(ACCOUNT_ARCHIVE_GRANTS.items()):
                if grant["expires"] < now:
                    ACCOUNT_ARCHIVE_GRANTS.pop(key, None)
            ACCOUNT_ARCHIVE_GRANTS[token] = {
                "actor": actor["id"], "role": role, "account_id": account_id,
                "sha256": digest, "generated": now, "expires": now + ACCOUNT_ARCHIVE_TTL
            }
        return self.send_json(200, {
            "filename": account_archive.archive_filename(user, now),
            "content": content, "sha256": digest, "token": token,
            "expires_at_unix": now + ACCOUNT_ARCHIVE_TTL
        })

    def delete_account_after_archive(self, data):
        """Reject destructive calls lacking a freshly validated archive grant."""
        actor = self.user()
        if not actor or actor.get("is_demo") or actor["role"] != "dispatch" or not actor.get("dispatch_admin"):
            return self.send_json(403, {"error": "Dispatch administrator required."})
        if not isinstance(data, dict):
            return self.send_json(400, {"error": "Invalid deletion request."})
        role, account_id = data.get("role"), data.get("id")
        token, digest = data.get("token"), data.get("sha256")
        if (role not in ("rider", "driver") or not isinstance(account_id, str) or
                not isinstance(token, str) or not isinstance(digest, str)):
            return self.send_json(400, {"error": "A saved local archive is required before deletion."})
        with LOCK:
            grant = ACCOUNT_ARCHIVE_GRANTS.get(token)
            if (not grant or grant["expires"] < time.time() or
                    grant["actor"] != actor["id"] or
                    grant["role"] != role or grant["account_id"] != account_id or
                    not hmac.compare_digest(grant["sha256"], digest)):
                return self.send_json(409, {"error": "Archive authorization is missing, expired, or invalid. Save a new local archive."})
            user = auth.get_account_for_archive(account_id, role)
            if not user:
                ACCOUNT_ARCHIVE_GRANTS.pop(token, None)
                return self.send_json(404, {"error": "Account not found."})
            if account_archive.account_has_active_ride(STORE, user):
                return self.send_json(409, {"error": "Account has an unfinished ride. Deletion is blocked."})
            current = account_archive.serialise_archive(
                account_archive.build_archive(STORE, user, grant["generated"]))
            if not hmac.compare_digest(
                    account_archive.archive_sha256(current), grant["sha256"]):
                ACCOUNT_ARCHIVE_GRANTS.pop(token, None)
                return self.send_json(409, {"error": "Account history changed after export. Save an updated archive before deleting."})
            deleted = (auth.delete_rider_user(account_id) if role == "rider"
                       else auth.delete_driver_user(account_id))
            if not deleted:
                return self.send_json(404, {"error": "Account was not found. No deletion occurred."})
            # Invalidate all grants for the account: a saved file is required per deletion.
            for key, item in list(ACCOUNT_ARCHIVE_GRANTS.items()):
                if item["account_id"] == account_id:
                    ACCOUNT_ARCHIVE_GRANTS.pop(key, None)
        record_event("account_deleted", role=role, actor=actor["id"])
        return self.send_json(200, {"ok": True, "role": role, "account_id": account_id,
                                    "archive_sha256": digest})

    def prepare_history_archive(self, qs):
        """Create a bound, expiring export grant for private Dispatch history."""
        actor = self.user()
        if not actor or actor.get("role") != "dispatch" or actor.get("is_demo") or not actor.get("dispatch_admin"):
            return self.send_json(403, {"error": "Non-demo Dispatch administrator required."})
        kind = _first(qs, "kind")
        if kind not in history_purge.KINDS:
            return self.send_json(400, {"error": "Choose chat or rides history."})
        with LOCK:
            if history_purge.any_open_rides(STORE):
                return self.send_json(409, {"error": "Finish or cancel all active rides before archiving and clearing history."})
            now = time.time()
            content = history_purge.serialise(history_purge.snapshot(STORE, kind, now))
            digest = history_purge.sha256(content)
            token = secrets.token_urlsafe(32)
            for key, grant in list(HISTORY_PURGE_GRANTS.items()):
                if grant["expires"] < now:
                    HISTORY_PURGE_GRANTS.pop(key, None)
            HISTORY_PURGE_GRANTS[token] = {
                "actor": actor["id"], "kind": kind,
                "sha256": digest, "generated": now, "expires": now + HISTORY_PURGE_TTL
            }
        return self.send_json(200, {
            "filename": history_purge.filename(kind, now), "content": content,
            "sha256": digest, "token": token, "expires_at_unix": now + HISTORY_PURGE_TTL
        })

    def clear_history_after_archive(self, data):
        """Reject mutations unless a fresh, matching exported snapshot exists."""
        actor = self.user()
        if not actor or actor.get("role") != "dispatch" or actor.get("is_demo") or not actor.get("dispatch_admin"):
            return self.send_json(403, {"error": "Non-demo Dispatch administrator required."})
        if not isinstance(data, dict) or data.get("kind") not in history_purge.KINDS:
            return self.send_json(400, {"error": "Choose chat or rides history."})
        kind, token, digest = data["kind"], data.get("token"), data.get("sha256")
        if not isinstance(token, str) or not isinstance(digest, str):
            return self.send_json(409, {"error": "Save a local history archive before deletion."})
        with LOCK:
            grant = HISTORY_PURGE_GRANTS.get(token)
            if (not grant or grant["expires"] < time.time() or
                    grant["actor"] != actor["id"] or grant["kind"] != kind or
                    not hmac.compare_digest(grant["sha256"], digest)):
                return self.send_json(409, {"error": "History archive grant missing, expired, or mismatched. Export again."})
            if history_purge.any_open_rides(STORE):
                return self.send_json(409, {"error": "An active ride exists. Finish it before deleting history."})
            latest = history_purge.serialise(history_purge.snapshot(STORE, kind, grant["generated"]))
            if not hmac.compare_digest(history_purge.sha256(latest), grant["sha256"]):
                HISTORY_PURGE_GRANTS.pop(token, None)
                return self.send_json(409, {"error": "History changed after export. Save a new archive before deleting."})
            before = copy.deepcopy(STORE)
            try:
                counts = history_purge.purge(STORE, kind)
                # A ride purge also removes ride-linked chat; invalidate cached
                # messages in every connected browser in either case.
                STORE["chat_epoch"] = int(STORE.get("chat_epoch") or 0) + 1
                save(STORE)
            except Exception:
                STORE.clear()
                STORE.update(before)
                raise
            # Another export is necessary for every destructive action.
            HISTORY_PURGE_GRANTS.clear()
            if kind == "rides":
                for ride_id in before.get("rides", {}):
                    RIDER_LOCATIONS.pop(ride_id, None)
            # Prevent newly connected clients receiving deleted chat or ride
            # data through the in-memory long-poll event replay buffer.
            with EVENT_COND:
                EVENTS.clear()
        record_event("history_purged", history_kind=kind)
        return self.send_json(200, {"ok": True, "kind": kind,
                                    "archive_sha256": digest, "deleted": counts})

    def dispatch_get(self, path, qs):
        if path == "/api/dispatch/history-archive":
            return self.prepare_history_archive(qs)
        if path == "/api/dispatch/account-archive":
            return self.prepare_account_archive(qs)
        if path == "/api/dispatch/map":
            with LOCK:
                snapshot = dispatch_map_snapshot(STORE)
            return self.send_json(200, snapshot)
        if path == "/api/dispatch/pricing":
            return self.send_json(200, {"pricing": current_pricing()})
        if path == "/api/dispatch/users":
            return self.send_json(200, {"users": auth.list_users("driver")})
        if path == "/api/dispatch/staff":
            actor = self.user()
            if not actor or actor.get("is_demo") or not actor.get("dispatch_admin"):
                return self.send_json(403, {"error": "Dispatch administrator required."})
            users = auth.list_users("dispatch")
            admins = [item for item in users if not item.get("is_demo")]
            if admins:
                owner_id = min(admins, key=lambda item: (item["created_at"], item["id"]))["id"]
                for staff in users:
                    staff["dispatch_admin"] = staff["id"] == owner_id
            return self.send_json(200, {"users": users})
        if path == "/api/dispatch/rider-accounts":
            return self.send_json(200, {"users": auth.list_users("rider")})
        if path == "/api/dispatch/events":
            since = int(_num(qs, "since", 0))
            wait = min(55.0, max(0.0, _num(qs, "wait", 25)))
            return self.send_json(200, read_events(since, None, wait))
        if path == "/api/dispatch/rides":
            with LOCK:
                rides = sorted(STORE["rides"].values(), key=lambda r: r["created"], reverse=True)
                return self.send_json(200, {
                    "rides": [dispatch_ride(r, STORE) for r in rides],
                    # Never insert showroom examples into STORE['rides']: they
                    # cannot be assigned, charged, messaged, or sent to drivers.
                    "demo_rides": demo_chatham_rides.samples(STORE)
                })
        if path == "/api/dispatch/riders":
            accounts = {
                "NR-" + account["id"][:10].upper(): account["created_at"]
                for account in auth.list_users("rider")
            }
            with LOCK:
                out = [
                    dispatch_rider(rec, STORE, account_created=accounts.get(rec.get("id")))
                    for rec in (STORE.get("riders") or {}).values()
                ]
            out.sort(key=lambda r: r.get("last_seen") or 0, reverse=True)
            return self.send_json(200, {"riders": out})
        if path.startswith("/api/dispatch/riders/"):
            rid = path.split("/")[4]
            accounts = {
                "NR-" + account["id"][:10].upper(): account["created_at"]
                for account in auth.list_users("rider")
            }
            with LOCK:
                rec = (STORE.get("riders") or {}).get(rid)
                if not rec:
                    return self.send_json(404, {"error": "not found"})
                return self.send_json(200, dispatch_rider(
                    rec, STORE, detail=True, account_created=accounts.get(rec.get("id"))
                ))
        if path == "/api/dispatch/drivers":
            now = time.time()
            with LOCK:
                out = []
                active_statuses = ("accepted", "to_pickup", "at_pickup", "to_dropoff", "at_dropoff")
                for rec in STORE.get("drivers", {}).values():
                    driver = dispatch_driver(rec, now)
                    current_ride = next((
                        ride for ride in sorted(
                            STORE.get("rides", {}).values(),
                            key=lambda item: float(item.get("created") or 0),
                            reverse=True
                        )
                        if ride.get("driver") == rec.get("name") and
                        ride.get("status") in active_statuses
                    ), None)
                    if current_ride:
                        driver["ride_id"] = current_ride.get("id")
                        driver["ride_status"] = current_ride.get("status")
                    out.append(driver)
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
        if path == "/":
            # Bare domain opens Hub; legacy ride links with query parameters open Rider.
            location = "/rider?" + parsed.query if parsed.query else "/hub"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path in ("/map-lab", "/map-lab/", "/map-lab.html"):
            self.send_response(302)
            self.send_header("Location", "/hub")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/map-lab-midnight.js":
            # Cached Rider/Dispatch pages can still request the former palette URL.
            self.path = "/map-midnight.js"
        elif path in ("/hub", "/hub/"):
            self.path = "/hub.html"
        elif path in ("/partner-portal", "/partner-portal/"):
            self.path = "/partner-portal.html"
        elif path in ("/partner-desk", "/partner-desk/", "/partner-desk.html"):
            self.send_response(302)
            self.send_header("Location", "/dispatch.html#partner-offers")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        elif path in ("/affiliate-hub", "/affiliate-hub/"):
            self.path = "/affiliate-hub.html"
        elif path in ("/partner-desk-demo", "/partner-desk-demo/"):
            self.send_response(302)
            self.send_header("Location", "/partner-portal")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        elif path in ("/rider", "/rider/"):
            self.path = "/index.html"
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
            if path in ("/api/partner-desk", "/api/affiliate-hub"):
                return partner_desk.api_get(self, STORE, LOCK, path)
            if path == "/api/auth/me":
                return self.account_endpoint(path)
            if path == "/api/chat/messages":
                user = self.require_role("rider", "driver", "dispatch")
                if not user:
                    return
                return self.send_json(200, {"messages": unified_chat_messages(user, _num(qs, "since", 0)), "now": time.time(), "chat_epoch": STORE.get("chat_epoch", 0)})
            if path == "/api/dispatch/":
                return self.send_json(404, {"error": "not found"})
            if path.startswith("/api/dispatch/"):
                if (path == "/api/dispatch/map" or os.environ.get("DATABASE_URL", "").strip()) and not self.require_role("dispatch"):
                    return
                return self.dispatch_get(path, qs)
            if path == "/api/config":
                # Host environment variable wins (lets you rotate the key
                # without a code change); otherwise use the built-in key.
                key = os.environ.get("CARTO_API_KEY", DEFAULT_CARTO_KEY).strip()
                return self.send_json(200, {
                    "softwareDemo": True,
                    "transportationServicesOffered": False,
                    "riderRegistrationOpen": False,
                    "cartoKey": key,
                    "geoapifyKey": os.environ.get("GEOAPIFY_BROWSER_KEY", "").strip(),
                    # Country filter for address lookup, so results stay local.
                    "country": os.environ.get("ADDRESS_COUNTRY", "us").strip().lower(),
                    # One source of truth: the client prices the preview with
                    # these rates instead of hard-coding its own copy.
                    "rates": current_pricing(),
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
                    if path.endswith("/messages"):
                        if user and user["role"] == "driver" and ride.get("driver_account_id") != user["id"]:
                            return self.send_json(404, {"error": "not found"})
                        since = _num(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query), "since", 0)
                        viewer = user["role"] if user else "dispatch"
                        messages = visible_ride_messages(STORE, rid, viewer, since)
                        return self.send_json(200, {"ride_id": rid, "messages": messages, "now": time.time()})
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
        if path.startswith("/api/partner-desk/") or path.startswith("/api/affiliate-hub/"):
            return partner_desk.api_post(self, STORE, LOCK, save, path, data)
        if path == "/api/chat/messages":
            user = self.require_role("rider", "driver", "dispatch")
            if not user:
                return
            return self.post_chat_message(user, data)

        if path.startswith("/api/rides/") and path.endswith("/location"):
            user = self.require_role("rider")
            if not user:
                return
            if not isinstance(data, dict):
                return self.send_json(400, {"error": "Send a location object."})
            ride_id = path.split("/")[3]
            with LOCK:
                ride = STORE["rides"].get(ride_id)
                if not ride or ride.get("rider_account_id") != user["id"]:
                    return self.send_json(404, {"error": "not found"})
                sharing_id = data.get("sharing_id")
                valid_sharing_id = isinstance(sharing_id, str) and 8 <= len(sharing_id) <= 80
                if data.get("sharing") is False:
                    if ride_id in RIDER_LOCATIONS:
                        RIDER_LOCATIONS[ride_id]["sharing"] = False
                    if valid_sharing_id:
                        RIDER_REVOKED_SHARES[(ride_id, sharing_id)] = time.time()
                    return self.send_json(200, {"sharing": False})
                if data.get("sharing") is not True:
                    return self.send_json(400, {"error": "Choose whether to share your live location."})
                if not valid_sharing_id:
                    return self.send_json(400, {"error": "Start a new location sharing session."})
                if (ride_id, sharing_id) in RIDER_REVOKED_SHARES:
                    return self.send_json(409, {"error": "Location sharing was stopped."})
                if ride.get("status") in ("completed", "cancelled"):
                    return self.send_json(409, {"error": "This ride has ended. Location sharing is off."})
                fix, error = read_location(data)
                if error:
                    return self.send_json(400, {"error": error})
                RIDER_LOCATIONS[ride_id] = dict(fix, sharing_id=sharing_id, sharing=True)
            return self.send_json(200, {"sharing": True, "at": fix["at"]})

        if path == "/api/rides":
            user = self.require_role("rider")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            pickup = clean_text(data.get("pickup"))
            dropoff = clean_text(data.get("dropoff"))
            name = user["display_name"] if user else clean_text(data.get("rider_name"), 60)
            # The preview cannot create a real transportation or payment order,
            # regardless of which account or client submits the request.
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
            fare_rates = current_pricing()
            ride = {
                "id": uuid.uuid4().hex[:8], "rider_name": name, "pickup": pickup, "dropoff": dropoff,
                "pickup_coords": pickup_coords,
                "dropoff_coords": parse_coords(data.get("dropoff_coords")),
                "distance_mi": round(miles, 1), "driver_to_pickup_mi": round(approach, 1),
                "fare_rates": fare_rates,
                "fare": fare(miles, approach, fare_rates), "status": "requested",
                "payment_method": "Simulation only: no payment collected",
                "simulated": True, "transportation_service": False,
                "rider_account_id": user["id"] if user else None,
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
            fix = None
            if data.get("coords") is not None:
                fix, error = read_location(data)
                if error:
                    return self.send_json(400, {"error": error})
            with LOCK:
                rec = touch_driver(STORE, name, fix["coords"] if fix else None,
                    clean_text(data.get("status"), 20),
                    location_at=fix["at"] if fix else None,
                    accuracy=fix["accuracy"] if fix else None)
                if user:
                    rec["account_id"] = user["id"]
                if data.get("location_sharing") is False:
                    for key in ("coords", "location_at", "location_accuracy"):
                        rec.pop(key, None)
                save(STORE)
                out = dispatch_driver(rec)
            return self.send_json(200, {"ok": True, "driver": out})

        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "dispatch":
            user = self.require_role("dispatch")
            if os.environ.get("DATABASE_URL", "").strip() and not user:
                return
            if user and user.get("is_demo"):
                # Default-deny all administrative mutations. Only the existing
                # simulated ride and messaging workflow is available publicly.
                allowed = ((len(parts) == 3 and parts[2] == "message") or
                           (len(parts) == 5 and parts[2] == "rides" and parts[4] in ("assign", "ack")) or
                           (len(parts) == 5 and parts[2] == "drivers" and parts[4] == "message"))
                if not allowed:
                    return self.send_json(403, {"error": "Demo Dispatch cannot manage accounts, passwords, pricing, or destructive operations."})
            if len(parts) == 3 and parts[2] == "history-deletion":
                return self.clear_history_after_archive(data)
            if len(parts) == 3 and parts[2] == "account-deletion":
                return self.delete_account_after_archive(data)
            if len(parts) == 3 and parts[2] == "pricing":
                rates, error = validate_pricing(data or {})
                if error:
                    return self.send_json(400, {"error": error})
                with LOCK:
                    STORE["pricing"] = rates
                    save(STORE)
                record_event("pricing_updated", rates=rates)
                return self.send_json(200, {"ok": True, "pricing": rates})
            if parts[2] == "staff":
                if not user or not user.get("dispatch_admin"):
                    return self.send_json(403, {"error": "Dispatch administrator required."})
                if len(parts) == 3:
                    created, error = auth.create_user(data.get("username"), data.get("display_name"),
                                                      data.get("password"), "dispatch")
                    if error:
                        return self.send_json(400, {"error": error})
                    return self.send_json(201, {"user": created})
                if len(parts) == 5 and parts[4] in ("enabled", "password", "sessions"):
                    action = parts[4]
                    if action == "enabled" and not isinstance(data.get("enabled"), bool):
                        return self.send_json(400, {"error": "enabled must be true or false"})
                    if action == "password" and not 8 <= len(str(data.get("password") or "")) <= 256:
                        return self.send_json(400, {"error": "Password must contain 8 to 256 characters."})
                    value = data.get("enabled") if action == "enabled" else data.get("password")
                    if not auth.manage_dispatch_staff(parts[3], action, value):
                        return self.send_json(404, {"error": "Dispatch staff account not found or protected."})
                    return self.send_json(200, {"ok": True})
                return self.send_json(404, {"error": "not found"})
            if len(parts) == 3 and parts[2] == "users":
                created, error = auth.create_user(data.get("username"), data.get("display_name"),
                                                  data.get("password"), "driver")
                if error:
                    return self.send_json(400, {"error": error})
                created["chat_color"] = driver_chat_color(created["id"])
                return self.send_json(201, {"user": created})
            if len(parts) == 5 and parts[2] == "users" and parts[4] == "delete":
                return self.send_json(409, {"error": "Direct account deletion is disabled. Save the required local archive through Dispatch first."})
            if len(parts) == 4 and parts[2] == "users" and parts[3]:
                if not isinstance(data.get("enabled"), bool):
                    return self.send_json(400, {"error": "enabled must be true or false"})
                if not auth.set_user_enabled(parts[3], data["enabled"]):
                    return self.send_json(404, {"error": "Driver account not found."})
                return self.send_json(200, {"ok": True})
            if len(parts) == 5 and parts[2] == "users" and parts[4] == "password":
                if not 8 <= len(str(data.get("password") or "")) <= 256:
                    return self.send_json(400, {"error": "Password must contain 8 to 256 characters."})
                if not auth.reset_password(parts[3], data["password"]):
                    return self.send_json(404, {"error": "Driver account not found."})
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
                if user and user["role"] == "rider" and action not in ("cancel", "rating", "message"):
                    return self.send_json(403, {"error": "not allowed"})
                if user and user["role"] == "driver" and action not in ("accept", "advance", "rating", "cancel", "message"):
                    return self.send_json(403, {"error": "not allowed"})
                if action == "message":
                    if user and user["role"] == "rider" and ride.get("rider_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "driver" and ride.get("driver_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "rider" and data.get("audience", "shared") == "shared" and not ride.get("driver_account_id"):
                        return self.send_json(409, {"error": "A driver has not been assigned yet. You can message Dispatch for now."})
                    message, error = add_ride_message(STORE, rid, user, data)
                    if error:
                        return self.send_json(400, {"error": error})
                    save(STORE)
                    record_event("ride_message", ride=rid, message=message)
                    return self.send_json(201, {"ok": True, "message": message})
                if action == "rating":
                    if user and user["role"] not in ("driver", "dispatch", "rider"):
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "driver" and ride.get("driver_account_id") != user["id"]:
                        return self.send_json(403, {"error": "not allowed"})
                    if user and user["role"] == "rider":
                        if ride.get("rider_account_id") != user["id"]:
                            return self.send_json(403, {"error": "not allowed"})
                        if ride.get("status") != "completed" or not ride.get("driver_account_id"):
                            return self.send_json(409, {"error": "Rate your driver after the ride is completed."})
                        if any(r.get("by") == "rider" for r in ride.get("ratings") or []):
                            return self.send_json(409, {"error": "You already rated this driver."})
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
                    if entry["by"] in ("driver", "dispatch") and rec is not None:
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
                        ride["fare"] = fare(ride["distance_mi"], ride["driver_to_pickup_mi"], ride.get("fare_rates"))
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
                    now = time.time()
                    if user and user["role"] == "driver":
                        ride["last_driver_release"] = {
                            "driver": user["display_name"], "at": now,
                        }
                        ride["driver"] = None
                        ride["driver_account_id"] = None
                        ride.pop("driver_coords", None)
                        ride["driver_to_pickup_mi"] = 0.0
                        ride["fare"] = fare(ride["distance_mi"], 0.0, ride.get("fare_rates"))
                        ride["status"] = "requested"
                        log_status(ride, "requested")
                    else:
                        actor = user["role"] if user else "rider"
                        ride["cancelled_by"] = actor
                        ride["cancelled_by_name"] = user["display_name"] if user else ride.get("rider_name")
                        ride["cancelled_at"] = now
                        ride["status"] = "cancelled"
                        log_status(ride, "cancelled")
                else:
                    return self.send_json(404, {"error": "unknown action"})
                if ride.get("status") in ("completed", "cancelled"):
                    RIDER_LOCATIONS.pop(rid, None)
                save(STORE)
                snapshot = public_ride(ride, STORE)
            # Status changes are pushed the same way, so the rider's screen
            # updates the moment a driver accepts instead of on a timer.
            event_type = ("ride_driver_released" if action == "cancel" and user and
                          user["role"] == "driver" else EVENT_FOR.get(action, "ride_status"))
            record_event(event_type, ride=rid, status=snapshot.get("status"), snapshot=snapshot)
            return self.send_json(200, snapshot)
        return self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"NightRider listening on http://0.0.0.0:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


