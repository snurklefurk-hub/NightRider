# NightRider (basic v0)

A starter ride-hailing ecosystem for regional private drivers and small companies.

## Deploy
See **DEPLOY.md** for step-by-step GitHub and Render instructions (render.yaml is included).

## Run
    python3 server.py          # http://localhost:8000 (set PORT to change)

Standard library only (Python 3.8+). No database; rides persist to rides.json.

## Pages
- `/` (index.html): Lyft-style rider page — full-screen map, pickup/drop-off address search, one fare estimate, request and live status.
- `/driver.html`: driver enters name, accepts open requests, moves ride through arrived → in progress → completed.
- `/dispatch.html`: dispatch board of all rides with cancel control.

## API
- GET /api/rides, GET /api/rides/{id}
- POST /api/rides  {rider_name, pickup, dropoff, distance_mi, pickup_coords?, driver_to_pickup_mi?}
- POST /api/rides/{id}/accept  {driver, driver_coords?}  (or {driver, demo: true} for the test driver)
- POST /api/rides/{id}/advance
- POST /api/rides/{id}/cancel

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
in `server.py` and also returned by `GET /api/config`, so the rider map always shows it as an amber
square and the rider estimate prices the $0.25/mile approach leg from City Hall. On the driver page,
**Use test driver (Savannah City Hall)** makes your accepts come from City Hall too, instead of this
device's GPS — handy for repeatable tests from anywhere.

## Verification
Checked by running the server and calling the API: create (201), validation (400), accept, double-accept (409), advance, cancel, and page/asset loads (200), unknown route (404). Visual layout has not been reviewed.

## Map and addresses (rider page)
The rider page uses Leaflet with CARTO *Dark Matter* map tiles (OpenStreetMap data) — a near-monochrome dark basemap that matches the NightRider night aesthetic. The pickup dot is teal, the drop-off dot is coral, and the route line is bright cyan so it stays visible on the dark base. Prefer a light map? Change `dark_all` to `voyager` in the tile URL in `public/index.html` — that one word switches the basemap.

CARTO now gates these tiles behind a free basemap key. A working key is built into `server.py` (`DEFAULT_CARTO_KEY`) so the map works out of the box, and `GET /api/config` passes it to the page at runtime. It is a public, client-side basemap key — it ships in every tile URL the browser requests — so it is not a secret. To rotate it, set `CARTO_API_KEY` in the host environment (see DEPLOY.md) to override the built-in value without changing code. If the key is ever blank, the page falls back to keyless OpenStreetMap tiles so the map still loads instead of going empty.

- Type an address in the pickup or drop-off box and pick a match (Nominatim lookup).
- Or tap **Use my location** for pickup, and click the map to drop the drop-off pin. Pins can be dragged.
- The route line and distance come from OSRM's public routing service (real road distance and time). If that service is unavailable, the page falls back to a straight-line estimate × 1.2.
- The fare box breaks out flag drop, trip, and driver approach, then shows one total. Press **Request NightRide**. (The amber square is the test driver at Savannah City Hall.)
- The status view tracks Requesting → Driver assigned → Driver arrived → En route → Completed.

Both OSM/Nominatim and OSRM are public services with fair-use limits, so lookups are throttled. For production we would host or pay for a routing/geocoding provider.
