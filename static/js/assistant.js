/* Nialike — on-page assistant bot (login/register pages) */
(function () {
  "use strict";

  function $(s, c) { return (c || document).querySelector(s); }

  var root = $("#nlBot");
  if (!root || root.dataset.ready) return;
  root.dataset.ready = "1";

  var URL_SEND = root.getAttribute("data-url") || "/assistant/";
  var BOT_NAME = root.getAttribute("data-name") || "Assistant";
  var GREETING = root.getAttribute("data-greeting") || "Hi! How can I help?";

  var panel = $("#nlBotPanel");
  var launcher = $("#nlBotLauncher");
  var nudge = $("#nlBotNudge");
  var msgs = $("#nlBotMsgs");
  var chipsBox = $("#nlBotChips");
  var form = $("#nlBotForm");
  var input = $("#nlBotInput");

  var chips = [];
  try { chips = JSON.parse($("#nl-bot-chips").textContent) || []; } catch (e) {}
  if (!chips.length) chips = ["How do I sign in?", "How does registration work?"];

  var greeted = false;
  var busy = false;
  var typeTimer = null;

  /* ---------- helpers ---------- */
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (m) return m[1];
    var el = document.querySelector("input[name='csrfmiddlewaretoken']");
    return el ? el.value : "";
  }

  function scrollDown() { msgs.scrollTop = msgs.scrollHeight; }

  var BOT_AV =
    '<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">' +
    '<line x1="32" y1="8" x2="32" y2="16"/><circle cx="32" cy="7" r="2.6" fill="#d9b45a" stroke="none"/>' +
    '<rect x="15" y="16" width="34" height="26" rx="9"/><circle cx="26" cy="28" r="3" fill="currentColor" stroke="none"/>' +
    '<circle cx="38" cy="28" r="3" fill="currentColor" stroke="none"/><path d="M27 35q5 3 10 0"/></svg>';

  function bubble(who, text, typewriter) {
    var b = document.createElement("div");
    b.className = "nl-msg " + who;
    var av = document.createElement("span");
    av.className = "nl-msg-av";
    if (who === "bot") { av.innerHTML = BOT_AV; }
    else { av.textContent = "U"; }
    var body = document.createElement("div");
    body.className = "nl-msg-txt";
    b.appendChild(av); b.appendChild(body);
    msgs.appendChild(b);
    if (!typewriter) { body.textContent = text; scrollDown(); return; }
    var i = 0;
    clearInterval(typeTimer);
    typeTimer = setInterval(function () {
      i += Math.max(1, Math.round(text.length / 90));
      body.textContent = text.slice(0, i);
      scrollDown();
      if (i >= text.length) { clearInterval(typeTimer); setBusy(false); }
    }, 14);
  }

  function typing(on) {
    var t = $(".nl-typing", msgs);
    if (on && !t) {
      t = document.createElement("div");
      t.className = "nl-msg bot nl-typing";
      t.innerHTML =
        '<span class="nl-msg-av">' + BOT_AV + '</span>' +
        '<div class="nl-msg-txt"><span></span><span></span><span></span></div>';
      msgs.appendChild(t);
      scrollDown();
    } else if (!on && t) {
      t.remove();
    }
  }

  function setBusy(v) {
    busy = v;
    input.disabled = v;
  }

  function showChips(list) {
    chipsBox.innerHTML = "";
    (list || []).slice(0, 6).forEach(function (c) {
      if (!c) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "nl-chip";
      b.textContent = c;
      chipsBox.appendChild(b);
    });
    chipsBox.classList.toggle("has", !!chipsBox.children.length);
  }

  /* ---------- send ---------- */
  function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    bubble("user", text);
    showChips([]);
    setBusy(true);
    typing(true);

    fetch(URL_SEND, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      credentials: "same-origin",
      body: JSON.stringify({ message: text })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
      .then(function (res) {
        typing(false);
        if (res.ok && res.data.reply) {
          bubble("bot", res.data.reply, true);
          showChips(res.data.chips || []);
        } else {
          setBusy(false);
          bubble("bot", res.data.error || "Sorry - I could not reach the server. Please try again.", true);
        }
      })
      .catch(function () {
        typing(false);
        setBusy(false);
        bubble("bot", "Network error - please check your connection and try again.", true);
      });
  }

  /* ---------- open / close ---------- */
  function dismissNudge() {
    if (nudge) { nudge.classList.remove("show"); }
  }
  if (nudge) {
    setTimeout(function () {
      if (panel.hidden) nudge.classList.add("show");
    }, 2200);
    $(".nl-bot-nudge-x", nudge).addEventListener("click", function (e) {
      e.stopPropagation();
      dismissNudge();
    });
  }

  function open() {
    panel.hidden = false;
    requestAnimationFrame(function () {
      panel.classList.add("open");
      root.classList.add("chatting");
    });
    launcher.setAttribute("aria-expanded", "true");
    dismissNudge();
    if (!greeted) {
      greeted = true;
      bubble("bot", GREETING, false);
      showChips(chips);
    }
    setTimeout(function () { input.focus(); }, 180);
  }

  function close() {
    panel.classList.remove("open");
    root.classList.remove("chatting");
    launcher.setAttribute("aria-expanded", "false");
    setTimeout(function () { panel.hidden = true; }, 200);
  }

  launcher.addEventListener("click", function () {
    if (panel.hidden) open(); else close();
  });
  $("#nlBotClose").addEventListener("click", close);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) close();
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    send(input.value);
    input.value = "";
  });

  chipsBox.addEventListener("click", function (e) {
    var chip = e.target.closest(".nl-chip");
    if (chip) send(chip.textContent);
  });
})();
