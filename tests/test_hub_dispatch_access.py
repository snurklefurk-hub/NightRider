"""Hub routing, Dispatch access boundaries and independent session tests."""
import os
import unittest
from unittest.mock import patch

import auth
import server


class FakeConnection:
    def __init__(self, existing=True):
        self.sql = []
        self.existing = existing

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, args=()):
        self.sql.append((sql, args))
        return self

    def fetchone(self):
        return ("staff",) if self.existing else None


def handler(path="/hub", user=None):
    obj = object.__new__(server.Handler)
    obj.path = path
    obj.headers = {}
    obj.sent = []
    obj.user = lambda: user
    obj.send_response = lambda code: obj.sent.append(("status", code))
    obj.send_header = lambda key, value: obj.sent.append((key, value))
    obj.end_headers = lambda: None
    obj.send_json = lambda code, payload: obj.sent.append(("json", code, payload))
    return obj


class HubAccessTests(unittest.TestCase):
    def test_root_routes_to_hub_and_query_links_stay_rider_direct(self):
        for url, expected in (("/", "/hub"),
                              ("/?source=card", "/rider?source=card")):
            h = handler(url)
            server.Handler.do_GET(h)
            self.assertIn(("status", 302), h.sent)
            self.assertIn(("Location", expected), h.sent)

    def test_hub_is_public_and_rider_is_protected(self):
        with patch.dict(os.environ, {"DATABASE_URL": "test"}):
            h = handler("/rider", None)
            self.assertFalse(server.Handler.page_access(h, "/rider"))
            self.assertIn(("status", 302), h.sent)
            self.assertIn(("Location", "/account.html?next=/rider"), h.sent)
            h = handler("/hub", None)
            self.assertTrue(server.Handler.page_access(h, "/hub"))
            h = handler("/rider", {"role": "rider"})
            self.assertTrue(server.Handler.page_access(h, "/rider"))

    def test_short_routes_serve_the_expected_static_files(self):
        with patch.object(server.SimpleHTTPRequestHandler, "do_GET") as base:
            h = handler("/hub")
            server.Handler.do_GET(h)
            self.assertEqual(h.path, "/hub.html")
            self.assertEqual(base.call_count, 1)
        with patch.object(server.SimpleHTTPRequestHandler, "do_GET") as base:
            h = handler("/rider")
            server.Handler.do_GET(h)
            self.assertEqual(h.path, "/index.html")
            self.assertEqual(base.call_count, 1)


class StaffAccessTests(unittest.TestCase):
    def test_non_admin_cannot_list_staff_accounts(self):
        h = handler(user={"role": "dispatch", "id": "nonowner",
                          "dispatch_admin": False})
        server.Handler.dispatch_get(h, "/api/dispatch/staff", {})
        self.assertEqual(h.sent[-1][1], 403)

    def test_first_dispatch_admin_can_list_staff_and_owner_is_marked(self):
        h = handler(user={"role": "dispatch", "id": "owner",
                          "dispatch_admin": True})
        staff = [
            {"id": "new", "created_at": 20, "role": "dispatch"},
            {"id": "owner", "created_at": 10, "role": "dispatch"},
        ]
        with patch.object(auth, "list_users", return_value=staff):
            server.Handler.dispatch_get(h, "/api/dispatch/staff", {})
        self.assertEqual(h.sent[-1][1], 200)
        self.assertTrue(h.sent[-1][2]["users"][1]["dispatch_admin"])
        self.assertFalse(h.sent[-1][2]["users"][0]["dispatch_admin"])

    def test_staff_change_refuses_protected_owner(self):
        connection = FakeConnection(existing=False)
        with patch.object(auth, "_connect", return_value=connection):
            self.assertFalse(auth.manage_dispatch_staff("original", "enabled", False))
        self.assertEqual(len(connection.sql), 1)
        self.assertIn("id<>(SELECT id", connection.sql[0][0])

    def test_disabling_staff_revokes_all_their_sessions(self):
        connection = FakeConnection(existing=True)
        with patch.object(auth, "_connect", return_value=connection):
            self.assertTrue(auth.manage_dispatch_staff("staff1", "enabled", False))
        self.assertTrue(any("UPDATE nr_users SET enabled" in sql
                            for sql, _ in connection.sql))
        self.assertTrue(any("DELETE FROM nr_sessions WHERE user_id" in sql
                            for sql, _ in connection.sql))

    def test_each_login_creates_a_new_session_without_replacing_others(self):
        connection = FakeConnection()
        with patch.object(auth, "_connect", return_value=connection):
            token_a = auth.create_session("dispatcher")
            token_b = auth.create_session("dispatcher")
            self.assertNotEqual(token_a, token_b)
            auth.delete_session(token_a)
        inserts = [args for sql, args in connection.sql if "INSERT INTO nr_sessions" in sql]
        self.assertEqual(len(inserts), 2)
        self.assertEqual(inserts[0][1], "dispatcher")
        self.assertEqual(inserts[1][1], "dispatcher")
        deletes = [(sql, args) for sql, args in connection.sql
                   if "DELETE FROM nr_sessions" in sql]
        self.assertEqual(len([sql for sql, _ in deletes if "WHERE token_hash" in sql]), 1)
        self.assertFalse(any("WHERE user_id" in sql for sql, _ in deletes))


if __name__ == "__main__":
    unittest.main()
