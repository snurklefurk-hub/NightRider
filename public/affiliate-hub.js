/* Invite-only partner preview: the token lives only in memory for this tab. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const message = $("affiliateMessage");
  let partnerKey = "";
  const demoMode = new URLSearchParams(window.location.search).get("demo") === "1";
  let demoPartnerId = null;
  function selectDemoPartner() {
    const partners = window.NightRiderPartnerDemo.partners();
    const picker = $("demoPartnerPick");
    if (!partners.some(p => p.id === demoPartnerId)) demoPartnerId = partners[0] && partners[0].id;
    picker.replaceChildren();
    partners.forEach(p => {
      const option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.name;
      picker.appendChild(option);
    });
    if (demoPartnerId) picker.value = demoPartnerId;
  }
  const date = (value) => value ? new Date(value * 1000).toLocaleString() : "—";
  const text = (tag, value, className) => {
    const el = document.createElement(tag);
    el.textContent = String(value == null ? "" : value);
    if (className) el.className = className;
    return el;
  };
  const line = (parent, tag, value, cls) => parent.appendChild(text(tag, value, cls));
  const button = (title, fn) => {
    const el = text("button", title);
    el.type = "button";
    el.addEventListener("click", fn);
    return el;
  };
  async function request(path, body) {
    if (demoMode) return window.NightRiderPartnerDemo.api(path, body, demoPartnerId);
    const result = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store", credentials: "omit",
      headers: { "Content-Type": "application/json", "X-NR-Partner-Token": partnerKey },
      ...(body === undefined ? {} : {body: JSON.stringify(body)})
    });
    const data = await result.json();
    if (!result.ok) throw new Error(data.error || "Request failed (" + result.status + ")");
    return data;
  }
  function error(e) { message.textContent = e.message || "Request failed."; }
  async function refresh() {
    if (demoMode) selectDemoPartner();
    const data = await request("/api/affiliate-hub");
    $("partnerIdentity").textContent = (demoMode ? "Simulating " : "Signed in as ") + data.partner.name;
    const list = $("affiliateOffers");
    list.replaceChildren();
    if (!data.offers.length) line(list, "p", "No offers yet. Submit an authorized simulation to begin.", "partner-muted");
    data.offers.forEach(o => {
      const row = document.createElement("div");
      row.className = "partner-entry";
      line(row, "strong", o.reference + " · " + o.status.replaceAll("_", " "));
      line(row, "div", o.pickup + " → " + o.dropoff);
      line(row, "div", date(o.pickup_at) + " · $" + Number(o.payout).toFixed(2) + " proposed payout", "partner-small");
      if (o.status === "submitted" || o.status === "awaiting_partner") {
        const actions = document.createElement("div");
        actions.className = "partner-actions";
        if (o.status === "awaiting_partner") actions.appendChild(button("Acknowledge terms (simulation)", () => decide(o, "confirm")));
        actions.appendChild(button("Withdraw offer", () => decide(o, "withdraw")));
        row.appendChild(actions);
      }
      if (o.status === "agreed_preview") line(row, "p", "Terms acknowledged · software simulation only. This is NOT a confirmed ride.", "partner-small");
      list.appendChild(row);
    });
    $("affiliateLogin").classList.add("partner-hidden");
    $("affiliateWorkspace").classList.remove("partner-hidden");
  }
  async function decide(o, action) {
    if (!confirm((action === "confirm" ? "Acknowledge these terms? " : "Withdraw this proposal? ") + "No real ride will be booked.")) return;
    try {
      await request("/api/affiliate-hub/offers/" + encodeURIComponent(o.id) + "/" + action, {revision: o.revision});
      await refresh();
      message.textContent = action === "confirm" ? "Terms acknowledged in simulation. No ride created." : "Offer withdrawn.";
    } catch (e) { error(e); try { await refresh(); } catch (_) {} }
  }
  $("keyForm").addEventListener("submit", async e => {
    e.preventDefault();
    partnerKey = $("partnerKey").value.trim();
    $("partnerKey").value = "";
    try {
      await refresh();
      message.textContent = "Verified partner workspace open. Software simulation only.";
    } catch (e) { partnerKey = ""; error(e); }
  });
  $("offerForm").addEventListener("submit", async e => {
    e.preventDefault();
    const form = e.currentTarget;
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const local = $("pickupAt").value;
      const parsed = new Date(local);
      if (!local || Number.isNaN(parsed.getTime())) throw new Error("Choose a valid pickup date and time.");
      const data = Object.fromEntries(new FormData(form));
      data.pickup_at = parsed.toISOString();
      delete data.pickup_at_local;
      data.passengers = Number(data.passengers);
      data.bags = Number(data.bags);
      data.payout = Number(data.payout);
      data.authorized = $("authorized").checked;
      await request("/api/affiliate-hub/offers", data);
      form.reset();
      $("passengers").value = "1";
      $("bags").value = "0";
      await refresh();
      message.textContent = "Simulated offer submitted for NightRider review. No reservation created.";
    } catch (err) { error(err); }
    finally { submit.disabled = false; }
  });
  $("refreshAffiliate").addEventListener("click", async () => {
    try { await refresh(); message.textContent = "Statuses refreshed."; } catch (e) { error(e); }
  });
  $("affiliateLogout").addEventListener("click", () => {
    if (demoMode) return;
    partnerKey = "";
    $("partnerKey").value = "";
    $("affiliateWorkspace").classList.add("partner-hidden");
    $("affiliateLogin").classList.remove("partner-hidden");
    message.textContent = "Access closed for this tab.";
  });
  if (demoMode) {
    $("affiliateLogin").classList.add("partner-hidden");
    $("affiliateDemoControls").classList.remove("partner-hidden");
    $("affiliateLogout").classList.add("partner-hidden");
    $("demoPartnerPick").addEventListener("change", async () => {
      demoPartnerId = $("demoPartnerPick").value;
      try { await refresh(); message.textContent = "Viewing sample affiliate. No real bookings or accounts."; }
      catch (e) { error(e); }
    });
    $("affiliateResetDemo").addEventListener("click", async () => {
      if (!confirm("Reset all local sample partners and offers?")) return;
      window.NightRiderPartnerDemo.reset();
      demoPartnerId = null;
      try { await refresh(); message.textContent = "Sample data reset. No real records affected."; }
      catch (e) { error(e); }
    });
    refresh().then(() => {
      message.textContent = "Sample partner workspace ready. No real bookings or accounts exist.";
    }).catch(error);
  }
})();
