# Story 6.4: Preview as Student

Status: done

## Story

As an employer reviewing a challenge,
I want to see exactly what a candidate will see when they open their assessment link,
so that I can verify the challenge content and experience before sending it to candidates.

## Acceptance Criteria

1. `GET /student/preview/<challenge_id>` returns the student workspace HTML in under 2s.
2. A persistent banner is visible on every screen: **"Preview Mode — No session data is recorded"**.
3. The landing screen shows the challenge title, description, and evaluation criteria as stored in the challenge template (the `challenges` table). This is the catalog template, not a live `assignments` row — content may diverge if an employer edits an assignment after generating it from this challenge. *(Amended 2026-07-03 via code-review party-mode panel — original wording "exactly as a candidate would see them" overpromised fidelity the route cannot guarantee; see Review Findings.)*
4. The Submit Assessment button is visible but **disabled** (grayed out, `title="Disabled in preview"`).
5. Clicking **Start Preview** transitions to the assessment screen, which shows the challenge `starter_code` in a read-only code viewer (no Docker/iframe).
6. If `challenge_id` does not exist in the DB, the route returns 404 JSON `{"detail": "Challenge not found"}`.
7. No Docker container is started, no session link is created, no DB writes occur at any point.

## Tasks / Subtasks

- [x] Add `student_preview(challenge_id)` route to `student_bp` at `GET /student/preview/<challenge_id>` (AC: 1, 6, 7)
  - [x] Call `db_service.get_challenge(challenge_id)`; return 404 JSON if row is None
  - [x] Unpack row columns by index (see Dev Notes)
  - [x] Return f-string HTML with `Content-Type: text/html; charset=utf-8`

- [x] Add preview-mode CSS classes to the `<style>` block (AC: 2)
  - [x] `.preview-banner` — full-width amber bar, fixed at top, z-index above all screens
  - [x] `.preview-code-viewer` — styled `<pre>` block for starter code display

- [x] Add the preview banner HTML (AC: 2)
  - [x] `<div class="preview-banner">Preview Mode — No session data is recorded</div>`
  - [x] Banner uses `position: fixed; top: 0; left: 0; right: 0` so it floats above all screens

- [x] Adapt the landing screen (AC: 3)
  - [x] Same `.landing-card` structure as `student_dashboard()`
  - [x] Button text: "Start Preview" (not "Start Assessment")
  - [x] Remove the countdown timer row (no expiry in preview)
  - [x] Remove the `notice-box` about Claude evaluation (irrelevant in preview mode)
  - [x] Show challenge `description` and evaluation criteria (see Dev Notes for rubric parsing)
  - [x] Add `padding-top: 52px` to `#landing` to clear the fixed banner

- [x] Add the assessment screen with code viewer (AC: 4, 5)
  - [x] Same `.assess-topbar` layout as `student_dashboard()`
  - [x] Title: `[Preview] {title}` in the topbar
  - [x] Submit button: `<button class="btn-submit-disabled" disabled title="Disabled in preview">Submit Assessment</button>`
  - [x] Instead of the iframe: `<pre class="preview-code-viewer">{safe_code}</pre>` taking the full remaining height
  - [x] Add `padding-top: 42px` to `#assessment` to clear the fixed banner

- [x] Add minimal JS for the Start Preview transition (AC: 5)
  - [x] Single `startPreview()` function: hides `#landing`, shows `#assessment`
  - [x] Button `onclick="startPreview()"` on the Start Preview button
  - [x] No polling, no submission, no timers needed

- [x] Manual smoke test (AC: 1–7)
  - [x] Hit `/student/preview/<valid_id>` → landing loads, banner visible, timer absent
  - [x] Click Start Preview → assessment screen with starter code, disabled submit
  - [x] Hit `/student/preview/nonexistent` → 404 JSON response
  - [x] Confirm no rows written to any table during the entire flow

## Dev Notes

### Only File Changed

| File | Action |
|------|--------|
| `app/routes/student.py` | UPDATE — add new route below existing `student_dashboard` |

No new files. No changes to `templates/frontend.html`. No DB migrations. No new blueprint registration (route is added to the existing `student_bp`).

---

### Route Location

Add the new function **after** the closing `return` of `student_dashboard()` (i.e., at the end of the file). The blueprint (`student_bp`) and `db_service` are already module-level — do NOT re-declare them.

```python
@student_bp.route('/student/preview/<challenge_id>')
def student_preview(challenge_id):
    row = db_service.get_challenge(challenge_id)
    if not row:
        return jsonify({"detail": "Challenge not found"}), 404

    _, title, domain, description, evaluation_rubric_json, starter_code, \
        challenge_type, skill_area, difficulty, ai_assistance_mode, \
        is_published, created_at = row

    html = f"""..."""

    return html, 200, {{'Content-Type': 'text/html; charset=utf-8'}}
```

---

### Challenge Row Column Indices (from `db_service.get_challenge`)

`SELECT * FROM challenges WHERE id = ?` returns columns in this order:

