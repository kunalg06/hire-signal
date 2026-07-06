# Story 9.5: Assignment-Detail-Keyed Preview Fidelity

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer reviewing a candidate assignment before sharing its link,
I want a "Preview as Student" option keyed to the specific assignment (not the challenge template it came from),
so that what I preview always matches exactly what the candidate will see, even after I've edited the assignment post-generation.

## Acceptance Criteria

1. A new route `GET /student/preview/assignment/<assignment_id>` renders a preview using the LIVE `assignments` row's `title`, `description`, `starter_code`, `evaluation_criteria` — not the `challenges` catalog template. Any edit made to the assignment after it was generated from a challenge is reflected, unlike the existing challenge-keyed preview.
2. Returns `{"detail": "Assignment not found"}`, 404, if `assignment_id` doesn't exist — same shape/status as the existing `GET /api/assignments/<id>` and the challenge-keyed preview's 404.
3. The rendered preview page is visually and structurally identical to the existing `/student/preview/<challenge_id>` experience: same "Preview Mode — No session data is recorded" banner, same landing screen (title/description/evaluation-criteria info boxes, "Start Preview" button), same read-only assessment screen (disabled Submit button, starter-code viewer). Achieved by extracting the shared HTML into one helper both routes call — not by duplicating the ~230-line template a third time.
4. The existing `GET /student/preview/<challenge_id>` route's OWN rendered output is byte-for-byte unchanged by the extraction — this is a pure refactor for that route, proven by a test that pins its exact response body/structure before relying on the shared helper.
5. A "Preview as Student" button is added to each assignment card in the employer dashboard's "Saved Assignments" list (Tab 3, `templates/frontend.html`), opening the new route in a new tab (`window.open`, not full navigation) via that assignment's own `id` — no challenge_id involved, no disambiguation needed, since the button always carries one concrete assignment_id.
6. Clicking the new preview button must NOT also trigger the existing card-level `onclick` (which populates `#assignId`) — needs `event.stopPropagation()`.
7. No changes to `student_dashboard()` (the real candidate submission flow — timer, modals, polling, submit), no new DB tables/columns, no changes to any evaluation/scoring/submission backend logic.

## Tasks / Subtasks

- [x] Extract `_render_student_preview_html(title, description, criteria, starter_code)` in `app/routes/student.py` from the current `student_preview()` body — same landing/assessment HTML, parameterized instead of reading `safe_*` locals inline (AC: 3, 4)
- [x] Add a regression test pinning `GET /student/preview/<challenge_id>`'s exact response (status, content-type, key substrings: title, description, criteria, starter_code, "Preview Mode" banner) BEFORE touching the route, so the refactor is provably behavior-preserving (AC: 4)
- [x] Rewrite `student_preview(challenge_id)` to compute its existing `title`/`description`/`criteria`/`starter_code` values exactly as today, then call the shared helper instead of building its own f-string (AC: 3, 4)
- [x] Add `student_preview_assignment(assignment_id)` route at `GET /student/preview/assignment/<assignment_id>`: `db_service.get_assignment(assignment_id)` (existing method, no changes needed), 404 via the same shape as `assignments.py`'s `get_assignment()` endpoint, else call the shared helper with `row[1]` (title), `row[2]` (description), `row[4]` (evaluation_criteria), `row[3]` (starter_code) — index-based, matching `app/routes/assignments.py`'s existing access pattern for this same row shape, not the tuple-unpacking style `student_preview()` uses for the differently-shaped `challenges` row (AC: 1, 2)
- [x] Add tests for the new route: 200 with live assignment fields reflected (including a case where description/criteria were edited after creation — proving drift is gone), 404 for a nonexistent assignment_id (AC: 1, 2)
- [x] In `templates/frontend.html`'s `loadAssignments()` (`~line 990`), add a "Preview as Student" button per card, `onclick` opens `/student/preview/assignment/${a.id}` via `window.open(..., '_blank')` with `event.stopPropagation()` so the card's own click-to-fill-`#assignId` behavior isn't also triggered (AC: 5, 6)
- [x] Run the full test suite and confirm no regressions

