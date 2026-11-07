"""Agent mailbox credential handling regression checks.

mailbox.role() compares bearer credentials with hmac.compare_digest, which
refuses non-ASCII strings. Comparing raw str values therefore raised
TypeError for any credential containing a non-ASCII character, and that
unhandled error surfaced to callers as an upstream 502 instead of a clean
401 rejection.

Also covers the owner-approved signed inbound beacon (GET
/agent-mailbox/in) with offline fixtures: no production database is used.
"""
import base64
import datetime
import hashlib
import hmac as hmac_module
import io
import os
import unittest
from unittest.mock import patch

import mailbox


GAB_TOKEN = "gab-token-value-0000000000000001"
HOSS_TOKEN = "hoss-token-value-000000000000002"
BARB_TOKEN = "barb-token-value-000000000000003"
READER_TOKEN = "reader-token-value-00000000000004"
ZIP_TOKEN = "zip-token-value-000000000000000005"
DATABASE_URL = "postgresql://fixture-only:test@127.0.0.1/none"


class FakeHandler:
    """Minimal request handler exposing only what mailbox reads."""

    def __init__(self, authorization=None):
        self.headers = {}
        if authorization is not None:
            self.headers["Authorization"] = authorization
        self.status = None
        self.payload = None

    def send_json(self, code, payload):
        self.status = code
        self.payload = payload


class MailboxCredentialTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "GAB_TOKEN": GAB_TOKEN,
            "HOSS_TOKEN": HOSS_TOKEN,
            "BARB_TOKEN": BARB_TOKEN,
            "READER_TOKEN": READER_TOKEN,
            "ZIP_TOKEN": ZIP_TOKEN,
        })
        environment.start()
        self.addCleanup(environment.stop)

    def role(self, authorization):
        return mailbox.role(FakeHandler(authorization))

    def test_valid_token_resolves_to_its_sender(self):
        self.assertEqual(self.role("Bearer " + GAB_TOKEN), "Gab")
        self.assertEqual(self.role("Bearer " + HOSS_TOKEN), "Hoss")
        self.assertEqual(self.role("Bearer " + BARB_TOKEN), "Barb")
        self.assertEqual(self.role("Bearer " + ZIP_TOKEN), "Zip")
        self.assertEqual(self.role("Bearer " + READER_TOKEN), "reader")

    def test_missing_or_malformed_header_is_rejected(self):
        self.assertIsNone(self.role(None))
        self.assertIsNone(self.role(""))
        self.assertIsNone(self.role("Basic " + GAB_TOKEN))
        self.assertIsNone(self.role(GAB_TOKEN))
        self.assertIsNone(self.role("Bearer "))

    def test_wrong_token_is_rejected(self):
        self.assertIsNone(self.role("Bearer wrong-token-value-00000000000"))

    def test_non_ascii_credential_is_rejected_without_raising(self):
        self.assertIsNone(self.role("Bearer " + GAB_TOKEN + "\u00e9"))
        self.assertIsNone(self.role("Bearer caf\u00e9-token-value-000000000000"))
        self.assertIsNone(self.role("Bearer " + "\u00e9" * 40))

    def test_non_ascii_in_scheme_is_rejected(self):
        self.assertIsNone(self.role("Bear\u00e9r " + GAB_TOKEN))

    def test_get_rejects_non_ascii_credential_with_401(self):
        handler = FakeHandler("Bearer " + GAB_TOKEN + "\u00e9")
        mailbox.get(handler, {})
        self.assertEqual(handler.status, 401)
        self.assertEqual(handler.payload, {"error": "Invalid token"})

    def test_post_rejects_non_ascii_credential_with_401(self):
        handler = FakeHandler("Bearer " + GAB_TOKEN + "\u00e9")
        mailbox.post(handler, {"body": "hello"})
        self.assertEqual(handler.status, 401)
        self.assertEqual(handler.payload, {"error": "Invalid token"})

    def test_read_only_token_cannot_post(self):
        handler = FakeHandler("Bearer " + READER_TOKEN)
        mailbox.post(handler, {"body": "hello"})
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.payload, {"error": "Read-only token"})


