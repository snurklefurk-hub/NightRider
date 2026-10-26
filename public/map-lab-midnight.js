/* NightRider Midnight paint palette, transcribed from the approved Android
 * Map Lab applyMidnightPalette() implementation (not a new source/style).
 * Both clients load the OpenFreeMap Fiord vector style and recolor its
 * existing layers. Changes here should be reflected in Android together.
 * No raster basemap tiles, routing backend, or API key is introduced.
 */
(function (root) {
  "use strict";
  const colors = Object.freeze({
    background: "#172635",
    fills: Object.freeze({
      water: "#0D1D33",
      landuse_residential: "#1D2D3C",
      landcover_ice_shelf: "#243748",
      landcover_wood: "#1C3440",
      park: "#213A42",
      building: "#324455",
      road_area_pier: "#263747"
    }),
    lines: Object.freeze({
      waterway: "#19394B",
      park_outline: "#34576A",
      road_pier: "#263747",
      highway_path: "#3E5A72",
      highway_minor: "#536F87",
      highway_major_casing: "#3A5368",
      highway_major_inner: "#7891A7",
      highway_major_subtle: "#607D94",
      highway_motorway_casing: "#465F75",
      highway_motorway_inner: "#9BAEC2",
      highway_motorway_subtle: "#728FA7",
      tunnel_motorway_casing: "#304459",
      tunnel_motorway_inner: "#53677E"
    }),
    labels: Object.freeze({
      highway_name_other: "#CEDBE6",
      highway_ref: "#E5EFF7",
      water_name: "#829EB7",
      place_city: "#B5C7D4",
      place_city_large: "#C4D5DF",
      place_town: "#A7C0CE",
      place_suburb: "#7E96A8",
      place_village: "#7F96A8"
    }),
    halo: "#172635",
    placeOtherOpacity: 0.2
  });

  // MapLibre style.load must have fired before calling apply().
  function apply(map) {
    if (!map || typeof map.getLayer !== "function") { return []; }
    const missing = [];
    function set(id, property, value) {
      if (map.getLayer(id)) { map.setPaintProperty(id, property, value); }
      else { missing.push(id); }
    }
    set("background", "background-color", colors.background);
    Object.keys(colors.fills).forEach(id => set(id, "fill-color", colors.fills[id]));
    Object.keys(colors.lines).forEach(id => set(id, "line-color", colors.lines[id]));
    Object.keys(colors.labels).forEach(id => {
      set(id, "text-color", colors.labels[id]);
      set(id, "text-halo-color", colors.halo);
    });
    set("place_other", "text-opacity", colors.placeOtherOpacity);
    return missing;
  }

  const api = Object.freeze({ colors, apply });
  root.NightRiderMidnight = api;
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
})(typeof window !== "undefined" ? window : globalThis);
