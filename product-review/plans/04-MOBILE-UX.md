# 04 — Mobile + Dashboard UX: Build-Ready Plan

**Workstream:** Mobile + Dashboard UX (agent 4 of 10)
**Date:** 2026-06-19
**Source audit:** product-review/05-DASHBOARD-UX.md
**Files touched:** templates/app_shell.html, templates/dashboard.html,
templates/command.html, static/app.css, static/assistant.js (scoped section),
static/app.js (scoped section), static/ui.css (one new block)

---

## Shared-file collision notes

`templates/app_shell.html` is the shell for every signed-in page. Any change
there (nav labels, tap targets) affects Command, Dashboard, Pipeline, Callers,
Settings, Simulator, ROI — test all routes after touching it.

`static/app.css` holds the `@media(max-width:900px)` block that hides nav labels
and the `@media(max-width:640px)` block for stat-row. Changes there affect every
app page.

`static/app.js` contains the Dashboard conversation viewer and the cancel-estimate
handler. The mobile card-list approach adds a new DOM structure those handlers
must find — keep `data-id` attributes intact so existing JS selectors still work.

`static/assistant.js` owns the `send` catch block. Only one section is modified.

---

## Change 1 — Restore mobile nav labels + bump tap targets

**Priority:** Quick win (S)
**Impact:** H — every signed-in page on a phone

### What and why

`app.css` line 150: `.nav-item span{display:none}` removes all text under
`@media(max-width:900px)`, leaving a horizontal icon-only strip. Dave sees five
icons he has never memorized. "ROI" (bar chart) and "Memory" (lightbulb) are
non-obvious to a non-tech contractor.

The nav-item touch zone in the 900px strip is approximately 42 x 36px — below
44x44px on the vertical axis.

### Exact change: `static/app.css`

Remove the span-hiding rule and add a `min-height` guard. Replace the existing
`@media(max-width:900px)` block with:

```css
@media(max-width:900px){
  .app{grid-template-columns:1fr}
  .sidebar{position:static;height:auto;flex-direction:row;align-items:center;
    gap:var(--space-3);border-right:0;border-bottom:1px solid var(--border);
    padding:var(--space-2) var(--space-4)}
  .sidebar-nav{flex-direction:row;margin-top:0}
  /* Keep labels — shorten via CSS not JS so no template change needed. */
  .nav-item{min-height:48px;flex-direction:column;gap:2px;
    padding:6px var(--space-2);font-size:.65rem;line-height:1.2}
  .nav-item svg{width:20px;height:20px}
  /* Hide the long business-name block, keep the avatar */
  .sidebar-foot{margin-top:0;border-top:0;padding:var(--space-2)}
  .sidebar-foot .biz{display:none}
  .dash-2col,.sim-2col{grid-template-columns:1fr}
  .page-body{padding:var(--space-6)}
  /* Sidebar-logout is visible in the footer row — ensure tap target */
  .sidebar-logout{width:44px;height:44px}
}
```

Labels stay in the Jinja templates unchanged — no template edit required.
`font-size:.65rem` keeps labels legible in the narrow strip without wrapping.
`flex-direction:column` stacks icon above label (standard mobile tab-bar pattern).

### Verify

1. Open `/dashboard` on an iPhone viewport (390px). All nav labels should read:
   "Command", "Pipeline", "Memory", "Callers", "ROI", "Demo", "Settings".
2. Tap each nav item with a thumb — no mis-tap on adjacent items.
3. Active state still highlights correctly.
4. No regression on desktop (>900px) — sidebar is vertical, labels full-size.

**Effort: S (15 min) | Risk: Low — CSS-only, single breakpoint block**

---

## Change 2 — Mobile lead table -> card list at <=640px

**Priority:** Highest-impact (M)
**Impact:** H — Dave's primary daily interaction on a phone

### What and why

`dashboard.html` renders a `<table>` with 4 columns (Customer / Phone / Stage /
Received) inside `.dt-wrap { overflow-x:auto }`. On a 390px viewport the table
horizontal-scrolls and the row click targets are approximately 40px tall (below
44px WCAG minimum). Phone numbers have no `tel:` link.

