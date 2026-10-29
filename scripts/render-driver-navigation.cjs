/* Fictional, static navigation screenshots; never requests GPS, tiles or routes.
 * Reference: Android a063c9f VelaNavigationActivity / NavigationRoadStyle / NavigationMarker.
 * Authoring only: NODE_PATH may point at a locally available Sharp installation. */
const fs = require("node:fs");
const path = require("node:path");

const palettes = {
  light: {hud:"#E8F8FF", text:"#103D58", accent:"#0876B8", muted:"#3E6075",
    land:"#E5EEF4", water:"#C9E1EE", park:"#DBE9E4", residential:"#E8F0F6",
    building:"#D6E0E9", minor:"#B2C0CC", casing:"#8798A7", road:"#FCFEFF",
    street:"#29445A", secondary:"#547085", route:"#3F84F5", marker:"#0E2131", ring:"#499DFF"},
  dark: {hud:"#071B12", text:"#F2F0DF", accent:"#19D47B", muted:"#9BB7A5",
    land:"#373C47", water:"#252F42", park:"#35464A", residential:"#3A414B",
    building:"#424752", minor:"#69727F", casing:"#1A2130", road:"#BBC1CA",
    street:"#F1F3F7", secondary:"#AEBBCB", route:"#70B5FF", marker:"#161C28", ring:"#B1CFFF"}
};

