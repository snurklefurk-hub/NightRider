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
    if offer["status"] == "submitted" and time.time() >= offer["expires_at"]:
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
    offer["revision"] += 1
    offer["updated_at"] = time.time()
    _log(store, "offer_" + target, actor, offer_id, offer["partner_id"])
    return dict(offer)


def list_offers(store, partner=None):
    _, offers, _ = collections(store)
    return sorted((dict(o) for o in offers.values()
                   if partner is None or o["partner_id"] == partner["id"]),
                  key=lambda o: o["created_at"], reverse=True)
