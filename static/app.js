// RingBack front-end glue. Vanilla JS — no build step.
// Chat bubbles are built to match templates/components/ui/chat_bubble.html.

const AGENT_SVG =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.7 6.1L20 10l-6.3 1.9L12 18l-1.7-6.1L4 10l6.3-1.9z"/></svg>';

function fmtClock(iso) {
  let d = iso ? new Date(iso) : new Date();
  if (isNaN(d.getTime())) d = new Date();
  let h = d.getHours();
  const m = d.getMinutes();
  const ap = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return h + ":" + String(m).padStart(2, "0") + " " + ap;
}

function clearEmpty(container) {
  const empty = container.querySelector(".empty");
  if (empty) empty.remove();
}

// Single fetch helper for every API call: throws on a non-2xx response and
// surfaces the server's JSON {error} message, so callers can try/catch, show a
// graceful message, and re-enable their controls in a finally block.
async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let msg = "Request failed (" + res.status + ")";
    try {
      const e = await res.json();
      if (e && e.error) msg = e.error;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

// Mirrors the chat_bubble macro: agent (right, dark, spark) vs customer (left, light, initial).
function addBubble(container, { text, who, time, initial }) {
  clearEmpty(container);
  const wrap = document.createElement("div");
  wrap.className = "msg msg-" + who;

  const av = document.createElement("span");
  av.className = "msg-avatar";
  if (who === "agent") av.innerHTML = AGENT_SVG;
  else av.textContent = (initial || "C").trim().charAt(0).toUpperCase() || "C";

  const stack = document.createElement("div");
  stack.className = "msg-stack";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.textContent = text;
  stack.appendChild(bubble);
  if (time) {
    const t = document.createElement("span");
    t.className = "msg-time";
    t.textContent = time;
    stack.appendChild(t);
  }

  wrap.appendChild(av);
  wrap.appendChild(stack);
  container.appendChild(wrap);
  container.scrollTop = container.scrollHeight;
}

function addMeta(container, text) {
  clearEmpty(container);
  const el = document.createElement("div");
  el.className = "chat-meta";
  el.textContent = text;
  container.appendChild(el);
}

// ---------- Simulator (the demo) ----------
(function () {
  const trigger = document.getElementById("trigger");
  if (!trigger) return;
  const thread = document.getElementById("thread");
  const form = document.getElementById("reply-form");
  const input = document.getElementById("reply-input");
  const sendBtn = form.querySelector("button");
  const status = document.getElementById("sim-status");
  const CUSTOMER = "Homeowner";
  // A demo homeowner's number (distinct from the business's own RingBack number,
  // which is shown in the device header from the business profile).
  const DEMO_CALLER = "+1 (415) 555-0142";
  let leadId = null;

  function banner(kind, label, text) {
    const el = document.createElement("div");
    el.className = "sim-banner sim-banner-" + kind;
    const strong = document.createElement("strong");
    strong.textContent = label;
    el.appendChild(strong);
    if (text) el.appendChild(document.createTextNode(" " + text));
    status.appendChild(el);
  }

  trigger.addEventListener("click", async () => {
    thread.innerHTML = "";
    status.innerHTML = "";
    addMeta(thread, "Missed call · just now");
    trigger.disabled = true;
    try {
      const data = await apiFetch("/api/sim/incoming", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: CUSTOMER, phone: DEMO_CALLER }),
      });
      leadId = data.lead_id;
      addBubble(thread, { text: data.reply, who: "agent", time: fmtClock() });
      input.disabled = false;
      sendBtn.disabled = false;
      trigger.lastChild.textContent = "Restart demo";
      input.focus();
    } catch (err) {
      addMeta(thread, "Could not start the demo. " + err.message);
    } finally {
      trigger.disabled = false;
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !leadId) return;
    addBubble(thread, { text, who: "customer", time: fmtClock(), initial: CUSTOMER });
    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    try {
      const data = await apiFetch("/api/sim/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lead_id: leadId, body: text }),
      });
      if (data.urgent) banner("urgent", "Urgent job", "— the owner is notified immediately.");
      addBubble(thread, { text: data.reply, who: "agent", time: fmtClock() });
      if (data.booked) banner("booked", "Estimate booked", "— " + data.booked + ". See it on the Dashboard.");
    } catch (err) {
      addMeta(thread, "Message not delivered. " + err.message);
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });
})();

