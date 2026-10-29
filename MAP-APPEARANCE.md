# NightRider shared LIGHT/DARK appearance

One appearance switch controls both the **site UI** and the **vector map**:
**LIGHT** is Frutiger Aero UI + NightRider Midnight (custom Fiord vector
palette); **DARK** is classic NightRider UI + OpenFreeMap Original Dark vectors.
The existing map-only toggle was removed. The UI preference is stored in
`localStorage["nightrider.ui-theme.v1"]`; older Aero settings remain valid,
while the obsolete `nightrider.map-mode.v1` preference is ignored.
The website's two-button control displays only **LIGHT** and **DARK**.

## Where

- **Rider booking map** (`/rider`, `public/index.html`): retains Leaflet's draggable pickup/drop-off, selection, route, fare and ride lifecycle; MapLibre/Leaflet integration supplies a vector basemap.
- **Dispatch live map** (`/dispatch.html`, `public/dispatch-map.js`): retains Leaflet driver/rider markers, live positions, route lines, status and controls, with a vector basemap.
- **Android appearance preview** (`com.nightrider.navpreview` in the separate Android repo): native MapLibre Android rendering; selects either mode.
- **Driver browser board** (`/driver.html`) has no embedded map.
- **Production Android Driver** (`com.nightrider.driver`) includes Vela-powered navigation and separate legacy GPS testing tools. See the companion repository's `NAVIGATION-VELA.md` for current behavior; this web directory change does not modify Android navigation.

## Persistence

The Rider, Dispatch, and public pages share `localStorage["nightrider.ui-theme.v1"]`
on the same browser origin and update each other across tabs via the storage
event. DARK is the default. The production Android app stores its choice as
`frutiger_aero_ui`; the separate Android appearance preview uses `aero_ui`. Both default
to DARK and ignore the old independent `map_mode` preference. These choices
are local to each browser or app and do not synchronize through accounts.

No MapTiler API keys or subscriptions are needed.

## Web compatibility and fallback

Rider and Dispatch keep the Leaflet layer/marker implementation to reduce
risk to booking and dispatch. The official `@maplibre/maplibre-gl-leaflet`
adapter (0.1.4) loads a pinned MapLibre GL JS v5 UMD bundle (5.17.0).
The adapter exposes `L.maplibreGL` and lets Leaflet overlays
continue working. If MapLibre cannot initialize WebGL or load an initial style,
the original CARTO/OSM raster tile path remains as a functional fallback.
That fallback is **not vector**, and a browser lacking GPU support cannot meet
the vector rendering requirement without alternative hardware/browser support.

`public/aero-theme.js` owns the shared UI preference and appearance controls.
`public/map-theme.js` follows that preference for Leaflet basemaps; it applies the
same initial Midnight paint values already used on Android through
`public/map-midnight.js`. Its output must be visually verified at the
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
- Compare matching coordinates and zoom in Android's appearance preview
  and the operational web maps; verify no loss of attribution.
- Test no-WebGL, failed CDN, failed tile style, and a slow connection. Ensure
  Leaflet raster fallback still supports booking and dispatch.
- Test Android's appearance preview and Driver with both modes, DARK default and persistence.
- Run `node --test tests/*.test.cjs`, plus
  independent Android preview and production app regression builds.

**Real-device/live production acceptance testing is still required** before
considering this fully validated.
