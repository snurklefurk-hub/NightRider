"""Mandatory local account archive and fail-closed deletion regression checks."""
import hashlib
import threading
import unittest
from unittest.mock import patch

import account_archive as archive
import auth
import server


RIDER = {"id": "rider987654321", "username": "riley", "display_name": "Riley",
         "role": "rider", "enabled": True, "created_at": 8}
DRIVER = {"id": "driver123", "username": "alex", "display_name": "Alex",
          "role": "driver", "enabled": True, "created_at": 9}
ADMIN = {"id": "owner", "display_name": "Owner", "role": "dispatch",
         "dispatch_admin": True}
OTHER = {"id": "staff", "display_name": "Staff", "role": "dispatch",
         "dispatch_admin": False}


def state(status="completed"):
    return {
        "rides": {
            "a": {"id": "a", "created": 10, "status": status,
                  "rider_account_id": RIDER["id"], "driver_account_id": DRIVER["id"],
                  "rider_id": "NR-" + RIDER["id"][:10].upper(),
                  "driver": "Alex", "fare": 50, "status_log": [{"status": status}],
                  "assignment_log": [{"to_driver": "Alex", "from_driver": None}]},
            "b": {"id": "b", "created": 12, "status": "completed",
                  "rider_account_id": "somebody-else", "driver": "Morgan",
                  "driver_account_id": "different"}
        },
        "riders": {"NR-" + RIDER["id"][:10].upper():
                   {"id": "NR-" + RIDER["id"][:10].upper(), "rides": ["a"]}},
        "drivers": {"Alex": {"account_id": DRIVER["id"], "name": "Alex"}},
        "driver_colors": {DRIVER["id"]: "#ffffff"},
        "account_messages": {
            RIDER["id"]: [{"text": "Forgot my luggage", "rider_account_id": RIDER["id"]}],
            "somebody-else": [{"text": "SECRET OTHER RIDER"}]
        },
        "ride_messages": [{"ride_id": "a", "text": "Where's the car?"},
                          {"ride_id": "b", "text": "Not this account"}],
        "messages": [{"driver": "Alex", "private": True, "text": "Check luggage"},
                     {"driver": "Morgan", "private": True, "text": "Unrelated private"}]
    }


class FakeHandler:
    def __init__(self, actor=ADMIN):
        self.actor = actor
        self.calls = []
    def user(self):
        return self.actor
    def send_json(self, code, payload):
        self.calls.append((code, payload))
        return code, payload


