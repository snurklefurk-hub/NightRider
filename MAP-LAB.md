# NightRider Midnight · Isolated Web Vector Map Lab

**Status:** separate appearance preview. The rider and dispatch pages now use
the same Light/Dark vector basemaps through a Leaflet adapter. The lab still
has no ride actions or driver navigation.

## Open

Go to `/map-lab.html` on the NightRider web host. This is an independent
MapLibre GL JS 6.15.0 page and is not embedded into a live ride flow.
MapLibre v6 must be loaded as an ES module from `dist/maplibre-gl.mjs`.
The map style follows the shared LIGHT/DARK site appearance, with no separate style selector. The lab imports the pinned version from UNPKG with a jsDelivr fallback; the
removed v5-style `dist/maplibre-gl.js` bundle cannot be used. If both CDNs
are inaccessible, the lab displays an explicit loading error. WebGL2 is
required by MapLibre v6.
`/dispatch.html` and `/` retain their Leaflet controls and overlays, but now
load vector basemaps when supported. Their raster tiles are a fallback.

The lab is reachable by URL as a static page, but its **Live dispatch** mode
uses the existing `GET /api/dispatch/map` endpoint. That endpoint is restricted
to an authenticated Dispatch account on the production service. Visitors
without Dispatch authorization can only see the demo data. No write endpoints
are called, even by the authorized mode. There is no event acknowledgement,
assignment, stage transition, status change, or dispatch message action.

## Visual comparison

- **Light · NightRider Midnight:** load OpenFreeMap's Fiord vector style,
  then apply the NightRider paint values used by the **Android Map Lab**.
- **Dark · Original Dark:** use the unmodified public dark vector style.
  Switching the style preserves the browser's current camera.
- **Dallas city streets:** latitude 32.7767, longitude -96.7970, zoom 14.2,
  exactly the default Android test camera.
- **Dallas interchange:** latitude 32.9244, longitude -96.7612, zoom 15.2,
  exactly the Android second camera preset.
- **Savannah:** dispatch-region reference to inspect road details in context.

Camera pitch is locked to zero. No 3D perspective. Displayed roads and labels
are GPU-rendered MapLibre vectors. Fiord's upstream style also has a distant-
zoom auxiliary raster background; strict vector-only world-background migration
is **not** yet complete, while road geometry remains vector-based.

## Markers and routes

Demo uses fictional/sample driver, rider, pickup and drop-off coordinates in
Dallas. This avoids exposing real driver/passenger information by default.

Live mode reads the existing role-protected dispatch map snapshot every
12 seconds only while selected and visible; this is **read-only polling** and
does not reuse Dispatch's ride-event acknowledgement channel.

- Driver locations, with stale/offline distinction
- Pickup and drop-off markers
- Rider positions only from the role-protected dispatch snapshot, with
  last-known/sharing labels
- Optional browser dispatcher position, requested only on button click,
  never posted to NightRider
- Pick a ride to preview the pickup-to-drop-off route and active driver
  approach. Requests go directly to existing public OSRM-compatible routing
  endpoints, not a NightRider server service. Public routers receive request
  coordinate pairs. Routing is cached and rate-limited in the browser, and
  failures show a dotted endpoint connector. Estimates ignore traffic.

Live routes are *only* estimates. The prototype provides **no** turn-by-turn
navigation, safety-critical guidance, or background GPS.

## Styling/maintenance

The canonical experimental Android colors were transcribed from
`nightrider-driver-android/nav-prototype/prototype/src/main/java/com/nightrider/navpreview/PreviewActivity.kt`
(`applyMidnightPalette`). The web copy is `public/map-lab-midnight.js`.
When refining Midnight, **update both** until the future shared-style publishing
pipeline is established. Missing upstream layer IDs are surfaced in the lab,
since OpenFreeMap may change public style internals.

MapLibre GL JS is BSD-3-Clause licensed. Keep the linked OpenStreetMap
contributors and OpenMapTiles data credits visible in the small footer **below**
each map; the built-in on-map attribution box was disabled to avoid duplicate
credits covering the map. Confirm the public vector tile host's attribution
and capacity requirements before commercial deployment. No MapTiler credentials,
services, or costs are added.

## Review an actual Field Test trace (local to your browser)

