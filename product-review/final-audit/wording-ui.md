# Wording + Layout/Design + A11Y Audit — Batches C–G
**Scope:** `git diff 92aacde..HEAD` — templates, static CSS/JS only. Read-only.
**Date:** 2026-06-20

---

## Verdict

**SHIP-WITH-FIXES**

Two P1 issues (one honesty, one a11y) and one P2 consistency gap need fixes before launch, but no P0 blockers were found. The wording discipline throughout this build is strong — the estimate vs. confirmed split in the ROI headline is especially well-executed. Fix the customers.html OG copy (overclaims real results that don't exist yet) and add aria-labels to the widget's phone/name inputs, then ship.

---

## P0 / P1 / P2 Findings

| Severity | File:line | Issue | Fix |
|----------|-----------|-------|-----|
| **P1** | `templates/customers.html:8,11` | OG/Twitter meta description reads "Real results from real contractors. FirstBack books the jobs you were missing." — but the page has zero real testimonials. Two blockquotes acknowledge this honestly; the metadata directly contradicts them. A social share of this URL will surface a factually false claim. | Change to: `"The space where real contractor results will live — be the first to share yours."` or similar hedged copy that matches the honest placeholder body. |
| **P1** | `static/widget.js:58-59` | The `fb-w-phone` and `fb-w-name` inputs have no `<label>` elements and no `aria-label` attributes. `placeholder` alone is not an accessible name (WCAG 1.3.1, 4.1.2). A screen-reader user will hear "edit, blank" for both fields. The dialog itself has `aria-label="Text us"` (good), but the fields inside are unlabeled. | Add `aria-label="Your phone number"` and `aria-label="Your name (optional)"` to the respective `<input>` elements in the injected HTML string. |
| **P2** | `templates/resources.html:24` | The Webinars card links to `/webinars` with the CTA "Save your spot" — an active commitment for a resource that has no scheduled events. The nav correctly de-linked Webinars (Plan 09-10), but this card still points to a dead-end. This is an inconsistency, not a new regression (it was pre-existing), but the batch touched this file (`resources.html` is in the diff), making it in scope to flag. | Change the card CTA to "Coming soon" (non-link) or remove the card until a real webinar date is set, to match the intent of Plan 09-10. |
| **P2** | `templates/analytics.html:6` | Page subtitle reads: "What FirstBack has recovered for [biz] — leads captured, estimates booked, and an estimate of the revenue that would have walked." The phrase "what FirstBack has recovered" implies collected money; the rest of the sentence corrects it, but the lead clause will be read first and remembered. | Change opening to: "What FirstBack has captured for [biz] —" or "Leads and bookings FirstBack has captured —" to avoid the "recovered = collected" implication at the start. |
| **P2** | `templates/growth_tray.html:41` | "they know you, they book faster" — a conversion-speed claim stated as fact, not as a rationale. Warm re-engagement cohorts do typically convert faster, but this product has no data to cite. | Soften to: "they know you and are more likely to book quickly" or "warm leads often book faster." |

---

## Honesty Check

**The single most important question: does any new copy overclaim?**

**Yes — one issue (P1 above):** `customers.html` OG/Twitter descriptions assert "real results from real contractors" when the page body itself admits there are none yet. Every other new copy area passes:

- **ROI headline (analytics.html):** Excellent discipline. Confirmed revenue (owner-entered) is labeled "confirmed recovered." Unconfirmed bookings are labeled "~$X estimated recovered." The fallback is "estimated recovered." The footnote ("Revenue is an estimate — not collected money.") is mandatory and always rendered. The `roi-foot` footnote also appears unconditionally below the fold.
- **Monthly recap SMS (alerts.py:258):** Appends `(estimated)` or `(based on your job value)` to every revenue figure. The ROI multiple is conditional (`if multiple`). No fabricated numbers.
- **Pricing page ROI anchor strip ($45K+ claim):** The `*` footnote is present and clearly states the math: "Based on contractors missing 5-10 calls/week at an average job value of $300–$1,500." The claim is a plausible range, not a study citation. This is borderline but defensible because it's sourced math, not a made-up number.
- **Voice callback on pricing page:** Labeled "coming soon" + "(beta — not yet available)" in the feature list and the FAQ is clear: "Today FirstBack handles everything by text." Honest.
- **Customer book lifetime value tile (~$...):** Uses `avg_is_estimated` flag to show "Trade estimate — set yours in Settings" when the figure is estimated. The `~$` prefix on the tile itself signals estimation.
- **Daily cap wording:** Changed from "Resting for a moment" (evasive) to "You've hit today's limit" (honest). Good fix.
- **Seasonal play:** "they book faster" is a mild unsubstantiated claim (P2 above) but not a serious overclaim — flagged separately.
- **"Set up in one day" (landing.html meta):** The onboarding flow was audited in a prior wave and confirmed as genuinely accomplishable in a day. Acceptable.

---

## Verified-Good

**CSS / Token existence:**
- `--space-5` added to `tokens.css` in Batch C — the previous miss is fixed.
- All new `var()` references in the diff resolve to defined tokens: `--accent`, `--accent-bg`, `--accent-strong`, `--accent-ring`, `--bg`, `--border`, `--border-strong`, `--danger`, `--danger-bg`, `--danger-ring`, `--ink`, `--ink-soft`, `--ink-faint`, `--radius`, `--surface`, `--text-sm`, `--text-xs` — all confirmed in `tokens.css` + `ui.css` + `app.css`.
- Pre-existing undefined-ish vars `--text-muted`, `--surface-card`, `--radius-lg` in `growth_tray.html` are pre-Batch-C and not new — out of scope but noted.
- `--surface-2` used in `.sidebar-logout:hover` is defined in `tokens.css:15`. Clean.

**Smart-quote / Jinja safety:**
- All typographic characters (em-dashes `—`, curly apostrophes `'`) in the diff appear exclusively in display-text HTML (comment text, `<p>` body, `<span>` labels) — never inside a Jinja expression `{{ }}` or `{% %}`, an HTML attribute value, or a JS string literal that would break parsing.
- The one JS string that could be tricky is `widget.js` line 60: `'Got it — we'll text you right back!'` — the `—` is an HTML entity (`&mdash;` rendered into innerHTML) and the apostrophe is an actual curly right single quotation mark U+2019, inside a double-quoted JS string. This is safe because the outer JS string delimiter is `"`, not `'`.

**Responsive / layout:**
- Mobile lead card list (`.lead-cards`) correctly uses `display:none` at ≥640px and `display:flex` at <640px via the media query block. Desktop table (`.leads-table-wrap`) inverts correctly.
- ROI anchor strip on `pricing.html` has `flex-wrap:wrap` and `gap:clamp(16px,4vw,40px)` — will stack at narrow viewports.
- Sidebar nav at mobile: `overflow-x:auto; scrollbar-width:none` with labels preserved (`display:inline`) and `min-height:48px` on `.nav-item`. The "Customers" addition fits the scrolling strip without breaking layout.
- `stat-row` on `customer_book.html` uses `repeat(auto-fit, minmax(0, 1fr))` — will collapse to `1fr 1fr` at mobile (existing `@media` rule in `app.css:170`) then single column if tiles are too wide.
- Growth tray streak bar: pure inline flex with proportional `span` elements — no overflow risk.

**A11y:**
- Mobile lead cards carry `role="button" tabindex="0" aria-pressed="false" aria-label="Open conversation with [name]"` — identical to the desktop `<tr>` rows. Batch C's fix held.
- Keyboard handler fix in `app.js:335`: `if (e.target !== row) return` prevents the card's `tel:` link from triggering the conversation-open handler on Enter/Space — keyboard dialing still works.
- Reduced-motion respected: `app.js:306` checks `window.matchMedia("(prefers-reduced-motion:reduce)")` and falls back to `"auto"` for `.scrollIntoView()` on mobile.
- "All clear" block in `command.html:62` has `role="status" aria-label="All clear"` — live region is appropriate.
- "Customers" nav item in `app_shell.html:50–53` has the `<span>Customers</span>` label, matching all other nav items.
- `convo-mark-won` button has a visible text label ("Mark closed ($)"). The `won-amount-input` has `aria-label="Closed job amount in dollars"`. The Save button text is programmatic (changed to "Saving..." / "Try again" via JS) — acceptable since it's adjacent to the labeled input.
- Widget panel: `role="dialog" aria-label="Text us"` and close button `aria-label="Close"` are correct. The floating trigger `aria-label="Text us"` is correct. **Exception:** phone/name inputs lack labels (flagged as P1 above).
- `chat-error-turn` (ui.css + app.js) uses visible color + border differentiation for error state — not color-only (has border-left accent + `color:var(--danger)` text).

**Nav consistency:**
- Webinars de-linked from both `marketing_base.html` and `onboarding.html` navs. Both changes are consistent with each other.
- "Customer stories" re-linked to `/resources/customer-stories` in both navs — consistent.
- "Customers" app nav item matches existing nav-item component pattern (svg + `<span>` label + active-state class).
- `sidebar-logout` gets the `width:44px; height:44px` tap target at mobile — consistent with the 48px `min-height` on nav items.

**Wording / copy (no issues found besides those in findings table):**
- `pill('Urgent', 'urgent')` variant used consistently in both the desktop table and mobile cards.
- "Mark closed ($)" button label is human and clear for a contractor owner.
- "You've hit today's limit" cap message is honest and direct.
- Settings `alert_all_clear` toggle copy: "a short 'all clear' text on quiet days, so you know it's working (needs the morning digest on)" — accurate and appropriately caveated.
- Voicemail/widget settings card subtitle is accurate: both are gated on the respective toggle.
- `pricing.html` "conversations / mo" → "missed-call replies / mo" rename is more precise and less ambiguous. Good change.
