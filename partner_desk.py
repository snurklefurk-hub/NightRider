"""Invite-only affiliate offer preview.

All affiliate offers are SOFTWARE SIMULATIONS. Nothing in this module creates rides,
collects payment, or guarantees driver availability. Mutations are serialized by
server.LOCK; multi-worker transactional dispatch is a future workstream.
"""
import hashlib
import hmac
import math
import secrets
import time
import uuid
from datetime import datetime, timezone

OFFER_STATES = ("submitted", "awaiting_partner", "agreed_preview",
                "declined", "withdrawn", "expired")
MAX_OFFER_AGE = 7 * 86400


class PartnerError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def collections(store):
    return (store.setdefault("affiliate_partners", {}),
            store.setdefault("affiliate_offers", {}),
            store.setdefault("affiliate_events", []))


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _text(value, length):
    return str(value or "").strip()[:length]


def _log(store, kind, actor, offer_id=None, partner_id=None):
    event = {"id": uuid.uuid4().hex, "type": kind, "actor": actor,
             "offer_id": offer_id, "partner_id": partner_id, "at": time.time()}
    collections(store)[2].append(event)
    return event


def create_partner(store, name, contact, actor):
    name, contact = _text(name, 120), _text(contact, 160)
    if len(name) < 2:
        raise PartnerError(400, "Organization name is required.")
    partners, _, _ = collections(store)
    partner_id = uuid.uuid4().hex
    # 256 bits of entropy; token is returned once and never stored in plaintext.
    token = secrets.token_urlsafe(32)
    partners[partner_id] = {"id": partner_id, "name": name, "contact": contact,
                            "enabled": True, "verified": True,
                            "token_hash": _hash(token), "created_at": time.time()}
    _log(store, "partner_approved", actor, partner_id=partner_id)
    return public_partner(partners[partner_id]), token


def public_partner(partner):
    return {key: partner.get(key) for key in
            ("id", "name", "contact", "enabled", "verified", "created_at")}


def authenticate(store, token):
    if not isinstance(token, str) or len(token) < 30 or len(token) > 150:
        return None
    digest = _hash(token)
    partners, _, _ = collections(store)
    for partner in partners.values():
        if (partner.get("enabled") and partner.get("verified") and
                hmac.compare_digest(digest, partner.get("token_hash", ""))):
            return partner
    return None


def set_partner_enabled(store, partner_id, enabled, actor):
    partners, _, _ = collections(store)
    partner = partners.get(partner_id)
    if not partner:
        raise PartnerError(404, "Partner not found.")
    if not isinstance(enabled, bool):
        raise PartnerError(400, "enabled must be true or false.")
    partner["enabled"] = enabled
    _log(store, "partner_enabled" if enabled else "partner_disabled", actor,
         partner_id=partner_id)
    return public_partner(partner)


def rotate_token(store, partner_id, actor):
    partners, _, _ = collections(store)
    partner = partners.get(partner_id)
    if not partner:
        raise PartnerError(404, "Partner not found.")
    token = secrets.token_urlsafe(32)
    partner["token_hash"] = _hash(token)
    _log(store, "partner_access_rotated", actor, partner_id=partner_id)
    return token