### Approach: CSS-driven card list via `display` toggle

The safest approach is to keep the existing `<table>` in the DOM (so the existing
`app.js` row-click handlers — which use `.dt-row[data-id]` — keep working) but
suppress it at <=640px and show a parallel `<div>` card list instead. This avoids
rewriting app.js.

**Step 1 — Add a `tel:` link to the phone cell (always visible, any viewport).**

In `templates/dashboard.html`, change line 56:

```html
<!-- BEFORE -->
<td class="dt-muted">{{ l.phone|phone }}</td>

<!-- AFTER -->
<td class="dt-muted"><a href="tel:{{ l.phone }}" class="tel-link">{{ l.phone|phone }}</a></td>
```

Add one CSS rule in `app.css` to prevent the link from inheriting blue underline
on desktop (where the whole row is already clickable):

```css
.tel-link{color:inherit;text-decoration:none}
.tel-link:hover{text-decoration:underline}
```

**Step 2 — Add a parallel card list for mobile, hidden on desktop.**

Immediately after the closing `{% endcall %}` of the Leads card (after line 71),
add a `<div>` block with class `lead-cards`:

```html
<div class="lead-cards" aria-label="Leads" role="list">
  {% if leads %}
    {% for l in leads %}
    <div class="lead-card dt-row" data-id="{{ l.id }}"
         role="listitem button" tabindex="0"
         aria-label="Open conversation with {{ l.name }}">
      <div class="lead-card-main">
        <span class="lead-card-name">{{ l.name }}</span>
        {% if l.urgent %}
        <span class="lead-card-dot" aria-label="Urgent" title="Urgent"></span>
        {% endif %}
      </div>
      <div class="lead-card-row2">
        <a href="tel:{{ l.phone }}" class="tel-link lead-card-phone"
           aria-label="Call {{ l.name }}" onclick="event.stopPropagation()">
          {{ l.phone|phone }}
        </a>
        <span class="lead-card-meta">{{ l.created_at|nicedate }}</span>
      </div>
      <div class="lead-card-row3">
        {% if l.stage == 'scheduled' %}{{ pill('Scheduled','booked') }}
        {% elif l.stage == 'warm' %}{{ pill('Warm','warning') }}
        {% else %}{{ pill('New','neutral') }}{% endif %}
        {% if l.urgent %} {{ pill('Urgent','urgent') }}{% endif %}
      </div>
      <svg class="lead-card-chevron" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round"
           stroke-linejoin="round" aria-hidden="true">
        <path d="m9 18 6-6-6-6"/>
      </svg>
    </div>
    {% endfor %}
  {% else %}
    {{ empty_state('No leads yet',
       'When a missed call comes in, FirstBack texts the caller and the new lead
        lands right here.',
       action_label='Try the live demo', action_href='/simulator') }}
  {% endif %}
</div>
```

Note: the `pill` macro is already imported at the top of dashboard.html.

**Step 3 — CSS for the card list (add to `app.css` inside the <=640px block):**

