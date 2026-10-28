"""Chat recipient/privacy and retry regression checks."""
import unittest
from unittest.mock import patch
import server

from server import (add_message, add_ride_message, add_account_message,
                    visible_account_messages, thread_messages, visible_ride_messages)


RIDER = {"id": "r1", "role": "rider", "display_name": "Riley"}
DISPATCH = {"id": "d1", "role": "dispatch", "display_name": "Dispatch"}
OLD_DRIVER = {"id": "old", "role": "driver", "display_name": "Alex"}
NEW_DRIVER = {"id": "new", "role": "driver", "display_name": "Sam"}


class ChatContractTest(unittest.TestCase):
    def setUp(self):
        self.state = {"ride_messages": [], "messages": [], "account_messages": {}, "rides": {}}

    def send_ride(self, who, text, audience="shared", client_id=None):
        msg, error = add_ride_message(
            self.state, "RIDE1", who,
            {"text": text, "audience": audience, "client_id": client_id}
        )
        self.assertIsNone(error)
        return msg

    def test_rider_cannot_message_dispatch_privately(self):
        msg = self.send_ride(RIDER, "I'm outside.", "dispatch")
        self.assertEqual(msg["audience"], "shared")
        self.assertEqual([m["text"] for m in visible_ride_messages(self.state, "RIDE1", "driver")],
                         ["I'm outside."])

    def test_reassigned_driver_sees_previous_shared_ride_history(self):
        self.send_ride(RIDER, "Where are you?")
        self.send_ride(DISPATCH, "Driver coming.")
        self.send_ride(OLD_DRIVER, "Traffic, five minutes.")
        # A newly assigned driver reads the same ride history, not a per-driver log.
        history = visible_ride_messages(self.state, "RIDE1", "driver")
        self.assertEqual([m["role"] for m in history], ["rider", "dispatch", "driver"])

    def test_dispatch_rider_only_does_not_leak_to_drivers(self):
        self.send_ride(DISPATCH, "I will call you shortly.", "rider")
        self.send_ride(RIDER, "Thanks")
        self.assertEqual(len(visible_ride_messages(self.state, "RIDE1", "dispatch")), 2)
        self.assertEqual([m["text"] for m in visible_ride_messages(self.state, "RIDE1", "driver")],
                         ["Thanks"])

    def test_legacy_rider_dispatch_message_becomes_driver_visible(self):
        self.state["ride_messages"].append({
            "id": "legacy", "ride_id": "RIDE1", "role": "rider",
            "from": "Riley", "audience": "dispatch", "text": "Old text", "at": 1
        })
        self.assertEqual(len(visible_ride_messages(self.state, "RIDE1", "driver")), 1)

    def test_driver_cannot_send_rider_only(self):
        message, error = add_ride_message(self.state, "RIDE1", OLD_DRIVER,
                                           {"text": "Private?", "audience": "rider"})
        self.assertIsNone(message)
        self.assertIn("Dispatch", error)

    def test_team_private_is_only_visible_to_dispatch_and_target_driver(self):
        add_message(self.state, "Alex", "To dispatch", driver="Alex", private=True, role="driver")
        add_message(self.state, "dispatch", "For Alex", driver="Alex", private=True, role="dispatch")
        add_message(self.state, "Sam", "Team notice", role="driver")
        self.assertEqual(len(thread_messages(self.state, "dispatch")), 3)
        self.assertEqual(len(thread_messages(self.state, "Alex")), 3)
        self.assertEqual([m["text"] for m in thread_messages(self.state, "Sam")], ["Team notice"])

    def test_previous_driver_keeps_original_chat_color(self):
        self.send_ride(OLD_DRIVER, "I am delayed")
        ride = {"id": "RIDE1", "driver": "Sam", "driver_account_id": "new"}
        self.state["rides"] = {"RIDE1": ride}
        with patch.object(server, "STORE", self.state):
            with patch.object(server, "driver_chat_color_map", return_value={
                "Alex": "#112233", "Sam": "#445566"
            }):
                messages = server.unified_chat_messages(DISPATCH)
        self.assertEqual(messages[0]["chat_color"], "#112233")

    def test_account_messages_survive_between_rides_and_hide_from_drivers(self):
        msg, error = add_account_message(self.state, "r1", DISPATCH,
                                          {"text": "You left your wallet.", "client_id": "notice1"})
        self.assertIsNone(error)
        self.assertEqual(msg["rider_account_id"], "r1")
        response, error = add_account_message(self.state, "r1", RIDER,
                                               {"text": "Can I pick it up?"})
        self.assertIsNone(error)
        self.assertEqual(len(visible_account_messages(self.state, RIDER)), 2)
        self.assertEqual(len(visible_account_messages(self.state, OLD_DRIVER)), 0)
        other = {"id": "other", "role": "rider", "display_name": "Other"}
        self.assertEqual(len(visible_account_messages(self.state, other)), 0)
        self.assertEqual(len(visible_account_messages(self.state, DISPATCH)), 2)
        # No ride records exist. Account history is independent of bookings.
        self.assertEqual(self.state["rides"], {})

    def test_account_retry_and_role_authorization(self):
        first, error = add_account_message(self.state, "r1", RIDER,
                                            {"text": "Thank you", "client_id": "repeat"})
        self.assertIsNone(error)
        second, error = add_account_message(self.state, "r1", RIDER,
                                             {"text": "Thank you", "client_id": "repeat"})
        self.assertIsNone(error)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.state["account_messages"]["r1"]), 1)
        denied, error = add_account_message(self.state, "r1", OLD_DRIVER,
                                             {"text": "Not permitted"})
        self.assertIsNone(denied)
        self.assertIn("Only riders", error)
        denied, error = add_account_message(self.state, "other", RIDER,
                                             {"text": "Wrong account"})
        self.assertIsNone(denied)
        self.assertIn("not found", error)

    def test_account_http_routing_checks_target_account(self):
        handler = object.__new__(server.Handler)
        handler.send_json = lambda code, data: (code, data)
        accounts = [{"id": "r1", "display_name": "Riley", "enabled": True},
                    {"id": "disabled", "display_name": "Former", "enabled": False}]
        with patch.object(server, "STORE", self.state), \
             patch.object(server.auth, "list_users", return_value=accounts), \
             patch.object(server, "save"), patch.object(server, "record_event"):
            code, payload = handler.post_chat_message(DISPATCH, {
                "text": "Is your payment resolved?", "rider_account_id": "r1"
            })
            self.assertEqual(code, 201)
            self.assertEqual(payload["message"]["rider_account_id"], "r1")
            code, _ = handler.post_chat_message(DISPATCH, {
                "text": "No access", "rider_account_id": "disabled"
            })
            self.assertEqual(code, 404)
            code, _ = handler.post_chat_message(OLD_DRIVER, {
                "text": "No access", "rider_account_id": "r1"
            })
            self.assertEqual(code, 403)
            code, payload = handler.post_chat_message(RIDER, {
                "text": "I have a question", "account_chat": True,
                "rider_account_id": "disabled"
            })
            self.assertEqual(code, 201)
            self.assertEqual(payload["message"]["rider_account_id"], "r1")

    def test_retry_deduplicates_team_and_ride_messages(self):
        first = self.send_ride(RIDER, "On my way", client_id="r-100")
        second = self.send_ride(RIDER, "On my way", client_id="r-100")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.state["ride_messages"]), 1)
        team1 = add_message(self.state, "Alex", "Checking", client_id="a-200", sender_id="old")
        team2 = add_message(self.state, "Alex", "Checking", client_id="a-200", sender_id="old")
        self.assertEqual(team1["id"], team2["id"])
        self.assertEqual(len(self.state["messages"]), 1)


if __name__ == "__main__":
    unittest.main()