class ArchiveContractTests(unittest.TestCase):
    def setUp(self):
        server.ACCOUNT_ARCHIVE_GRANTS.clear()
        self.store = state()

    def tearDown(self):
        server.ACCOUNT_ARCHIVE_GRANTS.clear()

    def test_rider_archive_is_complete_for_retained_account_not_others(self):
        doc = archive.build_archive(self.store, RIDER, 123)
        self.assertEqual([r["id"] for r in doc["rides"]], ["a"])
        self.assertEqual(doc["ride_messages"], [])
        self.assertEqual(doc["account_messages"], [])
        self.assertIn("Temporary chats", doc["chat_retention"])
        self.assertEqual(doc["rider_history"]["rides"], ["a"])
        dump = archive.serialise_archive(doc)
        self.assertNotIn("SECRET OTHER RIDER", dump)
        self.assertNotIn("password_hash", dump)
        self.assertEqual(archive.archive_sha256(dump),
                         hashlib.sha256(dump.encode("utf-8")).hexdigest())

    def test_driver_archive_includes_prior_assignments(self):
        self.store["rides"]["a"]["driver_account_id"] = "different"
        self.store["rides"]["a"]["driver"] = "Morgan"
        doc = archive.build_archive(self.store, DRIVER, 123)
        self.assertEqual([r["id"] for r in doc["rides"]], ["a"])
        self.assertEqual(doc["driver_chat_color"], "#ffffff")
        self.assertEqual(doc["team_messages"], [])
        self.assertNotIn("Check luggage", archive.serialise_archive(doc))

    def test_active_rider_or_driver_ride_prevents_deletion(self):
        self.store["rides"]["a"]["status"] = "accepted"
        self.assertTrue(archive.account_has_active_ride(self.store, RIDER))
        self.assertTrue(archive.account_has_active_ride(self.store, DRIVER))

    def test_non_admin_cannot_prepare_or_delete(self):
        h = FakeHandler(OTHER)
        with patch.object(server, "STORE", self.store):
            code, _ = server.Handler.prepare_account_archive(
                h, {"role": ["rider"], "id": [RIDER["id"]]})
        self.assertEqual(code, 403)
        code, _ = server.Handler.delete_account_after_archive(
            h, {"role": "rider", "id": RIDER["id"]})
        self.assertEqual(code, 403)

    def test_no_archive_grant_no_deletion_even_for_admin(self):
        h = FakeHandler()
        with patch.object(auth, "delete_rider_user") as delete:
            code, payload = server.Handler.delete_account_after_archive(
                h, {"role": "rider", "id": RIDER["id"],
                    "token": "fake", "sha256": "fake"})
        self.assertEqual(code, 409)
        self.assertIn("archive", payload["error"].lower())
        delete.assert_not_called()

    def test_valid_export_grant_then_deletes_only_expected_account(self):
        h = FakeHandler()
        with (patch.object(server, "STORE", self.store),
              patch.object(auth, "get_account_for_archive", return_value=RIDER),
              patch.object(auth, "delete_rider_user", return_value=True) as delete,
              patch.object(server, "record_event")):
            code, payload = server.Handler.prepare_account_archive(
                h, {"role": ["rider"], "id": [RIDER["id"]]})
            self.assertEqual(code, 200)
            self.assertEqual(archive.archive_sha256(payload["content"]), payload["sha256"])
            code, result = server.Handler.delete_account_after_archive(
                h, {"role": "rider", "id": RIDER["id"],
                    "token": payload["token"], "sha256": payload["sha256"]})
            self.assertEqual(code, 200)
            delete.assert_called_once_with(RIDER["id"])
            self.assertFalse(server.ACCOUNT_ARCHIVE_GRANTS)
            self.assertEqual(result["archive_sha256"], payload["sha256"])

    def test_temporary_chat_changes_do_not_invalidate_nonchat_account_archive(self):
        h = FakeHandler()
        with (patch.object(server, "STORE", self.store),
              patch.object(auth, "get_account_for_archive", return_value=RIDER),
              patch.object(auth, "delete_rider_user") as delete):
            code, payload = server.Handler.prepare_account_archive(
                h, {"role": ["rider"], "id": [RIDER["id"]]})
            self.assertEqual(code, 200)
            self.store["account_messages"][RIDER["id"]].append({"text": "new message"})
            code, result = server.Handler.delete_account_after_archive(
                h, {"role": "rider", "id": RIDER["id"],
                    "token": payload["token"], "sha256": payload["sha256"]})
            self.assertEqual(code, 200)
            delete.assert_called_once_with(RIDER["id"])

    def test_active_ride_blocks_export_and_never_issues_token(self):
        self.store["rides"]["a"]["status"] = "accepted"
        h = FakeHandler()
        with (patch.object(server, "STORE", self.store),
              patch.object(auth, "get_account_for_archive", return_value=RIDER)):
            code, result = server.Handler.prepare_account_archive(
                h, {"role": ["rider"], "id": [RIDER["id"]]})
        self.assertEqual(code, 409)
        self.assertFalse(server.ACCOUNT_ARCHIVE_GRANTS)

    def test_legacy_direct_driver_deletion_endpoint_is_blocked(self):
        # No caller, even an administrator, may bypass the archive grant.
        h = FakeHandler()
        h.path = "/api/dispatch/users/driver123/delete"
        h.headers = {}
        h.read_json = lambda: {}
        h.require_role = lambda *roles: ADMIN
        with patch.dict("os.environ", {"DATABASE_URL": "test"}):
            code, result = server.Handler.do_POST(h)
        self.assertEqual(code, 409)
        self.assertIn("archive", result["error"].lower())

    def test_export_token_expires(self):
        h = FakeHandler()
        with (patch.object(server, "STORE", self.store),
              patch.object(auth, "get_account_for_archive", return_value=RIDER),
              patch.object(auth, "delete_rider_user") as delete):
            code, payload = server.Handler.prepare_account_archive(
                h, {"role": ["rider"], "id": [RIDER["id"]]})
            server.ACCOUNT_ARCHIVE_GRANTS[payload["token"]]["expires"] = 0
            code, _ = server.Handler.delete_account_after_archive(
                h, {"role": "rider", "id": RIDER["id"],
                    "token": payload["token"], "sha256": payload["sha256"]})
            self.assertEqual(code, 409)
            delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
