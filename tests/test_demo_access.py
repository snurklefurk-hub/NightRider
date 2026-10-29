"""Demo sign-in, persistent permission boundaries, and simulated booking checks.

The account queries execute against an in-memory SQLite fixture; no production
connection, file-backed ride store, or externally running service is used.
"""
import http.cookiejar
import json
import os
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import auth
import server


class AccountFixture:
    """Execute the small shared SQL subset while adapting Postgres syntax."""
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        self.db.rollback() if error else self.db.commit()
        return False

    def execute(self, statement, args=()):
        statement = statement.replace("%s", "?").replace(" FOR UPDATE", "")
        if "ADD COLUMN IF NOT EXISTS is_demo" in statement:
            columns = [row[1] for row in self.db.execute("PRAGMA table_info(nr_users)")]
            if "is_demo" in columns:
                return self.db.execute("SELECT 1")
            statement = statement.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")
        return self.db.execute(statement, args)


class DemoAccessTests(unittest.TestCase):
    def setUp(self):
        self.accounts = AccountFixture()
        self.connect_patch = patch.object(auth, "_connect", return_value=self.accounts)
        self.connect_patch.start()
        auth.initialize()
        auth.ensure_demo_users()
        self.store_patch = patch.object(server, "STORE", server.ensure_store({"rides": {}}))
        self.store_patch.start()
        self.save_patch = patch.object(server, "save")
        self.save = self.save_patch.start()
        self.env_patch = patch.dict(os.environ, {"DATABASE_URL": "isolated-in-memory-fixture",
                                                "NIGHTRIDER_COOKIE_SECURE": "false"})
        self.env_patch.start()
        server.LOGIN_FAILURES.clear()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.env_patch.stop()
        self.save_patch.stop()
        self.store_patch.stop()
        self.connect_patch.stop()
        self.accounts.db.close()

    def call(self, path, body=None, headers=None):
        request = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            response = self.browser.open(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def login(self, role):
        code, response = self.call("/api/auth/login", {"username": "DEMO", "password": "PASSWORD", "demo_role": role})
        self.assertEqual(code, 200, response)
        self.assertTrue(response["user"]["is_demo"])
        self.assertEqual(response["user"]["role"], role)
        self.assertFalse(response["user"]["dispatch_admin"])
        return response["user"]

    def test_all_three_demo_roles_use_distinct_persistent_accounts(self):
        identities = [self.login(role)["id"] for role in ("rider", "driver", "dispatch")]
        self.assertEqual(len(set(identities)), 3)
        self.assertEqual(self.call("/api/auth/me")[1]["user"]["id"], identities[-1])
        before = self.accounts.db.execute("SELECT id,password_hash FROM nr_users ORDER BY id").fetchall()
        auth.ensure_demo_users()
        after = self.accounts.db.execute("SELECT id,password_hash FROM nr_users ORDER BY id").fetchall()
        self.assertEqual(before, after, "restarting must not replace account IDs or passwords")

    def test_demo_seeding_never_adopts_an_unrelated_existing_account(self):
        other = AccountFixture()
        with patch.object(auth, "_connect", return_value=other):
            auth.initialize()
            user, error = auth.create_user(auth.DEMO_ACCOUNTS["rider"]["username"], "Unrelated", "private-password", "rider")
            self.assertIsNone(error)
            with self.assertRaises(RuntimeError):
                auth.ensure_demo_users()
            self.assertFalse(auth.authenticate(user["username"], "private-password")["is_demo"])
            self.assertIsNone(auth.authenticate_demo("rider", "private-password"))
        other.db.close()

    def test_demo_dispatch_does_not_claim_bootstrap_admin_even_when_created_first(self):
        self.assertFalse(auth.has_dispatch_user())
        admin, error = auth.create_user("original-owner", "Owner", "owner-password", "dispatch")
        self.assertIsNone(error)
        self.assertTrue(auth.has_dispatch_user())
        self.assertTrue(auth.authenticate("original-owner", "owner-password")["dispatch_admin"])
        self.login("dispatch")
        self.assertFalse(self.call("/api/auth/me")[1]["user"]["dispatch_admin"])
        token = auth.create_session(admin["id"])
        self.assertTrue(auth.get_session(token)["dispatch_admin"])

    def test_android_existing_demo_login_selects_driver_without_api_change(self):
        code, response = self.call("/api/auth/login", {"username": "DEMO", "password": "PASSWORD"},
                                   {"X-NightRider-Client": "android"})
        self.assertEqual(code, 200)
        self.assertEqual(response["user"]["role"], "driver")
        self.assertTrue(response["token"])

    def test_registration_is_paused_and_bad_demo_credentials_fail(self):
        count = self.accounts.db.execute("SELECT COUNT(*) FROM nr_users").fetchone()[0]
        self.assertEqual(self.call("/api/auth/register", {"username": "newrider", "display_name": "New", "password": "long-password"})[0], 403)
        self.assertEqual(self.accounts.db.execute("SELECT COUNT(*) FROM nr_users").fetchone()[0], count)
        for role, password in (("admin", "PASSWORD"), ("rider", "wrong-password"), (None, "PASSWORD")):
            self.assertEqual(self.call("/api/auth/login", {"username": "DEMO", "password": password, "demo_role": role})[0], 401)

    def test_demo_account_management_is_denied_before_any_mutation(self):
        self.login("dispatch")
        before = self.accounts.db.execute("SELECT * FROM nr_users ORDER BY id").fetchall()
        for path in ("/api/dispatch/users", "/api/dispatch/users/target", "/api/dispatch/users/target/password",
                     "/api/dispatch/users/target/delete", "/api/dispatch/staff", "/api/dispatch/staff/target/enabled",
                     "/api/dispatch/staff/target/password", "/api/dispatch/staff/target/sessions",
                     "/api/dispatch/account-deletion", "/api/dispatch/pricing", "/api/dispatch/future-destructive-operation"):
            with self.subTest(path=path):
                self.assertEqual(self.call(path, {"password": "changed-password", "enabled": False})[0], 403)
        for path in ("/api/dispatch/staff", "/api/dispatch/account-archive?role=rider&id=target"):
            self.assertEqual(self.call(path)[0], 403)
        self.assertEqual(self.accounts.db.execute("SELECT * FROM nr_users ORDER BY id").fetchall(), before)
        self.save.assert_not_called()
        for role in ("rider", "driver", "dispatch"):
            self.login(role)
            self.assertEqual(self.call("/api/auth/change-password", {"current_password": "PASSWORD", "new_password": "changed-password"})[0], 403)

    def test_real_admin_keeps_account_management_and_demo_targets_are_protected(self):
        admin, _ = auth.create_user("owner", "Owner", "owner-password", "dispatch")
        self.assertEqual(self.call("/api/auth/login", {"username": "owner", "password": "owner-password"})[0], 200)
        self.assertEqual(self.call("/api/dispatch/users", {"username": "new-driver", "display_name": "New Driver", "password": "new-password"})[0], 201)
        self.assertEqual(self.call("/api/dispatch/staff")[0], 200)
        demo_driver = auth.authenticate_demo("driver", "PASSWORD")
        self.assertFalse(auth.change_password(demo_driver["id"], "changed-password"))
        self.assertFalse(auth.delete_driver_user(demo_driver["id"]))
        self.assertFalse(auth.set_user_enabled(demo_driver["id"], False))
        self.assertTrue(auth.get_session(auth.create_session(admin["id"]))["dispatch_admin"])

    def test_shared_booking_assignment_chat_and_completion_are_simulations(self):
        rider = self.login("rider")
        code, ride = self.call("/api/rides", {"pickup": "Practice A", "dropoff": "Practice B", "distance_mi": 2,
                                             "simulated": False, "transportation_service": True, "payment_method": "Charge my card"})
        self.assertEqual(code, 201)
        self.assertTrue(ride["simulated"])
        self.assertFalse(ride["transportation_service"])
        self.assertEqual(ride["payment_method"], "Simulation only — no payment collected")
        ride_id = ride["id"]
        driver = auth.authenticate_demo("driver", "PASSWORD")
        self.login("dispatch")
        self.assertEqual(self.call("/api/dispatch/rides/" + ride_id + "/assign", {"driver_account_id": driver["id"]})[0], 200)
        self.assertEqual(self.call("/api/chat/messages", {"account_chat": True, "rider_account_id": rider["id"], "text": "Practice account note"})[0], 201)
        self.login("driver")
        self.assertEqual(self.call("/api/chat/messages", {"account_chat": True, "rider_account_id": rider["id"], "text": "Forbidden"})[0], 403)
        self.assertEqual(self.call("/api/chat/messages", {"ride_id": ride_id, "text": "Practice trip note"})[0], 201)
        for _ in range(5):
            code, ride = self.call("/api/rides/" + ride_id + "/advance", {})
            self.assertEqual(code, 200)
        self.assertEqual(ride["status"], "completed")
        self.assertTrue(ride["simulated"])

    def test_existing_rider_bookings_are_also_simulated_and_health_is_public(self):
        auth.create_user("existing-rider", "Existing", "existing-password", "rider")
        self.assertEqual(self.call("/api/auth/login", {"username": "existing-rider", "password": "existing-password"})[0], 200)
        code, ride = self.call("/api/rides", {"pickup": "A", "dropoff": "B", "distance_mi": 2})
        self.assertEqual(code, 201)
        self.assertTrue(ride["simulated"])
        self.assertEqual(self.call("/api/config")[1]["transportationServicesOffered"], False)
        with patch.object(auth, "database_healthy", return_value=True):
            self.assertEqual(self.call("/healthz")[0], 200)


if __name__ == "__main__":
    unittest.main()
