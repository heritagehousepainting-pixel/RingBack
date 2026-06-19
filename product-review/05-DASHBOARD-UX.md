# 05 — Dashboard / Command-Center UX Audit

**Auditor lane:** Dashboard / Command-Center UX, Mobile, & Polish
**Date:** 2026-06-19
**Bar:** best-in-class, Dave test (non-tech contractor on a phone on a job site), set-and-forget, no-spin

---

## What was audited

- `templates/command.html` — Command Center (conversational home page)
- `templates/dashboard.html` — Dashboard (leads, conversation, estimates, alerts)
- `templates/app_shell.html` — Shell chrome (sidebar, responsive nav)
- `static/assistant.css` — Command-center styles
- `static/app.css` — App shell + dashboard layout
- `static/ui.css` — Design system / component tokens
- `static/tokens.css` — Design tokens
- `static/assistant.js` — Orb + chat controller
- `static/app.js` — Dashboard JS (conversation viewer, cancel, re-engage, etc.)
- Component macros: `stat_tile.html`, `empty_state.html`, `chat_bubble.html`, `data_table.html`

---

## Finding 1 — The two-home-screen split hides the daily workload

**WHAT:** The app has two separate "owner home" screens. `/dashboard` is the "did anything happen" operational screen (leads table, estimates, alerts). `/command` is the AI conversation home. The sidebar nav labels them "Command" (pointing to `/dashboard`) and there is no separate "Command Center" entry — the command center (`/command`) IS the nav destination for "Command". First-time owners land on whichever route the redirect sends them. The dashboard's stat tiles are on the dashboard only; the command center's morning briefing cards are on the command page only. On mobile at max-width:900px the sidebar collapses to a horizontal icon-only strip at the top — the nav-item labels are `display:none`, so "Command" and "Pipeline" icons have no visible text labels and rely entirely on icon recognition.

**WHY it matters for Dave:** Dave opens the app between jobs. He needs to see in one glance: "who called, who needs a reply, what's booked today." Right now that answer is split between two screens. The morning briefing on the command page does partially unify this — it lists actionable items — but those briefing items open into the AI chat, not into the leads table. So if Dave wants to see the full thread, he taps a briefing card, the AI loads and responds, and he has to read a chat response. That's three taps and a round-trip to the server where "tap the lead row in the table" would be one tap. On a phone between jobs, each extra step is a dropped ball.

Additionally, on the mobile nav at ≤900px, `nav-item span { display:none }` removes all text labels. Dave sees five icons he has never memorized. "ROI" (a bar chart icon) and "Memory" (a lightbulb icon) are non-obvious. Icon-only nav on a phone is a known UX anti-pattern for infrequent-user apps.

**Recommendation:** Pick one home screen and make it earn the title. Option A (higher lift, higher payoff): merge — embed the briefing widget at the top of the dashboard, keep the AI command bar docked at the bottom (it already exists there). The conversational AI becomes an overlay/drawer, not a separate page. Option B (lower lift): add text labels back to the mobile nav even on ≤900px. Use shorter labels (4–5 chars: "Home", "Jobs", "AI", "ROI", "Setup"). Never go icon-only for this audience. Either way, the briefing items on the command page should deep-link to the actual lead row in the dashboard, not open an AI chat response.

**Impact: H | Effort: M (Option B: S)**

---

## Finding 2 — The Dashboard leads table is not one-handed usable on mobile

**WHAT:** The dashboard leads table (`templates/dashboard.html`) renders a 4-column data table (Customer / Phone / Stage / Received) inside a `.dash-2col` two-column layout (1.5fr + 1fr). At ≤900px, `dash-2col` collapses to a single column (good), but the table itself does not adapt: it remains a 4-column `<table>` inside `.dt-wrap { overflow-x: auto }`. On a 390px phone (iPhone 15), the lead name column and phone column plus two pill columns will still horizontal-scroll. Row tap targets are `<tr>` elements — there is no explicit `min-height` on them, so the tap height is whatever the text height renders at with `padding: 12px 16px` (the `.dt tbody td` padding). That is approximately 40px — just below the 44px WCAG / Apple HIG minimum for comfortable one-thumb tap targets on a phone.