```css
/* Lead card list (mobile only — table hides, cards show) */
.lead-cards{display:none}           /* hidden on desktop */

@media(max-width:640px){
  /* Hide the 4-col table; show the card list instead */
  .leads-table-wrap{display:none}
  .lead-cards{display:flex;flex-direction:column;gap:0}

  .lead-card{
    display:grid;
    grid-template-columns:1fr auto;
    grid-template-rows:auto auto auto;
    align-items:center;
    gap:var(--space-1) var(--space-3);
    padding:var(--space-3) var(--space-4);
    border-bottom:1px solid var(--border);
    cursor:pointer;
    transition:background .12s ease;
    min-height:64px;           /* comfortably above 44px minimum */
  }
  .lead-card:last-child{border-bottom:0}
  .lead-card:hover{background:var(--bg)}
  .lead-card:focus-visible{outline:2px solid var(--accent-ring);outline-offset:-2px}
  .lead-card.is-selected{background:var(--accent-bg)}
  /* Urgent: red left border, same pattern as .review-nudge but on a row */
  .lead-card.is-urgent{border-left:3px solid var(--danger)}

  .lead-card-main{
    grid-column:1;grid-row:1;
    display:flex;align-items:center;gap:var(--space-2)
  }
  .lead-card-name{font-weight:600;font-size:var(--text-sm);color:var(--ink)}
  .lead-card-dot{
    width:8px;height:8px;border-radius:50%;
    background:var(--danger);flex:0 0 auto
  }
  .lead-card-row2{
    grid-column:1;grid-row:2;
    display:flex;align-items:center;gap:var(--space-3)
  }
  .lead-card-phone{font-size:var(--text-xs);color:var(--ink-soft)}
  .lead-card-meta{font-size:var(--text-xs);color:var(--ink-faint)}
  .lead-card-row3{grid-column:1;grid-row:3;display:flex;gap:var(--space-2);flex-wrap:wrap}
  .lead-card-chevron{
    grid-column:2;grid-row:1 / span 3;
    width:16px;height:16px;color:var(--ink-faint);align-self:center
  }
}
```

**Step 4 — Wrap the existing table in the Leads card with a class for targeting.**

In `dashboard.html`, the `data_table` macro renders a `.dt-wrap`. We need the
mobile CSS to hide the table via the card's wrapping element. The existing
`{% call card(title='Leads', flush=true) %}` can be supplemented by adding a
`<div class="leads-table-wrap">` wrapper around the `data_table` call:

```html
{% call card(title='Leads', flush=true) %}
  {% if leads %}
    <div class="leads-table-wrap">
      {% call data_table(['Customer','Phone','Stage','Received']) %}
        ...rows...
      {% endcall %}
    </div>
  {% else %}
    {{ empty_state(...) }}
  {% endif %}
{% endcall %}
```

The `.lead-cards` div goes OUTSIDE the card call, immediately after it.

**Step 5 — After opening a card, auto-scroll to the conversation on mobile.**

In `app.js`, inside `openLead()`, add after `convo.innerHTML = ""`:

```js
// On mobile, scroll the conversation panel into view after selecting a card.
if (window.innerWidth <= 640) {
  const convoCard = convo.closest('.card');
  if (convoCard) convoCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
```

This is a 3-line addition in a scoped IIFE — no collision risk.

### Verify

1. iPhone viewport (390px): leads render as cards, no horizontal scroll visible.
2. Tap a card: conversation panel scrolls into view; "Mark as spam" button appears.
3. Phone number tap opens dialer (no page navigation).
4. Desktop (1200px): table renders normally; card list hidden.
5. Keyboard: Tab + Enter on a card opens the conversation (existing JS unchanged).
6. Urgent lead: card has red left border.

**Effort: M (2-3 hrs) | Risk: Medium — adds a parallel DOM element; JS selectors
remain unchanged (`.dt-row[data-id]` works on both table rows and cards)**

---

## Change 3 — Tap targets on high-stakes action buttons (<=640px)

**Priority:** Quick win (S)
**Impact:** M — Cancel estimate, Mark as spam, screen actions

### What and why

`.btn-sm` is `height:32px` (`ui.css` line 43). The Cancel estimate button, Mark
as spam button, and screened-calls action buttons (Mark spam / This was real /
Text them back) all use `btn btn-ghost btn-sm`. On a phone 32px is below 44px.

### Exact change: `static/app.css` (inside existing `@media(max-width:640px)` block)

```css
/* Bump small buttons to comfortable tap size on mobile */
.btn-sm{height:44px;padding:0 var(--space-4)}
```

This single rule overrides `.btn-sm` height inside the 640px breakpoint only.
The font-size `.text-xs` stays — the extra height is vertical padding. No change
to button appearance on desktop.

Also bump the logout button tap target in the sidebar footer for the <=900px strip:

```css
/* inside @media(max-width:900px) block */
.sidebar-logout{width:44px;height:44px}
```

