/* NightRider role-aware messaging. Fixed controls; incoming messages never move the viewport. */
(function (root) {
  "use strict";
  function mount(options) {
    var role = options.role;
    var host = document.getElementById(options.host);
    if (!host) throw new Error("Chat host not found: " + options.host);
    var tabs = role === "dispatch" ? ["rider", "driver", "team"] :
               role === "driver" ? ["team", "dispatch", "rider"] :
               options.accountOnly ? ["account"] : ["rider"];
    var labels = { rider: role === "rider" ? "Driver + Dispatch" : "Rider",
      account: "Dispatch", driver: "Driver", dispatch: "Dispatch", team: "Team" };
    var active = tabs[0], rides = [], drivers = [], riderAccounts = [], selectedRide = "", selectedDriver = "";
    var messages = new Map(), loaded = false, seenAt = 0, fetching = false, sending = false, needHistory = false, chatEpoch = null;
    var unread = { rider: 0, driver: 0, dispatch: 0, team: 0, account: 0 };
    var rendered = new Set(), pendingId = "", pendingSignature = "";
    host.innerHTML =
      '<div class="nr-chat" aria-label="NightRider messages">' +
      '<div class="nr-chat-tabs nr-chat-tabs-' + tabs.length + '" role="group" aria-label="Message recipient">' +
      tabs.map(function (tab) { return '<button type="button" class="nr-chat-tab" data-recipient="' +
        tab + '" aria-pressed="false"><span>' + labels[tab] +
        '</span><span class="nr-chat-count" aria-hidden="true"></span></button>'; }).join("") +
      '</div>' +
      '<div class="nr-chat-target">' +
      '<label class="nr-chat-target-label" for="' + options.host + '-target">To</label>' +
      '<select id="' + options.host + '-target" class="nr-chat-select" aria-label="Select conversation"></select>' +
      '</div>' +
      '<div class="nr-chat-log chatlog" role="log" aria-label="Message history" aria-live="off"></div>' +
      '<div class="row chatrow nr-chat-compose">' +
      '<input type="text" maxlength="1000" autocomplete="off" placeholder="Message when stopped…" aria-label="Message text">' +
      '<button type="button" class="nr-chat-send">Send</button></div>' +
      '<p class="nr-chat-status tiny muted" role="status" aria-live="polite"></p>' +
      '</div>';
    var log = host.querySelector(".nr-chat-log");
    var target = host.querySelector(".nr-chat-select");
    var field = host.querySelector(".nr-chat-compose input");
    var send = host.querySelector(".nr-chat-send");
    var status = host.querySelector(".nr-chat-status");
    var buttons = Array.prototype.slice.call(host.querySelectorAll(".nr-chat-tab"));
    var caption = host.querySelector(".nr-chat-target-label");

    function itemKey(m) { return (m.message_kind || (m.ride_id ? "ride" : "team")) + ":" + m.id; }
    function kind(m) {
      if (m.message_kind === "account" || m.rider_account_id) {
        return role === "dispatch" ? "rider" : "account";
      }
      if (m.ride_id || m.message_kind === "ride") return "rider";
      return m.channel === "private" ? (role === "dispatch" ? "driver" : "dispatch") : "team";
    }
    function currentTarget() { return active === "rider" ? selectedRide : active === "driver" ? selectedDriver : ""; }
    function belongs(m) {
      if (kind(m) !== active) return false;
      if (active === "account") return m.message_kind === "account";
      if (active === "rider" && role === "dispatch") {
        return selectedRide.slice(0, 8) === "account:" ?
          m.rider_account_id === selectedRide.slice(8) :
          m.ride_id === selectedRide.slice(5);
      }
      if (active === "rider") return !!selectedRide && m.ride_id === selectedRide;
      if (active === "driver") return !!selectedDriver && m.driver === selectedDriver;
      return true;
    }
    function senderLabel(m) {
      var priv = m.message_kind === "account" ? " · Account" :
        m.audience === "rider" ? " · Rider only" :
        m.channel === "private" ? " · Private" : "";
      return (m.mine ? "You" : (m.from || "Dispatch")) + priv;
    }
    function bubble(m) {
      var wrap = document.createElement("div");
      wrap.className = "chatwrap " + (m.mine ? "me" : "them");
      wrap.dataset.key = itemKey(m);
      var line = document.createElement("div");
      var priv = m.channel === "private" || m.audience === "rider" || m.message_kind === "account";
      line.className = "chatline " + (m.mine ? "me" : "them") + (priv ? " private" : "");
      var color = /^#[0-9a-f]{6}$/i.test(m.chat_color || "") ? m.chat_color : "";
      if (color) line.style.setProperty("--sender-color", color);
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = senderLabel(m);
      if (color) who.style.color = color;
      line.appendChild(who);
      line.appendChild(document.createTextNode(m.text || ""));
      var time = document.createElement("span");
      time.className = "tiny muted";
      time.textContent = " · " + new Date(Number(m.at) * 1000).toLocaleTimeString();
      line.appendChild(time);
      wrap.appendChild(line);
      return wrap;
    }
    function ordered() {
      return Array.from(messages.values()).filter(belongs)
        .sort(function (a, b) { return Number(a.at) - Number(b.at) || itemKey(a).localeCompare(itemKey(b)); });
    }
    function render(rebuild, commanded) {
      var oldScroll = log.scrollTop;
      if (rebuild) { log.replaceChildren(); rendered.clear(); }
      ordered().forEach(function (m) {
        var key = itemKey(m);
        if (rendered.has(key)) return;
        rendered.add(key);
        log.appendChild(bubble(m));
      });
      if (commanded) log.scrollTop = log.scrollHeight;
      else if (rebuild) log.scrollTop = oldScroll;
      // No automatic scroll for new incoming messages, even if they are urgent.
    }
    function counts() {
      buttons.forEach(function (button) {
        var tab = button.dataset.recipient;
        button.setAttribute("aria-pressed", String(active === tab));
        var number = unread[tab] || 0;
        var badge = button.querySelector(".nr-chat-count");
        badge.textContent = number ? String(Math.min(number, 99)) : "";
        button.setAttribute("aria-label", labels[tab] + (number ? ", " + number + " unread" : ""));
      });
    }
    function optionsForTarget() {
      var prior = currentTarget();
      var entries = active === "rider" ?
        (role === "dispatch" ? riderAccounts.filter(function (r) { return r.enabled !== false; }).map(function (r) {
          return { value: "account:" + r.id, label: (r.display_name || "Rider") + " · Account" };
        }).concat(rides.map(function (r) {
          return { value: "ride:" + r.id, label: (r.rider_name || "Rider") + " · Ride " + r.id };
        })) : rides.map(function (r) {
          return { value: String(r.id), label: (r.rider_name || "Ride") + " · " + r.id };
        })) :
        active === "driver" ? drivers.map(function (d) {
          return { value: d.display_name || d.name || d, label: d.display_name || d.name || d };
        }) : [];
      // The selector keeps exactly the same space in every tab.
      target.replaceChildren();
      if (!entries.length) {
        var empty = document.createElement("option");
        empty.value = ""; empty.textContent = active === "team" ? "All drivers" :
          active === "account" ? "Private account messages" :
          active === "dispatch" ? "Private to Dispatch" :
          active === "driver" ? "No drivers available" : "No assigned ride";
        target.appendChild(empty);
        target.disabled = true;
      } else {
        entries.forEach(function (entry) {
          var option = document.createElement("option");
          option.value = entry.value; option.textContent = entry.label;
          target.appendChild(option);
        });
        target.disabled = role === "rider" || active === "dispatch";
      }
      var desired = prior && entries.some(function (e) { return e.value === prior; }) ? prior :
        (entries.length ? entries[0].value : "");
      if (active === "rider") selectedRide = desired;
      if (active === "driver") selectedDriver = desired;
      target.value = desired;
      caption.textContent = "To";
      if (active === "account") {
        caption.textContent = "Private to Dispatch · Between rides too";
      } else if (active === "rider" && role === "rider") {
        caption.textContent = "To Dispatch + assigned driver";
      } else if (active === "rider" && role === "driver") {
        caption.textContent = "To rider + Dispatch";
      } else if (active === "rider") {
        caption.textContent = selectedRide.slice(0, 8) === "account:" ?
          "Private account conversation" : "To rider only";
      } else if (active === "dispatch" || active === "driver") {
        caption.textContent = "Private conversation";
      } else {
        caption.textContent = "Team broadcast";
      }
      send.disabled = (active === "rider" && !selectedRide) || (active === "driver" && !selectedDriver);
    }
    function switchTo(tab) {
      if (tabs.indexOf(tab) < 0) return;
      active = tab;
      unread[tab] = 0;
      counts(); optionsForTarget();
      render(true, true); // User commanded the conversation change.
    }
    buttons.forEach(function (button) {
      button.addEventListener("click", function () { switchTo(button.dataset.recipient); });
    });
    target.addEventListener("change", function () {
      if (active === "rider") selectedRide = target.value;
      if (active === "driver") selectedDriver = target.value;
      unread[active] = 0; counts(); render(true, true);
    });
    function accept(list) {
      var newMessages = [];
      (list || []).forEach(function (m) {
        if (!m || !m.id || messages.has(itemKey(m))) return;
        messages.set(itemKey(m), m);
        newMessages.push(m);
        seenAt = Math.max(seenAt, Number(m.at) || 0);
      });
      var firstLoad = !loaded; loaded = true;
      newMessages.forEach(function (m) {
        if (!firstLoad && !m.mine) unread[kind(m)] = (unread[kind(m)] || 0) + 1;
      });
      counts();
      if (newMessages.length) render(false, false);
      return newMessages.length;
    }
    function refresh(full) {
      if (fetching) { if (full) needHistory = true; return; }
      fetching = true;
      var since = full ? 0 : Math.max(0, seenAt - 0.05);
      fetch("/api/chat/messages?since=" + since.toFixed(6), { cache: "no-store" })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) throw new Error(data.error || "Could not load messages");
            return data;
          });
        }).then(function (data) {
          // Purged history must disappear from every connected rider/driver/
          // Dispatch view, not just the administrator's reloaded browser.
          if (typeof data.chat_epoch === "number") {
            if (chatEpoch !== null && data.chat_epoch !== chatEpoch) {
              messages.clear();
              rendered.clear();
              log.replaceChildren();
              seenAt = 0;
              Object.keys(unread).forEach(function (tab) { unread[tab] = 0; });
              counts();
              needHistory = true; // Fetch any messages newer than the old cursor.
            }
            chatEpoch = data.chat_epoch;
          }
          var next = accept(data.messages || []);
          if (full && next) render(true, false); // Preserve position on history merge.
          status.textContent = "";
        }).catch(function () {
          status.textContent = "Messages offline — drafts stay here. Retry when connected.";
        }).then(function () {
          fetching = false;
          if (needHistory) { needHistory = false; refresh(true); }
        });
    }
    function requestBody() {
      var body = { text: field.value.trim() };
      if (active === "account") {
        body.account_chat = true;
      } else if (active === "rider") {
        if (role === "dispatch" && selectedRide.slice(0, 8) === "account:") {
          body.rider_account_id = selectedRide.slice(8);
        } else {
          body.ride_id = role === "dispatch" ? selectedRide.slice(5) : selectedRide;
          body.audience = role === "dispatch" ? "rider" : "shared";
        }
      } else if (active === "driver") {
        body.to_driver = selectedDriver;
      } else if (active === "dispatch") {
        body.private = true;
      }
      return body;
    }
    function sendMessage() {
      var body = requestBody();
      if (!body.text || sending || send.disabled) return;
      var signature = JSON.stringify(body);
      var sentTab = active, sentTarget = currentTarget();
      if (signature !== pendingSignature) {
        pendingSignature = signature;
        pendingId = "nr-" + Date.now() + "-" + Math.random().toString(36).slice(2);
      }
      body.client_id = pendingId;
      sending = true; send.disabled = true;
      fetch("/api/chat/messages", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      }).then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "Could not send message");
          return data;
        });
      }).then(function (data) {
        if (field.value.trim() === body.text) field.value = "";
        pendingSignature = ""; pendingId = "";
        status.textContent = "Sent";
        if (data.message) {
          var m = Object.assign({}, data.message, { mine: true,
            message_kind: data.message.rider_account_id ? "account" :
              data.message.ride_id ? "ride" : "team" });
          accept([m]);
          if (active === sentTab && currentTarget() === sentTarget) {
            render(false, true); // The driver explicitly sent into this tab.
          }
        }
        refresh();
      }).catch(function (error) {
        status.textContent = error.message + " — message not cleared; try Send again.";
      }).then(function () {
        sending = false;
        send.disabled = (active === "rider" && !selectedRide) || (active === "driver" && !selectedDriver);
      });
    }
    send.addEventListener("click", sendMessage);
    field.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); sendMessage(); }
    });
    function setRides(next) {
      var newRides = (next || []).filter(function (r) { return r && r.id; });
      var idsBefore = rides.map(function (r) { return String(r.id) + ":" + String(r.rider_name || ""); }).join("|");
      var idsAfter = newRides.map(function (r) { return String(r.id) + ":" + String(r.rider_name || ""); }).join("|");
      if (idsAfter === idsBefore) return; // Never rebuild an open select on ordinary refresh.
      rides = newRides;
      var oldTarget = selectedRide;
      optionsForTarget();
      if (selectedRide !== oldTarget) render(true, false);
      if (loaded) refresh(true);
    }
    function setDrivers(next) {
      var updated = (next || []).filter(function (d) { return !!(d && (d.display_name || d.name || typeof d === "string")); });
      var names = function (items) { return items.map(function (d) { return d.display_name || d.name || d; }).join("|"); };
      if (names(drivers) === names(updated)) return;
      drivers = updated;
      var before = selectedDriver;
      optionsForTarget();
      if (before !== selectedDriver) render(true, false);
    }
    function setRiderAccounts(next) {
      var updated = (next || []).filter(function (a) { return a && a.id; });
      var signature = function (arr) { return arr.map(function (a) {
        return a.id + ":" + a.display_name + ":" + a.enabled;
      }).join("|"); };
      if (signature(riderAccounts) === signature(updated)) return;
      riderAccounts = updated;
      var before = selectedRide;
      if (active === "rider") optionsForTarget();
      if (active === "rider" && selectedRide !== before) render(true, false);
    }
    // Called only by an explicit Text Rider / Text Driver click.
    function showRecipient(tab, id) {
      if (tabs.indexOf(tab) < 0 || !id) return false;
      var desired = String(id);
      if (tab === "driver" && !drivers.some(function (d) {
        return (d.display_name || d.name || d) === desired;
      })) return false;
      if (tab === "rider" && role === "dispatch" &&
          !riderAccounts.some(function (r) { return "account:" + r.id === desired; }) &&
          !rides.some(function (r) { return "ride:" + r.id === desired; })) return false;
      if (tab === "rider") selectedRide = desired;
      if (tab === "driver") selectedDriver = desired;
      switchTo(tab);
      if (target.value !== desired) {
        target.value = desired;
        render(true, true);
      }
      if (options.onNavigate) options.onNavigate();
      return true;
    }
    optionsForTarget(); counts(); refresh();
    return { refresh: refresh, setRides: setRides, setDrivers: setDrivers,
      setRiderAccounts: setRiderAccounts, showRecipient: showRecipient, show: switchTo };
  }
  root.NightRiderChat = { mount: mount };
})(window);
