/* ============================================================================
   RingBack — shared motion engine.
   Vanilla, dependency-free. Every block is gated on the presence of its target
   elements, so this file is inert on pages that don't use a given hook and safe
   to load on every shell. Honors prefers-reduced-motion (renders static
   end-states). Built to pair with the motion layer in static/ui.css.
   ============================================================================ */
(function () {
  "use strict";

  var REDUCE = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasIO = "IntersectionObserver" in window;
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }

  /* ---------- Scroll reveal (stagger groups + direction) ----------
     Elements: .reveal  (optional data-reveal="left|right|scale").
     Stagger:  put .reveal items inside [data-reveal-group] to delay siblings. */
  (function () {
    var els = document.querySelectorAll(".reveal");
    if (!els.length) return;

    each(document.querySelectorAll("[data-reveal-group]"), function (group) {
      each(group.querySelectorAll(".reveal"), function (el, i) {
        el.style.setProperty("--reveal-i", i);
      });
    });

    if (REDUCE || !hasIO) { each(els, function (el) { el.classList.add("in"); }); return; }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.14, rootMargin: "0px 0px -8% 0px" });
    each(els, function (el) { io.observe(el); });
  })();

  /* ---------- Count-up ----------
     <span data-countup="128" data-countup-decimals="1" data-countup-suffix="s">  */
  (function () {
    var els = document.querySelectorAll("[data-countup]");
    if (!els.length) return;

    function run(el) {
      var target = parseFloat(el.getAttribute("data-countup")) || 0;
      var dec = parseInt(el.getAttribute("data-countup-decimals") || "0", 10);
      var sfx = el.getAttribute("data-countup-suffix") || "";
      var pfx = el.getAttribute("data-countup-prefix") || "";
      function paint(v) { el.textContent = pfx + v.toFixed(dec) + sfx; }
      if (REDUCE) { paint(target); return; }
      var dur = 900, start = null;
      function step(ts) {
        if (start === null) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        paint(target * (1 - Math.pow(1 - p, 3))); // easeOutCubic
        if (p < 1) requestAnimationFrame(step); else paint(target);
      }
      requestAnimationFrame(step);
    }

    if (!hasIO) { each(els, run); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { run(e.target); io.unobserve(e.target); }
      });
    }, { threshold: 0.6 });
    each(els, function (el) { io.observe(el); });
  })();

  /* ---------- Accordion (smooth grid-rows height) ----------
     <div class="acc"><button class="acc-summary" aria-expanded="false">…</button>
       <div class="acc-panel"><div class="acc-inner"><div class="acc-body">…</div></div></div></div> */
  (function () {
    var btns = document.querySelectorAll(".acc > .acc-summary");
    if (!btns.length) return;
    each(btns, function (btn) {
      btn.addEventListener("click", function () {
        var acc = btn.closest(".acc");
        if (!acc) return;
        var open = acc.classList.toggle("is-open");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
  })();

  /* ---------- Segmented control · sliding indicator ----------
     <div class="seg"><span class="seg-ind"></span>
       <button class="seg-btn active">A</button><button class="seg-btn">B</button></div> */
  (function () {
    var segs = document.querySelectorAll(".seg");
    if (!segs.length) return;
    each(segs, function (seg) {
      var ind = seg.querySelector(".seg-ind");
      var btns = seg.querySelectorAll(".seg-btn");
      if (!ind || !btns.length) return;
      var pad = parseInt(getComputedStyle(seg).paddingLeft, 10) || 0;
      function move(btn) {
        ind.style.width = btn.offsetWidth + "px";
        ind.style.transform = "translateX(" + (btn.offsetLeft - pad) + "px)";
      }
      each(btns, function (btn) {
        btn.addEventListener("click", function () {
          each(btns, function (b) { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
          btn.classList.add("active"); btn.setAttribute("aria-selected", "true");
          move(btn);
        });
      });
      var active = seg.querySelector(".seg-btn.active") || btns[0];
      var prev = ind.style.transition;          // position on init without animating
      ind.style.transition = "none";
      move(active);
      void ind.offsetWidth;                     // force reflow
      ind.style.transition = prev;
      window.addEventListener("resize", function () {
        var on = seg.querySelector(".seg-btn.active") || btns[0];
        var t = ind.style.transition; ind.style.transition = "none";
        move(on); void ind.offsetWidth; ind.style.transition = t;
      });
    });
  })();

  /* ---------- Toast ---------- */
  window.rbToast = function (msg, tone) {
    var wrap = document.querySelector(".rb-toasts");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "rb-toasts"; document.body.appendChild(wrap); }
    var t = document.createElement("div");
    t.className = "rb-toast";
    t.innerHTML = '<span class="pill-dot"></span><span></span>';
    t.lastChild.textContent = msg || "Saved";
    wrap.appendChild(t);
    setTimeout(function () {
      t.style.transition = "opacity var(--dur-2) var(--ease-exit),transform var(--dur-2) var(--ease-exit)";
      t.style.opacity = "0"; t.style.transform = "translateY(6px)";
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 240);
    }, 2600);
  };

  /* ---------- Button loading helper (generic) ----------
     btn.dataset.loading sets a min spin time; used by demos and real submits. */
  window.rbButtonLoading = function (btn, on) {
    if (!btn) return;
    btn.classList.toggle("is-loading", on !== false);
  };

  /* ============================================================================
     Demo wiring (only fires where the data-* hooks exist — e.g. the /ui gallery)
     ============================================================================ */
  each(document.querySelectorAll("[data-loading-demo]"), function (btn) {
    btn.addEventListener("click", function () {
      if (btn.classList.contains("is-loading")) return;
      window.rbButtonLoading(btn, true);
      setTimeout(function () {
        window.rbButtonLoading(btn, false);
        window.rbToast(btn.getAttribute("data-loading-demo") || "Done");
      }, 1500);
    });
  });

  each(document.querySelectorAll("[data-shake-demo]"), function (btn) {
    var field = document.querySelector(btn.getAttribute("data-shake-demo"));
    if (!field) return;
    btn.addEventListener("click", function () {
      field.classList.add("has-error", "shake");
      setTimeout(function () { field.classList.remove("shake"); }, 450);
    });
  });

  each(document.querySelectorAll("[data-pop-demo]"), function (btn) {
    var slot = document.querySelector(btn.getAttribute("data-pop-demo"));
    if (!slot) return;
    btn.addEventListener("click", function () {
      slot.innerHTML = '<span class="pill pill-booked pop-in"><span class="pill-dot"></span>Saved</span>';
    });
  });

  each(document.querySelectorAll("[data-toast-demo]"), function (btn) {
    btn.addEventListener("click", function () { window.rbToast(btn.getAttribute("data-toast-demo") || "Saved"); });
  });
})();
