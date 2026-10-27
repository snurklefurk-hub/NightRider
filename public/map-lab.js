/* NightRider Midnight web map lab.
 * Standalone, read-only preview. No mutation endpoints, production page hooks,
 * background geolocation, API key, or ride lifecycle code.
 */
(async function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const mapHost = $("labMap"), notice = $("labNotice"), summary = $("labSummary");
  if (!mapHost || !notice) return;
  if (!window.NightRiderMidnight) {
    notice.textContent = "NightRider Midnight palette script failed to load. Refresh the page.";
    return;
  }

  // MapLibre GL JS v6 is ESM-only: dist/maplibre-gl.js no longer exists.
  // Import the pinned .mjs bundle; try a second CDN if the first is blocked.
  const mapLibreModules = [
    "https://unpkg.com/maplibre-gl@6.15.0/dist/maplibre-gl.mjs",
    "https://cdn.jsdelivr.net/npm/maplibre-gl@6.15.0/dist/maplibre-gl.mjs"
  ];
  let maplibregl = null;
  for (const url of mapLibreModules) {
    try {
      const module = await import(url);
      if (typeof module.Map !== "function") {
        throw new Error("MapLibre ESM Map export is unavailable");
      }
      maplibregl = module;
      break;
    } catch (error) {
      // Try the fallback CDN without interrupting the rest of Dispatch.
      console.warn("NightRider Map Lab: MapLibre CDN unavailable", url, error);
    }
  }
  if (!maplibregl) {
    notice.textContent = "Unable to load the MapLibre vector engine from either CDN. Check browser blockers or network restrictions, then reload.";
    return;
  }
  const FIORD = "https://tiles.openfreemap.org/styles/fiord";
  const DARK = "https://tiles.openfreemap.org/styles/dark";
  const PRESETS = {
    streets: { center: [-96.7970, 32.7767], zoom: 14.2 },
    junction: { center: [-96.7612, 32.9244], zoom: 15.2 },
    savannah: { center: [-81.0912, 32.0809], zoom: 13.2 }
  };
  const COLORS = { driver: "#82bee0", pickup: "#2ee6a0", dropoff: "#ff6f91",
    rider: "#ffc36b", dispatch: "#f3fdfb" };
  const EMPTY = { type: "FeatureCollection", features: [] };
  const RIDE_LABELS = {
    requested: "Unassigned", accepted: "Driver accepted", to_pickup: "Heading to pickup",
    at_pickup: "At pickup", to_dropoff: "Heading to drop-off", at_dropoff: "At drop-off"
  };
  const markers = new Map();
  const routeCache = new Map();
  const routeInFlight = new Map();
  let snapshot = demoSnapshot(), selectedRideId = "LAB-01", liveMode = false;
  let selectedStyle = "midnight", localPosition = null, styleReady = false;
  let lastLiveSnapshotAt = 0, activeRequest = null, routeToken = 0;
  let nextOsrmAt = 0, pendingRoute = Promise.resolve();
  const map = new maplibregl.Map({
    container: mapHost, style: FIORD,
    center: PRESETS.streets.center, zoom: PRESETS.streets.zoom,
    bearing: 0, pitch: 0, minPitch: 0, maxPitch: 0,
    dragRotate: false, pitchWithRotate: false, touchPitch: false,
    renderWorldCopies: false,
    maxZoom: 19, minZoom: 3, attributionControl: true
  });
  // Pinch zoom is allowed; rotation and pitch never are.
  if (map.touchZoomRotate && map.touchZoomRotate.disableRotation) {
    map.touchZoomRotate.disableRotation();
  }
  if (map.touchPitch && map.touchPitch.disable) { map.touchPitch.disable(); }
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "imperial", maxWidth: 110 }), "bottom-left");

  function announce(message) { notice.textContent = message; }
  function validCoords(coords) {
    return Array.isArray(coords) && coords.length === 2 &&
      coords.every(n => typeof n === "number" && Number.isFinite(n)) &&
      Math.abs(coords[0]) <= 90 && Math.abs(coords[1]) <= 180;
  }
  function lonLat(coords) { return [coords[1], coords[0]]; }
  function latLngOf(coords) { return validCoords(coords) ? lonLat(coords) : null; }
  function isLiveRider(fix) {
    return !!fix && fix.sharing !== false && fix.live !== false &&
      Date.now() / 1000 - Number(fix.at || 0) <= 120;
  }
  function demoSnapshot() {
    const now = Date.now() / 1000;
    return {
      now,
      drivers: [
        { name: "Test Driver", active: true, coords: [32.7856, -96.8004],
          status: "to_pickup", location_at: now - 13, location_fresh: true, ride_id: "LAB-01",
          color: "#82bee0", location_accuracy: 8 },
        { name: "Offline Example", active: false, coords: [32.7923, -96.7801],
          status: "offline", location_at: now - 500, location_fresh: false, color: "#82bee0" }
      ],
      rides: [{
        id: "LAB-01", rider_name: "Sample Passenger", driver: "Test Driver",
        pickup: "Test pickup · downtown Dallas", dropoff: "Test drop-off · Dallas",
        status: "to_pickup",
        pickup_coords: [32.7767, -96.7970], dropoff_coords: [32.7951, -96.7691],
        rider_location: { coords: [32.7759, -96.7952], sharing: true, live: true,
          at: now - 18, accuracy: 12 }
      }]
    };
  }
  function getRide() {
    return (snapshot.rides || []).find(r => String(r.id) === selectedRideId);
  }
  function getDriver(ride) {
    return ride && (snapshot.drivers || []).find(d => d.name === ride.driver);
  }
  function popup(title, lines) {
    const el = document.createElement("div");
    const head = document.createElement("strong");
    head.textContent = title;
    el.appendChild(head);
    lines.forEach(line => {
      const row = document.createElement("div");
      row.textContent = String(line == null ? "" : line);
      el.appendChild(row);
    });
    return el; // All server-controlled strings are inserted as text, never HTML.
  }
  function syncMarker(key, coords, kind, title, lines, stale, used, color) {
    const ll = latLngOf(coords);
    if (!ll) { return; }
    used.add(key);
    const signature = kind + "|" + String(color || COLORS[kind]) + "|" + !!stale;
    let entry = markers.get(key);
    if (!entry) {
      const pin = document.createElement("div");
      pin.className = "nr-lab-pin " + kind;
      pin.textContent = { driver: "D", pickup: "P", dropoff: "X",
        rider: "R", dispatch: "S" }[kind] || "?";
      pin.style.setProperty("--pin-color", color || COLORS[kind]);
      const marker = new maplibregl.Marker({ element: pin, anchor: "center" })
        .setLngLat(ll).addTo(map);
      entry = { marker, signature: "" };
      markers.set(key, entry);
    }
    entry.marker.setLngLat(ll);
    const pin = entry.marker.getElement();
    pin.className = "nr-lab-pin " + kind + (stale ? " stale" : "");
    pin.style.setProperty("--pin-color", color || COLORS[kind]);
    pin.setAttribute("aria-label", title);
    pin.title = title;
    entry.marker.setPopup(new maplibregl.Popup({ offset: 20, maxWidth: "320px" })
      .setDOMContent(popup(title, lines)));
    entry.signature = signature;
  }
  function updateRideSelect() {
    const select = $("labRide");
    if (selectedRideId && !(snapshot.rides || []).some(r => String(r.id) === selectedRideId)) {
      selectedRideId = "";
    }
    select.replaceChildren(new Option("All locations", ""));
    (snapshot.rides || []).forEach(ride =>
      select.add(new Option(String(ride.id) + " · " + (ride.rider_name || "Rider") +
        " · " + (RIDE_LABELS[ride.status] || ride.status), String(ride.id))));
    select.value = selectedRideId;
  }
  function renderMarkers() {
    const used = new Set(), current = Date.now() / 1000;
    const selected = getRide(), visibleRides = selected ? [selected] : (snapshot.rides || []);
    if ($("labDrivers").checked) (snapshot.drivers || []).forEach(driver => {
      if (!driver.active && !$("labOffline").checked) { return; }
      const stale = !driver.active || current - Number(driver.location_at || 0) > 120;
      syncMarker("driver:" + driver.name, driver.coords, "driver", driver.name,
        [(RIDE_LABELS[driver.status] || driver.status || "Driver"),
          stale ? "Last known position · may be stale" : "Recent shared position",
          driver.ride_id ? "Ride " + driver.ride_id : ""],
        stale, used, /^#[0-9a-f]{6}$/i.test(driver.color || "") ? driver.color : COLORS.driver);
    });
    visibleRides.forEach(ride => {
      const name = "Ride " + ride.id + " · " + (ride.rider_name || "Rider");
      syncMarker("pickup:" + ride.id, ride.pickup_coords, "pickup", "Pickup · " + name,
        [ride.pickup || "", RIDE_LABELS[ride.status] || ride.status || ""], false, used);
      syncMarker("dropoff:" + ride.id, ride.dropoff_coords, "dropoff", "Drop-off · " + name,
        [ride.dropoff || "", "Driver: " + (ride.driver || "Unassigned")], false, used);
      if ($("labRiders").checked && ride.rider_location) {
        const fix = ride.rider_location;
        const fresh = isLiveRider(fix);
        syncMarker("rider:" + ride.id, fix.coords, "rider",
          (fresh ? "Live" : "Last known") + " rider · " + name,
          [fresh ? "Sharing with Dispatch" : "Not currently sharing a fresh position",
            fix.at ? "Position: " + new Date(fix.at * 1000).toLocaleTimeString() : ""],
          !fresh, used);
      }
    });
    if (localPosition) {
      syncMarker("dispatch", localPosition, "dispatch", "Your browser location",
        ["Not shared with NightRider or Dispatch"], false, used);
    }
    markers.forEach((entry, key) => {
      if (!used.has(key)) { entry.marker.remove(); markers.delete(key); }
    });
    const active = (snapshot.drivers || []).filter(d => d.active).length;
    summary.textContent = (liveMode ? "LIVE DISPATCH · READ-ONLY" : "DEMO DATA · NO REAL RIDES") +
      " · " + active + " active driver(s) · " + (snapshot.rides || []).length +
      " ride(s)" + (liveMode && lastLiveSnapshotAt ?
        " · updated " + new Date(lastLiveSnapshotAt).toLocaleTimeString() : "");
    updateRoutes();
  }
  function fitView() {
    const selected = getRide(), entries = [...markers].filter(([key]) => {
      if (!selected) { return true; }
      return key.endsWith(":" + selected.id) ||
        key === "driver:" + selected.driver || key === "dispatch";
    });
    if (!entries.length) { announce("No locations with valid coordinates to fit."); return; }
    const bounds = new maplibregl.LngLatBounds();
    entries.forEach(([, item]) => bounds.extend(item.marker.getLngLat()));
    map.fitBounds(bounds, { padding: 70, maxZoom: 15, duration: 350 });
  }
  function updateCamera() {
    const ll = map.getCenter();
    $("labCamera").textContent = "Center " + ll.lat.toFixed(4) + ", " +
      ll.lng.toFixed(4) + " · Zoom " + map.getZoom().toFixed(1) + " · Pitch 0°";
  }
  function routeGeo(coords) {
    if (!coords || coords.length < 2) { return EMPTY; }
    return { type: "FeatureCollection", features: [{
      type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords }
    }] };
  }
  function ensureRouteLayers() {
    [["lab-trip", "#2fe9ff"], ["lab-approach", "#ffc36b"]].forEach(([id, color]) => {
      if (!map.getSource(id)) {
        map.addSource(id, { type: "geojson", data: EMPTY });
      }
      if (!map.getLayer(id + "-halo")) {
        map.addLayer({ id: id + "-halo", type: "line", source: id,
          paint: { "line-color": "#07121b", "line-width": 9, "line-opacity": 0.8 },
          layout: { "line-cap": "round", "line-join": "round" } });
      }
      if (!map.getLayer(id)) {
        map.addLayer({ id, type: "line", source: id,
          paint: { "line-color": color,
            "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.5, 15, 5, 19, 7],
            "line-opacity": 0.96,
            "line-dasharray": id === "lab-approach" ? [2, 1.7] : [1, 0] },
          layout: { "line-cap": "round", "line-join": "round" } });
      }
    });
  }
  function setRoute(id, coords, fallback) {
    if (!styleReady || !map.getSource(id)) { return; }
    map.getSource(id).setData(routeGeo(coords));
    if (map.getLayer(id)) {
      map.setPaintProperty(id, "line-dasharray",
        fallback ? [1.5, 3] : id === "lab-approach" ? [2, 1.7] : [1, 0]);
    }
  }
  function routeKey(from, to) {
    return [from, to].flat().map(n => Number(n).toFixed(4)).join(",");
  }
  function osrmRoute(from, to) {
    const key = routeKey(from, to), cached = routeCache.get(key);
    if (cached && Date.now() - cached.at < (cached.fallback ? 90000 : 1800000)) {
      return Promise.resolve(cached);
    }
    if (routeInFlight.has(key)) return routeInFlight.get(key);
    // Serialize and rate-limit ALL calls; routing is a lab approximation only.
    const task = pendingRoute.catch(() => {}).then(async () => {
      const existing = routeCache.get(key);
      if (existing && Date.now() - existing.at < (existing.fallback ? 90000 : 1800000)) {
        return existing;
      }
      const sleep = Math.max(0, nextOsrmAt - Date.now());
      if (sleep) await new Promise(resolve => setTimeout(resolve, sleep));
      nextOsrmAt = Date.now() + 1200;
      const path = lonLat(from).join(",") + ";" + lonLat(to).join(",") +
        "?overview=full&geometries=geojson&steps=false&alternatives=false";
      const endpoints = [
        "https://router.project-osrm.org/route/v1/driving/",
        "https://routing.openstreetmap.de/routed-car/route/v1/driving/"
      ];
      for (const endpoint of endpoints) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8500);
        try {
          const response = await fetch(endpoint + path, { signal: controller.signal,
            credentials: "omit" });
          if (!response.ok) throw new Error("OSRM unavailable");
          const data = await response.json();
          const coordinates = data.routes && data.routes[0] &&
            data.routes[0].geometry && data.routes[0].geometry.coordinates;
          if (!Array.isArray(coordinates) || coordinates.length < 2 ||
              coordinates.some(p => !Array.isArray(p) || p.length < 2 ||
                p.some(n => !Number.isFinite(n)))) throw new Error("Invalid road geometry");
          const result = { coords: coordinates, at: Date.now(), fallback: false };
          routeCache.set(key, result);
          return result;
        } catch (_err) {
          // Try fallback endpoint. Only endpoints are drawn if both fail.
        } finally {
          clearTimeout(timeout);
        }
      }
      const result = { coords: [lonLat(from), lonLat(to)], at: Date.now(), fallback: true };
      routeCache.set(key, result);
      return result;
    });
    routeInFlight.set(key, task);
    task.finally(() => routeInFlight.delete(key));
    pendingRoute = task.then(() => {}, () => {});
    return task;
  }
  function updateRoutes() {
    const token = ++routeToken, ride = getRide();
    if (!ride || !validCoords(ride.pickup_coords) || !validCoords(ride.dropoff_coords)) {
      setRoute("lab-trip", [], false);
      setRoute("lab-approach", [], false);
      return;
    }
    const from = ride.pickup_coords, to = ride.dropoff_coords;
    // Render fallback endpoints immediately; replace with road geometry if available.
    const cached = routeCache.get(routeKey(from, to));
    setRoute("lab-trip", cached ? cached.coords : [lonLat(from), lonLat(to)], !cached || cached.fallback);
    osrmRoute(from, to).then(result => {
      if (token === routeToken) {
        setRoute("lab-trip", result.coords, result.fallback);
        if (result.fallback) announce("Road route unavailable; dotted line joins endpoints.");
      }
    });
    const driver = getDriver(ride);
    const beforePickup = ["accepted", "to_pickup", "at_pickup"].includes(ride.status);
    const destination = beforePickup ? from : to;
    if (!driver || !driver.active || !driver.location_fresh ||
        !validCoords(driver.coords) || !validCoords(destination)) {
      setRoute("lab-approach", [], false);
      return;
    }
    const approach = routeCache.get(routeKey(driver.coords, destination));
    setRoute("lab-approach",
      approach ? approach.coords : [lonLat(driver.coords), lonLat(destination)],
      !approach || approach.fallback);
    osrmRoute(driver.coords, destination).then(result => {
      if (token === routeToken) setRoute("lab-approach", result.coords, result.fallback);
    });
  }
  function showSnapshot(data) {
    snapshot = data;
    updateRideSelect();
    renderMarkers();
  }
  function setDemo(message) {
    liveMode = false;
    lastLiveSnapshotAt = 0;
    selectedRideId = "LAB-01";
    $("labMode").value = "demo";
    showSnapshot(demoSnapshot());
    announce(message || "Sample markers shown. Select a ride to see read-only OSRM routes.");
  }
  async function fetchLive() {
    if (activeRequest) activeRequest.abort();
    const controller = new AbortController();
    activeRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/dispatch/map", {
        credentials: "same-origin", cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ?
        "Live mode requires a signed-in Dispatch account." :
        "Live map snapshot request failed (" + response.status + ").");
      const data = await response.json();
      if (!data || !Array.isArray(data.drivers) || !Array.isArray(data.rides)) {
        throw new Error("Unexpected map snapshot format.");
      }
      if (!liveMode || activeRequest !== controller) { return; }
      lastLiveSnapshotAt = Date.now();
      showSnapshot(data);
      announce("Authorized read-only dispatch snapshot loaded. No ride commands are sent.");
    } catch (err) {
      if (activeRequest === controller && liveMode) {
        if (err.name === "AbortError") announce("Live snapshot timed out; previous data may be stale.");
        else if (String(err.message).includes("Dispatch account")) setDemo(err.message + " Showing demo.");
        else announce(err.message + " · Previous data may be stale.");
      }
    } finally {
      clearTimeout(timeout);
      if (activeRequest === controller) activeRequest = null;
    }
  }
  function chooseStyle() {
    selectedStyle = $("labStyle").value;
    styleReady = false;
    announce("Loading " + (selectedStyle === "midnight" ? "NightRider Midnight" : selectedStyle) + " vector style…");
    map.setStyle(selectedStyle === "dark" ? DARK : FIORD);
  }
  map.on("style.load", () => {
    styleReady = true;
    if (selectedStyle === "midnight") {
      const missing = window.NightRiderMidnight.apply(map);
      if (missing.length) {
        announce("Midnight style loaded with " + missing.length +
          " missing palette layers. OpenFreeMap may have changed its style.");
      } else {
        announce("NightRider Midnight vector style ready · matches the Android palette.");
      }
    } else {
      announce("Original OpenFreeMap " + selectedStyle + " vector style ready.");
    }
    ensureRouteLayers();
    updateRoutes();
  });
  map.on("moveend", updateCamera);
  map.on("load", () => { updateCamera(); updateRideSelect(); renderMarkers(); });
  map.on("error", e => {
    // Map rendering and network errors should never modify dispatch data.
    if (e && e.error) {
      announce("Map resource issue: " + String(e.error.message || "check network") + ".");
    }
  });

  $("labStyle").addEventListener("change", chooseStyle);
  $("labLocation").addEventListener("change", e => {
    const preset = PRESETS[e.target.value];
    if (preset) map.jumpTo({ center: preset.center, zoom: preset.zoom, bearing: 0, pitch: 0 });
    updateCamera();
  });
  $("labRide").addEventListener("change", e => {
    selectedRideId = e.target.value;
    renderMarkers();
    if (selectedRideId) fitView();
  });
  ["labDrivers", "labRiders", "labOffline"].forEach(id => $(id).addEventListener("change", renderMarkers));
  $("labFit").addEventListener("click", fitView);
  $("labRefresh").addEventListener("click", () => {
    if (liveMode) fetchLive();
    else setDemo("Demo positions reset. No live data accessed.");
  });
  $("labMode").addEventListener("change", e => {
    if (activeRequest) { activeRequest.abort(); activeRequest = null; }
    if (e.target.value === "live") {
      liveMode = true;
      selectedRideId = "";
      snapshot = { drivers: [], rides: [] };
      updateRideSelect(); renderMarkers();
      announce("Checking Dispatch authorization for a read-only map snapshot…");
      fetchLive();
    } else setDemo();
  });
  $("labMyLocation").addEventListener("click", function () {
    if (localPosition) {
      localPosition = null;
      this.setAttribute("aria-pressed", "false");
      this.textContent = "My location";
      renderMarkers();
      return;
    }
    if (!navigator.geolocation) { announce("Geolocation is unavailable."); return; }
    navigator.geolocation.getCurrentPosition(position => {
      localPosition = [position.coords.latitude, position.coords.longitude];
      $("labMyLocation").textContent = "Clear location";
      $("labMyLocation").setAttribute("aria-pressed", "true");
      renderMarkers();
      map.easeTo({ center: lonLat(localPosition), zoom: 13.5, pitch: 0, bearing: 0 });
    }, () => announce("Location access denied or unavailable. No location was transmitted."),
    { enableHighAccuracy: false, maximumAge: 30000, timeout: 12000 });
  });

  window.addEventListener("focus", () => { if (liveMode) fetchLive(); });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && liveMode) fetchLive();
  });
  setInterval(() => { if (liveMode && !document.hidden && !activeRequest) fetchLive(); }, 12000);
  window.addEventListener("beforeunload", () => { if (activeRequest) activeRequest.abort(); });
  updateRideSelect();
  updateCamera();
})().catch(function (error) {
  const notice = document.getElementById("labNotice");
  if (notice) {
    notice.textContent = (error && error.name === "GPUInitializationError")
      ? "MapLibre loaded, but WebGL2 could not initialize. Enable browser hardware acceleration and try again."
      : "Map Lab startup failed: " + (error && error.message ? error.message : "unknown error") + ".";
  }
  console.error("NightRider Map Lab startup error", error);
});
