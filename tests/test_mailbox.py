"""Agent mailbox credential handling regression checks.

mailbox.role() compares bearer credentials with hmac.compare_digest, which
refuses non-ASCII strings. Comparing raw str values therefore raised
TypeError for any credential containing a non-ASCII character, and that
unhandled error surfaced to callers as an upstream 502 instead of a clean
401 rejection.
"""
import os
import unittest
from unittest.mock import patch

import mailbox


GAB_TOKEN = "gab-token-value-0000000000000001"
HOSS_TOKEN = "hoss-token-value-000000000000002"
BARB_TOKEN = "barb-token-value-000000000000003"
READER_TOKEN = "reader-token-value-00000000000004"


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
        })
        environment.start()
        self.addCleanup(environment.stop)

    def role(self, authorization):
        return mailbox.role(FakeHandler(authorization))

    def test_valid_token_resolves_to_its_sender(self):
        self.assertEqual(self.role("Bearer " + GAB_TOKEN), "Gab")
        self.assertEqual(self.role("Bearer " + HOSS_TOKEN), "Hoss")
        self.assertEqual(self.role("Bearer " + BARB_TOKEN), "Barb")
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
