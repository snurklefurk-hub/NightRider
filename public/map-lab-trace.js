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
  function summarize(fixes) {
    if (!Array.isArray(fixes) || fixes.length === 0) return null;
    const radians = degrees => degrees * Math.PI / 180;
    let distanceM = 0, largestGapS = 0, inaccurate = 0;
    for (let i = 0; i < fixes.length; i++) {
      const p = fixes[i];
      if (p.accuracyM > 30) inaccurate++;
      if (!i) continue;
      const q = fixes[i - 1];
      const a = radians(p.lat - q.lat), b = radians(p.lon - q.lon);
      const h = Math.sin(a / 2) ** 2 +
        Math.cos(radians(q.lat)) * Math.cos(radians(p.lat)) * Math.sin(b / 2) ** 2;
      const segment = 12742000 * Math.asin(Math.min(1, Math.sqrt(h)));
      // Reject obvious GPS jumps from distance totals, but retain raw trail.
      const elapsed = (p.epochMs - q.epochMs) / 1000;
      largestGapS = Math.max(largestGapS, elapsed);
      if (elapsed > 0 && segment / elapsed <= 55 && q.accuracyM <= 30 && p.accuracyM <= 30) {
        distanceM += segment;
      }
    }
    return {
      fixes: fixes.length,
      durationS: (fixes[fixes.length - 1].epochMs - fixes[0].epochMs) / 1000,
      distanceM, largestGapS, inaccurate,
      maxReportedSpeedMps: Math.max(...fixes.map(p => p.speedMps))
    };
  }
  return { parseCsv, summarize };
});
