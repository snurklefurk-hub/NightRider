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
        self.assertEqual(j["fare"], 13.4)  # 3 + 1.6 * 6.5

    def test_map_coordinates_are_stored(self):
        s, j = self.call("/api/rides", {"rider_name": "M", "pickup": "A", "dropoff": "B", "distance_mi": 2,
                                        "pickup_coords": '{"lat": 40.7, "lng": -74.0}', "dropoff_coords": "bad"})
        self.assertEqual(s, 201)
        self.assertEqual(j["pickup_coords"], [40.7, -74.0])
        self.assertIsNone(j["dropoff_coords"])

    def test_minimum_fare_applies(self):
        s, j = self.call("/api/rides", {"rider_name": "Q", "pickup": "A", "dropoff": "B", "distance_mi": 0.5})
        self.assertEqual(j["fare"], 7.0)

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

    def test_cancel_and_closed_ride(self):
        rid = self.new_ride()
        self.assertEqual(self.call(f"/api/rides/{rid}/cancel", {})[1]["status"], "cancelled")
        self.assertEqual(self.call(f"/api/rides/{rid}/cancel", {})[0], 409)

    def test_config_endpoint_returns_key_field(self):
        s, j = self.call("/api/config")
        self.assertEqual(s, 200)
        self.assertIn("googleMapsKey", j)

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
