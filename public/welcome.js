(function () {
  "use strict";
  var params = new URLSearchParams(location.search);
  var next = params.get("next");
  if (location.pathname.endsWith("/account.html") && (params.get("setup") === "1" || next === "/driver.html" || next === "/dispatch.html")) return;
  var key = "nightrider.welcome.seen.v1";
  var seen = false;
  try { seen = !!localStorage.getItem(key); } catch (error) { /* Show once per page when storage is unavailable. */ }

  var style = document.createElement("style");
  style.textContent = `
    .nr-welcome { width:min(92vw, 580px); max-height:min(90vh, 780px); overflow:auto; border:1px solid #35d994; border-radius:18px; padding:0; color:#e8f7ea; background:#0c2016; box-shadow:0 22px 90px #000b; }
    .nr-welcome::backdrop { background:rgba(2,13,8,.78); }
    .nr-welcome-inner { padding:clamp(22px,5vw,38px); }
    .nr-welcome-kicker { color:#45e6a0; text-transform:uppercase; letter-spacing:.2em; font-size:.72rem; font-weight:700; margin:0 0 12px; }
    .nr-welcome h2 { color:#f2faec; font-size:clamp(1.75rem,5vw,2.4rem); line-height:1.06; margin:0 0 12px; text-transform:none; letter-spacing:0; }
    .nr-welcome-intro { color:#c3d8c7; line-height:1.5; margin:0 0 20px; }
    .nr-welcome-list { display:grid; gap:10px; margin:0 0 20px; padding:0; list-style:none; }
    .nr-welcome-list li { background:#112d1e; border:1px solid #295a3b; border-radius:10px; padding:11px 14px; line-height:1.4; color:#bcd0be; font-size:.9rem; }
    .nr-welcome-list strong { color:#eaf8e9; display:block; margin-bottom:2px; }
    .nr-welcome-pilot { color:#f5c77b; font-size:.82rem; line-height:1.4; margin:0 0 18px; }
    .nr-welcome .nr-welcome-button { width:100%; margin:0; }
    .nr-welcome-open { font-size:.72rem; padding:.4rem .65rem; min-height:0; }
  `;
  document.head.appendChild(style);
  var dialog = document.createElement("dialog");
  dialog.className = "nr-welcome";
  dialog.setAttribute("aria-labelledby", "nrWelcomeTitle");
  dialog.setAttribute("aria-describedby", "nrWelcomeIntro");
  dialog.innerHTML = `<div class="nr-welcome-inner">
    <p class="nr-welcome-kicker">A different kind of ride</p>
    <h2 id="nrWelcomeTitle">Welcome to NightRider</h2>
    <p class="nr-welcome-intro" id="nrWelcomeIntro">An alternative to the big guys. No surging, no surprises, no downloads, no Indians.</p>
    <ul class="nr-welcome-list">
      <li><strong>Real dispatch, real support</strong>With a dispatcher always on duty and always just a text away.</li>
      <li><strong>Safety during the ride</strong>We don't do calls, at all. Less distractions, less confusion. Text your driver and dispatch through the website.</li>
      <li><strong>Your data, not ours</strong>Nothing is saved on our servers except a name and ride history. All payments handled on your favorite platform or cash in person</li>
      <li><strong>Make pickup easier</strong>Search nearby places, drop a pin, or use your location. You can control location sharing.</li>
    </ul>
    <p class="nr-welcome-pilot">NightRider is currently being tested; ride availability and payment options are not yet final.</p>
    <button class="cta nr-welcome-button" type="button" id="nrWelcomeContinue">Let’s ride</button>
  </div>`;
  document.body.appendChild(dialog);
  function remember() { try { localStorage.setItem(key, "1"); } catch (error) {} }
  dialog.addEventListener("close", remember);
  dialog.querySelector("#nrWelcomeContinue").addEventListener("click", function () { dialog.close(); });
  var nav = document.querySelector("body.rider header nav");
  if (nav && typeof dialog.showModal === "function") {
    var open = document.createElement("button");
    open.type = "button"; open.className = "alt nr-welcome-open"; open.textContent = "Welcome";
    open.addEventListener("click", function () { if (!dialog.open) dialog.showModal(); });
    nav.insertBefore(open, document.getElementById("signOut"));
  }
  if (!seen && typeof dialog.showModal === "function") dialog.showModal();
})();
