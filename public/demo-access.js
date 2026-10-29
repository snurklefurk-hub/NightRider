/* Shared gate for the closed NightRider software preview. */
(function () {
  "use strict";
  var role = document.body.getAttribute("data-demo-role");
  if (!role) { return; }
  var title = role.charAt(0).toUpperCase() + role.slice(1);
  var gate = document.createElement("div");
  gate.className = "demo-gate";
  gate.innerHTML = '<div class="demo-gate-card" role="dialog" aria-modal="true" aria-labelledby="demoGateTitle">' +
    '<p class="eyebrow">NightRider software preview</p><h1 id="demoGateTitle">' + title + ' demo access</h1>' +
    '<p>This work-in-progress is not a transportation service. Nothing here is live, and all trips are simulated.</p>' +
    '<p>Use the shared test account to explore the ' + title.toLowerCase() + ' experience.</p>' +
    '<label>Username<input id="demoUser" autocomplete="username" value="DEMO"></label>' +
    '<label>Password<input id="demoPass" type="password" autocomplete="current-password" value="PASSWORD"></label>' +
    '<button type="button" id="demoSignIn">Enter ' + title + ' demo</button><p class="msg" id="demoError"></p>' +
    '<p class="tiny muted">Demo credentials: DEMO / PASSWORD. No account creation is available.</p></div>';
  document.body.appendChild(gate);
  function show() { gate.hidden = false; document.body.classList.add("demo-locked"); }
  function hide() { gate.hidden = true; document.body.classList.remove("demo-locked"); }
  fetch("/api/demo/session", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (s) {
    if (s.signed_in && s.role === role) { hide(); } else { show(); }
  }).catch(show);
  document.getElementById("demoSignIn").addEventListener("click", function () {
    var button = this;
    button.disabled = true;
    fetch("/api/demo/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: role, username: document.getElementById("demoUser").value, password: document.getElementById("demoPass").value })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }).then(function (res) {
      button.disabled = false;
      if (!res.ok) { document.getElementById("demoError").textContent = res.j.error || "Sign-in failed."; return; }
      // Reload so the page's normal startup requests begin with its new
      // role-bound cookie rather than any unauthenticated requests made while
      // the sign-in dialog was visible.
      window.location.reload();
    }).catch(function () { button.disabled = false; document.getElementById("demoError").textContent = "Sign-in failed. Try again."; });
  });
}());
