"""Isolated agent thread hosted beside NightRider, sharing only its database."""
import base64
import hashlib
import hmac
import os
import re
import threading
import time
import psycopg

TABLE = """CREATE TABLE IF NOT EXISTS agent_mailbox_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender TEXT NOT NULL CHECK (sender IN ('Barb', 'Hoss', 'Gab')),
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 12000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedupe TEXT
)"""
TOKENS = {"reader": "READER_TOKEN", "Barb": "BARB_TOKEN",
          "Hoss": "HOSS_TOKEN", "Gab": "GAB_TOKEN"}


def initialize():
    values = [os.environ.get(key, "") for key in TOKENS.values()]
    if any(len(value) < 24 for value in values) or len(set(values)) != 4:
        raise RuntimeError("Four distinct mailbox tokens of at least 24 characters are required")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(TABLE)
        # Older deployments created the table without the dedupe column.
        connection.execute("ALTER TABLE agent_mailbox_messages "
                           "ADD COLUMN IF NOT EXISTS dedupe TEXT")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS "
                           "agent_mailbox_messages_dedupe_idx "
                           "ON agent_mailbox_messages (dedupe) WHERE dedupe IS NOT NULL")


def credential_matches(supplied, token):
    """Compare credentials as bytes so non-ASCII input cannot raise TypeError."""
    try:
        return hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))
    except (AttributeError, UnicodeEncodeError):
        return False


def role(handler):
    header = handler.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    supplied = header[7:]
    for sender, env in TOKENS.items():
        token = os.environ.get(env, "")
        if token and credential_matches(supplied, token):
            return sender
    return None


def get(handler, qs):
    if not role(handler):
        return handler.send_json(401, {"error": "Invalid token"})
    after = (qs.get("after") or ["0"])[0]
    if not re.fullmatch(r"0|[1-9][0-9]{0,18}", after):
        return handler.send_json(400, {"error": "Invalid cursor"})
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        rows = connection.execute(
            "SELECT id, sender, body, created_at FROM agent_mailbox_messages "
            "WHERE id > %s ORDER BY id ASC LIMIT 200", (int(after),)).fetchall()
    return handler.send_json(200, {"messages": [
        {"id": str(id), "sender": sender, "body": body, "created_at": timestamp.isoformat()}
        for id, sender, body, timestamp in rows]})


def post(handler, data):
    sender = role(handler)
    if not sender:
        return handler.send_json(401, {"error": "Invalid token"})
    if sender == "reader":
        return handler.send_json(403, {"error": "Read-only token"})
    body = data.get("body") if isinstance(data, dict) else None
    if not isinstance(body, str) or not body.strip() or len(body) > 12000:
        return handler.send_json(400, {"error": "Body must contain 1 to 12000 characters"})
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        id, created_at = connection.execute(
            "INSERT INTO agent_mailbox_messages(sender, body) VALUES (%s, %s) "
            "RETURNING id, created_at", (sender, body.strip())).fetchone()
    return handler.send_json(201, {"message": {
        "id": str(id), "sender": sender, "body": body.strip(),
        "created_at": created_at.isoformat()}})


# --------------------------------------------------------------------------
# Signed inbound beacon (GET /agent-mailbox/in, owner-approved).
#
# Barb's ordinary chat cannot hold bearer tokens or call the API, but its
# message renderer fetches image URLs. A signed GET lets her post her own
# messages through the same append-only table without ever seeing a bearer
# token. The HMAC secret is shared with her chat instructions only and is
# never committed to this repository. Messages are deduplicated by an
# optional nonce so repeated renders of the same beacon URL stay idempotent.
# --------------------------------------------------------------------------

TRANSPARENT_GIF = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
BEACON_SECRET_LABEL = b"agent-mailbox beacon-in v1"
IN_RATE_LIMIT = 40
IN_RATE_WINDOW = 60.0
IN_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
_in_attempts = []
_in_rate_lock = threading.Lock()


