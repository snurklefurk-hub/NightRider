"""Affiliate-preview security and state transitions, isolated from production."""
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import partner_desk as desk
import server


class FakeHandler:
    def __init__(self, user=None, token=""):
        self._user = user
        self.headers = {"X-NR-Partner-Token": token}
        self.result = None
        self.headers_sent = []

    def send_response(self, code):
        self.result = (code, {})

    def send_header(self, key, value):
        self.headers_sent.append((key, value))

    def end_headers(self):
        pass

    def user(self):
        return self._user

    def require_role(self, *roles):
        if not self._user or self._user.get("role") not in roles:
            self.send_json(401 if not self._user else 403, {"error": "not allowed"})
            return None
        return self._user

    def send_json(self, code, payload):
        self.result = (code, payload)
        return self.result


ADMIN = {"id": "owner", "role": "dispatch", "dispatch_admin": True, "is_demo": False}
STAFF = {"id": "staff", "role": "dispatch", "dispatch_admin": False, "is_demo": False}
DEMO = {"id": "demo", "role": "dispatch", "dispatch_admin": False, "is_demo": True}


class PartnerDomainTests(unittest.TestCase):
    def setUp(self):
        self.store = server.ensure_store({"rides": {}})
        self.lock = threading.Lock()
        self.saved = []
        self.save = lambda data: self.saved.append(True)
        self.env = patch.dict("os.environ", {"DATABASE_URL": "isolated-fixture"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def post(self, path, data, user=None, token=""):
        h = FakeHandler(user, token)
        desk.api_post(h, self.store, self.lock, self.save, path, data)
        return h.result

    def get(self, path, user=None, token=""):
        h = FakeHandler(user, token)
        desk.api_get(h, self.store, self.lock, path)
        return h.result

    def partner(self, name="Coastal Transport"):
        status, data = self.post("/api/partner-desk/partners",
                                 {"name": name, "contact": "Operations"}, ADMIN)
        self.assertEqual(status, 201)
        return data["partner"], data["access_token_once"]

    def payload(self, ref="JOB-102"):
        when = datetime.fromtimestamp(desk.time.time() + 3600, timezone.utc).isoformat()
        return {"reference": ref, "pickup": "Hotel main entrance", "dropoff": "Coligny Beach",
                "pickup_at": when, "passengers": 2, "bags": 1, "payout": 42.5,
                "notes": "Please check in at desk", "authorized": True,
                "service_class": "SUV"}  # The server ignores partner vehicle preferences.

    def test_partner_tokens_only_visible_once_and_can_be_revoked(self):
        partner, token = self.partner()
        self.assertNotIn(token, repr(self.store))
        self.assertTrue(desk.authenticate(self.store, token))
        self.assertEqual(self.get("/api/affiliate-hub", token=token)[0], 200)
        self.assertEqual(self.get("/api/affiliate-hub", token="invalid")[0], 401)
        status, result = self.post("/api/partner-desk/partners/" + partner["id"] + "/rotate", {}, ADMIN)
        self.assertEqual(status, 200)
        self.assertIsNone(desk.authenticate(self.store, token))
        new_token = result["access_token_once"]
        self.assertTrue(desk.authenticate(self.store, new_token))
        self.assertEqual(self.post("/api/partner-desk/partners/" + partner["id"] + "/enabled",
                                   {"enabled": False}, ADMIN)[0], 200)
        self.assertEqual(self.get("/api/affiliate-hub", token=new_token)[0], 401)

    def test_demo_staff_and_rider_cannot_create_partner_or_review_offers(self):
        path = "/api/partner-desk/partners"
        for user in (None, DEMO, STAFF, {"id": "rider", "role": "rider"}):
            self.assertIn(self.post(path, {"name": "Bad actor"}, user)[0], (401, 403))
            self.assertIn(self.get("/api/partner-desk", user)[0], (401, 403))
        self.assertFalse(self.store["affiliate_partners"])
        self.assertFalse(self.store["affiliate_offers"])

    def test_valid_offer_and_double_confirmation_are_rejected(self):
        partner, token = self.partner()
        status, data = self.post("/api/affiliate-hub/offers", self.payload(), token=token)
        self.assertEqual(status, 201)
        offer = data["offer"]
        self.assertEqual(offer["status"], "submitted")
        self.assertNotIn("service_class", offer)
        self.assertEqual(self.store["rides"], {})
        self.assertEqual(self.post("/api/affiliate-hub/offers", self.payload(), token=token)[0], 409)
        self.assertEqual(self.post("/api/partner-desk/offers/" + offer["id"] + "/accept",
                                   {"revision": 1}, ADMIN)[1]["offer"]["status"], "awaiting_partner")
        self.assertEqual(self.post("/api/partner-desk/offers/" + offer["id"] + "/accept",
                                   {"revision": 1}, ADMIN)[0], 409)
        status, data = self.post("/api/affiliate-hub/offers/" + offer["id"] + "/confirm",
                                 {"revision": 2}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(data["offer"]["status"], "agreed_preview")
        self.assertEqual(self.store["rides"], {})
        self.assertEqual(self.post("/api/affiliate-hub/offers/" + offer["id"] + "/confirm",
                                   {"revision": 3}, token=token)[0], 409)

    def test_partner_cannot_view_or_change_another_partner_offer(self):
        _, first_token = self.partner("First Company")
        _, second_token = self.partner("Second Company")
        offer = self.post("/api/affiliate-hub/offers", self.payload(), token=first_token)[1]["offer"]
        self.assertFalse(self.get("/api/affiliate-hub", token=second_token)[1]["offers"])
        self.assertEqual(self.post("/api/affiliate-hub/offers/" + offer["id"] + "/withdraw",
                                   {"revision": 1}, token=second_token)[0], 404)
        self.assertEqual(self.post("/api/affiliate-hub/offers/" + offer["id"] + "/withdraw",
                                   {"revision": 1}, token=first_token)[0], 200)

    def test_authorization_capacity_time_and_price_validation(self):
        _, token = self.partner()
        for update in ({"authorized": False}, {"passengers": 5}, {"bags": 6},
                       {"payout": float("nan")}, {"payout": -5}, {"pickup_at": "tomorrow"},
                       {"pickup_at": datetime.now().isoformat()}):
            with self.subTest(update=update):
                status, _ = self.post("/api/affiliate-hub/offers", dict(self.payload(), **update), token=token)
                self.assertIn(status, (400, 403, 422))
        self.assertFalse(self.store["affiliate_offers"])

    def test_acceptance_deadline_and_expired_confirmation(self):
        _, token = self.partner()
        offer = self.post("/api/affiliate-hub/offers", self.payload(), token=token)[1]["offer"]
        accepted = self.post("/api/partner-desk/offers/" + offer["id"] + "/accept", {"revision": 1}, ADMIN)[1]["offer"]
        with patch.object(desk.time, "time", return_value=accepted["confirmation_due_at"] + 2):
            visible = self.get("/api/affiliate-hub", token=token)[1]["offers"][0]
            self.assertEqual(visible["status"], "expired")
            status, _ = self.post("/api/affiliate-hub/offers/" + offer["id"] + "/confirm",
                                  {"revision": 2}, token=token)
        self.assertEqual(status, 410)
        self.assertEqual(self.store["affiliate_offers"][offer["id"]]["status"], "expired")
        self.assertTrue(self.saved)

    def test_partner_desk_page_is_admin_only_and_hub_links_exist(self):
        from pathlib import Path
        html = (Path(__file__).resolve().parents[1] / "public" / "hub.html").read_text()
        self.assertIn('href="/partner-desk-demo"', html)
        self.assertIn('href="/affiliate-hub?demo=1"', html)
        for page in ("/partner-desk", "/partner-desk/", "/partner-desk.html"):
            for user in (None, STAFF, DEMO):
                h = FakeHandler(user)
                self.assertFalse(server.Handler.page_access(h, page))
            h = FakeHandler(ADMIN)
            self.assertTrue(server.Handler.page_access(h, page))


if __name__ == "__main__":
    unittest.main()
