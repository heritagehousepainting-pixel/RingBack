# Phase 5c Correctness / Integration Audit

**Date:** 2026-06-18  
**Branch:** `staging` @ 1af7195  
**Auditor:** Read-only; no source or test files modified.  
**Suite:** 51 tests — all green.

---

## P1 Findings (must fix before $99 bar)

### P1-A — `settings.html` unconditional monitor-mode note
**File:** `templates/settings.html` lines 88–90  
**What breaks:** A hardcoded `<div>` saying "Screening is in monitor mode" has no surrounding `{% if screen_mode == 'monitor' %}` guard. It renders unconditionally — so a business that has auto-graduated to **enforce** (or that manually selected **off**) sees both the hardcoded "monitor mode" copy AND the correct conditional note below it (lines 100–106). The two messages directly contradict each other when mode is `enforce`.

**Root cause:** Pre-existing from commit `a9c00cd` (Phase 0 GAMMA). The correct per-mode conditional block was added in 5c but the old hardcoded note was not removed or gated.

**Suggested fix:**  
Wrap lines 88–90 in `{% if screen_mode == 'monitor' %}...{% endif %}`, OR delete them entirely since the conditional block at lines 100–106 already covers all three states correctly.

---

### P1-B — `would_screen` counts `screened_contact` toward graduation threshold + alert
**File:** `db.py` line 1891, `reminders.py` line 534–535, `alerts.py` line 125–128  
**Spec reference:** `PHASE5C-SPEC.md` line 57: "`would_screen` = monitor screened_spam"

**What breaks:** `db.screening_stats()` defines `would_screen` as:
```sql
SUM(CASE WHEN screen_status IN ('screened_spam','screened_contact') AND screen_mode='monitor' THEN 1 ELSE 0 END) AS would_screen
```
It includes **`screened_contact`** (known personal contacts, vendors, blocked numbers) alongside spam verdicts. The graduation job uses this same count:
```python
stats = db.screening_stats(bid, since=window_start)
would_screen = stats.get("would_screen", 0)
```
And the alert message says:
```
"Spam blocking is now ON -- this week we'd have blocked {N} robocallers and you rescued none."
```

**Proven by probe:** With `spam=5, screened_contact=6`, `would_screen=11` → graduation fires and the alert says "11 robocallers" when 6 were personal contacts. This violates the spec ("monitor screened_spam") and the alert is factually wrong.

**Impact:** Could trigger premature graduation when a business has many known contacts (vendors, family) that the phone screen naturally identifies. The "robocallers" claim is misleading to the owner.

**Suggested fix:** Either  
(a) In `db.screening_stats()`, change `would_screen` to only count `screened_spam`, OR  
(b) Add a `would_screen_spam` field alongside `would_screen` and use it in the graduation check and alert.  
Option (a) is a breaking change to `screening_stats` (affects the dashboard stat tile too which groups both). Option (b) is safer. The alert copy must reference only spam verdicts regardless.

---

## P2 Findings (fix before ship, not blocking)

### P2-A — `scan_screening_graduation`: `now_str` computed but never used
**File:** `reminders.py` line 495  
```python
now_str = now or now_dt.isoformat()
```
`now_str` is assigned and immediately discarded. The actual age calculation uses `now_dt` (real time). The `now` parameter accepted by the function is therefore non-functional — time-travel in tests must be done by manipulating `window_start`, not by passing `now`. This is a code smell that would confuse a future maintainer trying to test graduation timing without DB surgery.

**Suggested fix:** Either use `now_str` in the age calculation (parse it to a datetime) or remove the `now` parameter and document that the function always uses wall time.

---

### P2-B — `/pipeline` shows "Learning" card when manually-enforce, no `screening_promoted_at`
**File:** `app.py` lines 780–790  
```python
if _window_start and not biz.get("screening_promoted_at"):
    ...  # computes grad_days -> Learning card shows
```
When an owner manually sets `screen_mode = 'enforce'` via Settings (bypassing auto-graduation), `screening_promoted_at` is NULL (only `promote_screening()` sets it). The cockpit renders the "Learning (Day N of 7) — Nothing is silenced yet" card, which contradicts the active enforcement.

**Proven by probe:** With `screen_mode='enforce'`, `screening_promoted_at=NULL`, `window_start=3 days ago`, `/pipeline` renders `"Spam Shield: Learning"`.

