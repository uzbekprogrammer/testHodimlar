(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Тема
  var themeBtn = $("[data-theme-toggle]");
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("tem-theme", next); } catch (e) {}
  });

  // Мобильное меню
  var menuBtn = $("[data-menu-toggle]");
  if (menuBtn) menuBtn.addEventListener("click", function () { document.body.classList.toggle("nav-open"); });
  var scrim = $(".scrim");
  if (scrim) scrim.addEventListener("click", function () { document.body.classList.remove("nav-open"); });

  // Подтверждение опасных действий
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Автоотправка фильтров
  $$("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  // Копирование (пароли, логины)
  $$("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var v = btn.getAttribute("data-copy");
      var done = function () { var t = btn.textContent; btn.textContent = "Скопировано"; setTimeout(function () { btn.textContent = t; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(v).then(done); else done();
    });
  });

  // Счётчик символов
  $$("textarea[data-max]").forEach(function (ta) {
    var out = $("[data-counter-for='" + ta.id + "']");
    var upd = function () { if (out) out.textContent = ta.value.length + " / " + ta.getAttribute("data-max"); };
    ta.addEventListener("input", upd); upd();
  });

  // Живое обновление KPI на «Обзоре» (раз в 30 секунд)
  if ($("[data-live-kpi]")) {
    var refresh = function () {
      if (document.hidden) return;
      fetch("/api/stats", { credentials: "same-origin" }).then(function (r) {
        if (r.status === 401) { location.href = "/login"; return null; }
        return r.ok ? r.json() : null;
      }).then(function (d) {
        if (!d) return;
        $$("[data-kpi]").forEach(function (el) {
          var v = d[el.getAttribute("data-kpi")];
          if (v !== undefined && String(v) !== el.textContent) { el.textContent = v; el.classList.add("pulse"); setTimeout(function () { el.classList.remove("pulse"); }, 1200); }
        });
        var u = $("[data-live-stamp]"); if (u) u.textContent = new Date().toLocaleTimeString("ru-RU");
      }).catch(function () {});
    };
    setInterval(refresh, 30000);
  }
})();
