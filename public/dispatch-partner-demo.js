/* Browser-local Partner Hub walkthrough inside Dispatch; never posts a real offer. */
(function () {
  "use strict";
  const panel = document.getElementById("dispatchSampleOffers");
  const list = document.getElementById("dispatchDemoOfferList");
  const info = document.getElementById("dispatchDemoOfferStatus");
  if (!panel || !list || !window.NightRiderPartnerDemo) return;
  const demo = window.NightRiderPartnerDemo;
  const make = (tag, value) => {
    const node = document.createElement(tag);
    node.textContent = String(value == null ? "" : value);
    return node;
  };
  const action = (title, handler) => {
    const btn = make("button", title);
    btn.type = "button";
    btn.addEventListener("click", handler);
    return btn;
  };
  function refresh() {
    try {
      demo.reload();
      const data = demo.api("/api/partner-desk");
      list.replaceChildren();
      if (!data.offers.length) list.appendChild(make("p", "No sample offers yet."));
      for (const offer of data.offers) {
        const entry = make("div", "");
        entry.className = "partner-entry";
        entry.appendChild(make("strong", offer.partner_name + ": " + offer.reference));
        entry.appendChild(make("p", offer.pickup + " to " + offer.dropoff));
        entry.appendChild(make("p", "Status: " + offer.status.replaceAll("_", " ") +
          " | Proposed payout: $" + Number(offer.payout).toFixed(2)));
        if (offer.status === "submitted" || offer.status === "awaiting_partner") {
          const controls = make("div", "");
          controls.className = "partner-actions";
          if (offer.status === "submitted") controls.appendChild(action("Accept sample terms", () => decide(offer, "accept")));
          controls.appendChild(action("Decline sample offer", () => decide(offer, "decline")));
          entry.appendChild(controls);
        }
        list.appendChild(entry);
      }
    } catch (error) {
      info.textContent = error.message || "Sample offers are unavailable.";
    }
  }
  function decide(offer, choice) {
    if (!window.confirm("Update this sample offer? No transportation will be arranged.")) return;
    try {
      demo.api("/api/partner-desk/offers/" + encodeURIComponent(offer.id) + "/" + choice,
        {revision: offer.revision});
      info.textContent = choice === "accept"
        ? "Sample terms accepted. The partner can acknowledge them in Partner Hub."
        : "Sample offer declined.";
    } catch (error) {
      info.textContent = error.message || "Could not update the sample.";
    }
    refresh();
  }
  document.getElementById("dispatchDemoOfferRefresh").addEventListener("click", refresh);
  document.getElementById("dispatchDemoOfferReset").addEventListener("click", function () {
    if (!window.confirm("Reset fictional Partner Hub offers in this browser?")) return;
    demo.reset();
    info.textContent = "Sample offers reset.";
    refresh();
  });
  window.addEventListener("storage", event => {
    if (event.key === "nr-affiliate-browser-demo-v1") refresh();
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  fetch("/api/auth/me", {credentials: "same-origin", cache: "no-store"})
    .then(response => response.ok ? response.json() : Promise.reject(new Error("Cannot verify Dispatch session.")))
    .then(data => {
      if (!data.user || data.user.role !== "dispatch" || data.user.is_demo !== true) return;
      panel.hidden = false;
      // Demo Dispatch sees the local walkthrough, not administrator-only real offers.
      const notice = document.getElementById("deskAccessNotice");
      const status = document.getElementById("deskMessage");
      if (notice) notice.hidden = true;
      if (status) status.hidden = true;
      refresh();
    })
    .catch(() => { /* Keep sample controls hidden unless verified as demo Dispatch. */ });
})();