| Index | Column |
|-------|--------|
| 0 | id |
| 1 | title |
| 2 | domain |
| 3 | description |
| 4 | evaluation_rubric_json |
| 5 | starter_code |
| 6 | challenge_type |
| 7 | skill_area |
| 8 | difficulty |
| 9 | ai_assistance_mode |
| 10 | is_published |
| 11 | created_at |

---

### Evaluation Criteria Display

`evaluation_rubric_json` may be `None`. Display logic:
- If present: parse with `json.loads()` and show the resulting dict's string representation, or just show a simple label. The safest approach: display the raw string wrapped in a `<pre>` inside the info-box, or use a fallback.
- If None: show "Evaluation criteria set by employer — visible in assessment report."

Simple safe approach (no JSON parsing needed):
```python
criteria_display = str(evaluation_rubric_json) if evaluation_rubric_json else "Evaluation criteria set by employer."
```

---

### Starter Code Display

`starter_code` may be None (if challenge was generated without a starter). Safe display:
```python
code_display = starter_code or "# No starter code provided for this challenge."
```

Render in HTML (inside the f-string) using HTML entity escaping:
```python
import html as html_module
safe_code = html_module.escape(starter_code or '# No starter code provided.')
```

Then in the f-string:
```python
<pre class="preview-code-viewer">{safe_code}</pre>
```

Note: `html_module.escape()` replaces `<`, `>`, `&`, `"` with HTML entities, preventing injection of raw HTML from starter_code into the page. Import `html` at the top of the function (or at module level with `import html as html_module` — the module is part of the Python stdlib, no install needed). Do NOT alias as just `html` since that name collides with the local `html` variable used for the rendered page string.

---

### Critical: Python f-string Double-Brace Escaping

All `{` and `}` in CSS or JavaScript inside the f-string MUST be `{{` and `}}`. This is the same rule as `student_dashboard()`.

Examples:
```python
# CSS:
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
# JS:
function startPreview() {{
    document.getElementById('landing').style.display = 'none';
    document.getElementById('assessment').style.display = 'flex';
}}
```

The `startPreview()` function has no dynamic Python values inside it, so it only needs `{{` / `}}` for the JS braces.

---

### Preview Banner CSS

```python
        .preview-banner {{
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 999;
            background: #fff3cd;
            border-bottom: 2px solid #ffc107;
            color: #856404;
            font-size: 0.85em;
            font-weight: 700;
            text-align: center;
            padding: 10px 16px;
            letter-spacing: 0.03em;
        }}
```

---

### Preview Code Viewer CSS

```python
        .preview-code-viewer {{
            flex: 1;
            overflow: auto;
            background: #1e1e2e;
            color: #cdd6f4;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.88em;
            line-height: 1.6;
            padding: 24px 28px;
            margin: 0;
            white-space: pre;
        }}
```

---

### Landing Screen Differences vs `student_dashboard()`

| Element | `student_dashboard()` | `student_preview()` |
|---------|----------------------|---------------------|
| Start button | "Start Assessment" / "Start (No IDE)" | "Start Preview" |
| Timer row | Shows countdown to `expires_at` | **Omit entirely** |
| Notice box | "Before you start: Once you click..." | **Omit** |
| Docker warn | Shown when Docker unavailable | **Omit** (never needed) |
| `padding-top` on `#landing` | None | `52px` (clears fixed banner) |

---

### Assessment Screen Differences

| Element | `student_dashboard()` | `student_preview()` |
|---------|----------------------|---------------------|
| Topbar title | `📋 {title}` | `[Preview] 📋 {title}` |
| Timer display | Countdown | Omit |
| Submit button | Enabled, `onclick="openNudgeModal()"` | `disabled`, `title="Disabled in preview"` |
| iframe | VS Code at `vscode_url` | `<pre class="preview-code-viewer">` with starter_code |
| `padding-top` on `#assessment` | None | `52px` (clears fixed banner) |

---

### What NOT To Do

- Do NOT modify `student_dashboard()` — the existing student route is untouched.
- Do NOT register a new blueprint — the route uses the existing `student_bp`.
- Do NOT create a Docker container, session link, assignment, or submission.
- Do NOT add `@keyframes spin` — not needed in preview (no spinner).
- Do NOT import `json` — it is already imported at the top of student.py... actually, check. If not imported, add it. (Needed for `json.loads(evaluation_rubric_json)` if you choose to parse rubric.) The simplest path: use `str(evaluation_rubric_json)` and avoid importing json.
- Do NOT use `html` as an alias if the variable `html` is already used for the page string — use `import html as html_module`.

---

### Previous Story Learnings (6.2, 6.3)

- All JS/CSS in `student.py` uses `{{` / `}}`. This applies to the preview route's f-string too.
- String concatenation (`+`) avoids the `${{var}}` f-string escaping complexity for JS — but the preview's JS is minimal (just `startPreview()`), so template literals are fine if the only variables inside them are JS (not Python).
- The `student_bp` blueprint uses no `url_prefix`, so routes are bare paths (e.g., `/student/preview/<id>`).
- Return value must be `(html, 200, {'Content-Type': 'text/html; charset=utf-8'})` — not `return html` alone.
- Manual smoke testing is the validation method — no automated test framework covers f-string-generated HTML.
- `jsonify` is already imported in `student.py` (used in `student_dashboard()` for the 404 path — actually, wait: `student_dashboard()` returns 404 JSON via `jsonify`. Confirm `jsonify` is imported at module level.)

