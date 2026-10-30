"""All NightRider messaging works in RAM without persistent chat history."""
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import server


RIDER = {"id": "r1", "role": "rider", "display_name": "Rider", "is_demo": True}
DRIVER = {"id": "d1", "role": "driver", "display_name": "Alex", "is_demo": True}
DISPATCH = {"id": "dispatch1", "role": "dispatch", "display_name": "Dispatch", "is_demo": False}


def state():
    return server.ensure_store({
        "rides": {"trip-1": {"id": "trip-1", "created": 123.0,
                             "status": "requested", "rider_account_id": "r1",
                             "driver_account_id": "d1", "driver": "Alex"}},
        "riders": {"NR-R1": {"rides": ["trip-1"]}},
        "drivers": {},
        "pricing": {"flag_drop": 8.0, "trip_per_mile": 2.0},
        "messages": [],
        "ride_messages": [],
        "account_messages": {},
        "chat_epoch": 0,
        "partner_payload": {"unchanged": True},
    })


class HandlerFixture:
    def __init__(self, user=RIDER, path=None, data=None):
        self.actor = user
        self.path = path or "/api/chat/messages"
        self.body = data or {}
        self.headers = {}
    def user(self):
        return self.actor
    def require_role(self, *roles):
        return self.actor if self.actor and self.actor["role"] in roles else None
    def read_json(self):
        return self.body
    def send_json(self, code, data):
        return code, data


class EphemeralChatTests(unittest.TestCase):
    def test_saved_snapshot_omits_all_chat_channels_even_if_nondemo(self):
        store = state()
        store["messages"] = [{"text": "SECRET TEAM"}]
        store["ride_messages"] = [{"text": "SECRET RIDE"}]
        store["account_messages"] = {"r1": [{"text": "SECRET ACCOUNT"}]}
        store["chat_epoch"] = 1234
        before = copy.deepcopy(store)
        with patch.dict(os.environ, {"DATABASE_URL": "testing"}, clear=False), \
             patch.object(server.auth, "save_app_state") as writer:
            server.save(store)
        writer.assert_called_once()
        saved = writer.call_args.args[0]
        for key in server.VOLATILE_CHAT_KEYS:
            self.assertNotIn(key, saved)
        self.assertEqual(saved["rides"], before["rides"])
        self.assertEqual(saved["partner_payload"], before["partner_payload"])
        self.assertEqual(saved["pricing"], before["pricing"])
        self.assertEqual(store, before, "saving must not erase live RAM chat")

    def test_local_json_write_never_contains_chat_and_preserves_nonchat_data(self):
        store = state()
        store["messages"].append({"text": "SECRET TEAM"})
        store["ride_messages"].append({"text": "SECRET RIDE"})
        store["account_messages"]["r1"] = [{"text": "SECRET ACCOUNT"}]
        with tempfile.TemporaryDirectory() as folder:
            filename = os.path.join(folder, "rides.json")
            with patch.dict(os.environ, {"DATABASE_URL": ""}), \
                 patch.object(server, "DATA_FILE", filename):
                server.save(store)
                with open(filename, encoding="utf-8") as f:
                    contents = f.read()
                self.assertNotIn("SECRET", contents)
                disk = json.loads(contents)
        self.assertTrue(disk["partner_payload"]["unchanged"])
        for key in server.VOLATILE_CHAT_KEYS:
            self.assertNotIn(key, disk)

    def test_restart_discards_all_legacy_messages_and_rotates_chat_epoch(self):
        saved = state()
        saved["messages"].append({"text": "OLD GROUP"})
        saved["ride_messages"].append({"text": "OLD RIDE"})
        saved["account_messages"]["r1"] = [{"text": "OLD PRIVATE"}]
        previous = saved["chat_epoch"]
        self.assertTrue(server.start_temporary_chat(saved))
        self.assertEqual(saved["messages"], [])
        self.assertEqual(saved["ride_messages"], [])
        self.assertEqual(saved["account_messages"], {})
        self.assertIsInstance(saved["chat_epoch"], int)
        self.assertLess(saved["chat_epoch"], 2 ** 48)
        self.assertNotEqual(saved["chat_epoch"], previous)
        self.assertEqual(saved["rides"]["trip-1"]["status"], "requested")
        self.assertFalse(server.start_temporary_chat({"rides": {}}))

    def test_all_chat_routes_work_but_never_call_persistent_save(self):
        store = state()
        events = []
        def event(kind, ride=None, **extra):
            events.append(kind)
        with patch.object(server, "STORE", store), \
             patch.object(server, "save", side_effect=AssertionError("chat attempted durable save")), \
             patch.object(server, "record_event", side_effect=event), \
             patch.object(server.auth, "list_users", return_value=[{"id": "r1", "enabled": True}]), \
             patch.object(server, "driver_chat_color_map", return_value={}):
            sends = [
                (server.Handler.post_chat_message, HandlerFixture(RIDER), RIDER,
                 {"text": "Temporary rider private", "account_chat": True}, "account_messages"),
                (server.Handler.post_chat_message, HandlerFixture(DISPATCH), DISPATCH,
                 {"text": "Temporary dispatch team"}, "messages"),
                (server.Handler.post_chat_message, HandlerFixture(DRIVER), DRIVER,
                 {"text": "Temporary ride", "ride_id": "trip-1"}, "ride_messages"),
            ]
            for method, h, actor, data, field in sends:
                code, payload = method(h, actor, data)
                self.assertEqual(code, 201, payload)
                self.assertTrue(store[field])
            code, _ = server.Handler.driver_message(
                HandlerFixture(DRIVER), "Alex", {"text": "Legacy driver"})
            self.assertEqual(code, 201)
            code, _ = server.Handler.dispatch_message(
                HandlerFixture(DISPATCH), {"text": "Legacy dispatch"})
            self.assertEqual(code, 201)
            h = HandlerFixture(RIDER, "/api/rides/trip-1/message",
                               {"text": "Legacy ride", "audience": "shared"})
            with patch.dict(os.environ, {"DATABASE_URL": "testing"}):
                code, _ = server.Handler.do_POST(h)
            self.assertEqual(code, 201)
            self.assertEqual(len(store["ride_messages"]), 2)
            self.assertEqual(len(store["messages"]), 3)
            self.assertEqual(len(store["account_messages"]["r1"]), 1)
            chat = server.unified_chat_messages(RIDER)
            self.assertEqual(sorted(m["text"] for m in chat),
                             ["Legacy ride", "Temporary ride", "Temporary rider private"])
            self.assertTrue(events)


if __name__ == "__main__":
    unittest.main()
