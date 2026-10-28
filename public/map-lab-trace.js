/* Local-only parser for the exported NightRider Android Field Test CSV.
 * No network, geolocation, storage, or dispatch operations.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.NightRiderTrace = api;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";
  function parseCsv(value) {
    if (typeof value !== "string" || value.length > 250000) {
      throw new Error("Trace file is too large (250 KB maximum).");
    }
    const rows = value.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
    const oldHeader = "epoch_ms,latitude,longitude,accuracy_m,speed_mps";
    const enrichedHeader = oldHeader + ",provider,map_decision";
    const motionHeader = enrichedHeader +
      ",fusion_heading_deg,gyro_yaw_dps,linear_accel_mps2,phone_azimuth_deg";
    const header = rows.shift();
    const hasMotion = header === motionHeader;
    const hasDecisions = header === enrichedHeader || hasMotion;
    if (header !== oldHeader && !hasDecisions) {
      throw new Error("This is not a NightRider Field Test CSV.");
    }
    if (rows.length < 1 || rows.length > 1500) {
      throw new Error("Expected between 1 and 1,500 recorded GPS fixes.");
    }
    let previous = 0;
    return rows.map((row, i) => {
      const fields = row.split(",");
      if (fields.length !== (hasMotion ? 11 : hasDecisions ? 7 : 5) ||
          fields.slice(0, hasDecisions ? 7 : 5).some(field => field.trim() === "")) {
        throw new Error("Invalid GPS data at row " + (i + 2) + ".");
      }
      const [epochMs, lat, lon, accuracyM, speedMps] = fields.slice(0, 5).map(Number);
      const provider = hasDecisions ? fields[5] : null;
      const mapDecision = hasDecisions ? fields[6] : null;
      const inertial = hasMotion ? fields.slice(7).map(s =>
        s.trim() === "" ? null : Number(s)) : [null, null, null, null];
      const [fusionHeadingDeg, gyroYawDps, linearAccelMps2, phoneAzimuthDeg] = inertial;
      if (![epochMs, lat, lon, accuracyM, speedMps].every(Number.isFinite) ||
          epochMs <= previous || !Number.isSafeInteger(epochMs) ||
          Math.abs(lat) > 90 || Math.abs(lon) > 180 ||
          accuracyM < 0 || accuracyM > 100000 || speedMps < 0 || speedMps > 500 ||
          (hasDecisions && (!["gps", "network", "fused", "passive", "unknown"].includes(provider) ||
          !["accepted", "rejected", "unrated"].includes(mapDecision))) ||
          inertial.some(x => x !== null && !Number.isFinite(x)) ||
          (fusionHeadingDeg !== null && (fusionHeadingDeg < 0 || fusionHeadingDeg >= 360)) ||
          (gyroYawDps !== null && Math.abs(gyroYawDps) > 120) ||
          (linearAccelMps2 !== null && (linearAccelMps2 < 0 || linearAccelMps2 > 60)) ||
          (phoneAzimuthDeg !== null && (phoneAzimuthDeg < 0 || phoneAzimuthDeg >= 360))) {
        throw new Error("Invalid coordinates or timestamp at row " + (i + 2) + ".");
      }
      previous = epochMs;
      return { epochMs, lat, lon, accuracyM, speedMps, provider, mapDecision,
        hasMotion, fusionHeadingDeg, gyroYawDps, linearAccelMps2, phoneAzimuthDeg };
    });
  }
  const radians = degrees => degrees * Math.PI / 180;
  function metersBetween(a, b) {
    const lat = radians(b.lat - a.lat), lon = radians(b.lon - a.lon);
    const h = Math.sin(lat / 2) ** 2 +
      Math.cos(radians(a.lat)) * Math.cos(radians(b.lat)) * Math.sin(lon / 2) ** 2;
    return 12742000 * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function analyze(fixes) {
    if (!Array.isArray(fixes) || !fixes.length) {
      return { usable: [], ignored: [], accuracyLimitM: 15 };
    }
    // Enhanced exports carry the phone's actual navigation decisions.
    // Old recordings continue to use the local quality approximation.
    if (fixes.every(p => p.mapDecision === "accepted" || p.mapDecision === "rejected")) {
      return {
        usable: fixes.filter(p => p.mapDecision === "accepted"),
        ignored: fixes.filter(p => p.mapDecision === "rejected"),
        accuracyLimitM: null,
        source: "device"
      };
    }
    // Adjust for normal city GPS while rejecting isolated degraded fixes.
    const accuracies = fixes.map(p => p.accuracyM).sort((a, b) => a - b);
    const center = Math.floor(accuracies.length / 2);
    const median = accuracies.length % 2 ? accuracies[center] :
      (accuracies[center - 1] + accuracies[center]) / 2;
    const accuracyLimitM = Math.min(30, Math.max(15, median * 2));
    const usable = [], ignored = [];
    fixes.forEach(p => {
      if (p.accuracyM > accuracyLimitM) { ignored.push(p); return; }
      const previous = usable[usable.length - 1];
      if (previous) {
        const elapsed = (p.epochMs - previous.epochMs) / 1000;
        if (elapsed <= 0 || metersBetween(previous, p) / elapsed > 55) {
          ignored.push(p);
          return;
        }
      }
      usable.push(p);
    });
    return { usable, ignored, accuracyLimitM, source: "estimated" };
  }
  function summarize(fixes) {
    if (!Array.isArray(fixes) || fixes.length === 0) return null;
    const report = analyze(fixes);
    let distanceM = 0, largestGapS = 0, largestUsableGapS = 0;
    for (let i = 1; i < fixes.length; i++) {
      largestGapS = Math.max(largestGapS,
        (fixes[i].epochMs - fixes[i - 1].epochMs) / 1000);
    }
    for (let i = 1; i < report.usable.length; i++) {
      const a = report.usable[i - 1], b = report.usable[i];
      distanceM += metersBetween(a, b);
      largestUsableGapS = Math.max(largestUsableGapS,
        (b.epochMs - a.epochMs) / 1000);
    }
    return {
      fixes: fixes.length,
      durationS: (fixes[fixes.length - 1].epochMs - fixes[0].epochMs) / 1000,
      distanceM, largestGapS, largestUsableGapS,
      inaccurate: fixes.filter(p => p.accuracyM > 30).length,
      ignored: report.ignored.length,
      source: report.source,
      deviceAccepted: report.source === "device" ? report.usable.length : null,
      deviceRejected: report.source === "device" ? report.ignored.length : null,
      accuracyLimitM: report.accuracyLimitM,
      maxReportedSpeedMps: Math.max(...fixes.map(p => p.speedMps)),
      hasMotion: fixes.some(p => p.hasMotion === true),
      fusedHeadingSamples: fixes.filter(p => p.fusionHeadingDeg != null).length,
      maxAbsYawDps: fixes.some(p => p.gyroYawDps != null) ?
        Math.max(...fixes.filter(p => p.gyroYawDps != null)
          .map(p => Math.abs(p.gyroYawDps))) : null,
      maxAccelMps2: fixes.some(p => p.linearAccelMps2 != null) ?
        Math.max(...fixes.filter(p => p.linearAccelMps2 != null)
          .map(p => p.linearAccelMps2)) : null
    };
  }
  return { parseCsv, analyze, summarize };
});