(This was already noted in Change 1 above — confirming it is included there.)

### Verify

1. Dashboard on iPhone viewport: "Cancel", "Mark as spam", "Text them back"
   buttons tap comfortably without requiring precise targeting.
2. Desktop: button sizes unchanged.
3. No layout overflow: `.dt-actions` cell expands to accommodate 44px button.

**Effort: S (10 min) | Risk: Low — CSS-only, scoped to <=640px**

---

## Change 4 — Phone numbers as tel: links (dashboard scheduled estimates table)

**Priority:** Quick win (S)
**Impact:** M — direct dial from dashboard without copying

### What and why

The scheduled-estimates table in `dashboard.html` (line 89) also shows phone
numbers without `tel:` links. The leads table fix (Change 2) covers the leads
section. This change covers the appointments and screened-calls tables.

### Exact change: `templates/dashboard.html`

**Appointments table (line 89):**
```html
<!-- BEFORE -->
<td class="dt-muted">{{ a.lead_phone|phone }}</td>

<!-- AFTER -->
<td class="dt-muted"><a href="tel:{{ a.lead_phone }}" class="tel-link">{{ a.lead_phone|phone }}</a></td>
```

**Screened calls table (line 119):**
```html
<!-- BEFORE -->
<td class="dt-strong">{{ c.from_number|phone }}

<!-- AFTER -->
<td class="dt-strong"><a href="tel:{{ c.from_number }}" class="tel-link">{{ c.from_number|phone }}</a>
```

The `.tel-link` CSS rule added in Change 2 covers both cases.

### Verify

1. Dashboard with a booked appointment: phone number in estimates table is tappable.
2. Screened calls section: caller number is tappable.
3. Desktop: links are styled as plain text (inherit color, no underline unless hover).

**Effort: S (10 min) | Risk: Low — template-only, no JS**

---

## Change 5 — Error states styled as errors, not timestamps

**Priority:** Quick win (S)
**Impact:** H — prevents silent failures that kill retention

### What and why

`app.js` line 295 (`openLead` catch): `addMeta(convo, "Could not load this lead. " + err.message)`
`assistant.js` send catch (not audited line-by-line here, but the pattern is the same):
failed sends call `addMeta()` which renders a `.chat-meta` div — same styling as a
timestamp separator (uppercase, faint, tiny). Dave cannot distinguish a failure from
a "10:32 AM" divider.

### New helper function: `addErrorTurn()` in `static/app.js`

Add this function immediately after `addMeta()` (after line 95):

```js
// Renders a visually distinct error card inside the chat pane.
// retryFn: optional function — if provided, a "Tap to retry" button is shown.
function addErrorTurn(container, message, retryFn) {
  clearEmpty(container);
  const el = document.createElement('div');
  el.className = 'chat-error-turn';
  const txt = document.createElement('span');
  txt.textContent = message;
  el.appendChild(txt);
  if (retryFn) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-ghost btn-sm';
    btn.textContent = 'Tap to retry';
    btn.addEventListener('click', function() {
      el.remove();
      retryFn();
    });
    el.appendChild(btn);
  }
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}
```

**Replace `addMeta` error calls in `app.js`:**

Line 296 (openLead catch), change:
```js
// BEFORE
addMeta(convo, "Could not load this lead. " + err.message);

// AFTER
addErrorTurn(convo, "Could not load this lead. " + err.message,
  function() { openLead(row); });
```

**In `assistant.js` (the `send` catch block):**

Locate the existing error append (pattern: `addMeta(convo, "Could not send...")`)
and replace with:
```js
addErrorTurn(convo, "Couldn't send that. Try again.", function() { send(text); });
```

Note: `addErrorTurn` must also be available in `assistant.js`. Since both files
load in the same page context (app_shell.html loads app.js first, then assistant.js
via a defer), the function declared in app.js is available globally. If assistant.js
is also loaded on non-dashboard pages (the command center), confirm `app.js` loads
before it — it does (`app_shell.html` lines 96-97).

