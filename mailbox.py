"""Isolated agent thread hosted beside NightRider, sharing only its database."""
import hmac
import os
import re
import psycopg

TABLE = """CREATE TABLE IF NOT EXISTS agent_mailbox_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender TEXT NOT NULL CHECK (sender IN ('Barb', 'Hoss', 'Gab')),
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 12000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""
TOKENS = {"reader": "READER_TOKEN", "Barb": "BARB_TOKEN",
          "Hoss": "HOSS_TOKEN", "Gab": "GAB_TOKEN"}


def initialize():
    values = [os.environ.get(key, "") for key in TOKENS.values()]
    if any(len(value) < 24 for value in values) or len(set(values)) != 4:
        raise RuntimeError("Four distinct mailbox tokens of at least 24 characters are required")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(TABLE)


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

