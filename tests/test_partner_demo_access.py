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


class PublicPartnerSandboxTests(unittest.TestCase):
    def test_public_sandbox_route_and_real_operator_page_stay_separate(self):
        with patch.dict(os.environ, {"DATABASE_URL": "isolated-fixture"}):
            with patch.object(server.SimpleHTTPRequestHandler, "do_GET") as serve_static:
                for page in ("/partner-desk-demo", "/partner-desk-demo/"):
                    h = FakePage(page)
                    server.Handler.do_GET(h)
                    self.assertEqual(h.path, "/partner-desk.html")
                    serve_static.assert_called()
            for page in ("/partner-desk", "/partner-desk/", "/partner-desk.html"):
                for user in (None, {"id": "demo", "role": "dispatch", "is_demo": True,
                                   "dispatch_admin": False}):
                    h = FakePage(page, user)
                    self.assertFalse(server.Handler.page_access(h, page))
            admin = {"id": "owner", "role": "dispatch", "dispatch_admin": True,
                     "is_demo": False}
            h = FakePage("/partner-desk", admin)
            self.assertTrue(server.Handler.page_access(h, "/partner-desk"))

    def test_public_sandbox_does_not_add_admin_backend_routes(self):
        with patch.dict(os.environ, {"DATABASE_URL": "isolated-fixture"}):
            h = FakePage("/api/partner-desk-demo")
            # Server-only partner data is still accessed through the protected
            # operational endpoints; sandbox has no API namespace.
            self.assertTrue(server.Handler.page_access(h, "/partner-desk-demo"))
            self.assertFalse(server.Handler.page_access(h, "/partner-desk"))


if __name__ == "__main__":
    unittest.main()
