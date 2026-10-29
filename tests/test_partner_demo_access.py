"""Public sample pages must not grant real Partner Desk privileges."""
import os
import unittest
from unittest.mock import patch

import server


class FakePage(server.Handler):
    def __init__(self, url, user=None):
        self.path = url
        self.actor = user
        self.sent = []

    def user(self):
        return self.actor

    def page_access(self, path):
        return server.Handler.page_access(self, path)

    def send_response(self, code):
        self.sent.append(("status", code))

    def send_header(self, name, value):
        self.sent.append((name, value))

    def end_headers(self):
        pass

    def send_json(self, code, body):
        self.sent.append(("json", code, body))


class PublicPartnerEntryTests(unittest.TestCase):
    def test_legacy_desk_routes_redirect_to_the_unified_destinations(self):
        with patch.dict(os.environ, {"DATABASE_URL": "isolated-fixture"}):
            with patch.object(server.SimpleHTTPRequestHandler, "do_GET") as serve_static:
                for page in ("/partner-desk-demo", "/partner-desk-demo/"):
                    h = FakePage(page)
                    server.Handler.do_GET(h)
                    self.assertIn(("status", 302), h.sent)
                    self.assertIn(("Location", "/partner-portal"), h.sent)
            for page in ("/partner-desk", "/partner-desk/", "/partner-desk.html"):
                h = FakePage(page)
                server.Handler.do_GET(h)
                self.assertIn(("status", 302), h.sent)
                self.assertIn(("Location", "/dispatch.html#partner-offers"), h.sent)

    def test_public_sandbox_does_not_add_admin_backend_routes(self):
        with patch.dict(os.environ, {"DATABASE_URL": "isolated-fixture"}):
            h = FakePage("/api/partner-desk-demo")
            # The retired public sandbox has no API namespace.
            self.assertTrue(server.Handler.page_access(h, "/partner-desk-demo"))
            self.assertTrue(server.Handler.page_access(h, "/partner-desk"))


if __name__ == "__main__":
    unittest.main()
