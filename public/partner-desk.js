/* Operator-facing Partner Desk. Render untrusted strings as text, never HTML. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const message = $("deskMessage");
  const workspace = $("deskWorkspace");
  const date = (value) => value ? new Date(value * 1000).toLocaleString() : "—";
  const text = (tag, value, className) => {
    const el = document.createElement(tag);
    el.textContent = String(value == null ? "" : value);
    if (className) el.className = className;
    return el;
  };
  const button = (title, fn) => {
    const b = text("button", title);
    b.type = "button";
    b.addEventListener("click", fn);
    return b;
  };
  const line = (parent, tag, value, className) => parent.appendChild(text(tag, value, className));
  const error = (err) => { message.textContent = err.message || "Request failed."; };
  async function request(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed (" + response.status + ")");
    return result;
  }
  function showSecret(key) {
    $("partnerSecret").textContent = key;
    $("partnerSecretBox").classList.remove("partner-hidden");
  }
  function renderPartners(partners) {
    const list = $("partnerList");
    list.replaceChildren();
    if (!partners.length) line(list, "p", "No verified transportation partners yet.", "partner-muted");
    partners.forEach(p => {
      const row = document.createElement("div");
      row.className = "partner-entry";
      line(row, "strong", p.name);
      line(row, "div", p.contact || "No contact listed", "partner-small");
      line(row, "div", p.enabled ? "Approved · access active" : "Access disabled", "partner-status");
      const actions = document.createElement("div");
      actions.className = "partner-actions";
      actions.appendChild(button(p.enabled ? "Disable" : "Re-enable", async () => {
        if (!confirm((p.enabled ? "Disable " : "Re-enable ") + p.name + " partner access?")) return;
        try {
          await request("/api/partner-desk/partners/" + encodeURIComponent(p.id) + "/enabled", {enabled: !p.enabled});
          await refresh();
        } catch (e) { error(e); }
      }));
      actions.appendChild(button("Rotate key", async () => {
        if (!confirm("Rotate " + p.name + " access key? Its old key will stop working immediately.")) return;
        try {
          const data = await request("/api/partner-desk/partners/" + encodeURIComponent(p.id) + "/rotate", {});
          showSecret(data.access_token_once);
          message.textContent = "New key issued for " + p.name + ". Copy it securely.";
          await refresh();
        } catch (e) { error(e); }
      }));
      row.appendChild(actions);
      list.appendChild(row);
    });
  }
  function renderOffers(offers) {
    const list = $("offerList");
    list.replaceChildren();
    if (!offers.length) line(list, "p", "No submitted offers yet.", "partner-muted");
    offers.forEach(o => {
      const row = document.createElement("div");
      row.className = "partner-entry";
      line(row, "strong", o.partner_name + " · " + o.reference);
      line(row, "div", o.pickup + " → " + o.dropoff);
      line(row, "div", "Pickup: " + date(o.pickup_at) + " · " + o.passengers + " passenger(s) · " + o.bags + " bag(s)", "partner-small");
      line(row, "div", "Proposed payout: $" + Number(o.payout).toFixed(2) + " · " + o.status.replaceAll("_", " "), "partner-status");
      if (o.notes) line(row, "p", "Instructions: " + o.notes, "partner-small");
      if (o.status === "submitted" || o.status === "awaiting_partner") {
        const actions = document.createElement("div");
        actions.className = "partner-actions";
        if (o.status === "submitted") actions.appendChild(button("Accept proposed terms", () => decide(o, "accept")));
        actions.appendChild(button("Decline", () => decide(o, "decline")));
        row.appendChild(actions);
      }
      list.appendChild(row);
    });
  }
  function renderEvents(events) {
    const list = $("eventList");
    list.replaceChildren();
    if (!events.length) line(list, "p", "No events yet.");
    events.slice().reverse().forEach(e => line(list, "div", date(e.at) + " · " + e.type.replaceAll("_", " ")));
  }
  async function decide(o, action) {
    if (!confirm((action === "accept" ? "Accept these terms? Partner acknowledgment will still be required. " : "Decline this offer? ") + "No real ride will be booked.")) return;
    try {
      await request("/api/partner-desk/offers/" + encodeURIComponent(o.id) + "/" + action, {revision: o.revision});
      message.textContent = "Offer " + (action === "accept" ? "accepted; awaiting partner acknowledgment." : "declined.");
      await refresh();
    } catch (e) { error(e); await refresh(); }
  }
  async function refresh() {
    try {
      const data = await request("/api/partner-desk");
      workspace.classList.remove("partner-hidden");
      renderPartners(data.partners);
      renderOffers(data.offers);
      renderEvents(data.events);
      if (message.textContent.startsWith("Checking")) message.textContent = "Partner Desk ready · software demo only.";
    } catch (e) { workspace.classList.add("partner-hidden"); error(e); }
  }
  $("hideSecret").addEventListener("click", () => {
    $("partnerSecret").textContent = "";
    $("partnerSecretBox").classList.add("partner-hidden");
  });
  $("partnerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const data = await request("/api/partner-desk/partners", {
        name: $("partnerName").value, contact: $("partnerContact").value
      });
      showSecret(data.access_token_once);
      form.reset();
      message.textContent = "Partner approved. Copy their one-time key securely.";
      await refresh();
    } catch (e) { error(e); }
    finally { submit.disabled = false; }
  });
  refresh();
})();