// ---------- Dashboard conversation viewer ----------
(function () {
  const rows = document.querySelectorAll(".dt-row[data-id]");
  const convo = document.getElementById("convo");
  if (!rows.length || !convo) return;
  const notesEl = document.getElementById("lead-notes");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function renderNotes(lead) {
    if (!notesEl) return;
    if (!(lead.summary || lead.address || lead.project_type)) {
      notesEl.innerHTML = "";
      return;
    }
    const stage = (lead.stage || "").toLowerCase();
    const pill =
      stage === "scheduled" ? "pill-booked" : stage === "warm" ? "pill-warning" : "pill-neutral";
    const label = stage ? stage.charAt(0).toUpperCase() + stage.slice(1) : "Lead";
    const row = (k, v) =>
      v ? `<div class="ln-row"><dt>${k}</dt><dd>${esc(v)}</dd></div>` : "";
    notesEl.innerHTML =
      `<div class="ln-head"><span>Lead notes</span><span class="pill ${pill}">${esc(label)}</span></div>` +
      `<dl class="ln-grid">${row("Name", lead.name)}${row("Address", lead.address)}${row("Project", lead.project_type)}</dl>` +
      (lead.summary ? `<p class="ln-summary">${esc(lead.summary)}</p>` : "");
  }

  async function openLead(row) {
    rows.forEach((r) => {
      r.classList.remove("is-selected");
      r.setAttribute("aria-pressed", "false");
    });
    row.classList.add("is-selected");
    row.setAttribute("aria-pressed", "true");
    if (notesEl) notesEl.innerHTML = '<p class="ln-loading">Loading notes…</p>';
    convo.innerHTML = "";
    try {
      const data = await apiFetch(`/api/leads/${row.dataset.id}/messages`);
      const lead = data.lead || {};
      renderNotes(lead);
      if (!data.messages.length) {
        addMeta(convo, "No messages yet for " + (lead.name || "this lead"));
        return;
      }
      addMeta(convo, "Conversation with " + (lead.name || "lead"));
      data.messages.forEach((m) => {
        addBubble(convo, {
          text: m.body,
          who: m.direction === "out" ? "agent" : "customer",
          time: fmtClock(m.created_at),
          initial: lead.name || "C",
        });
      });
    } catch (err) {
      if (notesEl) notesEl.innerHTML = "";
      addMeta(convo, "Could not load this lead. " + err.message);
    }
  }

  rows.forEach((row) => {
    row.addEventListener("click", () => openLead(row));
    // Keyboard support: rows are role="button" tabindex="0" — Enter/Space activate.
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        openLead(row);
      }
    });
  });
})();

// ---------- Dashboard: cancel a booked estimate ----------
(function () {
  const buttons = document.querySelectorAll(".appt-cancel[data-id]");
  if (!buttons.length) return;
  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const when = btn.dataset.when || "this estimate";
      if (!window.confirm("Cancel " + when + "? The slot reopens and the customer is texted.")) return;
      btn.disabled = true;
      btn.textContent = "Cancelling…";
      try {
        await apiFetch("/api/appointments/" + btn.dataset.id + "/cancel", { method: "POST" });
        window.location.reload(); // refresh stats, the estimates table, and the calendar
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Try again";
      }
    });
  });
})();

// ---------- Marketing / front-door mobile nav (hamburger) ----------
(function () {
  const nav = document.querySelector(".ob-nav");
  const burger = nav && nav.querySelector(".ob-burger");
  if (!nav || !burger) return;
  function setOpen(open) {
    nav.classList.toggle("is-open", open);
    burger.setAttribute("aria-expanded", open ? "true" : "false");
    burger.setAttribute("aria-label", open ? "Close menu" : "Menu");
  }
  burger.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(!nav.classList.contains("is-open"));
  });
  // Close when tapping outside the nav or pressing Escape.
  document.addEventListener("click", (e) => {
    if (nav.classList.contains("is-open") && !nav.contains(e.target)) setOpen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
  });
})();

// ---------- Scroll reveal (marketing landing only) ----------
(function () {
  const els = document.querySelectorAll(".reveal");
  if (!els.length) return;
  if (!("IntersectionObserver" in window)) {
    els.forEach((e) => e.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  els.forEach((e) => io.observe(e));
})();

// ---------- Settings: disconnect Google Calendar ----------
// (Connecting Google is a real OAuth redirect via the "Connect" link; the other
// providers are "Coming soon". Only disconnect needs JS.)
(function () {
  const btn = document.getElementById("google-disconnect");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      await apiFetch("/api/calendar/google/disconnect", { method: "POST" });
      window.location.href = "/settings";
    } catch (_) {
      btn.disabled = false;
      btn.textContent = "Try again";
    }
  });
})();