**CSS for the error card: add to `static/ui.css`** (after the `.chat-meta` rule,
around line 151):

```css
.chat-error-turn{
  align-self:stretch;
  display:flex;align-items:center;justify-content:space-between;
  gap:var(--space-3);
  padding:var(--space-3) var(--space-4);
  margin:var(--space-2) 0;
  background:var(--danger-bg);
  border:1px solid var(--danger-ring);
  border-left:3px solid var(--danger);
  border-radius:var(--radius);
  font-size:var(--text-sm);
  color:var(--danger);
  line-height:1.4;
}
.chat-error-turn .btn{
  flex:0 0 auto;
  color:var(--danger);
  border-color:var(--danger-ring);
}
```

**Usage gauge "resting" state — `templates/command.html` inline script:**

The `over_daily_cap` branch (line 128-132) currently sets plain text:
`el.textContent='Resting for a moment — back shortly.'`

Replace that branch with a visible briefing-style card injected above the gauge:

```js
if(d.over_daily_cap){
  var nudge=document.createElement('div');
  nudge.className='cap-nudge';
  nudge.innerHTML='You\'ve hit today\'s limit. Refills at midnight'
    +(refill?(' ('+_fmtDate(d.period_ends)+')'):'')+
    ' &mdash; or <a href="/pricing">add more to keep going</a>.';
  var gauge=document.getElementById('usageGauge');
  if(gauge && gauge.parentNode) gauge.parentNode.insertBefore(nudge,gauge);
  el.hidden=true; /* hide the faint gauge line */
  return;
}
```

And add a CSS rule in `command.html`'s inline `<style>` block:
```css
.cap-nudge{
  padding:var(--space-3) var(--space-4);
  background:var(--danger-bg);
  border:1px solid var(--danger-ring);
  border-radius:var(--radius);
  font-size:var(--text-sm);
  color:var(--danger);
  text-align:center;
  margin-bottom:var(--space-2);
}
.cap-nudge a{color:var(--danger);font-weight:600}
```

Note: `&mdash;` is ASCII-safe in HTML; no smart-quote risk.

### Verify

1. Simulate a network error on the command center (throttle to offline in DevTools,
   send a message): a red card with "Couldn't send that. Tap to retry" appears —
   not a faint timestamp.
2. "Tap to retry" retries the send and removes the error card.
3. Simulate a network error on the dashboard conversation viewer (throttle, click
   a lead): red error card appears in the conversation panel.
4. Trigger the daily cap state (or mock the `/api/usage` response with `over_daily_cap:true`):
   a visible red-tinted nudge card appears above the command bar — not micro grey text.
5. No regression: normal timestamps still render as `.chat-meta`.

**Effort: S (45 min) | Risk: Low-medium — touches assistant.js catch block (scoped);
`addErrorTurn` is additive; no existing logic removed**

---

## Change 6 — Always-present "all clear" empty state on the command center

**Priority:** Quick win (S)
**Impact:** M — orientation for Dave on quiet days

### What and why

`command.html` line 37: `{% if briefing and briefing['items'] %}` — the briefing
block only renders when there are action items. On a quiet day Dave opens the app
to a floating orb with no context: no "all clear", no last activity line.

### Exact change: `templates/command.html`

Replace the conditional briefing block with a version that always renders:

