/* PUBLIC SOFTWARE DEMO ONLY. Browser-local, fictitious data, NO server API calls.
 * Keeping the demo behind a separate adapter makes it impossible for demo
 * actions to mutate the actual affiliate store or obtain operational keys.
 */
(function (root) {
  "use strict";
  const KEY = "nr-affiliate-browser-demo-v1";
  let memory = null;
  const now = () => Date.now() / 1000;
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const fail = (message) => { throw new Error(message); };
  const id = () => "demo-" + Math.random().toString(36).slice(2, 10);
  const sample = () => {
    const created = now();
    const partner = {id: "demo-coastal", name: "Coastal Transport (Sample)", contact: "Sample dispatcher",
      enabled: true, verified: true, created_at: created};
    const offer = {id: "demo-offer-1", partner_id: partner.id, partner_name: partner.name,
      reference: "SAMPLE-101", pickup: "Resort main entrance, Hilton Head Island",
      dropoff: "Coligny Beach Park", pickup_at: created + 86400,
      passengers: 2, bags: 1, payout: 42.00, notes: "Sample trip: no actual passenger",
      authorized: true, status: "submitted", revision: 1,
      created_at: created, updated_at: created, expires_at: created + 86400};
    return {partners: [partner], offers: [offer], events: [
      {id: id(), type: "offer_submitted", actor: partner.id, offer_id: offer.id, at: created}
    ]};
  };
  function storage() {
    try { return root.localStorage; } catch (_) { return null; }
  }
  function read() {
    if (memory) return memory;
    const store = storage();
    try {
      const raw = store && store.getItem(KEY);
      if (raw) {
        const data = JSON.parse(raw);
        if (Array.isArray(data.partners) && Array.isArray(data.offers) &&
            Array.isArray(data.events)) return (memory = data);
      }
    } catch (_) { /* Browser storage may be disabled or older data invalid. */ }
    return (memory = sample());
  }
  function write(data) {
    memory = data;
    try { const store = storage(); if (store) store.setItem(KEY, JSON.stringify(data)); }
    catch (_) { /* The current tab can still run a transient demo. */ }
  }
  function reset() {
    memory = sample();
    write(memory);
    return copy(memory);
  }
  function log(data, type, actor, offer) {
    data.events.push({id: id(), type: type, actor: actor, offer_id: offer && offer.id, at: now()});
    data.events = data.events.slice(-100);
  }
  function current(offer) {
    const due = offer.status === "awaiting_partner" ? offer.confirmation_due_at : offer.expires_at;
    if ((offer.status === "submitted" || offer.status === "awaiting_partner") && now() >= due) {
      return {...offer, status: "expired"};
    }
    return offer;
  }
  function transition(data, offerId, action, revision, partnerId) {
    const offer = data.offers.find(o => o.id === offerId && (!partnerId || o.partner_id === partnerId));
    if (!offer) fail("This sample offer is unavailable.");
    if (!Number.isInteger(revision) || offer.revision !== revision) fail("Offer changed. Refresh and retry.");
    const active = current(offer);
    if (active.status === "expired") {
      offer.status = "expired";
      offer.revision++;
      offer.updated_at = now();
      log(data, "offer_expired", "demo", offer);
      write(data);
      fail("Offer expired. Reset the demo to start again.");
    }
    const admin = !partnerId;
    const changes = {
      "submitted:accept:admin": "awaiting_partner",
      "submitted:decline:admin": "declined",
      "submitted:withdraw:partner": "withdrawn",
      "awaiting_partner:confirm:partner": "agreed_preview",
      "awaiting_partner:withdraw:partner": "withdrawn",
      "awaiting_partner:decline:admin": "declined"
    };
    const target = changes[[offer.status, action, admin ? "admin" : "partner"].join(":")];
    if (!target) fail("This offer cannot perform that action.");
    offer.status = target;
    offer.updated_at = now();
    offer.revision++;
    if (target === "awaiting_partner") offer.confirmation_due_at = Math.min(now() + 300, offer.pickup_at);
    log(data, "offer_" + target, admin ? "demo-dispatch" : partnerId, offer);
    write(data);
    return {offer: copy(offer)};
  }
  function offerFromForm(data, partner, payload) {
    if (!partner || !partner.enabled || !partner.verified) fail("Choose an enabled sample affiliate.");
    const pickup = String(payload.pickup || "").trim().slice(0, 180);
    const dropoff = String(payload.dropoff || "").trim().slice(0, 180);
    const ref = String(payload.reference || "").trim().slice(0, 80);
    if (pickup.length < 5 || dropoff.length < 5 || ref.length < 2) fail("Reference, pickup and destination are required.");
    if (data.offers.some(o => o.partner_id === partner.id && o.reference.toLowerCase() === ref.toLowerCase()))
      fail("This sample reservation reference already exists.");
    const passengers = Number(payload.passengers), bags = Number(payload.bags), payout = Number(payload.payout);
    if (!Number.isInteger(passengers) || passengers < 1 || passengers > 4 ||
        !Number.isInteger(bags) || bags < 0 || bags > 4) fail("Use 1–4 passengers and 0–4 bags.");
    if (!Number.isFinite(payout) || payout <= 0 || payout > 10000) fail("Enter a valid proposed payout.");
    if (payload.authorized !== true) fail("Sample passenger booking authority must be attested.");
    const pickup_at = new Date(payload.pickup_at).getTime() / 1000;
    if (!Number.isFinite(pickup_at) || pickup_at <= now() || pickup_at > now() + 90 * 86400)
      fail("Pickup must be within the next 90 days.");
    if (data.offers.length >= 30) fail("Demo is full. Reset it to start over.");
    const stamp = now();
    const offer = {id: id(), partner_id: partner.id, partner_name: partner.name,
      reference: ref, pickup, dropoff, pickup_at, passengers, bags, payout: Math.round(payout * 100) / 100,
      notes: String(payload.notes || "").trim().slice(0, 800), authorized: true,
      status: "submitted", revision: 1, created_at: stamp, updated_at: stamp,
      expires_at: Math.min(stamp + 7 * 86400, pickup_at)};
    data.offers.unshift(offer);
    log(data, "offer_submitted", partner.id, offer);
    write(data);
    return {offer: copy(offer)};
  }
  function api(path, payload, partnerId) {
    const data = read();
    const parts = path.split("/").filter(Boolean);
    const admin = parts[1] === "partner-desk";
    if (parts[0] !== "api" || (parts[1] !== "partner-desk" && parts[1] !== "affiliate-hub"))
      fail("Unknown demo action.");
    if (admin) {
      if (parts.length === 2) return copy({partners: data.partners, offers: data.offers.map(current), events: data.events});
      if (parts[2] === "partners" && parts.length === 3 && payload) {
        if (data.partners.length >= 12) fail("Demo partner limit reached. Reset to begin again.");
        const name = String(payload.name || "").trim().slice(0, 120);
        if (name.length < 2) fail("Organization name is required.");
        const partner = {id: id(), name, contact: String(payload.contact || "").trim().slice(0, 160),
          enabled: true, verified: true, created_at: now()};
        data.partners.push(partner);
        log(data, "partner_approved", "demo-dispatch");
        write(data);
        return {partner: copy(partner), access_token_once: "DEMO-ONLY-NO-REAL-ACCESS"};
      }
      if (parts[2] === "partners" && parts.length === 5 && payload) {
        const partner = data.partners.find(p => p.id === parts[3]);
        if (!partner) fail("Sample partner not found.");
        if (parts[4] === "enabled") {
          if (typeof payload.enabled !== "boolean") fail("Invalid sample account status.");
          partner.enabled = payload.enabled;
          log(data, partner.enabled ? "partner_enabled" : "partner_disabled", "demo-dispatch");
          write(data);
          return {partner: copy(partner)};
        }
        if (parts[4] === "rotate") return {access_token_once: "DEMO-ONLY-NO-REAL-ACCESS"};
      }
      if (parts[2] === "offers" && parts.length === 5 && payload && ["accept", "decline"].includes(parts[4]))
        return transition(data, parts[3], parts[4], payload.revision, null);
    } else {
      const partner = data.partners.find(p => p.id === partnerId && p.enabled && p.verified);
      if (!partner) fail("Sample partner disabled or unavailable. Choose another or reset the demo.");
      if (parts.length === 2) return copy({partner, offers: data.offers.filter(o => o.partner_id === partner.id).map(current)});
      if (parts[2] === "offers" && parts.length === 3 && payload)
        return offerFromForm(data, partner, payload);
      if (parts[2] === "offers" && parts.length === 5 && payload && ["confirm", "withdraw"].includes(parts[4]))
        return transition(data, parts[3], parts[4], payload.revision, partner.id);
    }
    fail("Unknown demo action.");
  }
  function partners() {
    return copy(read().partners.filter(p => p.enabled && p.verified));
  }
  // Cross-tab updates are read from localStorage, not a shared server.
  function reload() { memory = null; }
  root.NightRiderPartnerDemo = {api, partners, reset, reload};
})(typeof window === "object" ? window : this);