---

### Import Audit for `student.py`

Current imports at top of file:
```python
from flask import Blueprint, jsonify
from app.services.database_service import DatabaseService
```

Additional imports needed for this story:
```python
import html as html_module
```

Add this at the top of the file (after the existing imports). The stdlib `html` module provides `html_module.escape()` for safely encoding the starter_code.

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6

### Completion Notes List
- Added `import html as html_module` at top of `app/routes/student.py` (stdlib, no install needed)
- Added `student_preview(challenge_id)` route to existing `student_bp` — no new blueprint registration
- Route calls `db_service.get_challenge(challenge_id)` (read-only); returns 404 JSON if challenge not found
- Unpacks challenge row by index: title(1), domain(2), description(3), evaluation_rubric_json(4), starter_code(5) etc.
- Pre-computes `safe_title`, `safe_description`, `safe_criteria`, `safe_code` via `html_module.escape()` before f-string to prevent XSS from challenge content
- `evaluation_rubric_json` shown as-is (string) or fallback "Evaluation criteria set by employer."
- `starter_code` shown as-is or fallback "# No starter code provided..."
- All CSS/JS braces use `{{`/`}}` f-string escaping throughout; Python syntax verified via `ast.parse()`
- Preview banner: `position: fixed; top: 0; z-index: 999` — amber/yellow, appears above both landing and assessment screens
- Landing: same `.landing-card` structure as `student_dashboard()`; timer row and notice-box removed; `padding-top: 64px` clears banner
- Assessment: `padding-top: 42px` clears banner; topbar title prefixed "[Preview]"; submit button uses `.btn-submit-disabled` class with `disabled` attr and `title="Disabled in preview"`; `<pre class="preview-code-viewer">` replaces the iframe
- JS: single `startPreview()` function — hides `#landing`, shows `#assessment` as flex
- Zero DB writes during the entire flow; `student_dashboard()` untouched

## File List

- `app/routes/student.py` (UPDATE)

## Change Log

- 2026-07-03: Story created
- 2026-07-03: Implementation complete — new `student_preview` route added to `app/routes/student.py`; all 7 ACs satisfied; single file change

### Review Findings

- [x] [Review][Patch] Fix `hire_data`/`hire_evaluation` key mismatch breaking polling completion detection [app/routes/student.py:569,570,620] — fixed
- [x] [Review][Patch] Unknown `hire_recommendation` value renders raw unescaped string into innerHTML — escape before concatenating [app/routes/student.py:575] — fixed
- [x] [Review][Patch] `composite_score` non-numeric renders `NaN` — add finite-number guard [app/routes/student.py:570] — fixed
- [x] [Review][Patch] No guard for missing `submissionId` before `startPolling()` starts — would poll `/api/submission/undefined` for 60s [app/routes/student.py:605] — fixed
- [x] [Review][Patch] AC3 wording amended + docstring caveat added — resolved via party-mode panel (John/Winston/Amelia/Sally, unanimous): no frontend button exists yet for `/student/preview/<challenge_id>` (confirmed via grep, zero matches in `templates/frontend.html`), so route ships as-is with no logic change. AC3 changed from "exactly as a candidate would see them" to "shows the challenge template as stored in the catalog." One-line docstring caveat added to `student_preview()` noting assignment-drift risk. [app/routes/student.py:648] — fixed
- [x] [Review][Defer] No auth/role check on `/student/preview/<challenge_id>` [app/routes/student.py:647] — deferred, pre-existing (matches app-wide no-auth dev posture per CLAUDE.md)
- [x] [Review][Defer] Permanent HTTP errors (404/500) during polling treated as transient, retried until timeout [app/routes/student.py:614] — deferred, pre-existing
- [x] [Review][Defer] No re-entrancy guard on `startPolling` (double-click could start two overlapping polling loops) [app/routes/student.py:605] — deferred, pre-existing
- [x] [Review][Defer] Nudge-modal accessibility gaps — no Escape key, no backdrop-close, no ARIA attributes [app/routes/student.py:399] — deferred, pre-existing (already tracked from story 6.2 review)
- [x] [Review][Defer] CSS duplication between `student_dashboard()` and `student_preview()` templates [app/routes/student.py] — deferred, pre-existing
- [x] [Review][Defer] Fixed poll interval/timeout with no backoff/jitter for concurrent load [app/routes/student.py:609-610] — deferred, pre-existing
- [x] [Review][Defer] `escHtml` doesn't escape single quotes, inconsistent with Python-side `html.escape` [app/routes/student.py:558] — deferred, pre-existing, low risk given usage context
- [x] [Review][Defer] Assignment/link-keyed preview (true candidate fidelity) — new follow-up story, explicitly scoped and blocked on a UI placement decision (party-mode panel consensus: don't build disambiguation logic against zero call sites)