function scene(mode) {
  const p = palettes[mode], light = mode === "light";
  const vertical = [44, 136, 228, 320, 412];
  const horizontal = [282, 372, 462, 552, 642, 732];
  const buildings = [];
  // Shared fictional city blocks; geometry is identical for both appearances.
  for (let row = 0; row < horizontal.length - 1; row++) {
    for (let col = 0; col < vertical.length - 1; col++) {
      const x = vertical[col] + 14, y = horizontal[row] + 14;
      if ((row === 1 && col === 1) || (row === 3 && col === 2)) {
        buildings.push(`<rect x="${x-3}" y="${y-3}" width="70" height="68" rx="5" fill="${p.park}"/>
          <path d="M${x+32} ${y}v62m-31-31h62" stroke="${p.minor}" stroke-width="2" opacity=".5"/>
          <circle cx="${x+32}" cy="${y+31}" r="8" fill="${p.building}"/>`);
      } else {
        for (let i = 0; i < 2; i++) for (let j = 0; j < 3; j++) {
          buildings.push(`<rect x="${x+i*33}" y="${y+j*22}" width="${22+(row+col+i)%5}" height="14" rx="1.5" fill="${p.building}"/>`);
        }
      }
    }
  }
  const roads = [...vertical.map(x => `M${x} 246V758`), ...horizontal.map(y => `M-10 ${y}H430`)];
  const lines = roads.map(d => `<path d="${d}" stroke="${p.casing}" stroke-width="14"/><path d="${d}" stroke="${p.road}" stroke-width="10"/>`).join("");
  const font = light ? "Nunito Sans, Trebuchet MS, Arial, sans-serif" : "Roboto, Arial, sans-serif";
  const buttonFill = light ? "url(#button)" : "#123A28";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="420" height="860" viewBox="0 0 420 860">
  <title>Simulated NightRider navigation · ${mode}</title>
  <desc>Fictional pickup route, next turn in 420 feet onto Bay Street. Current custom ${mode} appearance. No real GPS or travel directions.</desc>
  <defs>
    <linearGradient id="button" x2="0" y2="1"><stop stop-color="#E3F9FF"/><stop offset=".35" stop-color="#34B4E9"/><stop offset="1" stop-color="#0876B8"/></linearGradient>
    <clipPath id="map"><rect y="156" width="420" height="580"/></clipPath>
    <style>text{font-family:${font}}.street{font-size:11px;fill:${p.street};paint-order:stroke;stroke:${p.land};stroke-width:3px;stroke-linejoin:round}.district{font-size:11px;letter-spacing:1.2px;fill:${p.secondary}}</style>
  </defs>
  <rect width="420" height="860" fill="${p.hud}"/>
  <rect width="420" height="27" fill="${p.accent}"/>
  <text x="210" y="18" text-anchor="middle" font-size="10" font-weight="700" letter-spacing="1.3" fill="${light ? "#FFFFFF" : "#071B12"}">SIMULATED PREVIEW · ${mode.toUpperCase()}</text>
  <rect x="9" y="40" width="69" height="36" rx="${light ? 18 : 10}" fill="${buttonFill}" stroke="${p.accent}"/>
  <text x="43.5" y="63" text-anchor="middle" font-size="13" font-weight="600" fill="${light ? "#FFFFFF" : p.accent}">Back</text>
  <text x="91" y="62" font-size="12.5" fill="${p.accent}">NIGHTRIDER · VELA</text>
  <rect x="306" y="40" width="104" height="36" rx="${light ? 18 : 10}" fill="${buttonFill}" stroke="${p.accent}"/>
  <text x="358" y="63" text-anchor="middle" font-size="13" font-weight="600" fill="${light ? "#FFFFFF" : p.accent}">Following</text>
  <text x="12" y="105" font-size="14" fill="${p.text}">To pickup · Next turn 420 ft</text>
  <text x="12" y="139" font-size="22" fill="${p.text}">Turn right onto Bay Street</text>
  <g clip-path="url(#map)">
    <rect y="156" width="420" height="580" fill="${p.land}"/>
    <path d="M0 156H420V216C334 240 262 212 190 224S61 222 0 244Z" fill="${p.water}"/>
    <text x="103" y="190" class="district" transform="rotate(-3 103 190)">SAVANNAH RIVER</text>
    <path d="M0 255H420V758H0Z" fill="${p.residential}"/>
    ${buildings.join("")}
    <path d="M0 240C140 222 280 244 420 229" fill="none" stroke="${p.minor}" stroke-width="5"/>
    <g fill="none">${lines}</g>
    <path d="M228 752V282H360V248" fill="none" stroke="#141D2E" stroke-width="17" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="M228 752V282H360V248" fill="none" stroke="${p.route}" stroke-width="10" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="82" y="270" class="street">Bay Street</text>
    <text x="250" y="360" class="street">Bryan Street</text>
    <text x="250" y="450" class="street">Congress Street</text>
    <text x="55" y="540" class="street">Broughton Street</text>
    <text x="251" y="630" class="street">State Street</text>
    <text x="251" y="720" class="street">York Street</text>
    <text x="124" y="695" class="street" transform="rotate(-90 124 695)">Whitaker Street</text>
    <text x="307" y="595" class="street" transform="rotate(-90 307 595)">Abercorn Street</text>
    <text x="183" y="424" text-anchor="middle" class="district" style="font-size:8px;letter-spacing:.4px">SQUARE</text>
    <circle cx="360" cy="248" r="10" fill="${p.route}" stroke="#FFFFFF" stroke-width="3"/>
    <rect x="286" y="214" width="77" height="24" rx="12" fill="${p.hud}"/>
    <text x="324.5" y="230" text-anchor="middle" font-size="11" fill="${p.text}">Demo pickup</text>
    <circle cx="228" cy="627" r="22" fill="${p.marker}"/>
    <circle cx="228" cy="627" r="21" fill="none" stroke="${p.ring}" stroke-width="3.5"/>
    <path d="M228 611L240 639L228 632L216 639Z" fill="#FFFFFF"/>
    <rect x="10" y="700" width="90" height="25" rx="4" fill="${p.hud}"/>
    <text x="55" y="717" text-anchor="middle" font-size="10" fill="${p.muted}">Fictional map</text>
  </g>
  <text x="12" y="769" font-size="18" fill="${p.text}">1.2 mi · 5 min · 24 mph</text>
  <text x="12" y="796" font-size="13" fill="${p.text}">GPS 1s · accuracy 6 m · heading 0°</text>
  <text x="12" y="818" font-size="13" fill="${p.muted}">Route ready · simulated values</text>
  <text x="210" y="846" text-anchor="middle" font-size="10" letter-spacing=".6" fill="${p.muted}">SOFTWARE DEMO · NO TRANSPORTATION OFFERED</text>
  </svg>`;
}

async function main() {
  const sharp = require("sharp");
  const output = path.join(__dirname, "..", "public", "images", "navigation");
  for (const mode of Object.keys(palettes)) {
    await sharp(Buffer.from(scene(mode)), {density:216}).png().toFile(path.join(output, "navigation-" + mode + ".png"));
    console.log("Rendered navigation-" + mode + ".png");
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = {scene, palettes};
