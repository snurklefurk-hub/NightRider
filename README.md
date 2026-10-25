# NightRider

A starter ride-hailing ecosystem for regional private drivers and small companies.

## Deploy
See **DEPLOY.md** and **ACCOUNT-SETUP.md** for the GitHub, Render, account, and database setup.

## Run
    pip install -r requirements.txt
    NIGHTRIDER_REQUIRE_DATABASE=false python3 server.py

The production service requires PostgreSQL through `DATABASE_URL`. The local-only
mode above is for development and does not enable accounts or protect API routes.
Do not expose it to the public internet.

## Pages
- `/` (index.html): Lyft-style rider page — full-screen map, pickup/drop-off address search, one fare estimate, request and live status.
- `/driver.html`: signed-in drivers accept open requests, advance their assigned rides through five stages, and rate riders.
- `/dispatch.html`: live dispatch board — see **Dispatch** below.
- `/account.html`: rider account creation and sign-in. Dispatch creates driver accounts.

## API
- GET /api/rides, GET /api/rides/{id}
- POST /api/auth/register, /api/auth/login, /api/auth/logout, /api/auth/change-password
- POST /api/auth/setup-dispatch  one-time first-dispatch setup using `NIGHTRIDER_SETUP_TOKEN`
- POST /api/rides  {payment_method, pickup, dropoff, distance_mi, pickup_coords?, driver_to_pickup_mi?}
- POST /api/rides/{id}/accept  {driver_coords?}
- POST /api/rides/{id}/advance  moves the ride to its next stage (accepted → to_pickup → at_pickup → to_dropoff → at_dropoff → completed)
- POST /api/rides/{id}/cancel
- GET /api/events?since=&ride=&wait=  long-poll event stream (rider screens)
- POST /api/rides/{id}/rating  {by: "driver"|"dispatch", stars, issues?, note?}

- POST /api/drivers/ping  {name, status?, coords?}  driver presence heartbeat
- GET /api/drivers/{name}/messages?since=  shared conversation as this driver sees it
- POST /api/drivers/{name}/message  {text, private?}  driver text (group, or private to dispatch)

Dispatch routes:
- GET /api/dispatch/rides, GET /api/dispatch/riders
- GET /api/dispatch/drivers  active + known drivers (last_seen, status, idle seconds)
- GET /api/dispatch/events?since=&wait=  (wakes the instant a ride is requested)
- POST /api/dispatch/rides/{id}/ack  {by}  acknowledgment handshake
- GET /api/dispatch/messages?since=  shared conversation as dispatch sees it
- POST /api/dispatch/message  {text, to}  dispatch text; to="all" is a group text, to=<name> is private
- POST /api/dispatch/drivers/{name}/message  {text}  alias: private dispatch → driver text (kept for compatibility)
- GET /api/dispatch/export?from=&to=  plain-text ride log

## Dispatch: push, not polling
The dispatch board no longer polls on a timer. It holds one long-lived request open on
`/api/dispatch/events`; the server wakes it the moment a rider requests a ride. Each incoming
request is acknowledged back to the rider (`ride_acknowledged`) so the rider's screen can show
"dispatch received your request" — a handshake that nothing was dropped. There is also a **Force
refresh** button, and the board shows the five most recent rides plus a small counts strip at the
bottom. Each ride card shows its current stage label and how long the ride has spent in each stage,
and the driver's status follows the same stage labels. Event state is in memory only, so it resets when the server restarts; rides themselves
persist to `rides.json`.

## Active drivers and one shared conversation
The driver page sends a heartbeat to `/api/drivers/ping` every 30 seconds. Any driver seen within
the last 90 seconds is listed as **active** on the dispatch board (with its status and how long ago
it checked in); older ones drop to **idle**.

Texting is one persistent **Team text** card, not a control on each driver row. Both the dispatch
page and the driver page show the same conversation and poll it every few seconds:

- **Group (default).** Every text is visible to dispatch and all drivers. Dispatch sends to
  **Everyone (group)**; a driver just sends normally.
- **Private.** Dispatch picks a driver in the **To** menu, or a driver ticks **Private to
  dispatch**, to send a note only those two can see. Private texts still appear in the same window
  and are colour-coded amber with a **private** tag, so they are never confused with the group
  thread. The server filters private texts out of any other driver's view.

Messages are kept in memory with the rest of the event state, so they clear on a server restart.

When a driver's text is waiting, dispatch flags it three ways: the **Team text** card pulses, the
card header shows the first 25 characters of the newest waiting text, and a quiet cue repeats every
four seconds (toggle with the **Sound** button). The recent-ride cards are a fixed size and no
longer carry a rider rating — rating a rider is the driver's job.