```html
<div id="briefingSlot">
{% if briefing and briefing['items'] %}
<div class="briefing" role="region" aria-label="Your briefing">
  <p class="briefing-headline">{{ briefing['headline'] }}</p>
  {% if briefing['sub'] %}<p class="briefing-sub">{{ briefing['sub'] }}</p>{% endif %}
  <ul class="briefing-list">
    {% for it in briefing['items'] %}
    <li class="briefing-item is-{{ it['tone'] }}">
      <button type="button" class="briefing-row" data-action="{{ it['action'] }}">
        {% if it['label'] %}<span class="sr-only">{{ it['label'] }}: </span>{% endif %}
        <span class="briefing-dot" aria-hidden="true"></span>
        <span class="briefing-text">
          <span class="briefing-t">{{ it['title'] }}</span>
          {% if it['sub'] %}<span class="briefing-s">{{ it['sub'] }}</span>{% endif %}
        </span>
        <span class="briefing-go" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m9 18 6-6-6-6"/>
          </svg>
        </span>
      </button>
    </li>
    {% endfor %}
  </ul>
</div>
{% else %}
<div class="briefing briefing--clear" role="status" aria-label="All clear">
  <p class="briefing-headline briefing-headline--clear">
    All clear
    {% if last_lead_name %}
    <span class="briefing-last">Last lead: {{ last_lead_name }}
      {% if last_lead_ago %}&mdash; {{ last_lead_ago }}{% endif %}.
      <a href="/dashboard">View dashboard</a>
    </span>
    {% else %}
    <span class="briefing-last">No missed calls yet.
      <a href="/simulator">Try the demo</a></span>
    {% endif %}
  </p>
</div>
{% endif %}
</div>{# /briefingSlot #}
```

**Backend requirement:** the `/command` route must pass `last_lead_name` (string or
None) and `last_lead_ago` (human-readable string, e.g. "2 hours ago") to the
template context. This is a 3-line addition in the route handler — query
`SELECT name, created_at FROM leads ORDER BY created_at DESC LIMIT 1`.

**CSS for the clear state** (in `assistant.css` or the inline style block in
command.html):

```css
.briefing--clear{
  background:transparent;
  border:1px dashed var(--border-strong);
  border-radius:var(--radius);
  padding:var(--space-3) var(--space-4);
}
.briefing-headline--clear{
  font-size:var(--text-sm);
  color:var(--ink-soft);
  display:flex;flex-direction:column;gap:var(--space-1);
  margin:0;
}
.briefing-last{
  font-size:var(--text-xs);
  color:var(--ink-faint);
}
.briefing-last a{color:var(--accent-strong);text-decoration:none}
.briefing-last a:hover{text-decoration:underline}
```

### Verify

1. Log in with an account that has no action items in the briefing:
   "All clear" card renders with last-lead line (or "No missed calls yet" if
   truly new).
2. Log in with action items: existing briefing list renders; no "all clear" shown.
3. "View dashboard" link navigates to `/dashboard`.
4. No JS required — server-rendered, works with JS disabled.

**Effort: S (30 min) + small backend query | Risk: Low — additive only;
existing `{% if %}` branch preserved as-is**

---

## Change 7 — Urgency signals: red border/tint on urgent tiles and lead rows

**Priority:** Quick win (S)
**Impact:** M — Dave's 10-second glance when opening the app

### What and why

The "Urgent" stat tile and urgent lead rows both rely on a small orange pill to
signal urgency. On a 10-second glance while moving between jobs, a pill is too
subtle. The pattern already exists in the codebase: `.review-nudge` uses
`border:1px solid var(--accent-ring)` and `.sim-banner-urgent` uses
`background:var(--danger-bg)`. Apply the same logic to urgent tiles and rows.

### Exact change A: `templates/dashboard.html` — urgent stat tile

Replace the stat_tile macro call for Urgent (line 31) with a version that passes
an extra class when `urgent_count > 0`:

```html
<!-- BEFORE -->
{{ stat_tile(urgent_count, 'Urgent',
   sub=('Needs follow-up' if urgent_count else 'All clear'),
   sub_tone=('bad' if urgent_count else 'good')) }}

<!-- AFTER -->
<div {% if urgent_count %}class="stat-tile-urgent"{% endif %}>
  {{ stat_tile(urgent_count, 'Urgent',
     sub=('Needs follow-up' if urgent_count else 'All clear'),
     sub_tone=('bad' if urgent_count else 'good')) }}
</div>
```

Wait — the `stat_tile` macro renders inside a `stat_row` grid and the `.stat-tile`
class is on the macro's root element. The cleaner approach: add an `extra_class`
param to `stat_tile.html`, or simply apply the urgency style with a sibling CSS
selector using the `.stat-sub.bad` indicator that is already present.

**CSS-only approach (zero template change):**

