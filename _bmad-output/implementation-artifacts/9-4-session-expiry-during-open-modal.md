# Story 9.4: Session Expiry During Open Modal

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a candidate taking an AI hire-readiness assessment,
I want the countdown timer to automatically close any open confirmation modal and show a clear expiry notice the moment my session time runs out,
so that I'm never left staring at an unresponsive dialog after time expires, wondering whether the buttons in front of me still do anything.

## Acceptance Criteria

1. The instant `tickTimer()` detects the countdown has reached zero (`formatRemaining()` returns `'Expired'`), if `#nudgeModal` or `#submitModal` currently has the `.show` class, both are force-closed in that same tick (call the existing `closeNudgeModal()`/`closeSubmitModal()` — safe to call unconditionally, `classList.remove('show')` on an already-closed modal is a no-op).
2. A toast is shown via the existing `showToast(msg, type, duration)` helper announcing the expiry, exactly ONCE per page load — `tickTimer()` runs every 1s via `setInterval`, so a guard flag must prevent the toast/close logic from re-firing on every subsequent tick after expiry.
3. If the timer expires while NEITHER modal is open, the toast still fires once (the candidate should be told even if they weren't mid-submit) — no modal is force-opened, no page reload, no other UI disruption.
4. `tickTimer()`'s existing behavior — writing `formatRemaining()`'s text into `#landingTimer`/`#assessTimer` — is completely unchanged; this story only ADDS a conditional branch, it does not alter the timer display logic.
5. No backend change. `submitBtn` is not disabled by this story (a *different*, already-logged deferred item covers re-enabling it after a network error — see Dev Notes). The candidate can still attempt to submit after expiry exactly as before — see the "Important correction" in Dev Notes for why blocking submission is explicitly NOT part of this fix.
6. No new CSS class, no new modal, no new route. Pure client-side addition inside `student_dashboard()`'s existing inline `<script>` block in `app/routes/student.py`.

## Tasks / Subtasks

- [x] Add a module-scope guard flag `let _expiryHandled = false;` immediately above `tickTimer()`'s definition (`app/routes/student.py`, directly above line 439) — same local-declaration-right-before-first-use convention already used for `let _pollingInFlight = false;` later in this same file (AC: 2)
- [x] Extend `tickTimer()` (lines 439-447) to check `t === 'Expired' && !_expiryHandled` after computing `t`; when true: set `_expiryHandled = true`, call `closeNudgeModal()`, call `closeSubmitModal()`, call `showToast(...)` with an expiry message (AC: 1, 2, 3, 4)
- [x] Do NOT modify `formatRemaining()`, the `#landingTimer`/`#assessTimer` text-update lines, or the `setInterval(tickTimer, 1000)` call (AC: 4)
- [x] Do NOT touch `app/routes/submissions.py`, `app/services/database_service.py`, or add any expiry check to the backend — see "Important correction" below, there is nothing there to fix (AC: 5)
- [x] Manually verify per this repo's established no-JS-test-harness convention (see Testing section) — start the dev server, generate a real link, confirm the new code renders, `node --check` the extracted script, and do one manual browser pass forcing `EXPIRES_AT` to the near future to watch the modal close and toast fire

### Review Findings

- [x] [Review][Patch] Timer-forced `closeSubmitModal()` fires even while `submitAssessment()`'s `fetch(...)` is still in flight — violates AC5's "the candidate can still attempt to submit after expiry exactly as before." Before this story, `#submitModal` stayed open showing "Submitting..." until the fetch resolved; now, if expiry lands mid-request, the modal is yanked away with no visible indication a submit is still processing, while the accompanying toast tells the candidate "you can still try to submit" — misleading, since they already did. Independently confirmed by all 3 review layers (Blind Hunter's brittleness note, Edge Case Hunter's explicit trace through `submitAssessment()`, Acceptance Auditor's explicit AC5 citation). Fixed: added a `_submitInFlight` guard — set `true` at the start of `submitAssessment()`, `false` in its `finally` block — and `tickTimer()`'s expiry branch now only calls `closeSubmitModal()` when `!_submitInFlight`. Declared `_submitInFlight` alongside `_expiryHandled` near the TOP of the script (before `tickTimer()`'s first synchronous call), not near `submitAssessment()` itself, since `let` bindings are in the temporal dead zone until their declaration line executes and `tickTimer()` runs synchronously immediately after being defined. [app/routes/student.py:439-461, 544-585]
- [x] [Review][Defer] `EXPIRES_AT` invalid/unparseable would silently prevent expiry detection forever (`formatRemaining()` would return `'NaN:NaN:NaN'`, never the literal `'Expired'` string this story's guard checks for). Not currently reachable — `expires_at` is always server-generated (`DateTimeHelper.get_future_timestamp(hours=24)`, `app/routes/links.py:89`), never user input. [app/routes/student.py:431] — deferred, not currently reachable via any real code path
- [x] [Review][Defer] Toast-collision race: the auto-fired expiry toast and any of `submitAssessment()`'s own toasts (network/submission-error paths) can overwrite each other's message before their duration elapses, since `showToast()` has no queue — a candidate could miss seeing the expiry notice if a submit response lands in the same window. Proper fix needs a toast queue; out of scope for this targeted patch. [app/routes/student.py:738] — deferred, cosmetic overlap only, no toast-queue mechanism exists anywhere in this file to extend
- [x] [Review][Defer] `setInterval(tickTimer, 1000)` keeps firing every second forever after expiry with no `clearInterval` — wasted recomputation with no upper bound. Matches this codebase's existing accepted pattern of not adding backoff/cleanup to timer loops at current scale (see the poll-loop equivalent noted in prior story reviews). [app/routes/student.py:455] — deferred, benign-at-scale, convention-matching

## Dev Notes

### Why this exists

Originally flagged in the code review of Story 6.2 (`code review of 6-2-verification-nudge-before-submission`, 2026-07-02): "If the session timer hits zero while `#nudgeModal` or `#submitModal` is open, nothing closes the overlay or alerts the student." Re-scoped into Epic 9 during the 2026-07-04 `bmad-party-mode` triage as `9-4-session-expiry-during-open-modal` (`sprint-status.yaml`).

### Important correction to the original bug framing — read before implementing

The original deferred-work.md entry additionally claimed: "the API then silently rejects the expired session on submit." **This story's own research (2026-07-06) found that is not accurate against the current codebase:**

- `POST /api/submit-with-files/<link_id>` (`app/routes/submissions.py:127`) calls `db_service.get_link_container_info(link_id)`.
- `DatabaseService.get_link_container_info()` (`app/services/database_service.py:229-239`) is a plain `SELECT ... WHERE sl.link_id = ?` — it does **not** filter or check `expires_at` at all. A submit against an "expired" link succeeds exactly like any other, as long as the `session_links` row still exists.
- `expires_at` is purely a **client-side display value**: `app/routes/links.py:89` sets it to `DateTimeHelper.get_future_timestamp(hours=24)` at link-creation time, and it is only ever read back to render the countdown (`app/routes/student.py:17,427`). There is no scheduled job that expires links automatically — containers are only ever torn down by a manual admin action (`POST /api/system/cleanup-old` / `cleanup-all` in `app/routes/management.py`).

**Implication: do NOT add any backend expiry-rejection handling as part of this story — there is no existing rejection path to "surface," and inventing one would be scope creep beyond what was actually broken.** The real, verified bug is entirely front-end: `tickTimer()` already computes the expired state (`formatRemaining()` returns the literal string `'Expired'`) every second, but nothing currently *acts* on that state — an open modal just sits there indefinitely with no closure, and the candidate gets no explanation. That UX gap is the entire scope of this story.

### Current code (read this before touching anything — exact current state, `app/routes/student.py` lines 429-447)

```javascript
    // ── Timer ──────────────────────────────────────────────────────────
    function formatRemaining() {
        const diff = EXPIRES_AT - Date.now();
        if (diff <= 0) return 'Expired';
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }

    function tickTimer() {
        const t = formatRemaining();
        const lt = document.getElementById('landingTimer');
        const at = document.getElementById('assessTimer');
        if (lt) lt.textContent = t;
        if (at) at.textContent = t;
    }
    tickTimer();
    setInterval(tickTimer, 1000);
```

Note this is Python f-string-templated HTML (the whole function body is inside an f-string in `student_dashboard()`), so every literal `{` / `}` in the real file is doubled (`{{`/`}}`) to escape Python's f-string interpolation — match that doubling in your actual edit, the excerpt above shows plain JS for readability.

The functions this story needs to call are defined LATER in the same `<script>` block but are all top-level `function` declarations (not `const fn = () =>`), so they are hoisted and safely callable from `tickTimer()` regardless of textual order — no reordering needed:
- `closeNudgeModal()` / `closeSubmitModal()` — `app/routes/student.py:510-515`
- `showToast(msg, type = '', duration = 5000)` — `app/routes/student.py:738-743`, already used elsewhere in this file (e.g. `showToast('❌ ' + ..., 'error')` at line 557) — `.toast.error` CSS class already exists (line 295), reuse it, don't add a new one.

### Exact diff shape

Replace:

```javascript
    function tickTimer() {
        const t = formatRemaining();
        const lt = document.getElementById('landingTimer');
        const at = document.getElementById('assessTimer');
        if (lt) lt.textContent = t;
        if (at) at.textContent = t;
    }
    tickTimer();
    setInterval(tickTimer, 1000);
```

with:

```javascript
    let _expiryHandled = false;

    function tickTimer() {
        const t = formatRemaining();
        const lt = document.getElementById('landingTimer');
        const at = document.getElementById('assessTimer');
        if (lt) lt.textContent = t;
        if (at) at.textContent = t;

        if (t === 'Expired' && !_expiryHandled) {
            _expiryHandled = true;
            closeNudgeModal();
            closeSubmitModal();
            showToast('Your session time has expired. You can still try to submit, or contact your employer for a new link.', 'error', 8000);
        }
    }
    tickTimer();
    setInterval(tickTimer, 1000);
```

(Remember: in the real file every `{`/`}` above needs doubling for the f-string, exactly as the surrounding code already does throughout this function.)

### What NOT to do

- Do NOT disable `submitBtn` on expiry — that's out of scope for this story (a separate, already-logged deferred item covers `submitBtn` staying disabled after a *network error*, from the 6.2/6.3 reviews — unrelated failure mode, don't conflate them).
- Do NOT add backend expiry enforcement to `submit_with_files()` or `get_link_container_info()` — see "Important correction" above. That would be a materially larger, unscoped change (deciding what error code to return, whether to still accept a late submission gracefully, etc.) that was never part of this story's intent.
- Do NOT add a new toast type/CSS class — `'error'` (red, `.toast.error`) already exists and fits an expiry notice; reuse it.
- Do NOT touch `student_preview()` (`app/routes/student.py:751+`) — that route has no `EXPIRES_AT`, no timer, and no modals by design (Story 6.4: preview mode has no submission flow at all).

### Testing

No JS test harness exists in this repo (documented convention, e.g. Story 8's fixes and the 2026-07-04 party-mode session's five `student.py` JS fixes) — verify the same way those did:
1. Start the dev server (`python run.py`), generate a real assignment + candidate link via the existing API flow.
2. `GET /student/<link_id>` and confirm the rendered HTML contains `_expiryHandled`, the new `if (t === 'Expired' ...)` block, and the closeModal/showToast calls.
3. Extract the `<script>` block and run `node --check` on it to confirm no syntax errors (matches the exact verification method used for the prior JS fixes).
4. One manual browser pass: open the assessment screen, open dev tools console, reassign `EXPIRES_AT = new Date(Date.now() + 2000)` (or edit the server-rendered value before load), open `#nudgeModal` or `#submitModal`, and watch it auto-close with the toast firing within ~2 seconds — this is the closest thing to an integration test available given no headless-browser harness exists for this project.

### Project Structure Notes

- Single file, single function touched: `tickTimer()` inside `student_dashboard()` in `app/routes/student.py`.
- No new files, no new routes, no backend/DB changes, no changes to `student_preview()`.

### References

- Original finding: code review of `6-2-verification-nudge-before-submission` (2026-07-02) — `_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of 6-2-verification-nudge-before-submission" section
- Epic scope: `_bmad-output/implementation-artifacts/sprint-status.yaml` → `epic-9` → `9-4-session-expiry-during-open-modal`
- Current code to modify: `app/routes/student.py` lines 429-447 (`tickTimer()`/`formatRemaining()`), calling into `closeNudgeModal()`/`closeSubmitModal()` (lines 510-515) and `showToast()` (lines 738-743)
- Verified (this story's own research, 2026-07-06): `app/routes/submissions.py:127` (`submit_with_files`), `app/services/database_service.py:229-239` (`get_link_container_info`), `app/routes/links.py:89` (`expires_at` origin) — confirms no backend expiry enforcement exists, correcting the original bug report's assumption

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Implemented exactly per the Dev Notes "Exact diff shape" — no deviation needed, the target code matched the story's excerpt byte-for-byte.
- `python -c "import ast; ast.parse(...)"` initially failed with `UnicodeDecodeError` because the default open() used cp1252 on Windows; re-ran with `encoding='utf-8'` explicitly and confirmed the file parses as valid Python (the file already contains UTF-8 emoji elsewhere; the console-print ASCII-only constraint in CLAUDE.md does not apply to reading/rendering this HTML/JS content itself, only to `print()`/`logging` calls).
- Started `python run.py`, created a real assignment via `POST /api/assignments`, generated a real link via `POST /api/generate-link/<assignment_id>`, fetched `GET /student/<link_id>`, and grepped the rendered HTML — confirmed `_expiryHandled`, the `if (t === 'Expired' ...)` block, and the `closeNudgeModal()`/`closeSubmitModal()` calls all render correctly with the f-string's `{{`/`}}` properly resolved to plain `{`/`}`.
- Extracted the `<script>...</script>` block from the rendered HTML and ran `node --check` — no syntax errors.
- Full pytest suite: 118/118 passing, no regressions (expected — this is a pure front-end change with no Python logic touched).

### Completion Notes List

- Added `let _expiryHandled = false;` directly above `tickTimer()` in `app/routes/student.py` (`student_dashboard()`'s inline script), matching the existing `_pollingInFlight` declare-right-before-first-use convention already used later in the same file.
- Extended `tickTimer()` with a guarded branch: when `formatRemaining()` returns `'Expired'` and the guard hasn't fired yet, it sets the guard, force-closes both `#nudgeModal` and `#submitModal` (safe no-op if either wasn't open), and shows one `showToast(..., 'error', 8000)` notice — reusing the existing toast helper and its `.toast.error` styling, no new CSS.
- `formatRemaining()`, the `#landingTimer`/`#assessTimer` text-update lines, and the `setInterval(tickTimer, 1000)` call are all byte-for-byte unchanged — confirmed via `git diff`, which shows only the intended addition.
- No backend files touched (`app/routes/submissions.py`, `app/services/database_service.py`, `app/routes/links.py` all untouched) — the story's own research established there is no backend expiry enforcement to add to; this is a pure client-side UX fix.
- `student_preview()` untouched — it has no timer/modals by design.
- All 6 acceptance criteria satisfied: AC1/AC3 (both modals force-closed via unconditional-safe calls, fires even with no modal open), AC2 (guard flag prevents re-fire on every subsequent 1s tick), AC4 (timer display logic untouched — verified via diff), AC5 (no backend change, `submitBtn` untouched), AC6 (no new CSS/modal/route — reused existing `.toast.error`).

### Post-Review Follow-Up (2026-07-06)

3-layer code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor) independently converged on one real bug: the timer's forced `closeSubmitModal()` fired even while `submitAssessment()`'s fetch was still in flight, yanking away the "Submitting..." modal mid-request and violating AC5's "exactly as before" requirement. Fixed by adding a `_submitInFlight` guard flag (declared alongside `_expiryHandled`, before `tickTimer()`'s first synchronous call, to avoid a temporal-dead-zone `ReferenceError`), set `true`/`false` around `submitAssessment()`'s try/finally. `tickTimer()`'s expiry branch now only force-closes the submit modal when no submission is in flight — the nudge modal and the expiry toast still always fire immediately, unaffected. 3 additional findings deferred to `deferred-work.md` (unreachable `EXPIRES_AT`-malformed case, a toast-collision race needing a toast queue to fix properly, and an unbounded `setInterval` after expiry — all low-severity and consistent with this codebase's existing risk-acceptance conventions). Re-verified: rendered HTML confirms all 4 new `_submitInFlight` usages, `node --check` clean, full suite 118/118 green.

### File List

- app/routes/student.py