// ---------- Settings: in-house calendar ----------
(function () {
  const root = document.getElementById("calendar");
  if (!root) return;
  const grid = document.getElementById("cal-grid");
  const monthLbl = document.getElementById("cal-month");
  const detail = document.getElementById("cal-detail");
  let data = null;
  let current = null; // "YYYY-MM" or null = this month
  let selected = null; // ISO date

  function fmtPhone(raw) {
    let d = String(raw || "").replace(/\D/g, "");
    if (d.length === 11 && d[0] === "1") d = d.slice(1);
    return d.length === 10 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : (raw || "");
  }
  function chipTime(label) {
    const i = label.indexOf("·");
    return (i >= 0 ? label.slice(i + 1) : label).trim();
  }
  function fmtLongDate(iso) {
    const [y, m, dd] = iso.split("-").map(Number);
    return new Date(y, m - 1, dd).toLocaleDateString(undefined, {
      weekday: "long", month: "long", day: "numeric",
    });
  }
  function findDay(iso) {
    for (const w of data.weeks) for (const d of w) if (d.date === iso) return d;
    return null;
  }

  async function load(month) {
    try {
      data = await apiFetch(root.dataset.endpoint + (month ? "?month=" + month : ""));
      current = `${data.year}-${String(data.month).padStart(2, "0")}`;
      render();
    } catch (err) {
      grid.innerHTML = "";
      monthLbl.textContent = "Calendar unavailable";
      detail.textContent = "Could not load the calendar. Please try again.";
    }
  }

  function render() {
    monthLbl.textContent = data.label;
    grid.innerHTML = "";
    data.weeks.forEach((w) => w.forEach((d) => grid.appendChild(cell(d))));
    renderDetail();
  }

  function cell(day) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "cal-day"
      + (day.inMonth ? "" : " not-month")
      + (day.today ? " is-today" : "")
      + (day.past ? " is-past" : "")
      + (day.busy ? " is-busy" : "")
      + (day.estimates.length ? " has-est" : "")
      + (selected === day.date ? " is-selected" : "");
    let html = `<span class="cal-date">${day.day}</span>`;
    if (day.busy) html += `<span class="cal-flag">Busy</span>`;
    day.estimates.slice(0, 2).forEach((e) => {
      html += `<span class="cal-chip">${chipTime(e.label)}</span>`;
    });
    if (day.estimates.length > 2) html += `<span class="cal-more">+${day.estimates.length - 2} more</span>`;
    el.innerHTML = html;
    // Screen-reader label: full date + its state, since the visible cell is terse.
    const est = day.estimates.length;
    const state = day.busy ? "marked busy"
      : est ? est + (est === 1 ? " estimate booked" : " estimates booked")
      : day.past ? "past" : "open";
    el.setAttribute("aria-label", `${fmtLongDate(day.date)}, ${state}`);
    if (selected === day.date) el.setAttribute("aria-current", "date");
    if (day.past) el.setAttribute("aria-disabled", "true");
    el.addEventListener("click", () => { selected = day.date; render(); });
    return el;
  }

  function emptyDetail() {
    return `<div class="cal-detail-empty">`
      + `<span class="cal-detail-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg></span>`
      + `<p>Select a day to see its estimates or block it as busy.</p></div>`;
  }

  function renderDetail() {
    if (!selected) { detail.innerHTML = emptyDetail(); return; }
    const d = findDay(selected);
    if (!d) { detail.innerHTML = emptyDetail(); return; }
    let h = `<div class="cal-detail-head"><h5>${fmtLongDate(d.date)}</h5>`;
    if (!d.past) {
      h += `<button type="button" class="btn btn-sm ${d.busy ? "btn-secondary" : "btn-ghost"} cal-block">${d.busy ? "Unblock day" : "Block day"}</button>`;
    }
    h += `</div>`;
    if (d.busy) h += `<p class="cal-detail-note">Marked busy — the AI won’t offer this day.</p>`;
    if (d.estimates.length) {
      h += `<ul class="cal-est-list">` + d.estimates.map((e) =>
        `<li><span class="cal-est-when">${e.label}</span><span class="cal-est-who">${e.name || "Lead"} · ${fmtPhone(e.phone)}</span></li>`
      ).join("") + `</ul>`;
    } else if (!d.busy) {
      h += `<p class="cal-detail-note">No estimates booked.${d.past ? "" : " This day is open for the AI to fill."}</p>`;
    }
    detail.innerHTML = h;
    const blk = detail.querySelector(".cal-block");
    if (blk) blk.addEventListener("click", async () => {
      blk.disabled = true;
      try {
        await apiFetch("/api/calendar/busy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date: d.date, busy: !d.busy }),
        });
        await load(current);  // re-renders the grid + detail (replaces this button)
      } catch (err) {
        blk.disabled = false;
        blk.textContent = "Try again";
      }
    });
  }

  root.querySelector(".cal-prev").addEventListener("click", () => load(data.prev));
  root.querySelector(".cal-next").addEventListener("click", () => load(data.next));
  root.querySelector(".cal-today").addEventListener("click", () => { selected = null; load(null); });

  load(null);
})();

