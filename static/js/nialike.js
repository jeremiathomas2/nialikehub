/* Nialike — UI behaviour (theme, drawer, modals, toasts, filters) */
(function () {
  "use strict";

  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  /* ---------- Theme ---------- */
  var SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.3 11.3 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

  function applyTheme(dark) {
    document.documentElement.classList.toggle("dark", dark);
    document.body.classList.toggle("dark", dark);
    $$(".js-theme-icon").forEach(function (i) { i.innerHTML = dark ? MOON : SUN; });
    var t = $("#drawerThemeToggle");
    if (t) t.classList.toggle("on", dark);
  }
  window.toggleTheme = function () {
    var dark = !document.body.classList.contains("dark");
    applyTheme(dark);
    try { localStorage.setItem("nl-theme", dark ? "dark" : "light"); } catch (e) {}
  };

  /* ---------- Appearance drawer ---------- */
  window.openDrawer = function () {
    var d = $("#drawer"), s = $("#scrim");
    if (d) d.classList.add("open");
    if (s) s.classList.add("show");
  };
  window.closeDrawer = function () {
    var d = $("#drawer"), s = $("#scrim");
    if (d) d.classList.remove("open");
    if (s && !$("#sidebar").classList.contains("open")) s.classList.remove("show");
  };
  window.setVar = function (name, value, el) {
    document.documentElement.style.setProperty(name, value);
    try {
      var saved = JSON.parse(localStorage.getItem("nl-vars") || "{}");
      saved[name] = value;
      localStorage.setItem("nl-vars", JSON.stringify(saved));
    } catch (e) {}
    $$(".swatch").forEach(function (s) { s.classList.remove("sel"); });
    if (el) el.classList.add("sel");
  };
  window.setFont = function (fam) {
    document.documentElement.style.setProperty("--font-display", fam);
    try { localStorage.setItem("nl-font", fam); } catch (e) {}
  };
  window.resetAppearance = function () {
    ["--accent", "--gold"].forEach(function (n) { document.documentElement.style.removeProperty(n); });
    try { localStorage.removeItem("nl-vars"); localStorage.removeItem("nl-font"); } catch (e) {}
    location.reload();
  };

  /* ---------- Sidebar (mobile slide-in + desktop rail collapse) ---------- */
  function isMobile() {
    return window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
  }
  function syncMenuBtn() {
    var btn = $("#menuToggle"), sb = $("#sidebar"), layout = $(".layout");
    if (!btn) return;
    var open = sb
      ? (isMobile() ? sb.classList.contains("open") : !layout.classList.contains("rail"))
      : false;
    btn.setAttribute("aria-expanded", String(open));
    btn.classList.toggle("active", open);
  }
  window.openSidebar = function () {
    var sb = $("#sidebar");
    if (sb) sb.classList.add("open");
    var s = $("#scrim"); if (s) s.classList.add("show");
    syncMenuBtn();
  };
  window.closeSidebar = function () {
    var sb = $("#sidebar");
    if (sb) sb.classList.remove("open");
    var s = $("#scrim"); if (s && !$("#drawer").classList.contains("open")) s.classList.remove("show");
    syncMenuBtn();
  };
  window.toggleSidebar = function () {
    if (!$("#sidebar") || !$(".layout")) return;
    if (isMobile()) {
      if ($("#sidebar").classList.contains("open")) closeSidebar();
      else openSidebar();
      return;
    }
    var rail = $(".layout").classList.toggle("rail");
    try { localStorage.setItem("nl-rail", rail ? "1" : "0"); } catch (e) {}
    $$(".nav-group.open").forEach(function (g) { g.classList.remove("open"); });
    syncMenuBtn();
  };
  window.addEventListener("resize", function () {
    closeSidebar();
    syncMenuBtn();
  });

  /* ---------- Modals ---------- */
  window.openModal = function (id) {
    var m = document.getElementById(id);
    if (m) m.classList.add("show");
  };
  window.closeModal = function (id) {
    var m = document.getElementById(id);
    if (m) m.classList.remove("show");
  };
  document.addEventListener("click", function (e) {
    if (e.target.classList && e.target.classList.contains("modal-backdrop")) {
      e.target.classList.remove("show");
    }
  });

  /* ---------- Toasts ---------- */
  var TOAST_COLORS = { success: "var(--ok)", error: "var(--danger)", warning: "var(--warn)", info: "var(--info)" };
  window.toast = function (msg, type) {
    type = type || "success";
    var stack = $(".toast-stack");
    if (!stack) return;
    var t = document.createElement("div");
    t.className = "toast t-" + type;
    t.style.borderLeftColor = TOAST_COLORS[type] || TOAST_COLORS.success;
    t.textContent = msg;
    stack.appendChild(t);
    setTimeout(function () { t.remove(); }, 3200);
  };

  /* ---------- Copy ---------- */
  function doCopy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast("Copied to clipboard"); });
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); toast("Copied to clipboard"); } catch (e) {}
      ta.remove();
    }
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-text]");
    if (btn) { doCopy(btn.getAttribute("data-copy-text")); return; }
    btn = e.target.closest("[data-copy]");
    if (btn) {
      var src = document.querySelector(btn.getAttribute("data-copy"));
      if (src) doCopy(src.value || src.textContent);
    }
  });

  /* ---------- Confirm ---------- */
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f.hasAttribute && f.hasAttribute("data-confirm") && !window.confirm(f.getAttribute("data-confirm"))) {
      e.preventDefault();
    }
  }, true);

  /* ---------- Chip filters + search ---------- */
  function bindFilters(scope) {
    $$(".chip[data-filter]", scope).forEach(function (chip) {
      chip.addEventListener("click", function () {
        var group = chip.closest("[data-chip-group]") || document;
        $$(".chip[data-filter]", group).forEach(function (c) { c.classList.remove("active"); });
        chip.classList.add("active");
        var val = chip.getAttribute("data-filter");
        $$("[data-chip-rows] tr[data-status]", group).forEach(function (tr) {
          tr.style.display = (val === "all" || tr.getAttribute("data-status") === val) ? "" : "none";
        });
      });
    });
    $$("[data-search-rows]", scope).forEach(function (input) {
      input.addEventListener("input", function () {
        var q = input.value.toLowerCase();
        var rows = $$(input.getAttribute("data-search-rows") + " tbody tr");
        rows.forEach(function (tr) {
          tr.style.display = tr.textContent.toLowerCase().indexOf(q) > -1 ? "" : "none";
        });
      });
    });
  }

  /* ---------- Auto-submit selects ---------- */
  $$("select[data-autosubmit]").forEach(function (sel) {
    sel.addEventListener("change", function () {
      if (sel.form) sel.form.submit();
    });
  });

  /* ---------- Template fill ---------- */
  $$("[data-template-body]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var ta = $(btn.getAttribute("data-template-body"));
      if (ta) { ta.value = btn.getAttribute("data-body") || ""; toast("Template loaded"); }
    });
  });

  /* ---------- Event -> guest select sync ---------- */
  var guestDataEl = $("#guest-data");
  if (guestDataEl) {
    var data = {};
    try { data = JSON.parse(guestDataEl.textContent); } catch (e) {}
    var evSel = $("#pay-event"), gSel = $("#pay-guest");
    function fillGuests() {
      if (!evSel || !gSel) return;
      gSel.innerHTML = '<option value="">- No guest -</option>';
      (data[evSel.value] || []).forEach(function (g) {
        var o = document.createElement("option");
        o.value = g.id; o.textContent = g.name;
        gSel.appendChild(o);
      });
    }
    if (evSel) { evSel.addEventListener("change", fillGuests); fillGuests(); }
  }

  /* ---------- Row links ---------- */
  $$("tr.row-link[data-href]").forEach(function (tr) {
    tr.addEventListener("click", function (e) {
      if (e.target.closest("a, button, form, select, input")) return;
      window.location.href = tr.getAttribute("data-href");
    });
  });

  /* ---------- Password visibility ---------- */
  $$("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var wrap = btn.closest(".input-wrap");
      var input = wrap ? wrap.querySelector("input") : null;
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("showing", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      input.focus();
    });
  });

  /* ---------- User menu ---------- */
  window.toggleUserMenu = function () {
    var w = $(".user-menu");
    if (!w) return;
    var open = !w.classList.contains("open");
    w.classList.toggle("open", open);
    var b = $(".user-pill", w);
    if (b) b.setAttribute("aria-expanded", String(open));
  };
  document.addEventListener("click", function (e) {
    $$(".user-menu.open").forEach(function (m) {
      if (!e.target.closest(".user-menu") || e.target.closest(".user-menu") !== m) {
        m.classList.remove("open");
      }
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      $$(".user-menu.open").forEach(function (m) { m.classList.remove("open"); });
      if ($("#sidebar") && $("#sidebar").classList.contains("open")) closeSidebar();
    }
  });

  /* ---------- Sidebar accordion groups ---------- */
  window.toggleNavGroup = function (headEl) {
    var group = headEl.closest(".nav-group");
    if (!group) return;
    var wasOpen = group.classList.contains("open");
    $$(".nav-group.open").forEach(function (g) { g.classList.remove("open"); });
    if (!wasOpen) group.classList.add("open");
  };

  /* ---------- Init ---------- */
  function init() {
    var theme = null;
    try { theme = localStorage.getItem("nl-theme"); } catch (e) {}
    var dark = theme !== null
      ? theme === "dark"
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(!!dark);

    var font = null;
    try { font = localStorage.getItem("nl-font"); } catch (e) {}
    if (font) document.documentElement.style.setProperty("--font-display", font);

    var vars = null;
    try { vars = JSON.parse(localStorage.getItem("nl-vars") || "{}"); } catch (e) {}
    Object.keys(vars || {}).forEach(function (k) { document.documentElement.style.setProperty(k, vars[k]); });

    var rail = null;
    try { rail = localStorage.getItem("nl-rail"); } catch (e) {}
    if (rail === "1" && !isMobile()) {
      var layout = $(".layout");
      if (layout) layout.classList.add("rail");
    }
    syncMenuBtn();

    bindFilters(document);

    // Animate chart bars
    $$(".bar").forEach(function (b, i) {
      b.style.animationDelay = (i * 60) + "ms";
    });

    // Server-rendered toasts
    $$(".toast.auto").forEach(function (t, i) {
      setTimeout(function () { t.remove(); }, 3200 + i * 250);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