**Suggested fix:** Add a mode guard:
```python
if _window_start and not biz.get("screening_promoted_at") and _effective_screen_mode(biz) == 'monitor':
```

---

### P2-C — `or` vs `is None` for per-tenant thresholds
**File:** `app.py` line 2355–2356  
```python
hard = biz.get("screen_hard") or SCREEN_SCORE_HARD
mid  = biz.get("screen_mid")  or SCREEN_SCORE_MID
```
A stored value of `0` would silently fall back to the config default. In practice the UI only writes values from `SCREEN_SENSITIVITY_PRESETS` (minimum `35`) or `NULL`, so `0` is never stored through normal paths. Theoretical-only in the current codebase, but semantically wrong.

**Suggested fix:**
```python
hard = biz.get("screen_hard") if biz.get("screen_hard") is not None else SCREEN_SCORE_HARD
mid  = biz.get("screen_mid")  if biz.get("screen_mid")  is not None else SCREEN_SCORE_MID
```

---

## Verified Correct

| Area | Verdict |
|------|---------|
| Templates parse (both dashboard.html and settings.html with app filters) | PASS |
| Smart quotes: all curly apostrophes are content inside ASCII-delimited Jinja2 strings | PASS |
| Burst precision-first: `+35 < HARD=80`, never reaches HARD alone | PASS |
| Burst double-count prevention: `burst_count = 0` when `crowd_count >= CROWD_MIN` | PASS |
| Window boundary: exactly 7d passes (`age_days < 7` → `False` at exactly 7.0) | PASS |
| Lazy-init: NULL `window_start` → set to now + skip current pass | PASS |
| Rescue atomicity: upserts customer, increments `screening_false_positives`, resets window in one conn | PASS |
| Rescue idempotency (2nd tap): does not double-text (thread-exists guard); fp increments again (correct) | PASS |
| Rescue opt-out guard: 400 for `is_suppressed` callers | PASS |
| Double-graduation prevention: after promotion, `screen_mode='enforce'` → graduation job skips | PASS |
| Alert dedupe: `screening_graduated` key + 1-year window per business | PASS |
| Effective mode: `reminders.py` inline calc matches `app.py._effective_screen_mode()` for all inputs | PASS |
| Settings round-trip: `screen_sensitivity=aggressive` → `screen_hard=65, screen_mid=35` → reloads checked | PASS |
| Per-tenant thresholds: flow into **both** `triage.screen_caller()` calls in `_screen_missed_caller` | PASS |
| Reputation gate: toggle off → no paid lookup; toggle on → lookup fires in ambiguous band | PASS |
| `record_screening_rescue` ↔ graduation seam: rescue sets `window_start=now()` → `age_days<7` → no graduation | PASS |
| `db.promote_screening()`: sets `screen_mode='enforce'` + `screening_promoted_at` atomically | PASS |
| `db.global_spam_count(within_hours=N)`: correctly filters by `created_at >= now - Nh` | PASS |
| CORE documented deviation (burst only when crowd < CROWD_MIN): sound, no double-count | PASS |
| `scan_screening_graduation` wired in `tick_once` with try/except isolation | PASS |
| `screening_graduated` in `ALERT_KINDS`, `_TOGGLE_COL`, `_LONG_DEDUPE_KINDS`, `_subject` | PASS |
| Alert message: says "blocked N robocallers" not "texted" or "contacted" | PASS |
| `_save_screening_prefs`: unknown/blank preset writes `NULL, NULL` (correctly clears overrides) | PASS |
| `test_screening_graduation.py`: real DB, covers all 7 spec gates + alert body + column existence | PASS |
| `test_screening_ui.py`: real test client, rescue/double-tap/opt-out/threshold/reputation/cockpit | PASS |
| utcnow dead-branch: `window_start` is always written with `timezone.utc` → `_ws.tzinfo` never None | PASS |
| Suite: all 51 tests green | PASS |

---

## Test Coverage Gaps (P2, no failing test)

1. **No test for P1-B (screened_contact graduation inflation)** — test always uses `status="screened_spam"`. A mixed-verdict graduation test is missing.
2. **No test for P2-B (manual enforce + Learning card)** — test_screening_ui.py only checks monitor mode for the cockpit card.
3. **Settings reverse-map of "default" (NULL) preset** — tested implicitly but no explicit round-trip for "choose aggressive, save, then choose Default, verify NULL".
4. **`scan_screening_graduation(now=...)` time-travel** — parameter is accepted but unused; no test catches this.
