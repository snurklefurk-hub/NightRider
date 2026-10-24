# NightRider (basic v0)

A starter ride-hailing ecosystem for regional private drivers and small companies.

## Deploy
See **DEPLOY.md** for step-by-step GitHub and Render instructions (render.yaml is included).

## Run
    python3 server.py          # http://localhost:8000 (set PORT to change)

Standard library only (Python 3.8+). No database; rides persist to rides.json.

## Pages
- `/` (index.html): Lyft-style rider page — full-screen map, pickup/drop-off address search, ride tiers with live prices, request and live status.
- `/driver.html`: driver enters name, accepts open requests, moves ride through arrived → in progress → completed.
- `/dispatch.html`: dispatch board of all rides with cancel control.

## API
- GET /api/rides, GET /api/rides/{id}
- POST /api/rides  {rider_name, pickup, dropoff, distance_mi}
- POST /api/rides/{id}/accept  {driver}
- POST /api/rides/{id}/advance
- POST /api/rides/{id}/cancel

Fare is a placeholder: base tier is max($7, $3 + $1.60/mile); XL is ×1.5 and Lux is ×2.0. No payments or accounts yet.

## Verification
Checked by running the server and calling the API: create (201), validation (400), accept, double-accept (409), advance, cancel, and page/asset loads (200), unknown route (404). Visual layout has not been reviewed.

## Map and addresses (rider page)
The rider page uses Leaflet with CARTO *Dark Matter* map tiles (OpenStreetMap data) — a near-monochrome dark basemap that matches the NightRider night aesthetic. The pickup dot is teal, the drop-off dot is coral, and the route line is bright cyan so it stays visible on the dark base. Prefer a light map? Change `dark_all` to `voyager` in the tile URL in `public/index.html` — that one word switches the basemap.

CARTO now gates these tiles behind a free basemap key. A working key is built into `server.py` (`DEFAULT_CARTO_KEY`) so the map works out of the box, and `GET /api/config` passes it to the page at runtime. It is a public, client-side basemap key — it ships in every tile URL the browser requests — so it is not a secret. To rotate it, set `CARTO_API_KEY` in the host environment (see DEPLOY.md) to override the built-in value without changing code. If the key is ever blank, the page falls back to keyless OpenStreetMap tiles so the map still loads instead of going empty.

- Type an address in the pickup or drop-off box and pick a match (Nominatim lookup).
- Or tap **Use my location** for pickup, and click the map to drop the drop-off pin. Pins can be dragged.
- The route line and distance come from OSRM's public routing service (real road distance and time). If that service is unavailable, the page falls back to a straight-line estimate × 1.2.
- Ride tiers (NightRider / XL / Lux) show a live price for the distance; pick one and press **Request NightRide**.
- The status view tracks Requesting → Driver assigned → Driver arrived → En route → Completed.

Both OSM/Nominatim and OSRM are public services with fair-use limits, so lookups are throttled. For production we would host or pay for a routing/geocoding provider.
