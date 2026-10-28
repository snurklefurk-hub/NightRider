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
    if (rows.shift() !== "epoch_ms,latitude,longitude,accuracy_m,speed_mps") {
      throw new Error("This is not a NightRider Field Test CSV.");
    }
    if (rows.length < 1 || rows.length > 1500) {
      throw new Error("Expected between 1 and 1,500 recorded GPS fixes.");
    }
    let previous = 0;
    return rows.map((row, i) => {
      const fields = row.split(",");
      if (fields.length !== 5 || fields.some(field => field.trim() === "")) {
        throw new Error("Invalid GPS data at row " + (i + 2) + ".");
      }
      const [epochMs, lat, lon, accuracyM, speedMps] = fields.map(Number);
      if (![epochMs, lat, lon, accuracyM, speedMps].every(Number.isFinite) ||
          epochMs <= previous || !Number.isSafeInteger(epochMs) ||
          Math.abs(lat) > 90 || Math.abs(lon) > 180 ||
          accuracyM < 0 || accuracyM > 100000 || speedMps < 0 || speedMps > 500) {
        throw new Error("Invalid coordinates or timestamp at row " + (i + 2) + ".");
      }
      previous = epochMs;
      return { epochMs, lat, lon, accuracyM, speedMps };
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
    return { usable, ignored, accuracyLimitM };
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
      accuracyLimitM: report.accuracyLimitM,
      maxReportedSpeedMps: Math.max(...fixes.map(p => p.speedMps))
    };
  }
  return { parseCsv, analyze, summarize };
});
