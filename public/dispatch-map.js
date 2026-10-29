(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var canvas = $("dispatchMap"), status = $("dispatchMapStatus"), selector = $("mapRideSelect");
  if (!canvas || !status || !selector) { return; }
  if (!window.L) {
    status.textContent = "The map could not load. Refresh the page to try again.";
    return;
  }
  var map = L.map(canvas, { minZoom: 3, maxZoom: 19, scrollWheelZoom: false,
    attributionControl: false })
    .setView([32.0809, -81.0912], 12);
  var driverLayer = L.layerGroup().addTo(map), rideLayer = L.layerGroup().addTo(map);
  var riderLayer = L.layerGroup().addTo(map), dispatchLayer = L.layerGroup().addTo(map);
  var routeLayer = L.layerGroup().addTo(map);
  var pairLayer = L.layerGroup().addTo(map);
  var demoLayer = L.layerGroup().addTo(map), demoLines = {};
  // The individual layer checkboxes live next to Show offline drivers.
  // Avoid Leaflet's Layers button overlapping the Light / Dark control.
  var overlays = {
    mapShowDrivers: driverLayer,
    mapShowRidePins: rideLayer,
    mapShowRiders: riderLayer,
    mapShowDispatch: dispatchLayer,
    mapShowRoutes: routeLayer,
    mapShowDemo: demoLayer
  };
  Object.keys(overlays).forEach(function (id) {
    var input = $(id), layer = overlays[id];
    if (!input) { return; }
    input.checked = map.hasLayer(layer);
    input.addEventListener("change", function () {
      if (input.checked) { map.addLayer(layer); }
      else { map.removeLayer(layer); }
      render();
    });
  });
  L.control.scale({ imperial: true, metric: false }).addTo(map);
  var markers = {}, routes = {}, routeCache = {}, routeQueue = [], routeRequests = 0, nextRouteAt = 0;
  var snapshot = { drivers: [], rides: [], demo_drivers: [], demo_rides: [], now: Date.now() / 1000 };
  var snapshotReceived = Date.now(), selectedId = "", fitted = false;
  var loading = false, refreshQueued = false, localPosition = null, localWatch = null;
  var baseLayer = null, tileErrors = 0, usingFallback = false, mapError = "";
  var dispatcherAccuracy = null;
  var labels = {
    requested: "Unassigned", accepted: "Driver accepted", to_pickup: "Heading to pickup",
    at_pickup: "At pickup", to_dropoff: "Heading to drop-off", at_dropoff: "At drop-off",
    available: "Available", busy: "Busy", offline: "Offline"
  };
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function point(value) {
    if (!Array.isArray(value) || value.length !== 2 || value.some(function (n) {
      return typeof n !== "number" || !Number.isFinite(n);
    })) { return null; }
    return Math.abs(value[0]) <= 90 && Math.abs(value[1]) <= 180 ? value : null;
  }
  function now() { return snapshot.now + (Date.now() - snapshotReceived) / 1000; }
  function riderIsLive(fix) {
    return fix && fix.sharing !== false && fix.live !== false && now() - fix.at <= 120;
  }
  function age(at) {
    if (!at) { return "No location fix"; }
    var seconds = Math.max(0, Math.round(now() - at));
    return seconds < 60 ? seconds + "s ago" : seconds < 3600 ? Math.floor(seconds / 60) + "m ago" : Math.floor(seconds / 3600) + "h ago";
  }
  function driverFor(ride) {
    return snapshot.drivers.find(function (driver) { return driver.name === ride.driver; });
  }
  function allMapRides() {
    return snapshot.rides.concat(map.hasLayer(demoLayer) ? snapshot.demo_rides || [] : []);
  }
  function visibleRides() {
    return selectedId ? allMapRides().filter(function (ride) { return ride.id === selectedId; }) : allMapRides();
  }
  // Keep the original geographic coordinates. Do not shift a driver's pin
  // merely to expose an overlapping rider pin: a joint pin represents both.
  function coLocated(a, b) {
    var first = point(a), second = point(b);
    return !!first && !!second && first[0] === second[0] && first[1] === second[1];
  }
  function mapTileLayer(fallback, key) {
    // Vector basemap runs within the existing Leaflet map. Dispatch overlay
    // groups, routes, location and focus controls remain fully unchanged.
    if (baseLayer && baseLayer._nrVector) return;
    if (!baseLayer && window.NightRiderMapTheme && !map._nrVectorFailed) {
      var vector = window.NightRiderMapTheme.attach(map, {
        creditId: "dispatchMapCredit",
        onFallback: function () {
          baseLayer = null;
          mapTileLayer(true, "");
        }
      });
      if (vector) { baseLayer = vector; return; }
    }
    if (baseLayer) { map.removeLayer(baseLayer); }
    if (window.NightRiderMapTheme) {
      window.NightRiderMapTheme.setCredit("dispatchMapCredit", fallback ? "osm" : "carto");
    }
    usingFallback = fallback;
    var url = fallback ? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" :
      "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png" + (key ? "?key=" + encodeURIComponent(key) : "");
    baseLayer = L.tileLayer(url, {
      maxZoom: 19, attribution: '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap</a>' +
        (fallback ? "" : ' · <a href="https://carto.com/attributions">CARTO</a>')
    }).addTo(map);
    baseLayer.on("tileerror", function () {
      tileErrors += 1;
      if (tileErrors >= 3 && !usingFallback) { tileErrors = 0; mapTileLayer(true); }
      else if (tileErrors >= 5) { mapError = "Map tiles unavailable; location details are still available."; updateStatus(); }
    });
    baseLayer.on("tileload", function () { if (mapError) { mapError = ""; updateStatus(); } });
  }
  fetch("/api/config", { cache: "no-store" }).then(function (r) { return r.json(); })
    .then(function (cfg) { mapTileLayer(false, cfg.cartoKey); })
    .catch(function () { mapTileLayer(true); });

  function markerIcon(kind, color, stale, demo) {
    color = /^#[0-9a-f]{6}$/i.test(color || "") ? color : "#5ae6a5";
    var glyph = { driver: "D", pickup: "P", dropoff: "X", rider: "R",
                  dispatch: "S", pair: "D+R" }[kind];
    var size = kind === "pair" ? 40 : 30;
    return L.divIcon({
      className: "nr-map-marker" + (stale ? " is-stale" : "") +
        (demo ? " is-demo" : ""),
      html: '<span class="nr-map-pin ' + kind + '" style="--pin-color:' + color + '">' + glyph + "</span>",
      iconSize: [size, size], iconAnchor: [size / 2, size / 2]
    });
  }
  function syncMarker(key, coords, kind, color, title, html, layer, used, stale, demo) {
    if (!point(coords)) { return; }
    used[key] = true;
    var item = markers[key], signature = kind + color + !!stale + !!demo;
    if (!item) {
      var marker = L.marker(coords, { icon: markerIcon(kind, color, stale, demo), title: title, keyboard: true,
        zIndexOffset: { pair: 800, rider: 500, dispatch: 400, driver: 300 }[kind] || 0 });
      marker.bindPopup(html);
      marker.bindTooltip(document.createTextNode(title), { direction: "top", offset: [0, -12] });
      marker.addTo(layer);
      item = markers[key] = { marker: marker, layer: layer, signature: signature };
    } else {
      item.marker.setLatLng(coords).setPopupContent(html);
      if (signature !== item.signature) { item.marker.setIcon(markerIcon(kind, color, stale, demo)); item.signature = signature; }
      item.marker.setTooltipContent(document.createTextNode(title));
    }
    item.marker.options.title = title;
    var element = item.marker.getElement();
    if (element) { element.title = title; element.setAttribute("aria-label", title); }
  }

  function routeKey(start, end, moving) {
    var precision = moving ? 3 : 5;
    return start.concat(end).map(function (n) { return n.toFixed(precision); }).join(",");
  }
  function requestRoute(start, end, moving) {
    var key = routeKey(start, end, moving), cached = routeCache[key];
    if (cached && (cached.pending || Date.now() - cached.at < (cached.fallback ? 90000 : moving ? 60000 : 1800000))) { return cached; }
    cached = routeCache[key] = { pending: true, at: Date.now(), points: [start, end], fallback: true };
    routeQueue.push({ key: key, start: start, end: end });
    drainRoutes();
    return cached;
  }
  function drainRoutes() {
    if (routeRequests >= 1 || !routeQueue.length) { return; }
    var job = routeQueue.shift();
    routeRequests += 1;
    var path = job.start[1] + "," + job.start[0] + ";" + job.end[1] + "," + job.end[0] +
      "?overview=full&geometries=geojson&steps=false&alternatives=false";
    var services = ["https://router.project-osrm.org/route/v1/driving/", "https://routing.openstreetmap.de/routed-car/route/v1/driving/"];
    function fetchRoute(index) {
      // Public routing endpoints are limited to one request per second.
      return new Promise(function (resolve) { setTimeout(resolve, Math.max(0, nextRouteAt - Date.now())); })
        .then(function () {
          nextRouteAt = Date.now() + 1100;
          var controller = new AbortController(), timeout = setTimeout(function () { controller.abort(); }, 10000);
          return fetch(services[index] + path, { signal: controller.signal, credentials: "omit" })
            .then(function (r) { if (!r.ok) { throw new Error("Routing unavailable"); } return r.json(); })
            .then(function (result) {
              if (result.code !== "Ok" || !result.routes || !result.routes.length) { throw new Error("No road route"); }
              return result;
            }).finally(function () { clearTimeout(timeout); });
        }).catch(function (error) {
          if (index + 1 < services.length) { return fetchRoute(index + 1); }
          throw error;
        });
    }
    fetchRoute(0).then(function (result) {
      var route = result.routes && result.routes[0];
      if (result.code !== "Ok" || !route || !route.geometry || !Array.isArray(route.geometry.coordinates)) { throw new Error("No road route"); }
      var points = route.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
      if (points.length < 2 || points.some(function (p) { return !point(p); })) { throw new Error("Invalid road route"); }
      routeCache[job.key] = { points: points, miles: route.distance / 1609.344,
        minutes: route.duration / 60, at: Date.now(), fallback: false, pending: false };
    }).catch(function () {
      routeCache[job.key] = { points: [job.start, job.end], at: Date.now(), fallback: true, pending: false };
    }).then(function () {
      routeRequests -= 1;
      Object.keys(routeCache).filter(function (key) { return !routeCache[key].pending; }).slice(0, -200)
        .forEach(function (key) { delete routeCache[key]; });
      renderRoutes(); updateSelection();
      setTimeout(drainRoutes, 200);
    });
    drainRoutes();
  }
  function syncRoute(id, data, approach, used) {
    used[id] = true;
    var options = {
      color: data.fallback ? "#9bb7a5" : approach ? "#f4b860" : "#19d47b",
      weight: selectedId ? 5 : 3, opacity: data.fallback ? 0.65 : 0.85,
      dashArray: data.fallback ? "3 9" : approach ? "8 7" : null
    };
    var line = routes[id];
    if (!line) { line = routes[id] = L.polyline(data.points, options).addTo(routeLayer); }
    else { line.setLatLngs(data.points).setStyle(options); }
    var title = data.pending ? "Calculating road route…" : data.fallback ? "Road route unavailable · endpoints only" :
      (approach || "Expected trip route") + " · " + data.miles.toFixed(1) + " mi · about " + Math.max(1, Math.round(data.minutes)) + " min";
    line.bindTooltip(document.createTextNode(title));
  }
  function renderRoutes() {
    var used = {};
    visibleRides().forEach(function (ride) {
      if (ride.demo_preview) return; // DEMO routes are illustrative lines, not OSRM results.
      var pickup = point(ride.pickup_coords), dropoff = point(ride.dropoff_coords);
      if (pickup && dropoff) { syncRoute("trip:" + ride.id, requestRoute(pickup, dropoff, false), false, used); }
      var driver = driverFor(ride);
      var beforePickup = ["accepted", "to_pickup", "at_pickup"].indexOf(ride.status) >= 0;
      var destination = beforePickup ? pickup : dropoff;
      if (selectedId && destination && driver && driver.active && driver.location_fresh && point(driver.coords)) {
        syncRoute("approach:" + ride.id, requestRoute(driver.coords, destination, true),
          beforePickup ? "Driver to pickup" : "Driver to drop-off", used);
      }
    });
    Object.keys(routes).forEach(function (key) {
      if (!used[key]) { routeLayer.removeLayer(routes[key]); delete routes[key]; }
    });
  }
  function render() {
    var used = {}, showOffline = $("mapShowOffline").checked;
    var showDrivers = map.hasLayer(driverLayer), showRiders = map.hasLayer(riderLayer);
    // A shared GPS coordinate is represented by one D+R marker instead of
    // hiding the driver beneath the higher-z-index passenger marker.
    var realPairs = {};
    if (showDrivers && showRiders) snapshot.rides.forEach(function (ride) {
      var driver = driverFor(ride), fix = ride.rider_location;
      if (driver && driver.location_fresh && riderIsLive(fix) &&
          coLocated(driver.coords, fix.coords)) realPairs[driver.name] = ride;
    });
    snapshot.drivers.forEach(function (driver) {
      if (realPairs[driver.name]) return;
      if ((!driver.active && !showOffline) || !driver.location_at) { return; }
      var stale = !driver.active || now() - driver.location_at > 120;
      syncMarker("driver:" + driver.name, driver.coords, "driver", driver.color,
        driver.name, "<strong>" + esc(driver.name) + "</strong><br>" + esc(labels[driver.status] || driver.status) +
        (driver.ride_id ? " · Ride " + esc(driver.ride_id) : "") +
        "<br>" + (stale ? "Last known position" : "Location") + " · " + esc(age(driver.location_at)) +
        (driver.location_accuracy != null ? "<br>Accuracy: about " + Math.round(driver.location_accuracy) + " m" : ""),
        driverLayer, used, stale);
    });
    visibleRides().forEach(function (ride) {
      var title = "Ride " + ride.id + " · " + (ride.rider_name || "Rider");
      var info = "<strong>" + esc(title) + "</strong><br>" + esc(labels[ride.status] || ride.status) +
        "<br>" + esc(ride.driver || "Unassigned");
      syncMarker("pickup:" + ride.id, ride.pickup_coords, "pickup", "#19d47b", "Pickup · " + title,
        info + "<br><b>Pickup:</b> " + esc(ride.pickup), rideLayer, used, false);
      syncMarker("dropoff:" + ride.id, ride.dropoff_coords, "dropoff", "#d95c4f", "Drop-off · " + title,
        info + "<br><b>Drop-off:</b> " + esc(ride.dropoff), rideLayer, used, false);
      if (ride.rider_location) {
        var fix = ride.rider_location;
        var driver = driverFor(ride);
        var paired = !!driver && realPairs[driver.name] === ride;
        if (paired) {
          syncMarker("pair:" + ride.id, fix.coords, "pair", "#f4b860",
            "Driver + rider at same coordinate · " + title,
            info + "<br><b>Driver:</b> " + esc(driver.name) +
            "<br><b>Rider:</b> " + esc(ride.rider_name) +
            "<br>Both at the same reported coordinate (real shared locations).",
            pairLayer, used, false);
          return;
        }
        var live = riderIsLive(fix);
        var locationLabel = live ? "Live rider" : "Last known rider";
        var sharingLabel = live ? "Live location shared with Dispatch" :
          fix.sharing === false ? "Location sharing is off · last known position" : "No fresh location update · last known position";
        syncMarker("rider:" + ride.id, fix.coords, "rider", "#f4b860", locationLabel + " · " + title,
          info + "<br>" + sharingLabel + "<br>Recorded " + esc(new Date(fix.at * 1000).toLocaleString()) + " · " + esc(age(fix.at)) +
          (fix.accuracy != null ? "<br>Accuracy: about " + Math.round(fix.accuracy) + " m" : ""), riderLayer, used, !live);
      }
    });
    // DEMO fixtures never enter operational driver/rider collections, GPS
    // freshness indicators, or the driver application. This is a map overlay.
    var demoUsed = {}, demoRouteUsed = {};
    if (map.hasLayer(demoLayer)) {
      var demoRides = visibleRides().filter(function (ride) { return ride.demo_preview; });
      var demoDrivers = snapshot.demo_drivers || [];
      var pairedDemoDrivers = {};
      demoRides.forEach(function (ride) {
        var driver = demoDrivers.find(function (d) { return d.ride_id === ride.id; });
        var riderCoords = ride.rider_location && ride.rider_location.coords;
        if (showDrivers && showRiders && driver &&
            coLocated(driver.coords, riderCoords)) pairedDemoDrivers[driver.id] = ride;
      });
      if (showDrivers) demoDrivers.forEach(function (driver) {
        if (pairedDemoDrivers[driver.id]) return;
        if (selectedId && driver.ride_id && driver.ride_id !== selectedId) return;
        if (selectedId && !driver.ride_id) return;
        syncMarker("demo:driver:" + (driver.ride_id || driver.id), driver.coords,
          "driver", "#8bbcff", "DEMO driver · " + driver.name,
          "<strong>DEMO driver: " + esc(driver.name) + "</strong><br>" +
          esc(labels[driver.status] || driver.status) +
          "<br>Fixed fictional placement, not live GPS.",
          demoLayer, demoUsed, false, true);
      });
      demoRides.forEach(function (ride) {
        var driver = demoDrivers.find(function (d) { return d.ride_id === ride.id; });
        var riderCoords = ride.rider_location && ride.rider_location.coords;
        var label = "DEMO ride " + ride.id + " · " + ride.rider_name;
        syncMarker("demo:pickup:" + ride.id, ride.pickup_coords, "pickup",
          "#19d47b", "DEMO pickup · " + label,
          "<strong>" + esc(label) + "</strong><br>Fixed example pickup: " +
          esc(ride.pickup), demoLayer, demoUsed, false, true);
        syncMarker("demo:dropoff:" + ride.id, ride.dropoff_coords, "dropoff",
          "#d95c4f", "DEMO drop-off · " + label,
          "<strong>" + esc(label) + "</strong><br>Fixed example destination: " +
          esc(ride.dropoff), demoLayer, demoUsed, false, true);
        if (showDrivers && showRiders && driver &&
            pairedDemoDrivers[driver.id] === ride) {
          syncMarker("demo:pair:" + ride.id, riderCoords, "pair",
            "#f4b860", "DEMO driver + rider together · " + label,
            "<strong>DEMO · driver and passenger together</strong><br>" +
            "Driver: " + esc(driver.name) + "<br>Rider: " + esc(ride.rider_name) +
            "<br>Status: " + esc(labels[ride.status] || ride.status) +
            "<br>One fixed shared coordinate, not two live GPS fixes.",
            demoLayer, demoUsed, false, true);
        } else if (showRiders) {
          syncMarker("demo:rider:" + ride.id, riderCoords, "rider",
            "#f4b860", "DEMO rider · " + label,
            "<strong>DEMO rider: " + esc(ride.rider_name) +
            "</strong><br>Fixed example coordinate, not live GPS.",
            demoLayer, demoUsed, false, true);
        }
        // Fixed straight-line *illustration*, NOT live traffic or road routing.
        if (map.hasLayer(routeLayer) && point(ride.pickup_coords) && point(ride.dropoff_coords)) {
          var id = "demo:route:" + ride.id;
          var points = [ride.pickup_coords, ride.dropoff_coords];
          demoRouteUsed[id] = true;
          if (!demoLines[id]) {
            demoLines[id] = L.polyline(points, {color:"#8bbcff", weight:3,
              dashArray:"4 9", opacity:0.7}).addTo(demoLayer);
            demoLines[id].bindTooltip(document.createTextNode(
              "DEMO straight-line route · illustrative only, no ETA"));
          } else demoLines[id].setLatLngs(points);
        }
      });
    }
    Object.keys(demoLines).forEach(function (key) {
      if (!demoRouteUsed[key]) { demoLayer.removeLayer(demoLines[key]); delete demoLines[key]; }
    });
    Object.keys(markers).forEach(function (key) {
      if (key.indexOf("demo:") === 0 && !demoUsed[key]) {
        markers[key].layer.removeLayer(markers[key].marker); delete markers[key];
      }
    });
    Object.keys(demoUsed).forEach(function (key) { used[key] = true; });
    if (localPosition) {
      syncMarker("dispatch", localPosition.coords, "dispatch", "#f2f0df", "Your dispatch location",
        "<strong>Your dispatch location</strong><br>" + esc(new Date(localPosition.at).toLocaleTimeString()) +
        "<br>Accuracy: about " + Math.round(localPosition.accuracy) + " m", dispatchLayer, used, false);
      if (!dispatcherAccuracy) {
        dispatcherAccuracy = L.circle(localPosition.coords, { color: "#f2f0df", weight: 1, fillOpacity: 0.06,
          radius: localPosition.accuracy, interactive: false }).addTo(dispatchLayer);
      } else { dispatcherAccuracy.setLatLng(localPosition.coords).setRadius(localPosition.accuracy); }
    } else if (dispatcherAccuracy) { dispatchLayer.removeLayer(dispatcherAccuracy); dispatcherAccuracy = null; }
    Object.keys(markers).forEach(function (key) {
      if (!used[key]) { markers[key].layer.removeLayer(markers[key].marker); delete markers[key]; }
    });
    renderRoutes(); updateStatus(); updateSelection();
    if (!fitted && Object.keys(markers).length) { fitView(false); fitted = true; }
  }
  function fitView(onlySelected) {
    var points = [];
    Object.keys(markers).forEach(function (key) {
      var item = markers[key];
      if (!map.hasLayer(item.layer)) { return; }
      if (onlySelected && key.indexOf(selectedId) < 0) {
        var ride = snapshot.rides.find(function (r) { return r.id === selectedId; });
        if (!ride || key !== "driver:" + ride.driver) { return; }
      }
      points.push(item.marker.getLatLng());
    });
    if (points.length) { map.fitBounds(L.latLngBounds(points), { padding: [45, 45], maxZoom: 15, animate: false }); }
  }
  function updateSelector() {
    var previous = selectedId;
    if (selectedId && !allMapRides().some(function (r) { return r.id === selectedId; })) { selectedId = ""; }
    var choices = allMapRides();
    var signature = choices.map(function (r) { return r.id + r.status + r.driver + r.rider_name; }).join("|");
    if (selector.dataset.signature !== signature) {
      selector.innerHTML = '<option value="">All active rides</option>';
      choices.forEach(function (ride) {
        var option = document.createElement("option"); option.value = ride.id;
        option.textContent = (ride.demo_preview ? "DEMO · " : "") + ride.id +
          " · " + (ride.rider_name || "Rider") + " · " + (labels[ride.status] || ride.status);
        selector.appendChild(option);
      });
      selector.dataset.signature = signature;
    }
    selector.value = selectedId;
    if (previous && !selectedId) { $("mapRouteInfo").textContent = "That ride ended or its DEMO layer was hidden. Showing active rides."; }
  }
  function updateStatus() {
    var active = snapshot.drivers.filter(function (d) { return d.active; });
    var positioned = active.filter(function (d) { return point(d.coords) && d.location_at; });
    var unavailable = active.length - positioned.length;
    status.textContent = mapError || positioned.length + " of " + active.length + " online drivers located · " +
      snapshot.rides.length + " active rides · " +
      (map.hasLayer(demoLayer) ? (snapshot.demo_rides || []).length + " DEMO rides / " +
        (snapshot.demo_drivers || []).length + " fictional drivers · " : "") +
      "updated " + new Date(snapshot.now * 1000).toLocaleTimeString() +
      (unavailable ? " · " + unavailable + " driver location" + (unavailable === 1 ? "" : "s") + " unavailable" : "");
  }
  function updateSelection() {
    var out = $("mapRouteInfo"), rides = visibleRides();
    if (!selectedId) {
      var missing = rides.filter(function (r) { return !point(r.pickup_coords) || !point(r.dropoff_coords); }).length;
      out.textContent = rides.length ? "Select a ride to focus its route, driver and optional rider location. Estimates exclude live traffic." +
        (missing ? " " + missing + " ride(s) have missing map coordinates." : "") : "No active rides. Online drivers and your dispatch location remain visible.";
      return;
    }
    var ride = rides[0];
    if (!ride) { return; }
    if (ride.demo_preview) {
      out.textContent = "DEMO ONLY · " + ride.rider_name + " · " +
        (ride.driver || "Unassigned") + " · " + (labels[ride.status] || ride.status) +
        ". Fixed illustrative map positions, not live GPS. D+R denotes driver and passenger " +
        "sharing one point. Dashed routes are straight-line examples without road routing or ETA.";
      return;
    }
    var pickup = point(ride.pickup_coords), dropoff = point(ride.dropoff_coords);
    var text = ride.rider_name + " · " + (ride.driver || "Unassigned") + " · " + (labels[ride.status] || ride.status) + ". ";
    if (pickup && dropoff) {
      var route = routeCache[routeKey(pickup, dropoff, false)];
      if (route && !route.fallback) { text += "Expected trip: " + route.miles.toFixed(1) + " mi, about " + Math.max(1, Math.round(route.minutes)) + " min. "; }
      else { text += route && route.pending ? "Calculating road route. " : "Road route unavailable; dotted line connects endpoints only. "; }
    } else { text += "Pickup or drop-off coordinates were not saved for this ride. "; }
    var driver = driverFor(ride);
    var beforePickup = ["accepted", "to_pickup", "at_pickup"].indexOf(ride.status) >= 0;
    var destination = beforePickup ? pickup : dropoff;
    if (destination && driver && driver.active && driver.location_fresh && point(driver.coords)) {
      var leg = routeCache[routeKey(driver.coords, destination, true)];
      if (leg && !leg.fallback) {
        text += (beforePickup ? "Driver to pickup: " : "Driver to drop-off: ") + leg.miles.toFixed(1) +
          " mi, about " + Math.max(1, Math.round(leg.minutes)) + " min. ";
      }
    }
    var riderFix = ride.rider_location;
    text += riderIsLive(riderFix) ? "Rider location shared with Dispatch." : riderFix ?
      (riderFix.sharing === false ? "Rider sharing is off. " : "No fresh rider location. ") +
      "Last known point recorded " + new Date(riderFix.at * 1000).toLocaleString() + "." : "No rider location has been shared.";
    out.textContent = text;
  }
  function refresh() {
    if (loading) { refreshQueued = true; return; }
    loading = true;
    var controller = new AbortController(), timeout = setTimeout(function () { controller.abort(); }, 10000);
    fetch("/api/dispatch/map", { cache: "no-store", signal: controller.signal }).then(function (r) {
      if (!r.ok) { throw new Error(r.status === 401 || r.status === 403 ? "Sign in to Dispatch to view live locations." : "Map updates are unavailable. Retrying…"); }
      return r.json();
    }).then(function (data) {
      snapshot = Object.assign({rides:[],drivers:[],demo_rides:[],demo_drivers:[]}, data); snapshotReceived = Date.now();
      updateSelector(); render();
    }).catch(function (error) {
      render();
      status.textContent = (error.name === "AbortError" ? "Map update timed out. Retrying…" : error.message) + " Previous positions may be out of date.";
    }).then(function () {
      clearTimeout(timeout);
      loading = false;
      if (refreshQueued) { refreshQueued = false; refresh(); }
    });
  }
  function focusRide(id) {
    if (!allMapRides().some(function (r) { return r.id === id; })) { refresh(); return; }
    selectedId = id; selector.value = id; render(); fitView(true);
    $("dispatchMapCard").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function focusDriver(name) {
    var driver = snapshot.drivers.find(function (d) { return d.name === name; });
    if (!driver || !point(driver.coords) || !driver.location_at) { status.textContent = name + " has not shared a location yet."; return; }
    if (!driver.active) { $("mapShowOffline").checked = true; }
    $("mapShowDrivers").checked = true;
    map.addLayer(driverLayer); render();
    map.setView(driver.coords, 15, { animate: false });
    if (markers["driver:" + name]) { markers["driver:" + name].marker.openPopup(); }
    $("dispatchMapCard").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  selector.addEventListener("change", function () { selectedId = selector.value; render(); fitView(!!selectedId); });
  $("mapFitAll").addEventListener("click", function () { selectedId = ""; selector.value = ""; render(); fitView(false); });
  $("mapShowOffline").addEventListener("change", render);
  $("mapDispatchLocation").addEventListener("click", function () {
    var button = this;
    if (localWatch !== null) {
      navigator.geolocation.clearWatch(localWatch); localWatch = null; localPosition = null;
      button.textContent = "Show my location"; button.setAttribute("aria-pressed", "false"); render(); return;
    }
    if (!navigator.geolocation) { status.textContent = "This browser cannot provide your dispatch location."; return; }
    button.textContent = "Locating…";
    localWatch = navigator.geolocation.watchPosition(function (position) {
      var firstFix = !localPosition;
      localPosition = { coords: [position.coords.latitude, position.coords.longitude], accuracy: position.coords.accuracy, at: position.timestamp };
      button.textContent = "Hide my location"; button.setAttribute("aria-pressed", "true"); render();
      if (firstFix) { map.setView(localPosition.coords, 13, { animate: false }); }
    }, function (error) {
      navigator.geolocation.clearWatch(localWatch); localWatch = null; localPosition = null;
      button.textContent = "Show my location"; button.setAttribute("aria-pressed", "false"); render();
      status.textContent = error.code === 1 ? "Location permission was denied. Allow location access in your browser to show Dispatch on the map." : "Your dispatch location is unavailable. Try again when the device has a location fix.";
    }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
  });
  $("mapFullscreen").addEventListener("click", function () {
    var card = $("dispatchMapCard");
    if (document.fullscreenElement) { document.exitFullscreen(); }
    else if (card.requestFullscreen) { card.requestFullscreen().catch(function () {}); }
  });
  document.addEventListener("fullscreenchange", function () { setTimeout(function () { map.invalidateSize(); }, 100); });
  map.on("overlayadd", function () { if (!fitted) { fitView(false); } });
  if (window.ResizeObserver) { new ResizeObserver(function () { map.invalidateSize(); }).observe(canvas); }
  window.addEventListener("focus", refresh);
  window.NightRiderDispatchMap = { refresh: refresh, focusRide: focusRide, focusDriver: focusDriver };
  setInterval(function () { if (!document.hidden) { refresh(); } }, 5000);
  refresh();
})();