def _pickup_timestamp(value):
    if not isinstance(value, str) or len(value) > 45:
        raise PartnerError(400, "Provide a pickup time with timezone.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PartnerError(400, "Invalid pickup time.")
    if dt.tzinfo is None:
        raise PartnerError(400, "Pickup time must include a timezone.")
    stamp = dt.astimezone(timezone.utc).timestamp()
    if stamp <= time.time() or stamp > time.time() + 90 * 86400:
        raise PartnerError(400, "Pickup must be in the next 90 days.")
    return stamp


def submit_offer(store, partner, payload):
    if not partner.get("enabled") or not partner.get("verified"):
        raise PartnerError(403, "Partner is not approved.")
    if not isinstance(payload, dict):
        raise PartnerError(400, "Invalid offer.")
    pickup = _text(payload.get("pickup"), 180)
    dropoff = _text(payload.get("dropoff"), 180)
    ref = _text(payload.get("reference"), 80)
    notes = _text(payload.get("notes"), 800)
    if len(pickup) < 5 or len(dropoff) < 5 or len(ref) < 2:
        raise PartnerError(400, "Reference, pickup and destination are required.")
    try:
        passengers = int(payload.get("passengers"))
        bags = int(payload.get("bags"))
        payout = float(payload.get("payout"))
    except (ValueError, TypeError, OverflowError):
        raise PartnerError(400, "Passengers, bags and payout must be valid numbers.")
    if not (1 <= passengers <= 4 and 0 <= bags <= 4):
        raise PartnerError(422, "NightRider preview supports 1–4 passengers and 0–4 bags; luggage fit must be confirmed.")
    if not math.isfinite(payout) or payout <= 0 or payout > 10000:
        raise PartnerError(400, "Enter a finite proposed payout from $0.01 to $10,000.")
    if payload.get("authorized") is not True:
        raise PartnerError(403, "Passenger booking authority must be attested.")
    pickup_at = _pickup_timestamp(payload.get("pickup_at"))
    _, offers, _ = collections(store)
    if any(o["partner_id"] == partner["id"] and o["reference"].lower() == ref.lower()
           for o in offers.values()):
        raise PartnerError(409, "This partner reservation reference already exists.")
    now = time.time()
    offer = {"id": uuid.uuid4().hex[:12], "partner_id": partner["id"],
             "partner_name": partner["name"], "reference": ref,
             "pickup": pickup, "dropoff": dropoff, "pickup_at": pickup_at,
             "passengers": passengers, "bags": bags, "payout": round(payout, 2),
             "notes": notes, "authorized": True, "status": "submitted",
             "revision": 1, "created_at": now, "updated_at": now,
             "expires_at": min(pickup_at, now + MAX_OFFER_AGE)}
    offers[offer["id"]] = offer
    _log(store, "offer_submitted", partner["id"], offer["id"], partner["id"])
    return dict(offer)


def transition(store, offer_id, actor, action, revision, partner=None):
    _, offers, _ = collections(store)
    offer = offers.get(offer_id)
    if not offer or (partner and offer["partner_id"] != partner["id"]):
        raise PartnerError(404, "Offer not found.")
    if type(revision) is not int or revision != offer["revision"]:
        raise PartnerError(409, "Offer changed; refresh and review its current terms.")
    deadline = offer.get("confirmation_due_at") if offer["status"] == "awaiting_partner" else offer["expires_at"]
    if offer["status"] in ("submitted", "awaiting_partner") and time.time() >= deadline:
        offer["status"] = "expired"
        offer["revision"] += 1
        offer["updated_at"] = time.time()
        _log(store, "offer_expired", "system", offer_id, offer["partner_id"])
        raise PartnerError(410, "Offer expired. Reload the inbox.")
    allowed = {
        ("submitted", "accept", False): "awaiting_partner",
        ("submitted", "decline", False): "declined",
        ("submitted", "withdraw", True): "withdrawn",
        ("awaiting_partner", "confirm", True): "agreed_preview",
        ("awaiting_partner", "withdraw", True): "withdrawn",
        ("awaiting_partner", "decline", False): "declined",
    }
    target = allowed.get((offer["status"], action, bool(partner)))
    if not target:
        raise PartnerError(409, "This offer cannot perform that action.")
    offer["status"] = target
    if target == "awaiting_partner":
        offer["confirmation_due_at"] = min(time.time() + 300, offer["pickup_at"])
    offer["revision"] += 1
    offer["updated_at"] = time.time()
    _log(store, "offer_" + target, actor, offer_id, offer["partner_id"])
    return dict(offer)


def list_offers(store, partner=None):
    _, offers, _ = collections(store)
    result = []
    for offer in offers.values():
        if partner and offer["partner_id"] != partner["id"]:
            continue
        visible = dict(offer)
        due = visible.get("confirmation_due_at") if visible["status"] == "awaiting_partner" else visible["expires_at"]
        if visible["status"] in ("submitted", "awaiting_partner") and time.time() >= due:
            visible["status"] = "expired"
        result.append(visible)
    return sorted(result, key=lambda o: o["created_at"], reverse=True)


def _admin(handler):
    user = handler.require_role("dispatch")
    if not user:
        return None
    if user.get("is_demo") or not user.get("dispatch_admin"):
        handler.send_json(403, {"error": "Dispatch administrator required; demo users cannot manage partners."})
        return None
    return user


def _member(handler, store, lock):
    # Intentionally not a cookie: a partner key cannot accidentally inherit
    # a rider/driver/Dispatch session or become usable from a cross-site form.
    with lock:
        partner = authenticate(store, handler.headers.get("X-NR-Partner-Token", ""))
        return dict(partner) if partner else None


def api_get(handler, store, lock, path):
    if not __import__("os").environ.get("DATABASE_URL", "").strip():
        return handler.send_json(503, {"error": "Partner accounts require a database."})
    if path == "/api/partner-desk":
        if not _admin(handler):
            return
        with lock:
            partners, _, events = collections(store)
            result = {"partners": [public_partner(p) for p in partners.values()],
                      "offers": list_offers(store), "events": list(events[-100:])}
        return handler.send_json(200, result)
    if path == "/api/affiliate-hub":
        member = _member(handler, store, lock)
        if not member:
            return handler.send_json(401, {"error": "Verified partner access token required."})
        with lock:
            result = {"partner": public_partner(member),
                      "offers": list_offers(store, member)}
        return handler.send_json(200, result)
    return handler.send_json(404, {"error": "not found"})


def api_post(handler, store, lock, save, path, data):
    if not __import__("os").environ.get("DATABASE_URL", "").strip():
        return handler.send_json(503, {"error": "Partner accounts require a database."})
    if not isinstance(data, dict):
        return handler.send_json(400, {"error": "A JSON object is required."})
    parts = path.strip("/").split("/")
    is_admin = len(parts) >= 2 and parts[1] == "partner-desk"
    if is_admin:
        actor = _admin(handler)
        if not actor:
            return
        member = None
        actor_name = actor["id"]
    elif len(parts) >= 2 and parts[1] == "affiliate-hub":
        member = _member(handler, store, lock)
        if not member:
            return handler.send_json(401, {"error": "Verified partner access token required."})
        actor_name = member["id"]
    else:
        return handler.send_json(404, {"error": "not found"})
    try:
        with lock:
            if is_admin and parts == ["api", "partner-desk", "partners"]:
                value, token = create_partner(store, data.get("name"), data.get("contact"), actor_name)
                result, code = {"partner": value, "access_token_once": token}, 201
            elif is_admin and len(parts) == 5 and parts[2] == "partners" and parts[4] == "enabled":
                value = set_partner_enabled(store, parts[3], data.get("enabled"), actor_name)
                result, code = {"partner": value}, 200
            elif is_admin and len(parts) == 5 and parts[2] == "partners" and parts[4] == "rotate":
                token = rotate_token(store, parts[3], actor_name)
                result, code = {"access_token_once": token}, 200
            elif is_admin and len(parts) == 5 and parts[2] == "offers" and parts[4] in ("accept", "decline"):
                value = transition(store, parts[3], actor_name, parts[4], data.get("revision"))
                result, code = {"offer": value}, 200
            elif not is_admin and parts == ["api", "affiliate-hub", "offers"]:
                value = submit_offer(store, member, data)
                result, code = {"offer": value}, 201
            elif not is_admin and len(parts) == 5 and parts[2] == "offers" and parts[4] in ("confirm", "withdraw"):
                value = transition(store, parts[3], actor_name, parts[4], data.get("revision"), member)
                result, code = {"offer": value}, 200
            else:
                return handler.send_json(404, {"error": "not found"})
            save(store)
    except PartnerError as exc:
        # An attempted late action can mark an offer expired; persist that audit
        # transition even though its caller receives an HTTP 410.
        if exc.code == 410:
            with lock:
                save(store)
        return handler.send_json(exc.code, {"error": str(exc)})
    return handler.send_json(code, result)
