"""Guardrails for ten fictitious, Chatham-only Dispatch showroom rides."""
import collections
import unittest
from unittest.mock import patch

import demo_chatham_rides
import history_purge
import server


class FakeHandler:
    def send_json(self, code, data):
        return code, data


class ChathamDemoRideTests(unittest.TestCase):
    def setUp(self):
        self.store = server.ensure_store({"rides": {}, "messages": [],
                                         "account_messages": {}, "ride_messages": []})

    def test_exactly_three_incoming_five_completed_two_cancelled(self):
        samples = demo_chatham_rides.samples(self.store)
        self.assertEqual(len(samples), 10)
        self.assertEqual(collections.Counter(r["status"] for r in samples),
                         {"to_pickup": 1, "at_pickup": 1, "to_dropoff": 1, "completed": 5, "cancelled": 2})
        self.assertEqual(len(set(r["id"] for r in samples)), 10)
        self.assertEqual(len(set(r["rider_name"] for r in samples)), 10)
        self.assertTrue(all(r["demo_preview"] is True and r["simulated"] is True
                            and r["transportation_service"] is False
                            and r["payment_method"].startswith("Simulation only")
                            for r in samples))
        for ride in samples:
            self.assertIn(", GA ", ride["pickup"])
            self.assertIn(", GA ", ride["dropoff"])
            self.assertGreater(ride["created"], 0)
            self.assertTrue(ride["status_log"])
        self.assertFalse(self.store["rides"], "Preview must never create a canonical ride")

    def test_dispatch_only_payload_and_no_duplicate_rides_or_persistence(self):
        with (patch.object(server, "STORE", self.store),
              patch.object(server, "save") as save):
            code, first = server.Handler.dispatch_get(FakeHandler(),
                                                       "/api/dispatch/rides", {})
            code_again, again = server.Handler.dispatch_get(FakeHandler(),
                                                           "/api/dispatch/rides", {})
            self.assertEqual(code, 200)
            self.assertEqual(code_again, 200)
            self.assertEqual(first["rides"], [])
            self.assertEqual(len(first["demo_rides"]), 10)
            self.assertEqual(again, first)
            self.assertNotIn("demo_rides", self.store)
            save.assert_not_called()

    def test_preview_is_not_assignable_or_customer_visible(self):
        fake = demo_chatham_rides.samples(self.store)[0]
        self.assertNotIn(fake["id"], self.store["rides"])
        # Both driver and rider APIs resolve rides ONLY from canonical records.
        with patch.object(server, "STORE", self.store):
            code, _ = server.Handler.dispatch_get(FakeHandler(),
                                                  "/api/dispatch/rides", {})
        self.assertEqual(code, 200)
        self.assertEqual(self.store.get("rides"), {})
        self.assertFalse(any(ride.get("demo_preview") for ride in self.store["rides"].values()))

    def test_export_records_samples_then_clears_them_once_without_reseeding(self):
        content = history_purge.serialise(history_purge.snapshot(self.store, "rides", 1234))
        self.assertIn("Naomi Whitaker", content)
        self.assertIn("NR-DEMO-010", content)
        self.assertIn("dispatch_only_fictional_demo_rides", content)
        self.assertNotIn("Naomi Whitaker", history_purge.serialise(
            history_purge.snapshot(self.store, "chat", 1234)))
        self.assertFalse(history_purge.any_open_rides(self.store),
                         "Read-only incoming samples must not block deletion of real records")
        result = history_purge.purge(self.store, "rides")
        self.assertEqual(result, {"rides": 0, "demo_rides": 10})
        self.assertEqual(self.store["demo_chatham_samples_cleared"], True)
        self.assertEqual(demo_chatham_rides.samples(self.store), [])
        self.assertEqual(history_purge.purge(self.store, "rides"),
                         {"rides": 0, "demo_rides": 0})
        self.assertEqual(demo_chatham_rides.samples(server.ensure_store(self.store)), [])

    def test_three_geo_examples_and_five_fake_drivers_stay_isolated(self):
        rides = demo_chatham_rides.map_rides(self.store)
        drivers = demo_chatham_rides.demo_drivers(self.store)
        self.assertEqual(len(rides), 3)
        self.assertEqual(len(drivers), 5)
        self.assertEqual({r["status"] for r in rides}, {"to_pickup", "at_pickup", "to_dropoff"})
        self.assertEqual(len({d["id"] for d in drivers}), 5)
        self.assertTrue(all(d["demo_preview"] is True and d["location_kind"] ==
                            "fixed_demonstration_point" for d in drivers))
        self.assertTrue(all(r["rider_location"]["live"] is False and
                            r["rider_location"]["simulated"] is True for r in rides))
        for ride in rides:
            self.assertTrue(-82 < ride["pickup_coords"][1] < -80)
            self.assertTrue(31 < ride["pickup_coords"][0] < 33)
            self.assertNotIn(ride["id"], self.store["rides"])
        pickup = next(r for r in rides if r["status"] == "to_pickup")
        self.assertNotEqual(pickup["rider_location"]["coords"],
                            next(d["coords"] for d in drivers if d["ride_id"] == pickup["id"]))
        for ride in (r for r in rides if r["status"] in ("at_pickup", "to_dropoff")):
            driver = next(d for d in drivers if d["ride_id"] == ride["id"])
            self.assertEqual(driver["coords"], ride["rider_location"]["coords"],
                             "Co-located fixture must share exact coordinates")
        self.assertFalse(self.store["drivers"])
        self.assertFalse(self.store["rides"])
        history_purge.purge(self.store, "rides")
        self.assertEqual(demo_chatham_rides.map_rides(self.store), [])
        self.assertEqual(demo_chatham_rides.demo_drivers(self.store), [])

    def test_chat_purge_does_not_remove_demo_rides(self):
        history_purge.purge(self.store, "chat")
        self.assertEqual(len(demo_chatham_rides.samples(self.store)), 10)

    def test_actual_active_ride_still_blocks_rides_purge(self):
        self.store["rides"]["active"] = {"id": "active", "status": "requested"}
        self.assertTrue(history_purge.any_open_rides(self.store))
        with self.assertRaises(ValueError):
            history_purge.purge(self.store, "rides")
        self.assertEqual(len(demo_chatham_rides.samples(self.store)), 10)


if __name__ == "__main__":
    unittest.main()
