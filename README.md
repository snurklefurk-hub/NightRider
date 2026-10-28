# NightRider

NightRider is a pilot ride dispatch service. Riders request trips on the website, dispatch assigns them, and drivers use either the driver webpage or the separate Android app. All three roles sign in with NightRider accounts.

## Light and Dark appearance

A single site-wide **LIGHT / DARK** control appears in Rider, Dispatch, the
Driver Board, Account and Web Map Lab. **LIGHT** uses the Frutiger Aero-inspired
sky-blue glass UI, a rounded Nunito Sans font (with system fallbacks) and the
NightRider Midnight vector basemap. **DARK** uses the original NightRider
Verdant UI and OpenFreeMap Original Dark vector basemap. DARK is the default.
Switching appearance updates the map without a separate map-style button.
The choice is saved in the browser under
`localStorage["nightrider.ui-theme.v1"]`; existing Aero users retain LIGHT.
On unsupported WebGL devices, the existing raster fallback remains available.

Android Driver exposes LIGHT and DARK under Settings → Appearance. Its
standalone Map Lab test app uses the same two combined settings. Android
preferences are device-local and do not synchronize with browsers.

## Current pages

- `/` — rider booking, fare estimate, ride status, location sharing, chat, and driver rating.
- `/dispatch.html` — live ride board, map, chat, driver and rider accounts, ride rates, counts, and log export. A dispatch account is required.
- `/driver.html` — browser driver board for rides and chat. A driver account is required.
- `/account.html` — sign-in and rider registration.
- `/map-lab.html` — vector-map preview and local Android Field Test CSV review, with GPS quality and motion diagnostics; it does not change rides.

The Rider and Dispatch maps automatically match the site-wide LIGHT/DARK setting. Their Leaflet controls and ride markers remain in place, with a raster fallback if vector rendering fails. See [MAP-APPEARANCE.md](MAP-APPEARANCE.md) and [MAP-LAB.md](MAP-LAB.md) for the map setup and preview.

## Messaging

Rider messages always go to Dispatch and the assigned driver. Driver and Dispatch use fixed recipient tabs for Team, private and ride conversations. Shared ride history follows the ride when reassigned. The safety and privacy contract is in [CHAT-POLICY.md](CHAT-POLICY.md).

## Deployment and data

The live site is hosted on Render using [render.yaml](render.yaml). Production requires PostgreSQL through `DATABASE_URL`; account and session records are in separate tables, while rides, messages, ratings, and presence are kept in one JSON state record. Keep the web service at one instance until that state store supports concurrent writers.

The current free-tier setup is for testing. See [DEPLOY.md](DEPLOY.md) for Render settings and [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md) for account setup and recovery. Do not commit passwords, setup tokens, or database URLs.

## Local development

Install the dependency with `pip install -r requirements.txt`, then run `NIGHTRIDER_REQUIRE_DATABASE=false python server.py` in a local shell. That mode uses a local JSON file and does not provide account protection; it must stay on a developer machine. To test the real sign-in flow, use a development PostgreSQL database and the settings in [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md).

The frontend is plain HTML, CSS, and JavaScript in `public/`; the Python HTTP server is `server.py`, with account storage in `auth.py`. The Android driver app lives in the separate `nightrider-driver-android` repository.

## Checks

The map, trace-import and appearance tests run with `node --test tests/*.test.cjs` (the map CI also checks its pinned browser assets). For Python dispatch-map, rider-location and fare checks, set `NIGHTRIDER_REQUIRE_DATABASE=false` and run `python -m unittest discover -s tests -p 'test_*.py' -v`. For the Dispatch private-message notification test, run `node tests/client_notify_check.js`.

GitHub Actions runs these backend/Dispatch tests on relevant changes through `.github/workflows/backend-check.yml`, isolated from production and without Render database credentials. The pre-account anonymous-ride API suite was retired when sign-in became mandatory; full authenticated booking-to-completion integration tests are still needed. Successful source checks are not equivalent to testing real rides on devices.
