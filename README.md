# NightRider

NightRider is a pilot ride dispatch service. Riders request trips on the website, dispatch assigns them, and drivers use either the driver webpage or the separate Android app. All three roles sign in with NightRider accounts.

## Current pages

- `/` — rider booking, fare estimate, ride status, location sharing, chat, and driver rating.
- `/dispatch.html` — live ride board, map, chat, driver and rider accounts, ride rates, counts, and log export. A dispatch account is required.
- `/driver.html` — browser driver board for rides and chat. A driver account is required.
- `/account.html` — sign-in and rider registration.
- `/map-lab.html` — separate vector-map preview for appearance testing; it does not change rides.

The rider and dispatch maps offer **Light** (NightRider Midnight) and **Dark** (Original Dark) vector basemaps. Their Leaflet controls and ride markers remain in place, with a raster fallback if vector rendering fails. See [MAP-APPEARANCE.md](MAP-APPEARANCE.md) and [MAP-LAB.md](MAP-LAB.md) for the map setup and preview.

## Deployment and data

The live site is hosted on Render using [render.yaml](render.yaml). Production requires PostgreSQL through `DATABASE_URL`; account and session records are in separate tables, while rides, messages, ratings, and presence are kept in one JSON state record. Keep the web service at one instance until that state store supports concurrent writers.

The current free-tier setup is for testing. See [DEPLOY.md](DEPLOY.md) for Render settings and [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md) for account setup and recovery. Do not commit passwords, setup tokens, or database URLs.

## Local development

Install the dependency with `pip install -r requirements.txt`, then run `NIGHTRIDER_REQUIRE_DATABASE=false python server.py` in a local shell. That mode uses a local JSON file and does not provide account protection; it must stay on a developer machine. To test the real sign-in flow, use a development PostgreSQL database and the settings in [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md).

The frontend is plain HTML, CSS, and JavaScript in `public/`; the Python HTTP server is `server.py`, with account storage in `auth.py`. The Android driver app lives in the separate `nightrider-driver-android` repository.

## Checks

The map appearance tests run with `node --test tests/map_lab.test.cjs tests/map_mode.test.cjs`. For the local Python dispatch-map and pricing checks, set `NIGHTRIDER_REQUIRE_DATABASE=false` and run `python -m unittest discover -s tests`. The old anonymous-ride API suite was retired when account sign-in became mandatory; protected ride flows still need a dedicated integration suite. A source check does not replace a live ride test on a phone.