After a safe, passenger-operated or parked Android **Settings → Field test (live GPS)**
session, use **Save CSV** on the phone. Open the Web Map Lab and select that
CSV using **Review Android Field Test CSV (local file)**. The browser parses
the five-, seven-, or eleven-column file locally and draws the usable GPS trail in orange. The map
zooms to your trace; **Clear trail** removes it. Live/demo ride data are not
altered. No upload to NightRider, dispatch API call, or persistent browser
storage is performed for this import; switching pages clears it. The selected
map area is still visible to the external vector tile provider through normal
map-tile requests.

The importer rejects unfamiliar headers, out-of-range coordinates, repeated/
non-monotonic timestamps and traces exceeding 1,500 fixes / 250 KB. It is a
diagnostic overlay, not turn-by-turn guidance or proof of a driven route.
Field Test export and web import were introduced together and need hands-on
validation on an actual phone and desktop browser.

## Test checklist before any live migration

1. On desktop and Android, compare both Dallas presets and zooms in Light Midnight.
   Confirm highway/local road colors, labels, and intersection legibility.
2. Switch Light and Dark at the same camera position. Confirm controls,
   map credits, and zero pitch.
3. Test demo markers, offline toggle, selected ride, routes, and fallback.
4. Sign in as Dispatch and enable live mode; verify markers and endpoint routes
   without affecting any ride. Verify a driver/rider account cannot read live mode.
5. Confirm mobile responsiveness, resize, accessibility, low-bandwidth failures,
   and browser WebGL performance.
6. Test the current Dispatch board and Rider page to confirm they are unchanged.
7. Check the integrated Rider and Dispatch vector maps, including the raster
   fallback when WebGL or the vector provider is unavailable.

To run static tests: `node --check public/map-lab.js` and
`node --test tests/map_lab.test.cjs`. CI runs both on the map lab PR.


### Road-test GPS diagnostics

The Field Test CSV import is local to your browser and now distinguishes
**solid orange usable GPS trail** from **dashed red raw GPS readings**.
The red line intentionally includes inaccurate positions and teleport-like
spikes for diagnosis; it is not a recommended road or planned route.
The camera fits usable fixes so a single bad fix cannot shrink your drive.

The summary includes total sample count, elapsed minutes, approximate distance
reconstructed across rejected fixes, how many fixes were excluded from the
usable trail, how many reported >30m accuracy, and the longest raw GPS gap.
It uses an adaptive 15–30m accuracy limit and rejects impossible jumps above
55m/s between usable fixes. Distances are rough diagnostics, not turn-by-turn
guidance or certified mileage; low-signal segments may be missing.

No uploaded CSV, derived stats or reconstructed trace is sent to NightRider,
Dispatch, or a storage service. The chosen visible map region still results
in normal OpenFreeMap tile requests. Clearing the trail or leaving the page
discards all data.


### Enhanced Android Field Test CSVs (map acceptance tracking)

NightRider Driver's newer seven-column CSV exports append `provider`
and `map_decision` to the existing timestamp/coordinates/accuracy/speed
fields. The Web Map Lab accepts both the original five-column CSV and the
enhanced format. When every exported sample has a recorded map decision, the
orange trail follows **the actual GPS fixes accepted by the Android map**,
while the red trail preserves the original raw readings. The summary reports
map-accepted and map-rejected counts. Older files still show locally estimated
usable/filtered results and are labeled accordingly.

The enhanced CSV does **not** include the animation frames used by the new
navigation motion smoother. It therefore cannot prove whether the arrow
looked smooth, or reveal perceived lag; a safe passenger-observed device test
is still required. No trace is uploaded to dispatch or stored by the site.


### Optional inertial sensor columns from Field Test

The Field Test's opt-in motion-fusion preview adds **four optional columns**
after the original seven: `fusion_heading_deg`, `gyro_yaw_dps`,
`linear_accel_mps2`, and `phone_azimuth_deg`. The parser supports old
five-column, seven-column, and new eleven-column CSV files. Empty sensor cells
mean the feature was disabled or the sensor estimate was unavailable. All
accuracy/decision processing is unchanged; new sample counts and maximum
recorded turn rate/acceleration are shown in the local status.

Gyroscope-assisted heading is calibrated to reliable moving GPS and is only
used in the opt-in Android Field Test follow camera. The phone's rotation-
vector azimuth is *device* orientation, not uncalibrated vehicle bearing.
Because the phone may move in its mount and inertial estimates drift, the
extra columns are diagnostics, not validated vehicle attitude. Web Map Lab
never uploads these CSV contents or accesses the browser device sensors.
