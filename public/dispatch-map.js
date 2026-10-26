(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var canvas = $("dispatchMap"), status = $("dispatchMapStatus"), selector = $("mapRideSelect");
  if (!canvas || !status || !selector) { return; }
  if (!window.L) {
    status.textContent = "The map could not load. Refresh the page to try again.";
    return;
  }
  var map = L.map(canvas, { minZoom: 3, maxZoom: 19, scrollWheelZoom: false })
    .setView([32.0809, -81.0912], 12);
  var driverLayer = L.layerGroup().addTo(map), rideLayer = L.layerGroup().addTo(map);
  var riderLayer = L.layerGroup().addTo(map), dispatchLayer = L.layerGroup().addTo(map);
  var routeLayer = L.layerGroup().addTo(map);
  L.control.layers(null, {
    "Drivers": driverLayer, "Pickup / drop-off": rideLayer,
    "Riders sharing location": riderLayer, "Dispatch location": dispatchLayer,
    "Expected routes": routeLayer
  }, { collapsed: true }).addTo(map);
  L.control.scale({ imperial: true, metric: false }).addTo(map);
  map.attributionControl.addAttribution('<a href="https://project-osrm.org/">OSRM</a> · <a href="https://routing.openstreetmap.de/about.html">FOSSGIS routing</a> · <a href="https://www.openstreetmap.org/fixthemap">Fix the map</a>');
  var markers = {}, routes = {}, routeCache = {}, routeQueue = [], routeRequests = 0, nextRouteAt = 0;
  var snapshot = { drivers: [], rides: [], now: Date.now() / 1000 };
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
  function visibleRides() {
    return selectedId ? snapshot.rides.filter(function (ride) { return ride.id === selectedId; }) : snapshot.rides;
  }
  function mapTileLayer(fallback, key) {
    if (baseLayer) { map.removeLayer(baseLayer); }
    usingFallback = fallback;
    var url = fallback ? "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" :
      "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png" + (key ? "?key=" + encodeURIComponent(key) : "");
    baseLayer = L.tileLayer(url, {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' +
        (fallback ? "" : ' &copy; <a href="https://carto.com/attributions">CARTO</a>')
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

  function markerIcon(kind, color, stale) {
    color = /^#[0-9a-f]{6}$/i.test(color || "") ? color : "#8bbcff";
    var glyph = { driver: "D", pickup: "P", dropoff: "X", rider: "R", dispatch: "S" }[kind];
    return L.divIcon({
      className: "nr-map-marker" + (stale ? " is-stale" : ""),
      html: '<span class="nr-map-pin ' + kind + '" style="--pin-color:' + color + '">' + glyph + "</span>",
      iconSize: [30, 30], iconAnchor: [15, 15]
    });
  }
  function syncMarker(key, coords, kind, color, title, html, layer, used, stale) {
    if (!point(coords)) { return; }
    used[key] = true;
    var item = markers[key], signature = kind + color + !!stale;
    if (!item) {
      var marker = L.marker(coords, { icon: markerIcon(kind, color, stale), title: title, keyboard: true,
        zIndexOffset: { rider: 500, dispatch: 400, driver: 300 }[kind] || 0 });
      marker.bindPopup(html);
      marker.bindTooltip(document.createTextNode(title), { direction: "top", offset: [0, -12] });
      marker.addTo(layer);
      item = markers[key] = { marker: marker, layer: layer, signature: signature };
    } else {
      item.marker.setLatLng(coords).setPopupContent(html);
      if (signature !== item.signature) { item.marker.setIcon(markerIcon(kind, color, stale)); item.signature = signature; }
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
      color: data.fallback ? "#99aaa7" : approach ? "#ffc36b" : "#2fe9ff",
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
    snapshot.drivers.forEach(function (driver) {
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
      syncMarker("pickup:" + ride.id, ride.pickup_coords, "pickup", "#2ee6a0", "Pickup · " + title,
        info + "<br><b>Pickup:</b> " + esc(ride.pickup), rideLayer, used, false);
      syncMarker("dropoff:" + ride.id, ride.dropoff_coords, "dropoff", "#ff6f91", "Drop-off · " + title,
        info + "<br><b>Drop-off:</b> " + esc(ride.dropoff), rideLayer, used, false);
      if (ride.rider_location) {
        var fix = ride.rider_location;
        var live = riderIsLive(fix);
        var locationLabel = live ? "Live rider" : "Last known rider";
        var sharingLabel = live ? "Live location shared with Dispatch" :
          fix.sharing === false ? "Location sharing is off · last known position" : "No fresh location update · last known position";
        syncMarker("rider:" + ride.id, fix.coords, "rider", "#ffc36b", locationLabel + " · " + title,
          info + "<br>" + sharingLabel + "<br>Recorded " + esc(new Date(fix.at * 1000).toLocaleString()) + " · " + esc(age(fix.at)) +
          (fix.accuracy != null ? "<br>Accuracy: about " + Math.round(fix.accuracy) + " m" : ""), riderLayer, used, !live);
      }
    });
    if (localPosition) {
      syncMarker("dispatch", localPosition.coords, "dispatch", "#effff7", "Your dispatch location",
        "<strong>Your dispatch location</strong><br>" + esc(new Date(localPosition.at).toLocaleTimeString()) +
        "<br>Accuracy: about " + Math.round(localPosition.accuracy) + " m", dispatchLayer, used, false);
      if (!dispatcherAccuracy) {
        dispatcherAccuracy = L.circle(localPosition.coords, { color: "#effff7", weight: 1, fillOpacity: 0.06,
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
    if (selectedId && !snapshot.rides.some(function (r) { return r.id === selectedId; })) { selectedId = ""; }
    var signature = snapshot.rides.map(function (r) { return r.id + r.status + r.driver + r.rider_name; }).join("|");
    if (selector.dataset.signature !== signature) {
      selector.innerHTML = '<option value="">All active rides</option>';
      snapshot.rides.forEach(function (ride) {
        var option = document.createElement("option"); option.value = ride.id;
        option.textContent = ride.id + " · " + (ride.rider_name || "Rider") + " · " + (labels[ride.status] || ride.status);
        selector.appendChild(option);
      });
      selector.dataset.signature = signature;
    }
    selector.value = selectedId;
    if (previous && !selectedId) { $("mapRouteInfo").textContent = "That ride has ended. Showing current active rides."; }
  }
  function updateStatus() {
    var active = snapshot.drivers.filter(function (d) { return d.active; });
    var positioned = active.filter(function (d) { return point(d.coords) && d.location_at; });
    var unavailable = active.length - positioned.length;
    status.textContent = mapError || positioned.length + " of " + active.length + " online drivers located · " +
      snapshot.rides.length + " active rides · updated " + new Date(snapshot.now * 1000).toLocaleTimeString() +
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
      snapshot = data; snapshotReceived = Date.now();
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
    if (!snapshot.rides.some(function (r) { return r.id === id; })) { refresh(); return; }
    selectedId = id; selector.value = id; render(); fitView(true);
    $("dispatchMapCard").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function focusDriver(name) {
    var driver = snapshot.drivers.find(function (d) { return d.name === name; });
    if (!driver || !point(driver.coords) || !driver.location_at) { status.textContent = name + " has not shared a location yet."; return; }
    if (!driver.active) { $("mapShowOffline").checked = true; }
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