In `app.css` (or `ui.css` at the `.stat-tile` rule block):

```css
/* Urgency wash: if the stat-sub inside a tile has .bad tone,
   tint the tile's background to draw the eye. */
.stat-tile:has(.stat-sub.bad){
  background:var(--danger-bg);
  border-right-color:var(--danger-ring);
}
.stat-tile:has(.stat-sub.bad) .stat-value{
  color:var(--danger);
}
```

`:has()` is supported in all modern browsers (Safari 15.4+, Chrome 105+,
Firefox 121+). Add a comment noting the fallback: on old browsers the tile just
looks normal — no harm.

For the stat-row border adjustment (the urgent tile shares a right-border with
its neighbor), add:

```css
.stat-tile:has(.stat-sub.bad) + .stat-tile{
  border-left:none; /* remove double-border when the danger tile has a right-border */
}
```

### Exact change B: Lead table rows and cards — urgent row/card tint

**Table rows** (`app.css`):
```css
/* Urgent lead row: red left-border, faint danger background */
.dt tbody tr.is-urgent td:first-child{
  box-shadow:inset 3px 0 0 var(--danger)
}
.dt tbody tr.is-urgent{background:color-mix(in srgb,var(--danger) 3%,var(--surface))}
```

**Template:** Add `class="dt-row{% if l.urgent %} is-urgent{% endif %}"` to the
`<tr>` in `dashboard.html` (line 55):

```html
<!-- BEFORE -->
<tr class="dt-row" data-id="{{ l.id }}"

<!-- AFTER -->
<tr class="dt-row{% if l.urgent %} is-urgent{% endif %}" data-id="{{ l.id }}"
```

**Card list** (mobile): already handled in Change 2 CSS via `.lead-card.is-urgent`
and the `is-urgent` class logic below:

In the card list markup (Change 2), change the card outer div:
```html
<div class="lead-card dt-row{% if l.urgent %} is-urgent{% endif %}" data-id="{{ l.id }}"
```

The `.lead-card.is-urgent` CSS rule from Change 2 (`border-left:3px solid var(--danger)`)
already handles the visual treatment.

### Verify

1. Dashboard with `urgent_count > 0`: the Urgent stat tile has a red-tinted
   background and red stat-value number — stands out from the other four tiles.
2. Urgent lead rows have a red left-border stripe (desktop table).
3. On mobile card list: urgent cards have red left-border.
4. No urgent items: tiles all look normal; no red anywhere.
5. `:has()` fallback: test on an older browser — tile renders normally, no JS error.

**Effort: S (20 min) | Risk: Low — CSS :has() only; one template attribute addition
on the `<tr>`; confirmed no collision with existing `.is-selected` style**

---

## Change 8 (Option) — Two-home-screen merge vs. add deep-links

**Priority:** Medium — plan both, implement Option B now, log Option A for later
**Impact:** H (A) / M (B)

### Option A: Full merge (L effort, higher payoff)

Embed the morning briefing widget at the top of `dashboard.html`. Convert the
AI command bar to a sticky bottom drawer (`position:fixed;bottom:0`) available on
the dashboard. The `/command` route becomes a redirect to `/dashboard`. The
command center concept lives as a bottom sheet over the data screen.

**Effort: L (full day) | Risk: High — touches routing, template inheritance,
assistant.js initialization (which expects `.command-shell` to be present),
and the sidebar active-state logic. Defer until the mobile card-list (Change 2)
is shipped and validated.**

**Template changes needed:**
- `command.html` becomes a redirect or the briefing/orb block becomes a Jinja macro
  imported by both templates.
- `app_shell.html` active-state: currently `path.startswith('/dashboard')` for the
  "Command" nav item — would need to cover `/command` too.
- `assistant.js` must initialize when `.command-shell` is present inside
  `dashboard.html`, not as a standalone page.

### Option B: Deep-link briefing items to lead rows (S effort)

The briefing items on the command page open the AI chat (via `data-action`
attributes that the assistant.js click handler sends as a prompt). When the
action is "show me the lead thread," that is three taps + a round-trip vs.
one tap to the lead row.

