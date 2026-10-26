# NightRider Midnight · Isolated Web Vector Map Lab

**Status:** non-production preview. **No** replacement of rider or dispatch
Leaflet/CARTO maps, driver navigation, backend API, or ride lifecycle.

## Open

Go to `/map-lab.html` on the NightRider web host. This is an independent
MapLibre GL JS 6.15.0 page and is not linked or embedded into a live ride flow.
`/dispatch.html` and `/` remain on their existing Leaflet raster maps.

The lab is reachable by URL as a static page, but its **Live dispatch** mode
uses the existing `GET /api/dispatch/map` endpoint. That endpoint is restricted
to an authenticated Dispatch account on the production service. Visitors
without Dispatch authorization can only see the demo data. No write endpoints
are called, even by the authorized mode. There is no event acknowledgement,
assignment, stage transition, status change, or dispatch message action.

## Visual comparison

- **NightRider Midnight (default):** load OpenFreeMap's Fiord vector style,
  then set its native fill, line, text, halo, and background paint properties to
  the initial NightRider Midnight values in the **Android Map Lab**.
- **Original Fiord / Original Dark:** unmodified public vector styles for A/B
  comparison. Switching the style preserves the browser's current camera.
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

MapLibre GL JS is BSD-3-Clause licensed. Keep built-in OpenFreeMap/OpenStreetMap
attribution visible; confirm upstream hosted map usage requirements for future
commercial deployment. No MapTiler credentials, services, or costs are added.

## Test checklist before any live migration

1. On desktop and Android, compare both Dallas presets and zooms in Midnight.
   Confirm highway/local road colors, labels, and intersection legibility.
2. Switch Fiord, Dark, Midnight at the same camera position. Confirm controls,
   map credits, and zero pitch.
3. Test demo markers, offline toggle, selected ride, routes, and fallback.
4. Sign in as Dispatch and enable live mode; verify markers and endpoint routes
   without affecting any ride. Verify a driver/rider account cannot read live mode.
5. Confirm mobile responsiveness, resize, accessibility, low-bandwidth failures,
   and browser WebGL performance.
6. Test the current Dispatch board and Rider page to confirm they are unchanged.
7. Only after approval: separately plan controlled Dispatch migration with
   an explicit Leaflet fallback, then Rider migration if warranted.

To run static tests: `node --check public/map-lab.js` and
`node --test tests/map_lab.test.cjs`. CI runs both on the map lab PR.