// ---------- ROI / analytics page ----------
(function () {
  const root = document.getElementById("roi");
  if (!root) return;
  const tilesEl = document.getElementById("roi-tiles");
  const chartEl = document.getElementById("roi-chart");
  const buttons = root.querySelectorAll(".roi-r");
  const money = (n) => "$" + Number(n).toLocaleString();

  function tile(value, label, sub, tone) {
    return '<div class="stat-tile"><div class="stat-value">' + value + "</div>"
      + '<div class="stat-label">' + label + "</div>"
      + (sub ? '<div class="stat-sub ' + (tone || "") + '">' + sub + "</div>" : "")
      + "</div>";
  }
  function renderTiles(d) {
    const t = d.totals, hasRev = t.revenue != null;
    tilesEl.innerHTML =
      tile(t.leads, "Leads captured") +
      tile(t.booked, "Estimates booked", t.leads ? t.conversion + "% conversion" : null, t.booked ? "good" : "") +
      tile(t.conversion + "%", "Conversion rate") +
      tile(hasRev ? money(t.revenue) : "—", "Est. revenue recovered",
           hasRev ? "at " + money(d.avg_job_value) + "/job" : "Set avg job value in Settings",
           hasRev ? "good" : "");
  }
  function renderChart(series) {
    const days = (series || []).filter(Boolean);
    const total = days.reduce((s, d) => s + d.leads + d.booked, 0);
    if (!total) {
      chartEl.innerHTML = '<p class="roi-empty">No activity in this range yet. Fire a demo call to see it here.</p>';
      return;
    }
    const max = Math.max(1, ...days.map((d) => Math.max(d.leads, d.booked)));
    const W = 720, H = 200, pad = 24, n = days.length;
    const slot = (W - pad * 2) / n;
    const bw = Math.max(2, Math.min(16, slot * 0.34));
    const y = (v) => H - pad - (v / max) * (H - pad * 2);
    let rects = "";
    days.forEach((d, i) => {
      const cx = pad + slot * i + slot / 2;
      rects += '<rect class="roi-bar-leads" x="' + (cx - bw - 1).toFixed(1) + '" y="' + y(d.leads).toFixed(1)
        + '" width="' + bw.toFixed(1) + '" height="' + (H - pad - y(d.leads)).toFixed(1) + '" rx="2"><title>'
        + d.date + ": " + d.leads + " leads</title></rect>";
      rects += '<rect class="roi-bar-booked" x="' + (cx + 1).toFixed(1) + '" y="' + y(d.booked).toFixed(1)
        + '" width="' + bw.toFixed(1) + '" height="' + (H - pad - y(d.booked)).toFixed(1) + '" rx="2"><title>'
        + d.date + ": " + d.booked + " booked</title></rect>";
    });
    chartEl.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" class="roi-svg" preserveAspectRatio="none" role="img" '
      + 'aria-label="Leads and booked estimates per day">'
      + '<line class="roi-axis" x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + (H - pad) + '"/>'
      + rects + "</svg>"
      + '<div class="roi-xaxis"><span>' + days[0].date + "</span><span>" + days[days.length - 1].date + "</span></div>";
  }
  async function load(range) {
    try {
      const d = await apiFetch(root.dataset.endpoint + "?range=" + range);
      renderTiles(d);
      renderChart(d.series);
    } catch (err) {
      chartEl.innerHTML = '<p class="roi-empty">Could not load analytics. ' + err.message + "</p>";
    }
  }
  buttons.forEach((b) =>
    b.addEventListener("click", () => {
      buttons.forEach((x) => { x.classList.remove("is-active"); x.setAttribute("aria-pressed", "false"); });
      b.classList.add("is-active");
      b.setAttribute("aria-pressed", "true");
      load(b.dataset.range);
    })
  );
  load("30d");
})();
