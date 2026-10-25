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


    def call(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        req = u.Request(self.base + path, data=data, headers=hdrs,
                        method="POST" if data is not None else "GET")
        try:
            with u.urlopen(req) as r:
                return r.status, json.load(r)
        except u.HTTPError as e:
            return e.code, json.load(e)

    def call_text(self, path, headers=None):
        req = u.Request(self.base + path, headers=headers or {}, method="GET")
        try:
            with u.urlopen(req) as r:
                return r.status, r.read().decode("utf-8"), r.headers.get("Content-Type", "")
        except u.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers.get("Content-Type", "")

    def new_ride(self, body=None, headers=None):
        payload = {"rider_name": "Jordan", "pickup": "A", "dropoff": "B", "distance_mi": 6.5}
        payload.update(body or {})
        s, j = self.call("/api/rides", payload, headers=headers)
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

    # ---- Push + acknowledgement handshake ----
    def test_ride_request_is_pushed_with_a_receipt_handshake(self):
        rid = self.new_ride()
        s, j = self.call("/api/dispatch/events?since=0&wait=0")
        self.assertEqual(s, 200)
        mine = [e for e in j["events"] if e.get("ride") == rid]
        types = [e["type"] for e in mine]
        self.assertIn("ride_requested", types)
        requested = next(e for e in mine if e["type"] == "ride_requested")
        self.assertTrue(requested["ack_required"])
        self.assertEqual(requested["snapshot"]["status"], "requested")
        self.assertNotIn("rider_id", requested["snapshot"])

        s, j = self.call(f"/api/dispatch/rides/{rid}/ack", {"by": "Alex"})
        self.assertEqual(s, 200)
        self.assertEqual(j["ack"]["by"], "Alex")
        self.assertGreaterEqual(j["ack"]["latency_s"], 0)

        s, j = self.call(f"/api/rides/{rid}")
        self.assertEqual(j["dispatch_ack"]["by"], "Alex")
        s, j = self.call(f"/api/events?since=0&wait=0&ride={rid}")
        self.assertIn("ride_acknowledged", [e["type"] for e in j["events"]])

    def test_long_poll_returns_only_events_after_the_cursor(self):
        ride = self.new_ride()
        s, first = self.call("/api/events?since=0&wait=0")
        cursor = first["cursor"]
        s, empty = self.call(f"/api/events?since={cursor}&wait=0")
        self.assertEqual(empty["events"], [])
        self.assertTrue(empty["timed_out"])
        self.new_ride()
        s, later = self.call(f"/api/events?since={cursor}&wait=0")
        self.assertTrue(later["events"])
        self.assertTrue(all(e["seq"] > cursor for e in later["events"]))
        s, scoped = self.call(f"/api/events?since=0&wait=0&ride={ride}")
        self.assertTrue(scoped["events"])
        self.assertTrue(all(e.get("ride") == ride for e in scoped["events"]))

    def test_status_changes_are_pushed_too(self):
        rid = self.new_ride()
        cursor = self.call("/api/events?since=0&wait=0")[1]["cursor"]
        self.call(f"/api/rides/{rid}/accept", {"driver": "Sam"})
        s, j = self.call(f"/api/events?since={cursor}&wait=0&ride={rid}")
        accepted = [e for e in j["events"] if e["type"] == "ride_accepted"]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["snapshot"]["status"], "accepted")
        self.assertEqual(accepted[0]["snapshot"]["driver"], "Sam")

    def test_dispatch_routes_are_open_and_the_key_is_gone(self):
        # The dispatch key was removed: every dispatch route answers without it.
        for path in ["/api/dispatch/rides", "/api/dispatch/riders", "/api/dispatch/events",
                     "/api/dispatch/drivers"]:
            self.assertEqual(self.call(path)[0], 200, path)
        self.assertEqual(self.call("/api/dispatch")[0], 404)
        self.assertEqual(self.call("/api/dispatch/nope")[0], 404)
        self.assertEqual(self.call("/api/dispatch/rides/nope/ack", {})[0], 404)
        self.assertFalse(hasattr(server, "DEFAULT_DISPATCH_KEY"))
        self.assertFalse(hasattr(server, "dispatch_ok"))

    # ---- Active drivers + dispatch <-> driver texting ----
    def test_driver_heartbeat_lists_active_drivers(self):
        s, j = self.call("/api/drivers/ping", {"name": "Sam", "status": "available"})
        self.assertEqual(s, 200)
        self.assertTrue(j["ok"])
        self.assertGreater(j["driver"]["last_seen"], 0)
        listed = self.call("/api/dispatch/drivers")[1]["drivers"]
        sam = [d for d in listed if d["name"] == "Sam"]
        self.assertEqual(len(sam), 1)
        self.assertTrue(sam[0]["active"])
        self.assertEqual(sam[0]["status"], "available")
        # An unknown status falls back to a sane default rather than erroring.
        self.call("/api/drivers/ping", {"name": "Sam", "status": "nonsense"})
        last = [d for d in self.call("/api/dispatch/drivers")[1]["drivers"] if d["name"] == "Sam"][0]
        self.assertIn(last["status"], server.DRIVER_STATUSES)
        self.assertEqual(self.call("/api/drivers/ping", {"name": ""})[0], 400)

    def test_dispatch_and_driver_share_a_text_thread(self):
        self.call("/api/drivers/ping", {"name": "Rosa"})
        s, j = self.call("/api/drivers/Rosa/message", {"text": "On my way"})
        self.assertEqual(s, 201)
        self.assertEqual(j["message"]["from"], "driver")
        self.assertEqual(j["message"]["text"], "On my way")
        s, j = self.call("/api/dispatch/drivers/Rosa/message", {"text": "Copy that"})
        self.assertEqual(s, 201)
        self.assertEqual(j["message"]["from"], "dispatch")
        # Each side reads the same thread and sees both messages.
        driver_view = self.call("/api/drivers/Rosa/messages")[1]["messages"]
        dispatch_view = self.call("/api/dispatch/drivers/Rosa/messages")[1]["messages"]
        self.assertEqual([m["text"] for m in driver_view], ["On my way", "Copy that"])
        self.assertEqual([m["text"] for m in dispatch_view], ["On my way", "Copy that"])
        self.assertEqual([m["from"] for m in dispatch_view], ["driver", "dispatch"])
        # The `since` cursor returns only newer messages.
        cursor = driver_view[-1]["at"]
        self.call("/api/dispatch/drivers/Rosa/message", {"text": "Ride is waiting"})
        newer = self.call(f"/api/drivers/Rosa/messages?since={cursor}")[1]["messages"]
        self.assertEqual([m["text"] for m in newer], ["Ride is waiting"])
        # Empty text is refused on both sides.
        self.assertEqual(self.call("/api/drivers/Rosa/message", {"text": "   "})[0], 400)
        self.assertEqual(self.call("/api/dispatch/drivers/Rosa/message", {"text": ""})[0], 400)

    def test_ride_records_the_chosen_payment_method(self):
        s, j = self.call("/api/rides", {"rider_name": "Pat", "pickup": "A", "dropoff": "B",
                                        "distance_mi": 3, "payment_method": "Venmo"})
        self.assertEqual(s, 201)
        self.assertEqual(j["payment_method"], "Venmo")
        self.assertEqual(server.STORE["rides"][j["id"]]["payment_method"], "Venmo")
        text = self.call_text("/api/dispatch/export")[1]
        block = [b for b in text.split("-" * 68) if j["id"] in b][0]
        self.assertIn("Payment:  Venmo", block)

    # ---- Hidden rider identifiers ----
    def test_rider_id_is_derived_hidden_and_not_client_settable(self):
        signals = {"platform": "Win32", "screen": "1920x1080", "cores": "8", "canvas": "ab12"}
        s, j = self.call("/api/rides", {"rider_name": "Casey", "pickup": "A", "dropoff": "B",
                                        "distance_mi": 3, "device": signals, "rider_id": "NR-SPOOFED"})
        self.assertEqual(s, 201)
        self.assertNotIn("rider_id", j, "the rider must never receive their hidden id")
        self.assertIn("rider_summary", j)
        rid = j["id"]
        stored = server.STORE["rides"][rid]["rider_id"]
        self.assertTrue(stored.startswith("NR-"))
        self.assertNotEqual(stored, "NR-SPOOFED", "a client-supplied rider_id must be ignored")
        # Same device signals from the same client resolve to the same rider.
        s, j2 = self.call("/api/rides", {"rider_name": "Casey", "pickup": "C", "dropoff": "D",
                                          "distance_mi": 2, "device": signals})
        self.assertEqual(server.STORE["rides"][j2["id"]]["rider_id"], stored)
        # A different client is a different rider.
        s, j3 = self.call("/api/rides", {"rider_name": "Other", "pickup": "E", "dropoff": "F",
                                          "distance_mi": 2, "device": signals},
                          headers={"User-Agent": "OtherBrowser/9"})
        self.assertNotEqual(server.STORE["rides"][j3["id"]]["rider_id"], stored)
        # Nothing public ever exposes it.
        self.assertNotIn("rider_id", self.call(f"/api/rides/{rid}")[1])
        self.assertTrue(all("rider_id" not in r for r in self.call("/api/rides")[1]["rides"]))
        # Dispatch does see it, and so does the backend record.
        found = [r for r in self.call("/api/dispatch/rides")[1]["rides"] if r["id"] == rid]
        self.assertEqual(found[0]["rider_id"], stored)
        s, detail = self.call(f"/api/dispatch/riders/{stored}")
        self.assertEqual(s, 200)
        self.assertIn("Casey", detail["names"])
        self.assertEqual(detail["signals"]["canvas"], "ab12")
        self.assertIn(rid, [r["id"] for r in detail["rides"]])

    def test_signals_are_sanitised(self):
        s, j = self.call("/api/rides", {"rider_name": "Sam", "pickup": "A", "dropoff": "B", "distance_mi": 2,
                                        "device": {"platform": "Linux", "secret": "nope",
                                                   "screen": {"nested": 1}, "cores": "4"}})
        self.assertEqual(s, 201)
        rid = server.STORE["rides"][j["id"]]["rider_id"]
        sig = self.call(f"/api/dispatch/riders/{rid}")[1]["signals"]
        self.assertEqual(sig, {"platform": "Linux", "cores": "4"})

    # ---- Ratings and issues ----
    def test_ratings_and_issues_attach_to_the_hidden_rider(self):
        rid = self.new_ride({"rider_name": "Difficult", "device": {"platform": "Rater1"}})
        hidden = server.STORE["rides"][rid]["rider_id"]
        s, j = self.call(f"/api/rides/{rid}/rating", {"by": "driver", "by_name": "Sam", "stars": 2,
                                                      "issues": ["no-show", "rude"], "note": "late"})
        self.assertEqual(s, 201)
        self.assertEqual(j["rating"]["stars"], 2)
        self.assertEqual(j["rating"]["issues"], ["no-show", "rude"])
        s, j = self.call(f"/api/rides/{rid}/rating", {"by": "dispatch", "stars": 1, "issues": "unreachable"})
        self.assertEqual(s, 201)
        self.assertEqual(self.call(f"/api/rides/{rid}/ratings")[1]["ratings"][-1]["issues"], ["unreachable"])
        self.assertEqual(self.call(f"/api/riders/{hidden}/ratings")[0], 404)
        s, detail = self.call(f"/api/dispatch/riders/{hidden}")
        self.assertEqual(len(detail["ratings"]), 2)
        self.assertEqual(detail["summary"]["avg"], 1.5)
        self.assertEqual(detail["summary"]["issues"], 2)
        # Invalid input is refused.
        self.assertEqual(self.call(f"/api/rides/{rid}/rating", {"by": "rider", "stars": 5})[0], 400)
        self.assertEqual(self.call(f"/api/rides/{rid}/rating", {"by": "driver", "stars": 9})[0], 400)
        self.assertEqual(self.call(f"/api/rides/{rid}/rating", {"by": "driver", "stars": "bad"})[0], 400)
        self.assertEqual(self.call("/api/rides/nope/rating", {"by": "driver", "stars": 5})[0], 404)

    def test_ride_rated_event_is_pushed(self):
        rid = self.new_ride()
        cursor = self.call("/api/events?since=0&wait=0")[1]["cursor"]
        self.call(f"/api/rides/{rid}/rating", {"by": "driver", "by_name": "Sam", "stars": 5})
        s, j = self.call(f"/api/events?since={cursor}&wait=0&ride={rid}")
        self.assertIn("ride_rated", [e["type"] for e in j["events"]])

    # ---- Plain-text log export ----
    def test_export_log_covers_a_period_and_includes_every_ride(self):
        ids = [self.new_ride({"rider_name": "Log%d" % n, "device": {"platform": "Exporter%d" % n}})
               for n in range(3)]
        s, text, ctype = self.call_text("/api/dispatch/export")
        self.assertEqual(s, 200)
        self.assertIn("text/plain", ctype)
        self.assertIn("NightRider ride log", text)
        self.assertIn("Period:    all rides", text)
        for i in ids:
            self.assertIn(i, text)
        for n in range(3):
            self.assertIn("NR-", text)
            self.assertIn("Log%d" % n, text)
        self.assertIn("Status:   requested", text)
        # A window with no rides is empty but still a valid log.
        s, text, ctype = self.call_text("/api/dispatch/export?from=2100-01-01&to=2100-01-02")
        self.assertEqual(s, 200)
        self.assertIn("Rides:     0", text)
        self.assertIn("No rides in this period.", text)
        # A date-only period includes all of that day.
        today = __import__("datetime").date.today().isoformat()
        s, text, ctype = self.call_text("/api/dispatch/export?from=" + today + "&to=" + today)
        for i in ids:
            self.assertIn(i, text)
        self.assertEqual(self.call_text("/api/dispatch/export")[0], 200)

    def test_export_log_records_the_acknowledgement_and_rating(self):
        rid = self.new_ride({"rider_name": "Audit", "device": {"platform": "Audit1"}})
        self.call(f"/api/dispatch/rides/{rid}/ack", {"by": "Alex"})
        self.call(f"/api/rides/{rid}/rating", {"by": "dispatch", "stars": 1, "issues": ["unreachable"]})
        text = self.call_text("/api/dispatch/export")[1]
        block = [b for b in text.split("-" * 68) if rid in b][0]
        self.assertIn("dispatch ack", block)
        self.assertIn("by Alex", block)
        self.assertIn("dispatch 1/5", block)
        self.assertIn("issues: unreachable", block)


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
