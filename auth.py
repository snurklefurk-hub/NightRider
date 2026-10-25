"""NightRider's first-party account and session storage."""
import hashlib
import hmac
import os
import secrets
import time
import uuid

SESSION_DAYS = 14
PASSWORD_MIN = 8


def _database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def _connect():
    url = _database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is required for account storage")
    import psycopg
    return psycopg.connect(url)


def database_healthy():
    with _connect() as conn:
        conn.execute("SELECT 1").fetchone()
    return True


def initialize():
    """Create account tables and initialize the JSON state row if needed."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nr_users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('rider','driver','dispatch')),
                password_hash TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS nr_driver_name_unique "
                      "ON nr_users (lower(display_name)) WHERE role='driver'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nr_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES nr_users(id) ON DELETE CASCADE,
                expires_at DOUBLE PRECISION NOT NULL,
                created_at DOUBLE PRECISION NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS nr_sessions_expiry ON nr_sessions(expires_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nr_app_state (
                id SMALLINT PRIMARY KEY CHECK (id = 1),
                payload JSONB NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            )
        """)


def has_dispatch_user():
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM nr_users WHERE role='dispatch' AND enabled=TRUE LIMIT 1").fetchone()
    return bool(row)


def _password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$%s$%s" % (salt.hex(), digest.hex())


def _password_matches(password, stored):
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                                   n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)))
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def normalize_username(value):
    return str(value or "").strip().lower()[:120]


def validate_account(username, display_name, password):
    username = normalize_username(username)
    display_name = str(display_name or "").strip()[:60]
    password = str(password or "")
    if len(username) < 3 or any(ch.isspace() for ch in username):
        return None, "Username must be at least 3 characters with no spaces."
    if not display_name:
        return None, "Name is required."
    if len(password) < PASSWORD_MIN:
        return None, "Password must be at least 8 characters."
    if len(password) > 256:
        return None, "Password is too long."
    return {"username": username, "display_name": display_name, "password": password}, None


def create_user(username, display_name, password, role):
    account, error = validate_account(username, display_name, password)
    if error:
        return None, error
    if role not in ("rider", "driver", "dispatch"):
        return None, "Invalid account type."
    account_id = uuid.uuid4().hex
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO nr_users (id, username, display_name, role, password_hash, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (account_id, account["username"], account["display_name"], role,
                 _password_hash(account["password"]), time.time()),
            )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return None, "That username or driver name is already in use."
        raise
    return {"id": account_id, "username": account["username"],
            "display_name": account["display_name"], "role": role}, None


def authenticate(username, password):
    username = normalize_username(username)
    if len(str(password or "")) > 256:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, role, password_hash FROM nr_users "
            "WHERE username=%s AND enabled=TRUE", (username,),
        ).fetchone()
    if not row or not _password_matches(str(password or ""), row[4]):
        return None
    return {"id": row[0], "username": row[1], "display_name": row[2], "role": row[3]}


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _connect() as conn:
        conn.execute("DELETE FROM nr_sessions WHERE expires_at < %s", (now,))
        conn.execute("INSERT INTO nr_sessions(token_hash,user_id,expires_at,created_at) VALUES (%s,%s,%s,%s)",
                     (_token_hash(token), user_id, now + SESSION_DAYS * 86400, now))
    return token


def get_session(token):
    if not token:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT u.id,u.username,u.display_name,u.role FROM nr_sessions s "
            "JOIN nr_users u ON u.id=s.user_id WHERE s.token_hash=%s "
            "AND s.expires_at>%s AND u.enabled=TRUE", (_token_hash(token), time.time()),
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "display_name": row[2], "role": row[3]}


def delete_session(token):
    if token:
        with _connect() as conn:
            conn.execute("DELETE FROM nr_sessions WHERE token_hash=%s", (_token_hash(token),))


def change_password(user_id, password):
    if len(str(password or "")) < PASSWORD_MIN or len(str(password)) > 256:
        return False
    with _connect() as conn:
        conn.execute("UPDATE nr_users SET password_hash=%s WHERE id=%s",
                     (_password_hash(str(password)), user_id))
        conn.execute("DELETE FROM nr_sessions WHERE user_id=%s", (user_id,))
    return True


def reset_password(user_id, password):
    if len(str(password or "")) < PASSWORD_MIN or len(str(password)) > 256:
        return False
    with _connect() as conn:
        conn.execute("UPDATE nr_users SET password_hash=%s WHERE id=%s",
                     (_password_hash(str(password)), user_id))
        conn.execute("DELETE FROM nr_sessions WHERE user_id=%s", (user_id,))
    return True


def list_users(role=None):
    query = "SELECT id,username,display_name,role,enabled,created_at FROM nr_users"
    params = ()
    if role:
        query += " WHERE role=%s"
        params = (role,)
    query += " ORDER BY created_at DESC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [{"id": r[0], "username": r[1], "display_name": r[2],
             "role": r[3], "enabled": r[4], "created_at": r[5]} for r in rows]


def set_user_enabled(user_id, enabled):
    with _connect() as conn:
        conn.execute("UPDATE nr_users SET enabled=%s WHERE id=%s", (bool(enabled), user_id))
        if not enabled:
            conn.execute("DELETE FROM nr_sessions WHERE user_id=%s", (user_id,))


def load_app_state(local_path):
    import json
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM nr_app_state WHERE id=1").fetchone()
        if row:
            payload = row[0]
            payload = payload if isinstance(payload, dict) else json.loads(payload)
            if payload.get("account_identity_version") != 1:
                # Old rider IDs were derived from browser/device signals. Keep
                # ride history, but discard that identity and its signal profile.
                for ride in (payload.get("rides") or {}).values():
                    ride.pop("rider_id", None)
                    ride.pop("rider_account_id", None)
                payload["riders"] = {}
                payload["account_identity_version"] = 1
                conn.execute("UPDATE nr_app_state SET payload=%s::jsonb,updated_at=%s WHERE id=1",
                             (json.dumps(payload), time.time()))
            return payload
        if os.path.exists(local_path):
            with open(local_path, encoding="utf-8") as source:
                payload = json.load(source)
        else:
            payload = {"rides": {}}
        for ride in (payload.get("rides") or {}).values():
            ride.pop("rider_id", None)
            ride.pop("rider_account_id", None)
        payload["riders"] = {}
        payload["account_identity_version"] = 1
        conn.execute("INSERT INTO nr_app_state(id,payload,updated_at) VALUES (1,%s::jsonb,%s)",
                     (json.dumps(payload), time.time()))
        return payload


def save_app_state(payload, local_path):
    import json
    if _database_url():
        with _connect() as conn:
            conn.execute("""
                INSERT INTO nr_app_state(id,payload,updated_at) VALUES (1,%s::jsonb,%s)
                ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,updated_at=EXCLUDED.updated_at
            """, (json.dumps(payload), time.time()))
    else:
        temp_path = local_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as target:
            json.dump(payload, target, indent=2)
        os.replace(temp_path, local_path)