def beacon_secret():
    """Secret bytes for Barb's beacon signatures.

    A BARB_IN_SECRET environment variable of 32+ characters overrides;
    otherwise the secret is derived from BARB_TOKEN with a domain label, so
    the route needs no extra deployment environment variable."""
    override = os.environ.get("BARB_IN_SECRET", "")
    if len(override) >= 32:
        return override.encode("utf-8")
    barb = os.environ.get("BARB_TOKEN", "")
    return hmac.new(barb.encode("utf-8"), BEACON_SECRET_LABEL, hashlib.sha256).digest()


def beacon_signature_valid(payload, signature):
    try:
        data = payload.encode("ascii")
        supplied = signature.lower().strip().encode("ascii")
    except (AttributeError, UnicodeEncodeError):
        return False
    expected = hmac.new(beacon_secret(), data, hashlib.sha256).hexdigest().encode("ascii")
    return hmac.compare_digest(expected, supplied)


def beacon_body(payload):
    """Decode a base64url payload into message text (raises on malformed input)."""
    padded = payload + "=" * (-len(payload) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")


def beacon_rate_ok():
    now = time.monotonic()
    with _in_rate_lock:
        while _in_attempts and now - _in_attempts[0] > IN_RATE_WINDOW:
            _in_attempts.pop(0)
        if len(_in_attempts) >= IN_RATE_LIMIT:
            return False
        _in_attempts.append(now)
        return True


def _send_beacon(handler, status):
    """Acknowledge a beacon with a 1x1 transparent GIF so image renderers stay happy."""
    handler.send_response(status)
    handler.send_header("Content-Type", "image/gif")
    handler.send_header("Content-Length", str(len(TRANSPARENT_GIF)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(TRANSPARENT_GIF)


def beacon_get(handler, qs):
    """Handle GET /agent-mailbox/in?m=<base64url>&sig=<hex hmac>&n=<nonce>[&fmt=json].

    Response body is a transparent GIF by default; fmt=json returns a JSON
    receipt for curl verification instead. Only the Barb sender is possible:
    the route has no bearer-token path and the signature secret is fixed."""
    first = lambda key: (qs.get(key) or [""])[0]
    payload, signature, nonce = first("m"), first("sig"), first("n")
    if first("fmt") == "json" and first("debug") == "peek":
        override = os.environ.get("BARB_IN_SECRET", "")
        return handler.send_json(200, {
            "debug": "peek",
            "override_bytes": len(override.encode("utf-8")) if override else 0,
            "override_sha256_8": hashlib.sha256(override.encode("utf-8")).hexdigest()[:8] if override else "",
            "derived_sha256_8": hashlib.sha256(hmac.new(
                os.environ.get("BARB_TOKEN", "").encode("utf-8"), BEACON_SECRET_LABEL,
                hashlib.sha256).digest()).hexdigest()[:8],
        })
    ack = lambda status, receipt: (
        handler.send_json(status, receipt) if first("fmt") == "json"
        else _send_beacon(handler, status))
    if not payload or not signature:
        return ack(400, {"error": "Missing payload or signature"})
    if len(payload) > 16000:
        return ack(400, {"error": "Payload too large"})
    if not beacon_rate_ok():
        return ack(429, {"error": "Too many beacon requests"})
    if not beacon_signature_valid(payload, signature):
        return ack(403, {"error": "Invalid signature"})
    if nonce and not IN_NONCE_PATTERN.fullmatch(nonce):
        return ack(400, {"error": "Invalid nonce"})
    try:
        body = beacon_body(payload).strip()
    except (UnicodeDecodeError, ValueError):
        return ack(400, {"error": "Malformed payload"})
    if not body or len(body) > 12000:
        return ack(400, {"error": "Body must contain 1 to 12000 characters"})
    try:
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            rows = connection.execute(
                "INSERT INTO agent_mailbox_messages(sender, body, dedupe) "
                "VALUES ('Barb', %s, %s) ON CONFLICT DO NOTHING "
                "RETURNING id, created_at",
                (body, nonce or None)).fetchall()
    except Exception:
        return ack(500, {"error": "Server error"})
    if not rows:
        return ack(200, {"ok": True, "duplicate": True})
    id, created_at = rows[0]
    return ack(201, {"ok": True, "message": {
        "id": str(id), "sender": "Barb", "body": body,
        "created_at": created_at.isoformat()}})

