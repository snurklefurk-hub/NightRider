(function () {
  "use strict";
  var panel = document.getElementById("riderLocationPanel");
  var toggle = document.getElementById("riderLocationShare");
  var message = document.getElementById("riderLocationMessage");
  if (!panel || !toggle || !message) { return; }
  var rideId = null, watchId = null, timer = null, enabled = false;
  var generation = 0, latest = null, pending = false, lastSent = 0;
  var writes = Promise.resolve();
  var sharingId = null;

  function savedChoice() {
    try { return localStorage.getItem("nightrider.locationSharing." + rideId); }
    catch (error) { return null; }
  }
  function rememberChoice(on) {
    if (!rideId) { return; }
    try { localStorage.setItem("nightrider.locationSharing." + rideId, on ? "on" : "off"); }
    catch (error) { /* Sharing still works when browser storage is unavailable. */ }
  }

  function enqueue(id, body, checkGeneration) {
    writes = writes.catch(function () {}).then(function () {
      if (checkGeneration != null && (!enabled || generation !== checkGeneration)) { return; }
      return fetch("/api/rides/" + encodeURIComponent(id) + "/location", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), keepalive: true
      }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) { throw new Error(data.error || "Could not share your location."); }
          return data;
        });
      });
    });
    return writes;
  }

  function stop(text, notify) {
    var previousId = rideId;
    var previousSharingId = sharingId;
    var wasEnabled = enabled;
    enabled = false; generation += 1; toggle.checked = false;
    latest = null; lastSent = 0; pending = false; sharingId = null;
    if (watchId !== null && navigator.geolocation) { navigator.geolocation.clearWatch(watchId); }
    watchId = null;
    if (timer !== null) { clearInterval(timer); timer = null; }
    message.textContent = text || "Live sharing is off. Dispatch keeps your last shared point until the ride ends.";
    if (notify !== false && previousId && wasEnabled) {
      enqueue(previousId, { sharing: false, sharing_id: previousSharingId }).catch(function () {
        if (!enabled) { message.textContent = "Live updates stopped on this device. Dispatch may still show your last known point."; }
      });
    }
  }

  function fail(error) {
    if (!enabled) { return; }
    if (error && error.code === 1) {
      rememberChoice(false);
      stop("Location permission was denied. You can continue your ride without sharing.");
    } else {
      message.textContent = "Waiting for a location fix. Your ride can continue while we retry.";
    }
  }

  function publish() {
    if (!enabled || !rideId || !latest || pending || Date.now() - lastSent < 9000) { return; }
    if (Date.now() - latest.timestamp > 110000) {
      message.textContent = "Waiting for a fresh location fix.";
      return;
    }
    var id = rideId, token = generation, fix = latest;
    pending = true; lastSent = Date.now();
    enqueue(id, {
      sharing: true,
      sharing_id: sharingId,
      coords: { lat: fix.coords.latitude, lng: fix.coords.longitude },
      accuracy: fix.coords.accuracy,
      location_at: fix.timestamp / 1000
    }, token).then(function () {
      if (enabled && token === generation) {
        message.textContent = "Sharing with Dispatch · updated " + new Date(fix.timestamp).toLocaleTimeString();
      }
    }).catch(function (error) {
      if (enabled && token === generation) { message.textContent = error.message + " Retrying…"; }
    }).then(function () { if (token === generation) { pending = false; } });
  }

  function receive(position) { if (enabled) { latest = position; publish(); } }

  function start() {
    if (enabled) { toggle.checked = true; return; }
    if (!rideId || !navigator.geolocation) {
      toggle.checked = false;
      message.textContent = "This browser cannot share location. Your ride can continue without it.";
      return;
    }
    enabled = true; generation += 1; lastSent = 0;
    toggle.checked = true;
    sharingId = window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2);
    message.textContent = "Waiting for your permission and a location fix…";
    watchId = navigator.geolocation.watchPosition(receive, fail, {
      enableHighAccuracy: true, maximumAge: 10000, timeout: 20000
    });
    timer = setInterval(function () {
      if (!latest || Date.now() - latest.timestamp > 20000) {
        navigator.geolocation.getCurrentPosition(receive, fail, {
          enableHighAccuracy: true, maximumAge: 10000, timeout: 15000
        });
      } else { publish(); }
    }, 10000);
  }

  toggle.addEventListener("change", function () {
    if (!toggle.checked) {
      var turnOff = window.confirm("Turn off live location sharing? This may make pickup more difficult in congested or busy areas. Dispatch will keep your last known point for this ride, and your driver will use the pickup address you selected.");
      if (!turnOff) { toggle.checked = true; return; }
      rememberChoice(false);
      stop();
    } else {
      rememberChoice(true);
      start();
    }
  });

  window.addEventListener("nightrider:ride", function (event) {
    var ride = event.detail;
    var active = ride && ride.id && ride.status !== "completed" && ride.status !== "cancelled";
    var nextRideId = active ? ride.id : null;
    var changed = nextRideId !== rideId;
    if (!active || changed) { stop("Live location is off."); }
    rideId = nextRideId;
    panel.hidden = !active;
    if (active && changed && savedChoice() !== "off") { start(); }
  });
  window.addEventListener("pageshow", function (event) {
    if (event.persisted && rideId && savedChoice() !== "off") { start(); }
  });
  window.addEventListener("pagehide", function () {
    if (enabled && rideId && navigator.sendBeacon) {
      var sent = navigator.sendBeacon("/api/rides/" + encodeURIComponent(rideId) + "/location",
        new Blob([JSON.stringify({ sharing: false, sharing_id: sharingId })], { type: "application/json" }));
      stop(null, !sent);
    } else { stop(); }
  });
})();
