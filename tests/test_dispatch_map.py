"""Dispatch map access, live location consent, freshness and ride lifecycle."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


USERS = {
    "rider": {"id": "rider-1", "role": "rider", "display_name": "Rider"},
    "other": {"id": "rider-2", "role": "rider", "display_name": "Other rider"},
    "driver": {"id": "driver-1", "role": "driver", "display_name": "Driver"},
    "dispatch": {"id": "dispatch-1", "role": "dispatch", "display_name": "Dispatch"},
}


class AuthenticatedHandler(server.Handler):
    def user(self):
        return USERS.get(self.headers.get("Authorization"))


class DispatchMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), AuthenticatedHandler)
        cls.base = "http://127.0.0.1:%s" % cls.httpd.server_port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        self.store_patch = patch.object(server, "STORE", server.ensure_store({"rides": {}}))
        self.store_patch.start()
        self.save_patch = patch.object(server, "save")
        self.save_mock = self.save_patch.start()
        server.RIDER_LOCATIONS.clear()
        server.RIDER_REVOKED_SHARES.clear()
        self.ride = {
            "id": "ride-1", "status": "accepted", "driver": "Driver",
            "driver_account_id": "driver-1", "rider_account_id": "rider-1",
            "rider_id": "NR-RIDER", "rider_name": "Rider", "pickup": "Pickup",
            "dropoff": "Drop-off", "pickup_coords": [32.08, -81.09],
            "dropoff_coords": [32.09, -81.10], "distance_mi": 2, "created": time.time(),
        }
        server.STORE["rides"]["ride-1"] = self.ride

    def tearDown(self):
        self.save_patch.stop()
        self.store_patch.stop()
        server.RIDER_LOCATIONS.clear()
        server.RIDER_REVOKED_SHARES.clear()

    def call(self, path, body=None, user="dispatch"):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data,
            headers={"Content-Type": "application/json", "Authorization": user})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def fix(self, **extra):
        return dict({"sharing": True, "sharing_id": "sharing-session-1", "coords": {"lat": 32.081, "lng": -81.091},
                     "location_at": time.time(), "accuracy": 8}, **extra)

    def test_map_requires_dispatch_even_without_database_dev_mode(self):
        self.assertEqual(self.call("/api/dispatch/map", user="")[0], 401)
        for role in ("rider", "other", "driver"):
            self.assertEqual(self.call("/api/dispatch/map", user=role)[0], 403)
        self.assertEqual(self.call("/api/dispatch/map")[0], 200)

    def test_consent_owner_and_role_are_enforced(self):
        endpoint = "/api/rides/ride-1/location"
        self.assertEqual(self.call(endpoint, self.fix(), "other")[0], 404)
        self.assertEqual(self.call(endpoint, self.fix(), "driver")[0], 403)
        self.assertEqual(self.call(endpoint, self.fix(), "dispatch")[0], 403)
        self.assertEqual(self.call(endpoint, {"coords": {"lat": 1, "lng": 1}}, "rider")[0], 400)
        self.assertEqual(self.call(endpoint, [], "rider")[0], 400)
        self.assertEqual(server.RIDER_LOCATIONS, {})

    def test_shared_rider_position_never_enters_public_ride_or_saved_state(self):
        self.assertEqual(self.call("/api/rides/ride-1/location", self.fix(), "rider")[0], 200)
        code, data = self.call("/api/dispatch/map")
        self.assertEqual(code, 200)
        self.assertEqual(data["rides"][0]["rider_location"]["coords"], [32.081, -81.091])
        for role in ("driver", "rider"):
            _, public = self.call("/api/rides/ride-1", user=role)
            self.assertNotIn("rider_location", public)
            self.assertNotIn("location_at", public)
        self.assertNotIn("rider_location", server.STORE["rides"]["ride-1"])
        self.save_mock.assert_not_called()

    def test_stop_and_expiration_remove_rider_location(self):
        self.call("/api/rides/ride-1/location", self.fix(), "rider")
        server.RIDER_LOCATIONS["ride-1"]["at"] = time.time() - 121
        self.assertIsNone(self.call("/api/dispatch/map")[1]["rides"][0]["rider_location"])
        self.assertNotIn("ride-1", server.RIDER_LOCATIONS)
        self.call("/api/rides/ride-1/location", self.fix(), "rider")
        self.assertEqual(self.call("/api/rides/ride-1/location", {"sharing": False}, "rider")[0], 200)
        self.assertIsNone(self.call("/api/dispatch/map")[1]["rides"][0]["rider_location"])

    def test_ride_completion_clears_location_and_prevents_more_updates(self):
        self.call("/api/rides/ride-1/location", self.fix(), "rider")
        self.ride["status"] = "at_dropoff"
        self.assertEqual(self.call("/api/rides/ride-1/advance", {}, "driver")[0], 200)
        self.assertNotIn("ride-1", server.RIDER_LOCATIONS)
        self.assertEqual(self.call("/api/dispatch/map")[1]["rides"], [])
        self.assertEqual(self.call("/api/rides/ride-1/location", self.fix(), "rider")[0], 409)
        self.assertEqual(self.call("/api/rides/ride-1/location", {"sharing": False}, "rider")[0], 200)

    def test_late_update_cannot_restart_a_revoked_sharing_session(self):
        self.call("/api/rides/ride-1/location", self.fix(), "rider")
        self.call("/api/rides/ride-1/location", {"sharing": False, "sharing_id": "sharing-session-1"}, "rider")
        self.assertEqual(self.call("/api/rides/ride-1/location", self.fix(), "rider")[0], 409)
        self.assertNotIn("ride-1", server.RIDER_LOCATIONS)
        new_session = self.fix(sharing_id="sharing-session-2")
        self.assertEqual(self.call("/api/rides/ride-1/location", new_session, "rider")[0], 200)

    def test_bad_old_or_nonfinite_location_is_rejected(self):
        bad = [self.fix(coords={"lat": 100, "lng": 0}), self.fix(location_at=time.time() - 130),
               self.fix(location_at=float("nan")), self.fix(accuracy=-1),
               self.fix(coords={"lat": 0, "lng": float("inf")})]
        for fix in bad:
            self.assertEqual(self.call("/api/rides/ride-1/location", fix, "rider")[0], 400)

    def test_driver_presence_does_not_make_an_old_location_look_live(self):
        self.assertEqual(self.call("/api/drivers/ping", self.fix(status="accepted"), "driver")[0], 200)
        driver = server.STORE["drivers"]["Driver"]
        driver["location_at"] = time.time() - 121
        self.call("/api/drivers/ping", {"status": "at_pickup"}, "driver")
        item = self.call("/api/dispatch/map")[1]["drivers"][0]
        self.assertTrue(item["active"])
        self.assertFalse(item["location_fresh"])
        self.assertEqual(item["status"], "accepted")
        self.assertEqual(item["ride_id"], "ride-1")
        self.call("/api/drivers/ping", {"status": "at_pickup", "location_sharing": False}, "driver")
        self.assertNotIn("coords", server.STORE["drivers"]["Driver"])


if __name__ == "__main__":
    unittest.main()