The conversation panel (right column) has `max-height: 460px` fixed, which is reasonable for desktop but is never seen on mobile because the column stacks. On mobile the conversation area appears below the full leads table — the owner has to scroll past all leads to even see the conversation they just opened. There is no sticky "currently selected lead" indicator in the leads table to remind Dave which thread he's reading.

**WHY it matters for Dave:** Dave's in a truck. He opens the app to see who texted back. He's scrolling a table with tiny tap targets on a 6-inch screen. He taps the wrong row, gets the wrong conversation, and gives up. Phone-number format in the table (`dt-muted`) is formatted with `|phone` filter but there's no click-to-call `<a href="tel:...">` on those numbers. If Dave wants to call the lead back from the dashboard, he has to memorize or copy the number.

**Recommendation:**
1. On ≤640px, convert the leads table from a `<table>` to a card list — one card per lead showing name (bold), last message snippet, stage pill, and a "→" chevron. This is the standard native-app pattern and removes the horizontal scroll entirely.
2. Set `min-height: 48px` on `.dt tbody tr` for the intermediate (600–900px) range if the table is kept.
3. Wrap phone numbers in `<a href="tel:{{ l.phone }}">` so Dave can call with one tap from the list.
4. After a lead is selected, auto-scroll the conversation into view on mobile (or use a bottom sheet drawer).

**Impact: H | Effort: M**

---

## Finding 3 — Empty / loading states are good but error states are missing on the command center

**WHAT:** The command center and dashboard both handle the "no data" case correctly with the `empty_state` macro — every card has a good zero-state with actionable copy. The AI thinking state (three animated dots) is correct. The offline banner in `assistant.css` is present (`offline-banner`, shown when the connection drops). But the chat controller in `assistant.js` has an open gap: when an API fetch fails (the `catch` block in `send`), the error is appended to the transcript as a `chat-meta` div: `"Could not send. [error message]"`. This looks identical to a timestamp separator — same class, same dim small text. Dave cannot tell the difference between "10:32 AM" and "Could not send. 503 Service Unavailable."

