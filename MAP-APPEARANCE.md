# NightRider shared vector map appearance

The map basemap uses two modes throughout **currently implemented maps**:

| Mode | Style | Tile rendering |
| --- | --- | --- |
| **Light · NightRider Midnight** | OpenFreeMap Fiord with the custom Midnight Android palette | MapLibre vector |
| **Dark · Original Dark** | Unmodified `https://tiles.openfreemap.org/styles/dark` | MapLibre vector |

This is **map light/dark mode**, not a recoloring of every NightRider UI panel.

## Where

- **Rider booking map** (`/`, `public/index.html`): retains Leaflet's draggable pickup/drop-off, selection, route, fare and ride lifecycle; MapLibre/Leaflet integration supplies a vector basemap.
- **Dispatch live map** (`/dispatch.html`, `public/dispatch-map.js`): retains Leaflet driver/rider markers, live positions, route lines, status and controls, with a vector basemap.
- **Desktop vector map lab** (`/map-lab.html`): native MapLibre GL JS 6 rendering; selects either mode.
- **Android Map Lab** (`com.nightrider.navpreview` in the separate Android repo): native MapLibre Android rendering; selects either mode.
- **Driver browser board** (`/driver.html`) and **production Android Driver** (`com.nightrider.driver`) currently have **no embedded map**. Their dispatch/ride behavior is not changed. When embedded navigation is implemented, reuse these modes.

## Persistence

The Rider, Dispatch, and web Map Lab share `localStorage["nightrider.map-mode.v1"]`
on the same browser origin and update each other across tabs via the storage
event. The Android Map Lab stores the selected mode in a local
`SharedPreferences` file (`map_mode`). **These are device-local preferences, not
cross-device/account synchronization.** Initial value follows the device's
`prefers-color-scheme` / Android system night mode.

No MapTiler API keys or subscriptions are needed.

## Web compatibility and fallback

Rider and Dispatch keep the Leaflet layer/marker implementation to reduce
risk to booking and dispatch. The official `@maplibre/maplibre-gl-leaflet`
adapter (0.1.4) loads a pinned MapLibre GL JS v5 UMD bundle (5.17.0);
this is intentionally distinct from the standalone Map Lab's pinned v6
ES module. The adapter exposes `L.maplibreGL` and lets Leaflet overlays
continue working. If MapLibre cannot initialize WebGL or load an initial style,
the original CARTO/OSM raster tile path remains as a functional fallback.
That fallback is **not vector**, and a browser lacking GPU support cannot meet
the vector rendering requirement without alternative hardware/browser support.

`public/map-theme.js` is the single web mode controller; it applies the
same initial Midnight paint values already used on Android through
`public/map-lab-midnight.js`. Its output must be visually verified at the
same GPS coordinates and zoom on desktop and Android. Styling differences due
to renderer/device density are still possible.

The vector tile provider, OpenFreeMap, is an external public service. Preserve
its attribution. Validate usage terms and available capacity for commercial
scale before treating the hosted public tiles as a long-term SLA.

## Regression and rollout checks

- Open Rider. Switch Light/Dark and verify draggable pickup/dropoff, search,
  OSRM route and ride request still work. Test both vector and fallback paths.
- Open Dispatch with an authorized role. Verify live driver/rider positions,
  selectable rides, trip/approach routes, offline toggle, location permission,
  fullscreen/fit-all and marker details.
- In a second web tab verify the map appearance follows the first tab.
- Compare the same Dallas city-streets and interchange presets in native
  Android and web Map Labs; verify no tilt or loss of attribution.
- Test no-WebGL, failed CDN, failed tile style, and a slow connection. Ensure
  Leaflet raster fallback still supports booking and dispatch.
- Test Android Map Lab with both modes, system-night default and persistence.
- Run `node --test tests/map_lab.test.cjs tests/map_mode.test.cjs`, plus
  independent Android preview and production app regression builds.

**Real-device/live production acceptance testing is still required** before
considering this fully validated.
