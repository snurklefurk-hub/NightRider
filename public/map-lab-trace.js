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
  return { parseCsv };
});