The usage gauge at the bottom of the command center has three states (normal / low / resting). In the "resting" state (over daily cap), the message is `"Resting for a moment — back shortly."` with no time estimate and no upsell action on mobile (the inline `<a href="/pricing">` is there but it's 10px `ink-faint` text in a 1-line gauge). Dave will think the AI is broken, not that he's hit a limit.

**WHY it matters:** A contractor who gets a silent or confusing error during a send will not try again — he'll assume it failed and move on. Missed lead follow-ups are the core product failure mode.

**Recommendation:**
1. In the `catch` handler in `assistant.js`, render errors into a distinctly styled `.turn.error` bubble — red border-left, or a `.a-note.warn` note card — not a meta timestamp. The text should be plain: "Couldn't send that. Tap to retry."
2. In the usage gauge "resting" state, show a proper nudge card (not inline gauge text): "You've hit today's limit. Refills at midnight — or [add more] to keep going." Match the same `.briefing` card treatment used for action items.
3. Add a retry button on failed turns in the transcript.

**Impact: H | Effort: S**

---

## Finding 4 — The AI Command Center paradigm is underexplained for first-session users

**WHAT:** The command center hero copy says: "Tell me what you want done. I can pull your numbers, show your leads and booked estimates, save a contact, connect your calendar, and text a lead back." This is good capability copy. The suggestion chips (loaded async via `/api/command/suggestions`) should show example prompts — but they are hidden until JS loads, and they are rendered from `data-suggestions` JSON on the section element so they populate correctly. The welcome `data-hello` greeting is personalized.

The problem is: there is no ambient signal of what the AI has already done. The morning briefing shows items that "need you right now," but once the owner has acted on them (or dismissed them by scrolling), the command center homepage is empty except for the orb and the input. A contractor who came back the next day after the initial setup has no persistent "here's what happened while you were on the job" feed — that's on the dashboard, which is a different page.

The command-center "paradigm" — chat with your business AI — is a compelling differentiator but it requires trust-building. The first time Dave types "show my leads" and gets a stat card, that's magic. The second time he opens the app and sees an empty orb with no context, the magic is gone. The briefing slot (`#briefingSlot`) is the right fix and it IS wired — but it only shows `{% if briefing and briefing['items'] %}`, meaning if there are no items (new account, slow day), Dave gets nothing except the static hero copy. There is no "all quiet today — 0 missed calls since yesterday" zero-state briefing.

**WHY it matters:** The product is "set-and-forget." That means every time Dave opens the app he should feel immediately oriented ("all good / here's what needs you"). A blank orb + input box with no context is a chat UI, not a command center.

**Recommendation:**
1. Always render a briefing even when `items` is empty: "All clear — 0 missed calls since [yesterday]. [View dashboard]." This is a one-line zero state, not a card list.
2. Show a persistent "last activity" line in the hero subtitle when items is empty: "Last lead: Dave P. — 2 hours ago. [View]."
3. Consider making the briefing items deep-link directly to the lead row (not through AI chat) for the "show me the thread" action. The AI chat is right for "text them back" — but for "show me the conversation" a direct link is faster.

**Impact: M | Effort: S**

---

## Finding 5 — Contrast and tap-target baseline on mobile nav and action buttons

**WHAT:** The mobile nav collapses to icon-only at ≤900px. The `nav-item` color in its default state is `var(--ink-soft)` = `#4A5160`, on the sidebar background `var(--surface)` = `#FFFFFF`. Contrast ratio of `#4A5160` on `#FFFFFF` is approximately 5.3:1 — passes AA for text, but the interactive tap-zone for each icon is the `nav-item` anchor padding `9px 12px`, which on a horizontal strip at ≤900px means the touch target is approximately the icon width (18px) + 24px padding = 42px x 36px. That is below 44×44px for the height axis.

The `.btn-ghost` buttons on the dashboard action column (Mark as spam, Cancel, Text back) are 32px height (`btn-sm`). At 32px these fail the 44px minimum for comfortable touch use on a phone. These are high-stakes actions — "Cancel estimate" or "Mark as spam" — that Dave will tap while standing or driving.

The logout button in the sidebar footer (`sidebar-logout`) is 32×32px. Fine on desktop, too small on mobile where the footer strip is visible.

**Recommendation:**
1. On ≤640px, increase `.btn-sm` height from `32px` to `40px` minimum, or use full `.btn` size on mobile for destructive/important actions.
2. Mobile nav: add `min-height: 48px` to `.nav-item` in the ≤900px breakpoint (the horizontal strip) so each icon tap zone is 48px tall.
3. `sidebar-logout`: `min-width: 44px; min-height: 44px` on ≤900px.
4. In the Screened calls table, the "This was real" / "Text them back" / "Mark spam" buttons should be at least 40px on mobile — consider moving to a full-row tap on mobile (list card) rather than a table row with a small ghost button at the far right.

**Impact: M | Effort: S**

---

## Finding 6 — Premium / trustworthy visual identity is mostly solid but has one weak seam

**WHAT:** The Command Center is genuinely distinctive — WebGL orb, glassmorphism dock, morning briefing. The dark background with electric-blue/orange accent reads as premium and intentional. The design tokens are clean and consistent. Reduced-motion, offline, battery-save and high-contrast code paths all exist and are implemented correctly — rare for a product at this stage.

The one weak seam: the Dashboard is a different visual register from the Command Center. The dashboard is a standard light-mode data table UI — fine, clean, professional — but after the cinematic command center it reads as a generic SaaS dashboard. The stat tiles have no visual hierarchy emphasis for the most important number (e.g., "Urgent" count should draw the eye first, not share equal weight with "Calls screened"). The "Recent alerts" card at the bottom is essentially a log dump — pill + body text in a plain table — with no visual distinction between a booking event (great news) and an urgent flag (needs action). Both get the same row treatment.

On mobile the stat-row grid at ≤640px uses `1fr 1fr` — two columns of five tiles. That puts "Warm leads" and "Urgent" on one row, which is good. But "Calls screened" ends up on the last row as a solo tile spanning full width (because 5 tiles / 2 columns = 2 rows of 2 + 1 tail). The lone last tile looks like an afterthought.

**Recommendation:**
1. Give the "Urgent" stat tile a distinct treatment when `urgent_count > 0`: add a red left-border or a faint danger-bg wash — same pattern as `.review-nudge` but applied to the tile itself. This makes the "what needs me" signal immediate without reading numbers.
2. In "Recent alerts," distinguish booking events visually: add a green-tinted row or a stronger `pill-booked` badge so good news reads as good news at a glance.
3. On mobile stat-row, consider reordering the tiles: Urgent (if > 0) first, then Leads, Booked, Warm, Screened. Urgency-first ordering is the Dave test in tile form.
4. The four-column leads table could benefit from an `is-urgent` row class adding a red left-border when `l.urgent` is true — currently urgent leads only get a pill, which is easy to miss while scanning.

**Impact: M | Effort: S**

---

## The 3 Highest-Impact UX Fixes

### Fix A — Icon-only mobile nav (Find 1 + 5) — Effort: S, Impact: H
Add short text labels back to the mobile nav strip (≤900px) and bump touch targets to 48px height. This takes 5 lines of CSS. Every contractor using this on a phone immediately benefits. No architecture change.

### Fix B — Error states that read as errors (Find 3) — Effort: S, Impact: H
Replace `addMeta(convo, "Could not send...")` with a styled `.a-note.warn` card and add a retry button. The usage-gauge "resting" state needs a visible card, not grey micro-text. This is 30 lines of JS + 10 lines of CSS. This prevents the "I thought it was broken" drop-off that kills retention.

### Fix C — Mobile lead table → card list (Find 2) — Effort: M, Impact: H
At ≤640px, replace the 4-column table with a per-lead card showing: name (bold), last message preview (1 line, `dt-muted`), stage pill, urgent dot if applicable, and a `tel:` link on the phone number. This is the highest-effort fix on the list but also the most impactful for daily mobile use — Dave's primary interaction surface is the lead list.

---

## Verdict

The UX gap to best-in-class is **medium-large and primarily mobile**. The command center concept is genuinely differentiating and the implementation is more thoughtful than most competitors (briefing, offline state, battery awareness, reduced-motion, accessible focus rings all present). The gap is: (1) the two-screen split makes the daily "what needs me" question take too many taps; (2) on a phone the leads table is a desktop data table that requires horizontal scrolling and has 32px tap targets on high-stakes buttons; and (3) error states are invisible, which means failures are silent. Fix those three things and the daily workflow becomes effortless for a non-tech contractor. The premium visual identity is real but fragile — the Dashboard doesn't match the Command Center's confidence level, and urgency signals are too subtle for someone glancing at a screen for 10 seconds between jobs.

---

## Summary (≤180 words)

**Top findings:**

1. **Two-home-screen split + icon-only mobile nav (H/S)** — Daily workload is split between `/command` and `/dashboard`. On ≤900px, nav text labels disappear leaving icon-only navigation Dave can't memorize. Fix: add short text labels back, bump tap heights.

2. **Mobile lead table unusable one-handed (H/M)** — 4-column table horizontal-scrolls on phones, 32px `btn-sm` tap targets on Cancel/Mark-spam, no `tel:` links on phone numbers. Fix: card-list layout at ≤640px, 44px+ targets.

3. **Errors look like timestamps (H/S)** — Failed AI sends render as `chat-meta` timestamp text. Usage cap ("Resting") is 10px grey micro-text. Fix: `.a-note.warn` error card + retry button; visible cap card.

4. **Blank command center on quiet days (M/S)** — Zero-state briefing is hidden; Dave sees an empty orb with no context. Fix: always render "All clear — 0 missed calls" when no items.

5. **Urgency signals too subtle (M/S)** — Urgent stat tile and urgent lead rows have no distinct visual treatment (just a pill). Fix: red left-border on tile and row when urgent_count > 0.

**Verdict:** Gap to best-in-class is medium-large and primarily mobile. The command-center concept is genuinely differentiating but the daily driver (lead triage on a phone) is a desktop data table in disguise. Three targeted fixes (nav labels, card-list leads, error states) make it field-ready.
