# NightRider (basic v0)

A starter ride-hailing ecosystem for regional private drivers and small companies.

## Deploy
See **DEPLOY.md** for step-by-step GitHub and Render instructions (render.yaml is included).

## Run
    python3 server.py          # http://localhost:8000 (set PORT to change)

Standard library only (Python 3.8+). No database; rides persist to rides.json.

## Pages
- `/` (index.html): customer requests a ride and sees live status.
- `/driver.html`: driver enters name, accepts open requests, moves ride through arrived → in progress → completed.
- `/dispatch.html`: dispatch board of all rides with cancel control.

## API
- GET /api/rides, GET /api/rides/{id}
- POST /api/rides  {rider_name, pickup, dropoff, distance_mi}
- POST /api/rides/{id}/accept  {driver}
- POST /api/rides/{id}/advance
- POST /api/rides/{id}/cancel

Fare is a placeholder: max($7, $3 + $1.60/mile). No maps, payments, auth or geocoding yet.

## Verification
Checked by running the server and calling the API: create (201), validation (400), accept, double-accept (409), advance, cancel, and page/asset loads (200), unknown route (404). Visual layout has not been reviewed.

## Map and addresses (customer page)
Customers type pickup and drop-off, press "Find addresses on map", and the map shows both points. The distance fills in automatically (straight-line estimate × 1.2) and can be corrected by hand. The map uses OpenStreetMap (free, no key needed). Addresses are looked up by OpenStreetMap's Nominatim service, so lookups are limited to about one per second.