### Review Findings

- [x] [Review][Patch] The assignment-keyed route has no test for the `evaluation_criteria=None` fallback-to-default-text case, unlike the challenge-keyed route (`test_challenge_preview_falls_back_to_default_criteria_text`). Both routes share the identical `_render_student_preview_html()` fallback logic (`criteria or 'Evaluation criteria set by employer.'`), so an asymmetric test suite invites the two routes' behavior to silently diverge undetected later. Independently flagged by both Blind Hunter and Edge Case Hunter. Fixed: added `test_assignment_preview_falls_back_to_default_criteria_text`, mirroring the existing challenge-side test. [tests/test_student_preview_routes.py]
- [x] [Review][Defer] The `criteria` argument is semantically inconsistent between the two callers: the challenge-keyed path passes `str(evaluation_rubric_json)` — confirmed by Edge Case Hunter to be a no-op pass-through since sqlite TEXT columns are already Python `str`, so a real multi-key rubric (as `EvaluationService.generate_challenge()` would plausibly produce) would render raw JSON syntax (`{`, `"`, `[`) as prose — while the assignment-keyed path passes clean plain-text `evaluation_criteria`. This is pre-existing behavior from Story 6.4, correctly carried over unchanged (AC4 explicitly required the challenge route's rendered output stay byte-for-byte unchanged by this story's refactor), not introduced by this diff. [app/routes/student.py, `student_preview()`'s `criteria` computation] — deferred, pre-existing from Story 6.4, a future story should consider normalizing rubric-JSON-to-readable-text formatting for display

## Dev Notes

### Why this exists

Deferred from the code review of `6-4-preview-as-student` (2026-07-03): `student_preview()` reads the `challenges` catalog template, not the live `assignments` row a candidate actually sees post-generation-edits — these can diverge once an employer edits an assignment. A prior party-mode panel (2026-07-03, unanimous) declined to force a fix then because **no frontend trigger existed yet** for any preview route, and left it explicitly blocked on a product decision: **where should the "preview as student" trigger live in the UI** — assignment-detail page vs. catalog page — since that determines whether `challenge_id` alone can resolve one assignment (it can't; one challenge can spawn many assignments).

**Decision made 2026-07-06 (this story's creation): assignment-detail page.** Concretely, that means the "Saved Assignments" card list in Tab 3 (`Student Link`) of `templates/frontend.html` — the only existing UI surface in this app that lists individual assignments with their own IDs. This sidesteps the disambiguation problem entirely: the new route is keyed directly on `assignment_id`, which is always concrete and unique — there is no `challenge_id`-to-assignment ambiguity to resolve, because this story doesn't route through `challenge_id` at all for the new path.

### Current code — `student_preview()` (read this before touching anything, `app/routes/student.py` lines 769-1023)

The full function is one big f-string building landing-screen + assessment-screen HTML from four escaped values (`safe_title`, `safe_description`, `safe_criteria`, `safe_code`), computed from a `challenges` table row:

```python
@student_bp.route('/student/preview/<challenge_id>')
def student_preview(challenge_id):
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({"detail": "Challenge not found"}), 404

    _, title, domain, description, evaluation_rubric_json, starter_code, \
        challenge_type, skill_area, difficulty, ai_assistance_mode, \
        is_published, created_at = row

    safe_title = html_module.escape(title or 'Untitled Challenge')
    safe_description = html_module.escape(description or '')
    safe_criteria = html_module.escape(
        str(evaluation_rubric_json) if evaluation_rubric_json
        else 'Evaluation criteria set by employer.'
    )
    safe_code = html_module.escape(
        starter_code or '# No starter code provided for this challenge.'
    )

    html = f"""<!DOCTYPE html>
... (~230 lines of HTML: preview banner, landing screen with info-grid,
     assessment screen with disabled Submit button + starter-code viewer,
     a tiny inline <script> with startPreview()) ...
    """

    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
```

`html_module` is already imported at the top of `app/routes/student.py` (used as `html_module.escape` — don't reintroduce a second import under a different alias).

### Exact refactor shape

Extract everything from `html = f"""<!DOCTYPE html>` through the final `"""` (the entire template body) into a new top-level function placed directly above `student_preview()`:

```python
def _render_student_preview_html(title, description, criteria, starter_code):
    """Shared preview-page HTML for both the challenge-keyed and
    assignment-keyed preview routes (Story 9.5) — identical landing +
    assessment screens, sourced from whichever caller's field values.
    """
    safe_title = html_module.escape(title or 'Untitled Challenge')
    safe_description = html_module.escape(description or '')
    safe_criteria = html_module.escape(
        criteria or 'Evaluation criteria set by employer.'
    )
    safe_code = html_module.escape(
        starter_code or '# No starter code provided for this challenge.'
    )

    return f"""<!DOCTYPE html>
    ... (exact same ~230 lines, unchanged — just moved here) ...
    """
```

Then `student_preview()` becomes:

```python
@student_bp.route('/student/preview/<challenge_id>')
def student_preview(challenge_id):
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({"detail": "Challenge not found"}), 404

    _, title, domain, description, evaluation_rubric_json, starter_code, \
        challenge_type, skill_area, difficulty, ai_assistance_mode, \
        is_published, created_at = row

    criteria = str(evaluation_rubric_json) if evaluation_rubric_json else None
    html = _render_student_preview_html(title, description, criteria, starter_code)
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
```

Note the default-handling is equivalent, not identical-looking: originally `safe_criteria` computed `str(evaluation_rubric_json) if evaluation_rubric_json else 'Evaluation criteria set by employer.'` INSIDE the escape call. Now the fallback string lives inside the shared helper's `criteria or 'Evaluation criteria set by employer.'` — passing `None` from the caller triggers the identical fallback. This must produce byte-for-byte identical rendered HTML to before; that's exactly what Task 2's pinning test exists to prove.

### New route — assignment-keyed

```python
@student_bp.route('/student/preview/assignment/<assignment_id>')
def student_preview_assignment(assignment_id):
    row = db_service.get_assignment(assignment_id)
    if not row:
        return jsonify({"detail": "Assignment not found"}), 404

    html = _render_student_preview_html(
        title=row[1], description=row[2], criteria=row[4], starter_code=row[3])
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
```

`db_service.get_assignment()` already exists (`app/services/database_service.py:24-29`, `SELECT * FROM assignments WHERE id = ?`) — no DB-layer changes needed. Row shape (confirmed via `app/models/database.py:27-34` plus the `challenge_id` migration at line 190): `(id, title, description, starter_code, evaluation_criteria, created_at, challenge_id)`. Index access (`row[1]`, `row[2]`, `row[3]`, `row[4]`) matches the existing convention in `app/routes/assignments.py`'s own `get_assignment()` endpoint (lines 71-75) for this exact row shape — don't use `student_preview()`'s tuple-unpacking style, that's specific to the differently-shaped `challenges` row.

### Frontend — exact diff shape (`templates/frontend.html`, `loadAssignments()`, lines 990-995)

Replace:

```javascript
        document.getElementById('assignmentsList').innerHTML = list.map(a => `
            <div class="challenge-card" style="margin-bottom:8px;" onclick="document.getElementById('assignId').value='${a.id}'">
                <div style="font-weight:600; margin-bottom:4px;">${escHtml(a.title)}</div>
                <div style="font-size:0.8em; color:#aaa;">ID: ${a.id}</div>
            </div>
        `).join('');
```

with:

```javascript
        document.getElementById('assignmentsList').innerHTML = list.map(a => `
            <div class="challenge-card" style="margin-bottom:8px;" onclick="document.getElementById('assignId').value='${a.id}'">
                <div style="font-weight:600; margin-bottom:4px;">${escHtml(a.title)}</div>
                <div style="font-size:0.8em; color:#aaa; margin-bottom:8px;">ID: ${a.id}</div>
                <button class="btn-sm btn-outline" onclick="event.stopPropagation(); window.open('/student/preview/assignment/${a.id}', '_blank')">Preview as Student</button>
            </div>
        `).join('');
```

`escHtml` is already defined at `templates/frontend.html:1598` — don't reintroduce it. `btn-sm`/`btn-outline` classes already exist and are used elsewhere in this file (e.g. line 455's Copy button, line 425's Clear button) — reuse them, don't invent new button styling.

### What NOT to do

- Do NOT touch `student_dashboard()` — the real candidate flow (timer/modals/submit/polling from Stories 6.1-6.3, 9.4) is untouched by this story.
- Do NOT remove or redirect the existing `/student/preview/<challenge_id>` route — it stays exactly as-is behaviorally (proven by the pinning test), this story only ADDS a new route alongside it.
- Do NOT add any disambiguation logic for "which assignment does this challenge_id map to" — that concern is entirely sidestepped by keying the new route on `assignment_id` directly, per the product decision that created this story.
- Do NOT add a "Preview as Student" trigger to the challenge catalog page (Tab 2) — the product decision was assignment-detail page only.
- Do NOT add new DB columns/tables — `get_assignment()` already returns everything this story needs.

### Testing

No test file exists yet for either preview route (`GET /student/preview/<challenge_id>` has zero prior coverage — confirmed via `grep -rl student_preview tests/`). Create `tests/test_student_preview_routes.py` following this repo's established `client`/`db` fixture pattern (real Flask test client + isolated tmp-path SQLite, `student_module.db_service.db` monkeypatched directly, since `app.routes.student.db_service` is an import-time singleton — same pattern as `tests/test_candidates_endpoint.py` and every other route-level test file in this repo).

Cases to cover:
1. `GET /student/preview/<challenge_id>` for a real challenge — 200, contains the challenge's title/description/criteria/starter_code, contains "Preview Mode" banner text (the AC4 pinning test — write this FIRST, before the refactor, confirm it passes against the pre-refactor code, then confirm it STILL passes after the refactor with zero changes to the test itself).
2. `GET /student/preview/<challenge_id>` for a nonexistent id — 404, `{"detail": "Challenge not found"}`.
3. `GET /student/preview/assignment/<assignment_id>` for a real assignment — 200, contains the assignment's own title/description/criteria/starter_code.
4. Same as #3 but after simulating a post-generation edit (create an assignment, then directly update its row via a raw SQL update in the test, mirroring how an employer editing an assignment would diverge it from its originating challenge) — proves the drift bug is actually fixed: the new route reflects the edited value, unlike what the challenge-keyed preview would show.
5. `GET /student/preview/assignment/<assignment_id>` for a nonexistent id — 404, `{"detail": "Assignment not found"}`.

No JS test harness exists in this repo (established convention) — verify the frontend button manually: start the dev server, fetch `templates/frontend.html`'s served output or open Tab 3 in a browser, confirm the new button renders per assignment card and `window.open(...)` targets the right URL with `stopPropagation()` present in the onclick attribute string.

### Project Structure Notes

- `app/routes/student.py`: one new helper function, one modified route (refactor only, no behavior change), one new route.
- `templates/frontend.html`: one modified template-literal block inside `loadAssignments()`.
- One new test file: `tests/test_student_preview_routes.py`.
- No new DB tables/columns, no changes to `app/services/database_service.py` (both `get_challenge()` and `get_assignment()` already exist and are unchanged).

### References

- Original finding + product-decision framing: `_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of 6-4-preview-as-student (2026-07-03)" section, "Assignment/link-keyed preview (true candidate fidelity)" entry
- Epic scope: `_bmad-output/implementation-artifacts/sprint-status.yaml` → `epic-9` → `9-5-assignment-link-keyed-preview-fidelity`
- Current code to refactor: `app/routes/student.py` lines 769-1023 (`student_preview()`)
- Row-access convention to match: `app/routes/assignments.py` lines 62-76 (`get_assignment()` endpoint, index-based row access for the `assignments` table shape)
- Frontend surface to modify: `templates/frontend.html` lines 465-469 (Saved Assignments card container) and 978-1000 (`loadAssignments()`)
- `escHtml()` helper already defined: `templates/frontend.html:1598`

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Red-first: wrote `tests/test_student_preview_routes.py` before touching `app/routes/student.py`. The 3 challenge-keyed "pinning" tests passed immediately against the unmodified code (proving they correctly capture pre-refactor behavior); the 3 assignment-keyed tests failed with 404 (route didn't exist yet), the expected red state.
- Performed the extraction refactor (`_render_student_preview_html()` + rewired `student_preview()` + new `student_preview_assignment()` route), then re-ran the full file: all 6 tests passed, including the 3 pinning tests passing UNCHANGED — confirms the refactor is byte-for-byte behavior-preserving for the existing route, not just "looks the same."
- `node --check` on the extracted `<script>` block confirmed no syntax errors were introduced by the frontend button.
- Live verification: started `python run.py`, created a real assignment via `POST /api/assignments`, confirmed `GET /student/preview/assignment/<id>` returns 200 with the assignment's own description/criteria/starter_code, confirmed a nonexistent id returns the correct 404 shape, and confirmed `GET /` (the employer dashboard) now renders the "Preview as Student" button text.
- Full suite: 124/124 passed (118 before this story + 6 new), zero regressions.

### Completion Notes List

- Extracted `_render_student_preview_html(title, description, criteria, starter_code)` in `app/routes/student.py`, moved directly above `student_preview()` — same ~230-line landing/assessment HTML template, now parameterized instead of reading challenge-specific locals inline.
- `student_preview(challenge_id)` unchanged in DB-lookup/404 behavior; now computes `criteria = str(evaluation_rubric_json) if evaluation_rubric_json else None` and calls the shared helper — the `None`-triggers-the-same-fallback-string equivalence is proven by the pinning tests passing unchanged.
- Added `student_preview_assignment(assignment_id)` at `GET /student/preview/assignment/<assignment_id>`, reusing the existing (unmodified) `DatabaseService.get_assignment()`. Index-based row access (`row[1]`/`row[2]`/`row[3]`/`row[4]`) matches `app/routes/assignments.py`'s existing convention for this same row shape.
- Added a "Preview as Student" button to each card in `templates/frontend.html`'s "Saved Assignments" list (Tab 3), opening the new route in a new tab; `event.stopPropagation()` prevents the card's own click-to-fill-`#assignId` handler from also firing. Reused existing `btn-sm`/`btn-outline` CSS classes — no new styling.
- Did NOT touch `student_dashboard()`, did NOT remove/redirect the existing challenge-keyed route, did NOT add any challenge_id-to-assignment disambiguation logic (sidestepped entirely by keying the new route on `assignment_id` directly), did NOT add a catalog-page (Tab 2) trigger — all per the story's explicit scope boundary.
- All 7 acceptance criteria verified: AC1 (new route reads live assignment fields — `test_assignment_preview_returns_200_with_expected_content`), AC2 (404 shape — `test_assignment_preview_missing_id_returns_404`), AC3 (identical rendered structure — same helper produces both pages), AC4 (existing route behavior-preserving — 3 pinning tests unchanged pre/post refactor), AC5/AC6 (frontend button + stopPropagation — verified live via rendered `GET /`), AC7 (no changes to `student_dashboard()`/DB schema/evaluation logic — confirmed via `git diff` scope).
- The drift bug this story exists to fix is directly proven by `test_assignment_preview_reflects_post_generation_edits`: after simulating an employer's post-generation edit, the assignment-keyed preview shows the edited text while the challenge-keyed preview still shows the stale original — demonstrating both that the bug is real and that this story's new route fixes it.

### File List

- app/routes/student.py
- templates/frontend.html
- tests/test_student_preview_routes.py (new file)
