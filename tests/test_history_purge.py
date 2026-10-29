"""Export-before-delete contract for the Dispatch chat and ride history controls."""
import threading
import unittest
from unittest.mock import patch

import history_purge
import server


ADMIN = {"id": "owner", "role": "dispatch", "dispatch_admin": True, "is_demo": False}
STAFF = {"id": "staff", "role": "dispatch", "dispatch_admin": False, "is_demo": False}
DEMO = {"id": "demo", "role": "dispatch", "dispatch_admin": True, "is_demo": True}
RIDER = {"id": "rider", "role": "rider", "is_demo": False}


def fixture(status="completed"):
    return server.ensure_store({
        "rides": {
            "a": {"id": "a", "status": status, "rider_account_id": "r1", "created": 10},
            "b": {"id": "b", "status": "cancelled", "rider_account_id": "r2", "created": 11},
        },
        "messages": [
            {"id": "team", "role": "driver", "text": "Hello drivers", "channel": "team"},
            {"id": "private", "role": "dispatch", "text": "Only driver", "channel": "private"},
        ],
        "ride_messages": [
            {"id": "ride-a", "ride_id": "a", "text": "Pickup notes"},
            {"id": "ride-b", "ride_id": "b", "text": "Cancelled"},
        ],
        "account_messages": {"r1": [{"id": "account", "text": "Private rider account"}]},
        "riders": {
            "R1": {"rides": ["a"], "ratings": [{"ride": "a", "stars": 5}, {"ride": "old", "stars": 2}]},
            "R2": {"rides": ["b"], "ratings": []},
        },
        "drivers": {"Alex": {"name": "Alex"}},
        "pricing": {"flag_drop": 5},
    })


class FakeHandler:
    def __init__(self, actor=ADMIN):
        self.actor = actor
    def user(self):
        return self.actor
    def send_json(self, code, payload):
        return code, payload


