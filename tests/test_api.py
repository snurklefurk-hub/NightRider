import json, os, sys, threading, unittest, urllib.request as u
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server  # noqa: E402


class NightRiderAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        if os.path.exists(server.DATA_FILE):
            os.remove(server.DATA_FILE)

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = u.Request(self.base + path, data=data, headers={"Content-Type": "application/json"},
                        method="POST" if data is not None else "GET")
        try:
            with u.urlopen(req) as r:
                return r.status, json.load(r)
        except u.HTTPError as e:
            return e.code, json.load(e)

    def new_ride(self):
        s, j = self.call("/api/rides", {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 6.5})
        self.assertEqual(s, 201)
        return j["id"]

    def test_create_ride_computes_fare_and_status(self):
        s, j = self.call("/api/rides", {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 6.5})
        self.assertEqual(s, 201)
        self.assertEqual(j["status"], "requested")
        # $5 flag drop + $1/mi trip; no pickup coords, so the driver leg is 0.
        self.assertEqual(j["fare"], 11.5)
        self.assertEqual(j["driver_to_pickup_mi"], 0.0)

    def test_fare_includes_driver_approach_leg(self):
        s, j = self.call("/api/rides", {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 6.5,
                                        "driver_to_pickup_mi": 4.0})
        self.assertEqual(s, 201)
        # 5 + 1 * 6.5 + 0.25 * 4
        self.assertEqual(j["fare"], 12.5)
        self.assertEqual(j["driver_to_pickup_mi"], 4.0)

    def test_approach_defaults_to_city_hall_when_pickup_coords_given(self):
        s, j = self.call("/api/rides", {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 2.0,
                                        "pickup_coords": {"lat": 32.0956, "lng": -81.09111}})
        self.assertEqual(s, 201)
        # ~1.0 mile straight-line from Savannah City Hall.
        self.assertEqual(j["driver_to_pickup_mi"], 1.0)
        self.assertEqual(j["fare"], 7.25)  # 5 + 2.0 + 0.25 * 1.0

    def test_implausible_approach_is_rejected(self):
        s, j = self.call("/api/rides", {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 2.0,
                                        "driver_to_pickup_mi": 500})
        self.assertEqual(s, 400)
        self.assertIn("driver_to_pickup_mi", j["error"])

    def test_map_coordinates_are_stored(self):
        s, j = self.call("/api/rides", {"rider_name": "M", "pickup": "A", "dropoff": "B", "distance_mi": 2,
                                        "pickup_coords": '{"lat": 32.08, "lng": -81.09}', "dropoff_coords": "bad"})
        self.assertEqual(s, 201)
        self.assertEqual(j["pickup_coords"], [32.08, -81.09])
        self.assertIsNone(j["dropoff_coords"])

    def test_short_ride_still_pays_the_flag_drop(self):
        s, j = self.call("/api/rides", {"rider_name": "Q", "pickup": "A", "dropoff": "B", "distance_mi": 0.5})
        self.assertEqual(s, 201)
        self.assertEqual(j["fare"], 5.5)  # 5 + 1 * 0.5

    def test_validation_rejects_bad_input(self):
        self.assertEqual(self.call("/api/rides", {"rider_name": "", "pickup": "A", "dropoff": "B", "distance_mi": 1})[0], 400)
        self.assertEqual(self.call("/api/rides", {"rider_name": "x", "pickup": "A", "dropoff": "B", "distance_mi": "abc"})[0], 400)
        self.assertEqual(self.call("/api/rides", {"rider_name": "x", "pickup": "A", "dropoff": "B", "distance_mi": 0})[0], 400)

    def test_lifecycle_accept_advance_complete(self):
        rid = self.new_ride()
        s, j = self.call(f"/api/rides/{rid}/accept", {"driver": "Sam"})
        self.assertEqual((s, j["status"], j["driver"]), (200, "accepted", "Sam"))
        self.assertEqual(self.call(f"/api/rides/{rid}/accept", {"driver": "X"})[0], 409)
        self.assertEqual(self.call(f"/api/rides/{rid}/advance", {})[1]["status"], "arrived")
        self.assertEqual(self.call(f"/api/rides/{rid}/advance", {})[1]["status"], "in_progress")
        self.assertEqual(self.call(f"/api/rides/{rid}/advance", {})[1]["status"], "completed")
        self.assertEqual(self.call(f"/api/rides/{rid}/advance", {})[0], 409)

    def test_demo_flag_prices_acceptance_from_city_hall(self):
        s, j = self.call("/api/rides", {"rider_name": "J", "pickup": "A", "dropoff": "B", "distance_mi": 2.0,
                                        "pickup_coords": {"lat": 32.0956, "lng": -81.09111}})
        rid = j["id"]
        s, j = self.call(f"/api/rides/{rid}/accept", {"driver": "Test Driver", "demo": True})
        self.assertEqual(s, 200)
        self.assertEqual(j["status"], "accepted")
        self.assertEqual(j["driver_to_pickup_mi"], 1.0)
        self.assertEqual(j["fare"], 7.25)

    def test_cancel_and_closed_ride(self):
        rid = self.new_ride()
        self.assertEqual(self.call(f"/api/rides/{rid}/cancel", {})[1]["status"], "cancelled")
        self.assertEqual(self.call(f"/api/rides/{rid}/cancel", {})[0], 409)

    def test_config_endpoint_returns_builtin_carto_key(self):
        os.environ.pop("CARTO_API_KEY", None)
        s, j = self.call("/api/config")
        self.assertEqual(s, 200)
        self.assertTrue(j["cartoKey"], "a default CARTO key should be configured")
        self.assertTrue(j["cartoKey"].startswith("cb1_"))
        self.assertEqual(j["rates"], {"flag_drop": 5.0, "trip_per_mile": 1.0, "approach_per_mile": 0.25})
        self.assertEqual(j["demoDriver"]["coords"], [32.08111, -81.09111])
        self.assertEqual(j["demoDriver"]["label"], "Savannah City Hall")

    def test_config_endpoint_env_var_overrides_builtin_key(self):
        os.environ["CARTO_API_KEY"] = "test-key-123"
        try:
            s, j = self.call("/api/config")
            self.assertEqual((s, j["cartoKey"]), (200, "test-key-123"))
        finally:
            os.environ.pop("CARTO_API_KEY", None)

    def test_missing_ride_and_route(self):
        self.assertEqual(self.call("/api/rides/nope")[0], 404)
        self.assertEqual(self.call("/api/nope")[0], 404)

    def test_list_and_pages_load(self):
        self.new_ride()
        s, j = self.call("/api/rides")
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(j["rides"]), 1)
        for p in ["/", "/driver.html", "/dispatch.html", "/nightrider.css"]:
            with u.urlopen(self.base + p) as r:
                self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()


class FrontendSourceTests(unittest.TestCase):
    def test_public_pages_use_openstreetmap_and_no_google_key(self):
        pub = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
        joined = ""
        for name in sorted(os.listdir(pub)):
            if name.endswith(".html") or name.endswith(".css"):
                with open(os.path.join(pub, name), encoding="utf-8") as fh:
                    joined += fh.read()
        self.assertNotIn("googleapis", joined.lower())
        self.assertNotIn("api_key", joined.lower())
        self.assertIn("openstreetmap", joined.lower())
        with open(os.path.join(pub, "index.html"), encoding="utf-8") as fh:
            index = fh.read()
        self.assertIn("leaflet", index.lower())
        self.assertIn("nominatim", index.lower())


if __name__ == "__main__":
    unittest.main()
