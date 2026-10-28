# NightRider

NightRider is a pilot ride dispatch service. Riders request trips on the website, dispatch assigns them, and drivers use either the driver webpage or the separate Android app. All three roles sign in with NightRider accounts.

## The NightRider three-test commit rule

**Before EVERY commit, ask all three questions:**

1. **Does it make delivering a professional ride easier or safer?**
2. **Does it improve the driver's profitability, independence, or ability to retain customers?**
3. **Does it make a customer's experience more dependable, transparent, or trustworthy?**

If a change does not pass at least one of these, **do not commit it**, unless the product owner explicitly approves that specific change with **MAKE IT SO**. This applies to every agent and every subsystem, including infrastructure and maintenance. See [AGENTS.md](AGENTS.md) for the full decision rule.

**Owner-only override:** The product owner can say **MAKE IT SO** for one specific change, even if it fails all three value tests. Record the authorization and exact scope in the PR; use a commit footer like `NR-Override: MAKE IT SO - Implement the specifically requested experiment.` The exception does **not** waive security, privacy, driver safety, testing, or merge/release controls. The CI validates the footer's syntax, while the integration owner verifies that authorization came from the product owner. See [AGENTS.md](AGENTS.md).

Every standard commit needs a real `NR-Value:` trailer, such as `NR-Value: safety - Prevents unreliable GPS fixes from moving the navigation marker.` The `NightRider commit value gate` workflow checks every commit message in new PRs; it cannot judge whether the claimed benefit is true, so the integration owner must still review it. To enable the automatic *local, before-commit* question prompt in a Git clone, run `python3 scripts/setup_commit_gate.py` once. GitHub API commits bypass local hooks and must apply the questions before writing.

**Important:** The CI check reports violations, but it only becomes a mandatory GitHub merge blocker when branch protection/rulesets require `Require concrete benefit on every commit`. The repository's GitHub branch protection is not confirmed by this documentation.

## Working with multiple AI agents

NightRider's website/backend and Android app may be developed by independent AI agents at the same time. **Read [AGENTS.md](AGENTS.md) before changing code.** GitHub is the shared coordination hub; separate chat instances do not automatically share their plans or decisions.

- **Current work (live):** [Web/backend pull requests](https://github.com/snurklefurk-hub/NightRider/pulls) · [Android pull requests](https://github.com/snurklefurk-hub/nightrider-driver-android/pulls).
- **Announce work early:** Open a **draft pull request** on a dedicated branch so other agents can see scope, ownership and expected files.
- **Automatic coordination:** `.github/workflows/agent-coordination.yml` checks new PRs immediately using read-only access, flags overlapping source files in the same repo, and posts/refreshes cross-repo status comments through a trusted scheduled run every four hours (or a manual workflow run). It warns about other work; human review is still needed for cross-repo API/design conflicts.
- **Protected release process:** **WORK NR** is the default integration owner unless the product owner delegates it. Only that owner merges. A merge into web `main` may redeploy Render; a merge into Android `main` may publish a signed pilot APK. The bot **never** automatically merges or deploys anything.
- **Important:** Check current PRs instead of trusting a static status summary. A green overlap report is not a guarantee of compatible behavior. All relevant tests must pass before integration.

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

Ride messages from riders reach Dispatch and any assigned driver. A separate **account conversation** connects the rider and Dispatch even between trips (it is never visible to drivers). Dispatch can open these from recent ride tiles, the Rider tab, or the rider account directory; Text driver buttons on ride and driver tiles select the driver's private chat. These are browser/app messages, **not SMS**: an absent rider sees them next time they visit the site. The safety and privacy contract is in [CHAT-POLICY.md](CHAT-POLICY.md).

## Deployment and data

The live site is hosted on Render using [render.yaml](render.yaml). Production requires PostgreSQL through `DATABASE_URL`; account and session records are in separate tables, while rides, messages, ratings, and presence are kept in one JSON state record. Keep the web service at one instance until that state store supports concurrent writers.

The current free-tier setup is for testing. See [DEPLOY.md](DEPLOY.md) for Render settings and [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md) for account setup and recovery. Do not commit passwords, setup tokens, or database URLs.

## Local development

Install the dependency with `pip install -r requirements.txt`, then run `NIGHTRIDER_REQUIRE_DATABASE=false python server.py` in a local shell. That mode uses a local JSON file and does not provide account protection; it must stay on a developer machine. To test the real sign-in flow, use a development PostgreSQL database and the settings in [ACCOUNT-SETUP.md](ACCOUNT-SETUP.md).

The frontend is plain HTML, CSS, and JavaScript in `public/`; the Python HTTP server is `server.py`, with account storage in `auth.py`. The Android driver app lives in the separate `nightrider-driver-android` repository.

## Checks

The map, trace-import and appearance tests run with `node --test tests/*.test.cjs` (the map CI also checks its pinned browser assets). For Python dispatch-map, rider-location and fare checks, set `NIGHTRIDER_REQUIRE_DATABASE=false` and run `python -m unittest discover -s tests -p 'test_*.py' -v`. For the Dispatch private-message notification test, run `node tests/client_notify_check.js`.

GitHub Actions runs these backend/Dispatch tests on relevant changes through `.github/workflows/backend-check.yml`, isolated from production and without Render database credentials. The pre-account anonymous-ride API suite was retired when sign-in became mandatory; full authenticated booking-to-completion integration tests are still needed. Successful source checks are not equivalent to testing real rides on devices.