## Accounts and access

Every rider, driver, and dispatcher signs in with a NightRider account. Riders
can create their own accounts; dispatch creates driver accounts. The server
checks the account role and ride ownership on protected pages and API routes.
Passwords use salted scrypt hashes, web sessions use secure HTTP-only cookies,
and the Android driver app uses the same account service with an encrypted
session token. Setup steps and Render variables are in **ACCOUNT-SETUP.md**.

## Rider accounts, ratings and issues

Each ride belongs to the signed-in rider account. NightRider does not collect
browser or device fingerprints. Drivers and dispatch can file a 1–5 star rating
and issue tags (no-show, rude, messy, unsafe, payment, other); drivers see a
summary on rides they can access and dispatch can review rider accounts and
ride history.

## Export
Dispatch can download a plain-text ride log for a chosen date range or all rides,
including route, fare, driver, status, acknowledgments, and ratings.

## Fare

One formula, no ride types:

    fare = $5.00 flag drop + $1.00/mile pickup → drop-off + $0.25/mile driver → pickup

The third leg is the driver's approach. When a driver accepts, the driver page shares its
location and the server measures a straight-line (haversine) distance to the pickup. If the
browser will not share a location, the ride is still accepted and only that leg goes unpriced.
A wildly implausible approach distance (over 200 miles) is rejected rather than charged.

Payments remain placeholders; `fare` is an estimate stored on the ride.

## Test driver (T&E)

For internal testing only, the stand-in driver at Savannah City Hall can be
enabled by setting `NIGHTRIDER_ENABLE_DEMO_DRIVER=true`. It is off by default.

## Production setup

The account-enabled server requires a Render Postgres database and the
environment settings described in **ACCOUNT-SETUP.md**. The web service uses a
single application instance while rides and messages are stored as one JSON
state record in Postgres. Scale the service only after the state store is
changed to support concurrent multi-instance updates.

## Map and addresses (rider page)
The rider page uses Leaflet with CARTO *Dark Matter* map tiles (OpenStreetMap data) — a near-monochrome dark basemap that matches the NightRider night aesthetic. The pickup dot is teal, the drop-off dot is coral, and the route line is bright cyan so it stays visible on the dark base. Prefer a light map? Change `dark_all` to `voyager` in the tile URL in `public/index.html` — that one word switches the basemap.

CARTO now gates these tiles behind a free basemap key. A working key is built into `server.py` (`DEFAULT_CARTO_KEY`) so the map works out of the box, and `GET /api/config` passes it to the page at runtime. It is a public, client-side basemap key — it ships in every tile URL the browser requests — so it is not a secret. To rotate it, set `CARTO_API_KEY` in the host environment (see DEPLOY.md) to override the built-in value without changing code. If the key is ever blank, the page falls back to keyless OpenStreetMap tiles so the map still loads instead of going empty.

- Type an address in the pickup or drop-off box, then tap **Search** (or press Enter) and pick a match (Nominatim lookup).
- Address results are kept **local to the rider's area**: the lookup is boxed around the current area and filtered to one country, so a common street name no longer returns matches in other states or abroad. The area starts at the configured home region, switches to the device location when the rider allows it, and follows the map when they zoom in somewhere. Each match shows how many miles away it is, and the nearest match is listed first.
- If nothing matches inside the local box, the page widens the search once and says so ("showing wider results") instead of leaving the rider stuck. To change the country, set `ADDRESS_COUNTRY` in the host environment (default `us`).
- The lookup runs on **Search / Enter**, not as you type — this follows the Nominatim usage policy and keeps the number of requests down.
- Or tap **Use my location** for pickup, and click the map to drop the drop-off pin. Pins can be dragged.
- The route line and distance come from OSRM's public routing service (real road distance and time). If that service is unavailable, the page falls back to a straight-line estimate × 1.2.
- The fare box shows only the **total** — riders do not see the rate breakdown. Press **Request NightRide**.
- A payment popup appears before the request is sent; pick Cash App, PayPal, Zelle, Venmo, or Cash
  (all placeholders for now) and the choice is stored on the ride. The test-driver crosshair appears only when the internal demo driver is enabled.
- The map stops zooming at tile level 19, the deepest level the tiles actually render, so it never
  goes blank from over-zooming.
- The status view tracks Requesting → Driver assigned → Driver arrived → En route → Completed.

Both OSM/Nominatim and OSRM are public services with fair-use limits, so lookups are throttled. For production we would host or pay for a routing/geocoding provider.