class HistoryDeletionTests(unittest.TestCase):
    def setUp(self):
        server.HISTORY_PURGE_GRANTS.clear()
        self.store = fixture()
        self.saves = []
        self.events = []
        # Match the production signature so a duplicate event-kind keyword
        # fails the test rather than being swallowed by a loose MagicMock.
        def event(kind, ride=None, **extra):
            self.events.append((kind, extra))
        self.patches = [
            patch.object(server, "STORE", self.store),
            patch.object(server, "save", lambda x: self.saves.append(True)),
            patch.object(server, "record_event", event),
            patch.object(server, "RIDER_LOCATIONS", {}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        server.HISTORY_PURGE_GRANTS.clear()

    def export(self, kind, who=ADMIN):
        return server.Handler.prepare_history_archive(
            FakeHandler(who), {"kind": [kind]})

    def delete(self, kind, token=None, digest=None, who=ADMIN):
        return server.Handler.clear_history_after_archive(
            FakeHandler(who), {"kind": kind, "token": token, "sha256": digest})

    def test_private_chat_archive_captures_every_channel_before_purge(self):
        status, exported = self.export("chat")
        self.assertEqual(status, 200)
        data = history_purge.snapshot(self.store, "chat", exported["expires_at_unix"] - server.HISTORY_PURGE_TTL)
        self.assertEqual(len(data["team_and_private_driver_messages"]), 2)
        self.assertEqual(len(data["ride_messages"]), 2)
        self.assertEqual(len(data["rider_account_messages"]["r1"]), 1)
        self.assertEqual(history_purge.sha256(exported["content"]), exported["sha256"])
        status, result = self.delete("chat", exported["token"], exported["sha256"])
        self.assertEqual(status, 200)
        self.assertEqual(result["deleted"]["messages"], 5)
        self.assertEqual(self.store["messages"], [])
        self.assertEqual(self.store["ride_messages"], [])
        self.assertEqual(self.store["account_messages"], {})
        self.assertEqual(len(self.store["rides"]), 2)
        self.assertEqual(self.store["chat_epoch"], 1)
        self.assertEqual(len(self.saves), 1)
        self.assertEqual(self.events, [("history_purged", {"history_kind": "chat"})])
        self.assertEqual(len(server.HISTORY_PURGE_GRANTS), 0)
        self.assertEqual(self.delete("chat", exported["token"], exported["sha256"])[0], 409)

    def test_ride_purge_clears_linked_messages_and_rider_refs_only(self):
        status, exported = self.export("rides")
        self.assertEqual(status, 200)
        self.assertIn("Pickup notes", exported["content"])
        self.assertIn("stars", exported["content"])
        self.assertNotIn("Private rider account", exported["content"])
        status, result = self.delete("rides", exported["token"], exported["sha256"])
        self.assertEqual(status, 200)
        self.assertEqual(result["deleted"]["rides"], 2)
        self.assertEqual(self.store["rides"], {})
        self.assertEqual(self.store["ride_messages"], [])
        self.assertEqual(self.store["riders"]["R1"]["rides"], [])
        self.assertEqual(self.store["riders"]["R1"]["ratings"], [{"ride": "old", "stars": 2}])
        self.assertEqual(len(self.store["messages"]), 2)
        self.assertEqual(len(self.store["account_messages"]["r1"]), 1)
        self.assertIn("Alex", self.store["drivers"])

    def test_non_admin_and_demo_never_receive_archive_or_clear(self):
        for actor in (STAFF, DEMO, RIDER, None):
            with self.subTest(actor=actor):
                self.assertEqual(self.export("chat", actor)[0], 403)
                self.assertEqual(self.delete("rides", "fake", "fake", actor)[0], 403)
        self.assertFalse(server.HISTORY_PURGE_GRANTS)
        self.assertFalse(self.saves)

    def test_direct_deletion_missing_or_wrong_export_is_rejected(self):
        self.assertEqual(self.delete("chat")[0], 409)
        _, exported = self.export("chat")
        self.assertEqual(self.delete("rides", exported["token"], exported["sha256"])[0], 409)
        self.assertEqual(self.delete("chat", exported["token"], "wrong")[0], 409)
        self.assertEqual(self.delete("chat", "invented", exported["sha256"])[0], 409)
        self.assertEqual(len(self.store["messages"]), 2)

    def test_expired_token_and_changed_chat_both_block(self):
        _, exported = self.export("chat")
        server.HISTORY_PURGE_GRANTS[exported["token"]]["expires"] = 0
        self.assertEqual(self.delete("chat", exported["token"], exported["sha256"])[0], 409)
        self.assertEqual(len(self.store["messages"]), 2)
        _, fresh = self.export("chat")
        self.store["account_messages"]["r1"].append({"id": "new", "text": "New private"})
        status, response = self.delete("chat", fresh["token"], fresh["sha256"])
        self.assertEqual(status, 409)
        self.assertIn("changed", response["error"].lower())
        self.assertFalse(self.saves)

    def test_ride_update_after_export_blocks_deletion(self):
        _, exported = self.export("rides")
        self.store["rides"]["b"]["fare"] = 90
        self.assertEqual(self.delete("rides", exported["token"], exported["sha256"])[0], 409)
        self.assertEqual(len(self.store["rides"]), 2)

    def test_active_ride_blocks_both_export_and_delete(self):
        self.store["rides"]["a"]["status"] = "accepted"
        for kind in ("chat", "rides"):
            self.assertEqual(self.export(kind)[0], 409)
        self.store["rides"]["a"]["status"] = "completed"
        _, exported = self.export("rides")
        self.store["rides"]["a"]["status"] = "at_pickup"
        self.assertEqual(self.delete("rides", exported["token"], exported["sha256"])[0], 409)
        self.assertEqual(len(self.store["rides"]), 2)
        self.assertFalse(self.saves)

    def test_bad_type_does_not_permit_purge(self):
        self.assertEqual(self.export("accounts")[0], 400)
        self.assertEqual(self.delete("accounts", "foo", "foo")[0], 400)
        self.assertRaises(ValueError, history_purge.purge, self.store, "accounts")

    def test_save_failure_restores_records_and_grant_not_consumed(self):
        _, exported = self.export("chat")
        def failure(_): raise RuntimeError("database offline")
        with patch.object(server, "save", failure):
            with self.assertRaises(RuntimeError):
                self.delete("chat", exported["token"], exported["sha256"])
        self.assertEqual(len(self.store["messages"]), 2)
        self.assertEqual(len(self.store["ride_messages"]), 2)
        self.assertEqual(self.store["chat_epoch"], 0)


if __name__ == "__main__":
    unittest.main()