def beacon_payload(text):
    """Encode a message body the way Barb's instructions describe."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def beacon_signature(payload):
    """Sign exactly as the deployed route verifies (same helper, same env)."""
    data = payload.encode("ascii")
    return hmac_module.new(mailbox.beacon_secret(), data, hashlib.sha256).hexdigest()


class BeaconHandler:
    """Recording handler stub covering both JSON and pixel responses."""

    def __init__(self):
        self.status = None
        self.payload = None
        self.headers = {}
        self.out = io.BytesIO()

    def send_json(self, code, payload):
        self.status = code
        self.payload = payload

    def send_response(self, code):
        self.status = code

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self.out


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeCursor(self.rows)


class MailboxInitializationTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "GAB_TOKEN": GAB_TOKEN, "HOSS_TOKEN": HOSS_TOKEN,
            "BARB_TOKEN": BARB_TOKEN, "READER_TOKEN": READER_TOKEN,
            "ZIP_TOKEN": ZIP_TOKEN, "DATABASE_URL": DATABASE_URL,
        })
        environment.start()
        self.addCleanup(environment.stop)

    def statements(self, constraint):
        connection = FakeConnection([(constraint,)])
        with patch.object(mailbox.psycopg, "connect", return_value=connection):
            mailbox.initialize()
        return "\n".join(sql for sql, _ in connection.calls)

    def test_initialize_rebuilds_old_sender_constraint_for_zip(self):
        statements = self.statements("CHECK (sender IN ('Barb', 'Hoss', 'Gab'))")
        self.assertIn("DROP CONSTRAINT IF EXISTS agent_mailbox_messages_sender_check", statements)
        self.assertIn("ADD CONSTRAINT agent_mailbox_messages_sender_check", statements)
        self.assertIn("'Zip'", statements)

    def test_initialize_leaves_current_sender_constraint_alone(self):
        statements = self.statements(
            "CHECK (sender IN ('Barb', 'Hoss', 'Gab', 'Zip'))")
        self.assertNotIn("DROP CONSTRAINT", statements)
        self.assertNotIn("ADD CONSTRAINT", statements)


class BeaconUnitTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "GAB_TOKEN": GAB_TOKEN, "HOSS_TOKEN": HOSS_TOKEN,
            "BARB_TOKEN": BARB_TOKEN, "READER_TOKEN": READER_TOKEN,
            "ZIP_TOKEN": ZIP_TOKEN,
            "BARB_IN_SECRET": "", "DATABASE_URL": DATABASE_URL,
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(mailbox._in_attempts.clear)

    def test_beacon_secret_prefers_barb_in_secret_override(self):
        with patch.dict(os.environ, {"BARB_IN_SECRET": "x" * 40}):
            self.assertEqual(mailbox.beacon_secret(), (b"x" * 40))
        with patch.dict(os.environ, {"BARB_IN_SECRET": "short"}):
            self.assertNotEqual(mailbox.beacon_secret(), b"short")

    def test_beacon_secret_is_derived_from_barb_token_with_label(self):
        derived = hmac_module.new(BARB_TOKEN.encode("utf-8"),
                                  mailbox.BEACON_SECRET_LABEL,
                                  hashlib.sha256).digest()
        self.assertEqual(mailbox.beacon_secret(), derived)

    def test_signature_round_trip_accepts_correct_hex(self):
        payload = beacon_payload("Beacon signature check.")
        self.assertTrue(mailbox.beacon_signature_valid(payload, beacon_signature(payload)))
        self.assertTrue(mailbox.beacon_signature_valid(payload, beacon_signature(payload).upper()))

    def test_signature_rejects_wrong_key_tampered_or_unicode(self):
        payload = beacon_payload("OkCupid heritage test anchors.")
        self.assertFalse(mailbox.beacon_signature_valid(payload, "ab" * 32))
        self.assertFalse(mailbox.beacon_signature_valid(payload, beacon_signature(payload + "x")))
        self.assertFalse(mailbox.beacon_signature_valid(payload + "\u00e9", beacon_signature(payload)))
        self.assertFalse(mailbox.beacon_signature_valid(payload, ""))

    def test_beacon_body_round_trip_is_url_safe_and_unpadded(self):
        text = "Unicode check: caf\u00e9 \u2713\nManual test receipt."
        encoded = beacon_payload(text)
        self.assertFalse("=" in encoded)
        self.assertEqual(mailbox.beacon_body(encoded), text)

    def test_beacon_body_rejects_malformed_payload(self):
        with self.assertRaises((UnicodeDecodeError, ValueError)):
            mailbox.beacon_body("!!!!")

    def test_rate_limit_blocks_after_in_rate_limit(self):
        for index in range(mailbox.IN_RATE_LIMIT):
            self.assertTrue(mailbox.beacon_rate_ok(), index)
        self.assertFalse(mailbox.beacon_rate_ok())


class BeaconRouteTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "GAB_TOKEN": GAB_TOKEN, "HOSS_TOKEN": HOSS_TOKEN,
            "BARB_TOKEN": BARB_TOKEN, "READER_TOKEN": READER_TOKEN,
            "ZIP_TOKEN": ZIP_TOKEN,
            "BARB_IN_SECRET": "", "DATABASE_URL": DATABASE_URL,
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(mailbox._in_attempts.clear)
        self.query = {"m": [beacon_payload("[pipe test] hello from the beacon")],
                      "n": ["roundtrip-1"]}

    def connect(self, rows):
        connection = FakeConnection(rows)
        return patch.object(mailbox.psycopg, "connect", return_value=connection), connection

    STAMP = datetime.datetime(2026, 11, 6, 2, 26, 40, tzinfo=datetime.timezone.utc)

    def test_valid_beacon_inserts_as_barb_and_returns_gif(self):
        patcher, connection = self.connect([(1, self.STAMP)])
        with patcher:
            handler = BeaconHandler()
            self.query["sig"] = [beacon_signature(self.query["m"][0])]
            mailbox.beacon_get(handler, self.query)
        self.assertEqual(handler.status, 201)
        self.assertEqual(connection.calls[0][1], ("[pipe test] hello from the beacon", "roundtrip-1"))
        self.assertEqual(handler.headers.get("Content-Type"), "image/gif")
        self.assertTrue(handler.out.getvalue().startswith(b"GIF89a"))

    def test_fmt_json_returns_json_receipt(self):
        patcher, _ = self.connect([(1, self.STAMP)])
        with patcher:
            handler = BeaconHandler()
            query = dict(self.query, sig=[beacon_signature(self.query["m"][0])], fmt=["json"])
            mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 201)
        self.assertEqual(handler.payload["message"]["sender"], "Barb")

    def test_duplicate_nonce_is_idempotent(self):
        patcher, _ = self.connect([])
        with patcher:
            handler = BeaconHandler()
            query = dict(self.query, sig=[beacon_signature(self.query["m"][0])], fmt=["json"])
            mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.payload["duplicate"])

    def test_invalid_signature_never_reaches_the_database(self):
        handler = BeaconHandler()
        query = dict(self.query, sig=["f" * 64], fmt=["json"])
        mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.payload, {"error": "Invalid signature"})
        self.assertEqual(handler.out.getvalue(), b"")

    def test_malformed_or_missing_parts_return_clean_400(self):
        valid = beacon_payload("x")
        cases = [
            {"m": [""], "sig": [beacon_signature("")]},
            {"m": [valid]},
            {"m": [valid], "sig": [beacon_signature(valid)], "n": ["bad nonce!"]},
            {"m": ["!!not-base64!!"], "sig": [beacon_signature("!!not-base64!!")]},
        ]
        for case in cases:
            handler = BeaconHandler()
            query = dict(case, fmt=["json"])
            mailbox.beacon_get(handler, query)
            self.assertEqual(handler.status, 400, case)

    def test_nonce_with_newline_is_rejected(self):
        handler = BeaconHandler()
        query = dict(self.query, sig=[beacon_signature(self.query["m"][0])], fmt=["json"],
                     n=["round\ntrip"])
        mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 400)

    def test_payload_length_limit_is_enforced(self):
        payload = "y" * 16001
        handler = BeaconHandler()
        query = {"m": [payload], "sig": ["0" * 64], "fmt": ["json"]}
        mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 400)
        self.assertEqual(handler.payload, {"error": "Payload too large"})

    def test_rate_limit_returns_429(self):
        for index in range(mailbox.IN_RATE_LIMIT):
            handler = BeaconHandler()
            query = dict(self.query, sig=["0" * 64])
            mailbox.beacon_get(handler, query)
            self.assertEqual(handler.status, 403, index)
        handler = BeaconHandler()
        query = dict(self.query, sig=["0" * 64], fmt=["json"])
        mailbox.beacon_get(handler, query)
        self.assertEqual(handler.status, 429)
        self.assertEqual(handler.payload, {"error": "Too many beacon requests"})


if __name__ == "__main__":
    unittest.main()