Add a `deep_link` field to briefing items: if present and the action is
a lead-level thread view, render the `briefing-row` button as an `<a href="/dashboard?lead_id=X">`.

**Backend:** Add `deep_link` to the briefing item dict in the route handler
for items where `action` is a "view thread" intent.

**Template (command.html):**
```html
{% if it.get('deep_link') %}
<a class="briefing-row" href="{{ it['deep_link'] }}">
{% else %}
<button type="button" class="briefing-row" data-action="{{ it['action'] }}">
{% endif %}
  ...content...
{% if it.get('deep_link') %}</a>{% else %}</button>{% endif %}
```

**Dashboard JS:** On page load, check `?lead_id=X` in the URL. If present, auto-open
that lead's conversation:

```js
// In app.js, at the end of the Dashboard conversation viewer IIFE:
const urlLead = new URLSearchParams(location.search).get('lead_id');
if (urlLead) {
  const autoRow = document.querySelector('.dt-row[data-id="' + urlLead + '"]');
  if (autoRow) { autoRow.scrollIntoView({block:'nearest'}); openLead(autoRow); }
}
```

**Effort: S (45 min) | Risk: Low — additive; no structural change to routing or
assistant.js. Implement Option B now. Queue Option A for sprint 2.**

---

## Collision + Risk Summary

| Change | Files | Collision surface | Risk |
|--------|-------|-------------------|------|
| 1 — Nav labels | app.css | All signed-in pages at <=900px | Low |
| 2 — Card list | dashboard.html, app.css, app.js (3 lines) | Dashboard only | Medium |
| 3 — Tap targets | app.css | All <=640px btn-sm usage | Low |
| 4 — tel: links | dashboard.html | Dashboard leads/appts/screened | Low |
| 5 — Error states | app.js, assistant.js, command.html, ui.css | Command + Dashboard | Low-Med |
| 6 — All clear state | command.html + route handler | Command center only | Low |
| 7 — Urgency signals | app.css, dashboard.html | Dashboard only | Low |
| 8B — Deep-links | command.html, app.js, route handler | Command + Dashboard | Low |

**Most dangerous change:** Change 2 (card list). The existing `.dt-row[data-id]`
JS selector must match both `<tr>` elements (table, desktop) and `<div>` elements
(card list, mobile). The selector is class + attribute based so it naturally
selects both — verify with a querySelectorAll spot-check in the browser console.

**Smart-quote / ASCII risk:** Changes 6 and 5 use `&mdash;` (HTML entity, safe
in Jinja) and standard apostrophes in JS string literals. No curly quotes
introduced. All new Jinja strings use straight ASCII quotes.

---

## Ordered Change List (quickest wins first)

1. **Change 1** — Nav labels restored + 48px tap target — `app.css` — **S**
2. **Change 3** — Tap targets on action buttons — `app.css` — **S**
3. **Change 4** — tel: links on phone numbers — `dashboard.html` — **S**
4. **Change 7** — Urgency signals (tile tint, row border) — `app.css`, `dashboard.html` — **S**
5. **Change 5** — Error states styled as errors — `app.js`, `assistant.js`, `command.html`, `ui.css` — **S**
6. **Change 6** — All-clear empty state — `command.html` + route — **S**
7. **Change 8B** — Briefing deep-links to lead rows — `command.html`, `app.js`, route — **S**
8. **Change 2** — Mobile card-list layout — `dashboard.html`, `app.css`, `app.js` — **M**
9. **Change 8A** — Two-home merge (optional, sprint 2) — full stack — **L**

**Total effort without 8A:** 5 x S + 1 x M = approx. half a day (S items in
parallel) + 2-3 hrs for the card list.

**Biggest risk:** Change 2 (card list) — the parallel DOM approach is safe but
requires verifying that JS row selectors match both `<tr>` and `<div>` elements.
Spot-test with `document.querySelectorAll('.dt-row[data-id]')` in the browser
console after shipping.
