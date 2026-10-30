/* Public inquiry helper. No server submission or local data storage.
   The visitor sends the message from their own email client. */
(function (root) {
  "use strict";
  const recipient = "carson.nightrider@gmail.com";
  const audiences = {
    rider: {
      label: "Rider",
      interest: "Hello NightRider,\n\nI'm interested in hearing when your Savannah-area ride service launches.\n\nThanks!",
      question: "Hello NightRider,\n\nI have a question about the planned rider experience:\n\n"
    },
    driver: {
      label: "Driver",
      interest: "Hello NightRider,\n\nI'm interested in future driver opportunities around Savannah. Please let me know how to stay informed.\n\nThanks!",
      question: "Hello NightRider,\n\nI have a question about the proposed driver standards or opportunities:\n\n"
    },
    partner: {
      label: "Partner",
      interest: "Hello NightRider,\n\nI'm interested in a potential future partnership for our organization.\n\nThanks!",
      question: "Hello NightRider,\n\nI have a question about your proposed partner program:\n\n"
    }
  };
  function compose(audience, kind, name, replyEmail, message) {
    if (!Object.prototype.hasOwnProperty.call(audiences, audience)) throw new Error("Unknown contact audience.");
    if (kind !== "interest" && kind !== "question") throw new Error("Unknown inquiry type.");
    const subject = "NightRider " + audiences[audience].label + " " + (kind === "interest" ? "interest" : "question");
    const body = "Name: " + name.trim() +
      "\nReply email: " + replyEmail.trim() +
      "\nRegarding: " + audiences[audience].label + " / " + kind +
      "\n\n" + message.trim() + "\n";
    return "mailto:" + recipient + "?subject=" + encodeURIComponent(subject) +
      "&body=" + encodeURIComponent(body);
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { compose, audiences, recipient };
  if (!root || !root.document) return;
  function mount() {
    root.document.querySelectorAll("form[data-nr-contact]").forEach(function (form) {
      const audience = form.dataset.nrContact;
      if (!Object.prototype.hasOwnProperty.call(audiences, audience)) return;
      const kind = form.querySelector('[name="kind"]');
      const message = form.querySelector('[name="message"]');
      const name = form.querySelector('[name="name"]');
      const replyEmail = form.querySelector('[name="email"]');
      const status = form.parentElement.querySelector(".nr-contact-status");
      let previousPreset = audiences[audience][kind.value];
      if (!message.value.trim()) message.value = previousPreset;
      kind.addEventListener("change", function () {
        if (message.value === previousPreset) message.value = audiences[audience][kind.value];
        previousPreset = audiences[audience][kind.value];
      });
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!form.reportValidity()) return;
        if (status) status.textContent = "Your email app should open with a draft. Review it and press Send there. Nothing was submitted through this website.";
        root.location.href = compose(audience, kind.value, name.value, replyEmail.value, message.value);
      });
    });
  }
  if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", mount, { once: true });
  else mount();
})(typeof window !== "undefined" ? window : null);
