# NightRider (software demo / WIP)

NightRider is a closed, work-in-progress software demo. It offers no transportation
services, accepts no real bookings or payments, and every trip in the app is simulated.
Friends, family, drivers, riders, and interested reviewers can explore it with the shared
`DEMO` / `PASSWORD` test credentials on the Rider, Driver, and Dispatch pages. Each visible
role maps to a distinct internal demo account; public rider account creation is not available.

## Deploy
See **DEPLOY.md** for step-by-step GitHub and Render instructions (render.yaml is included).

## Run
    python3 server.py          # http://localhost:8000 (set PORT to change)

Standard library only (Python 3.8+). No database; rides persist to rides.json.

## Pages
- `/` (index.html): Lyft-style rider page — full-screen map, pickup/drop-off address search, one fare estimate, request and live status.
- `/driver.html`: driver enters name, accepts open requests, then moves the ride through five staged buttons — **Head to pickup → Arrive at pickup → Head to destination → Arrive at destination → Complete ride** — and rates the rider.
- `/dispatch.html`: live dispatch board — see **Dispatch** below.

## API
- GET /api/rides, GET /api/rides/{id}
- POST /api/rides  {rider_name, payment_method, pickup, dropoff, distance_mi, pickup_coords?, driver_to_pickup_mi?, device?}
- POST /api/rides/{id}/accept  {driver, driver_coords?}  (or {driver, demo: true} for the test driver)
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

## No dispatch key
Dispatch routes are open, like the rest of this starter — there is no login anywhere yet. A
dispatch key was removed because riders and drivers reach the same host; add real authentication
before anything ships to paying customers.

## Hidden rider IDs, ratings and issues
Every ride is stamped with a rider identity the rider can neither see nor change. It is derived on
the server from the request headers plus a few read-only browser signals the rider page reports
(SHA-256), so it works with no app install. It is **not** a hardware serial — it is a stable
best-effort fingerprint, not a verified identity. Drivers and dispatch can file a 1–5 star rating
and issue tags (no-show, rude, messy, unsafe, payment, other) against that ID; the running average
and issue count are shown to drivers and dispatch, while the ID itself is only ever visible on the
dispatch/backend side. Riders see their own average summary but never the ID.

## Export
The dispatch page can download a plain-text log of every ride for a chosen date range (or all
rides) — ID, rider, hidden ID, route, distance, fare, driver, status, dispatch acknowledgment and
ratings.

## Fare

One formula, no ride types:

    fare = $5.00 flag drop + $1.00/mile pickup → drop-off + $0.25/mile driver → pickup

The third leg is the driver's approach. When a driver accepts, the driver page shares its
location and the server measures a straight-line (haversine) distance to the pickup. If the
browser will not share a location, the ride is still accepted and only that leg goes unpriced.
A wildly implausible approach distance (over 200 miles) is rejected rather than charged.

No payments or accounts yet; `fare` is an estimate stored on the ride.

## Test driver (T&E)

For testing and engineering there is one stand-in driver, **Test Driver**, permanently parked at
the real **Savannah City Hall** (2 E Bay St, `32.08111, -81.09111`). It is defined as `DEMO_DRIVER`
in `server.py` and also returned by `GET /api/config`, so the rider map always shows it as a cyan
crosshair with a slow pulsing halo, and the rider estimate prices the $0.25/mile approach leg from City Hall. On the driver page,
**Use test driver (Savannah City Hall)** makes your accepts come from City Hall too, instead of this
device's GPS — handy for repeatable tests from anywhere.

## Verification
Checked by running the server and calling the API: create (201), validation (400), accept,
double-accept (409), advance, cancel, page/asset loads (200), unknown route (404), the event stream
and acknowledgment handshake, driver presence and dispatch↔driver messaging, payment-method
capture, map-zoom capping, ratings/issues validation, and plain-text export with date filters. The
automated suite (`python3 -m unittest discover -s tests`) covers the same ground. Visual layout has
not been reviewed.

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
  (all placeholders for now) and the choice is stored on the ride. (The pulsing crosshair is the test driver at Savannah City Hall.)
- The map stops zooming at tile level 19, the deepest level the tiles actually render, so it never
  goes blank from over-zooming.
- The status view tracks Requesting → Driver assigned → Driver arrived → En route → Completed.

Both OSM/Nominatim and OSRM are public services with fair-use limits, so lookups are throttled. For production we would host or pay for a routing/geocoding provider.
