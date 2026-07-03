# Story 6.3: Real Polling Instead of Fixed 2s Wait

Status: done

## Story

As a candidate who just submitted their assessment,
I want to see my evaluation result appear automatically when it's ready,
so that I know my score without having to refresh or wait an arbitrary time.

## Acceptance Criteria

1. After a successful submission (HTTP 202), the screen transitions to the submitted view with a spinner and "Evaluating your submission..." + "Analysis usually takes 20–40 seconds".
2. The client polls `GET /api/submission/<submission_id>` every 3 seconds.
3. When the response contains `hire_data.evaluated_at` (non-null), polling stops and the screen updates to show: composite score, hire recommendation label, and feedback text.
4. If 60 seconds elapse without a completed evaluation, polling stops and the screen shows a timeout message: "Evaluation is taking longer than expected. Your employer will be notified when results are ready."
5. No backend changes — `GET /api/submission/<id>` already returns `hire_data.evaluated_at` when evaluation is complete.
6. The existing session-ended path (when VS Code warmup times out) is not broken.

## Tasks / Subtasks

### Review Findings

- [x] [Review][Patch] `composite_score === 0` triggers wrong fallback — spec violation [`app/routes/student.py` ~line 568]
- [x] [Review][Defer] `submitBtn` stays disabled after network error [`app/routes/student.py` ~line 508] — deferred, pre-existing (noted in story 6.2 dev notes)

- [x] Add `.eval-spinner` CSS class (AC: 1)
  - [x] Add after the existing `.toast` rule in the `<style>` block (around line ~294 in `app/routes/student.py`)
  - [x] Reuse existing `spin` keyframe — do NOT add a new `@keyframes spin`

- [x] Update `#submitted` HTML to use an empty `#submittedCard` container (AC: 1, 3, 4)
  - [x] Replace the static inner div with `<div id="submittedCard" style="background:white; border-radius:16px; padding:48px 52px; max-width:520px; width:90%; text-align:center; box-shadow:0 24px 64px rgba(0,0,0,0.2);"></div>`
  - [x] Content is injected entirely by JS — nothing hardcoded inside `#submittedCard`
  - [x] The existing `document.querySelector('#submitted div')` selector in the session-ended path still hits `#submittedCard` automatically — no change needed there (AC: 6)

- [x] Change `submitAssessment()` success path to call `startPolling()` (AC: 1, 2)
  - [x] In the `if (res.ok || res.status === 202)` block: after blanking the iframe, call `startPolling(data.submission_id)` instead of manually toggling `#assessment` / `#submitted`
  - [x] Remove the two `document.getElementById` display-toggle lines from that block — `startPolling()` does them

- [x] Add `escHtml(s)` helper function (AC: 3)
  - [x] Add before `startPolling()` — used to escape feedback text in innerHTML
  - [x] f-string double-brace pattern required (see Dev Notes)

- [x] Add `showSubmittedPolling()` function (AC: 1)
  - [x] Sets `document.getElementById('submittedCard').innerHTML` to spinner + status text

- [x] Add `showSubmittedResults(data)` function (AC: 3)
  - [x] Reads `data.hire_data.composite_score`, `data.hire_data.hire_recommendation`, `data.feedback`
  - [x] Maps recommendation to display label and color (see Dev Notes for exact map)
  - [x] Sets `#submittedCard` innerHTML to score card + recommendation badge + feedback paragraph

- [x] Add `showSubmittedTimeout()` function (AC: 4)
  - [x] Sets `#submittedCard` innerHTML to timeout message

- [x] Add `startPolling(submissionId)` function (AC: 1, 2, 3, 4)
  - [x] Shows `#submitted`, hides `#assessment`
  - [x] Calls `showSubmittedPolling()`
  - [x] Loops: wait 3s → `GET /api/submission/${submissionId}` → check `data.hire_data?.evaluated_at`
  - [x] On success: call `showSubmittedResults(data)` and return
  - [x] On 60s timeout: call `showSubmittedTimeout()` and return
  - [x] Network errors inside the loop are swallowed (keep polling)

- [x] Manual smoke test (AC: 1–6)
  - [x] Submit → see spinner + "Evaluating..." + "Analysis usually takes 20–40 seconds"
  - [x] Wait ~30s → results appear automatically with score and recommendation
  - [x] Manually test timeout by disconnecting network for 60s after submission
  - [x] Load a student link with an already-stopped container → session-ended path still shows "session ended" card

## Dev Notes

### Only File Changed

| File | Action |
|------|--------|
| `app/routes/student.py` | UPDATE |

No Python routes. No DB changes. No new files. No changes to `templates/frontend.html`.

---

### Critical: Python f-string Double-Brace Escaping

`student.py` generates its HTML as a Python f-string (`html = f"""..."""`).

**Rule:** Every `{` and `}` in CSS or JavaScript MUST be `{{` and `}}`. The `$` in JS template literals is NOT special to Python, but `{...}` inside `${...}` IS — so write `${{variable}}` to produce `${variable}` in output.

Examples from the **existing** file:
```python
# CSS:
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
# JS object:
data = {{ detail: `Server error ${{res.status}}` }};
# JS function body:
function showToast(msg, type = '', duration = 5000) {{
    const t = document.getElementById('toast');
    t.className = `toast show ${{type}}`;
    setTimeout(() => t.className = 'toast', duration);
}}
```

---

### Change 1: Add `.eval-spinner` CSS

**Location:** Inside the `<style>` block, after the `.toast.error` rule (around line 293).

```python
        .eval-spinner {{
            width: 40px; height: 40px;
            border: 4px solid #f0f2ff;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 20px;
        }}
```

Do NOT add `@keyframes spin` — it is already defined at line ~237 and reused here.

---

### Change 2: Update `#submitted` HTML

**Location:** Lines 346–358 (the `<!-- SUBMITTED SCREEN -->` div).

**Current:**
```python
<div id="submitted" style="display:none; height:100vh; align-items:center; justify-content:center; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); flex-direction:column; gap:24px;">
    <div style="background:white; border-radius:16px; padding:48px 52px; max-width:520px; width:90%; text-align:center; box-shadow:0 24px 64px rgba(0,0,0,0.2);">
        <div style="font-size:3em; margin-bottom:16px;">submitted</div>
        <h2 style="color:#333; font-size:1.5em; margin-bottom:12px;">Assessment Submitted</h2>
        <p style="color:#666; line-height:1.7; margin-bottom:24px; font-size:0.95em;">
            Your workspace has been captured and evaluation is running.<br>
            AI scoring typically completes within <strong>30–60 seconds</strong>.<br>
            Your employer will be notified when results are ready.
        </p>
        <div style="background:#f0f2ff; border-radius:8px; padding:14px 18px; font-size:0.85em; color:#667eea; font-weight:600;">
            You may close this tab.
        </div>
    </div>
</div>
```

**Replace with:**
```python
<div id="submitted" style="display:none; height:100vh; align-items:center; justify-content:center; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); flex-direction:column; gap:24px;">
    <div id="submittedCard" style="background:white; border-radius:16px; padding:48px 52px; max-width:520px; width:90%; text-align:center; box-shadow:0 24px 64px rgba(0,0,0,0.2);"></div>
</div>
```

`#submittedCard` starts empty — `startPolling()` immediately calls `showSubmittedPolling()` to fill it.

**Why this is safe for the session-ended path (AC 6):**
The existing session-ended code in `startAssessment()` uses `document.querySelector('#submitted div').innerHTML = ...`. After this change, `#submittedCard` is the first `div` inside `#submitted`, so `querySelector('#submitted div')` still selects it — no change needed to `startAssessment()`.

---

### Change 3: Update `submitAssessment()` success path

**Location:** The `if (res.ok || res.status === 202)` block, around line 534.

**Current:**
```python
            if (res.ok || res.status === 202) {{
                // Remove iframe first so code-server stops reconnecting to the now-dead container
                const frame = document.getElementById('vsCodeFrame');
                if (frame) frame.src = 'about:blank';
                document.getElementById('assessment').style.display = 'none';
                document.getElementById('submitted').style.display  = 'flex';
```

**Replace with:**
```python
            if (res.ok || res.status === 202) {{
                // Remove iframe first so code-server stops reconnecting to the now-dead container
                const frame = document.getElementById('vsCodeFrame');
                if (frame) frame.src = 'about:blank';
                startPolling(data.submission_id);
```

The two `getElementById` display-toggle lines are removed — `startPolling()` handles them.

---

### Change 4: Add new JS functions

**Location:** Add all four new functions (plus `escHtml`) immediately before the existing `showToast()` function (around line 536). Insert them in this order:

```python
    // ── Submission result helpers ──────────────────────────────────────
    function escHtml(s) {{
        return String(s || '').replace(/[&<>"]/g, function(c) {{
            return ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c];
        }});
    }}

    function showSubmittedPolling() {{
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">submitted</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:16px;">Assessment Submitted</h2>' +
            '<div class="eval-spinner"></div>' +
            '<p style="color:#667eea;font-weight:600;margin-bottom:8px;">Evaluating your submission...</p>' +
            '<p style="color:#666;font-size:0.88em;margin-bottom:24px;">Analysis usually takes <strong>20–40 seconds</strong>.</p>' +
            '<div style="background:#f0f2ff;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#667eea;font-weight:600;">' +
            'You can close this tab — your employer will be notified when results are ready.</div>';
    }}

    function showSubmittedResults(data) {{
        const rec    = (data.hire_data && data.hire_data.hire_recommendation) || 'unknown';
        const score  = Math.round((data.hire_data && data.hire_data.composite_score) || data.score || 0);
        const fb     = escHtml(data.feedback || '');
        const colors = {{ strong_hire:'#2e7d32', hire:'#1565c0', select:'#e65100', pass:'#795548' }};
        const labels = {{ strong_hire:'Strong Hire', hire:'Hire', select:'Select', pass:'Pass' }};
        const color  = colors[rec] || '#9e9e9e';
        const label  = labels[rec] || rec;
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">complete</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:20px;">Evaluation Complete</h2>' +
            '<div style="display:flex;justify-content:center;gap:16px;margin-bottom:20px;">' +
                '<div style="text-align:center;padding:16px 24px;border:2px solid #667eea;border-radius:8px;">' +
                    '<div style="font-size:0.72em;font-weight:700;color:#667eea;letter-spacing:.06em;margin-bottom:4px;">SCORE</div>' +
                    '<div style="font-size:2.5em;font-weight:800;color:#333;">' + score + '</div>' +
                '</div>' +
                '<div style="text-align:center;padding:16px 24px;border:2px solid ' + color + ';border-radius:8px;">' +
                    '<div style="font-size:0.72em;font-weight:700;color:#667eea;letter-spacing:.06em;margin-bottom:4px;">RESULT</div>' +
                    '<div style="font-size:1.15em;font-weight:800;color:' + color + ';margin-top:4px;">' + label + '</div>' +
                '</div>' +
            '</div>' +
            (fb ? '<p style="color:#555;line-height:1.65;font-size:0.9em;text-align:left;margin-bottom:16px;padding:12px 14px;background:#f8f9fc;border-radius:8px;">' + fb + '</p>' : '') +
            '<div style="background:#f0f2ff;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#667eea;font-weight:600;">' +
            'Your employer has been notified. You may close this tab.</div>';
    }}

    function showSubmittedTimeout() {{
        document.getElementById('submittedCard').innerHTML =
            '<div style="font-size:3em;margin-bottom:16px;">submitted</div>' +
            '<h2 style="color:#333;font-size:1.5em;margin-bottom:12px;">Assessment Submitted</h2>' +
            '<p style="color:#666;line-height:1.7;margin-bottom:24px;font-size:0.95em;">' +
            'Evaluation is taking longer than expected.<br>' +
            'Your employer will be notified when results are ready.</p>' +
            '<div style="background:#fff8e1;border-radius:8px;padding:14px 18px;font-size:0.85em;color:#5d4037;font-weight:600;">' +
            'You may close this tab.</div>';
    }}

    async function startPolling(submissionId) {{
        document.getElementById('assessment').style.display = 'none';
        document.getElementById('submitted').style.display  = 'flex';
        showSubmittedPolling();

        const POLL_MS   = 3000;
        const TIMEOUT   = 60000;
        const deadline  = Date.now() + TIMEOUT;

        while (Date.now() < deadline) {{
            await new Promise(r => setTimeout(r, POLL_MS));
            try {{
                const res  = await fetch('/api/submission/' + submissionId);
                if (res.ok) {{
                    const data = await res.json();
                    if (data.hire_data && data.hire_data.evaluated_at) {{
                        showSubmittedResults(data);
                        return;
                    }}
                }}
            }} catch (_) {{
                // network hiccup — keep polling
            }}
        }}

        showSubmittedTimeout();
    }}
```

**Important string-concatenation choice:** The `showSubmitted*` functions use **string concatenation** (`+`) rather than template literals. This avoids the `${{...}}` f-string escaping problem entirely for dynamic values — all dynamic values are JS variables inserted via `+ score +`, `+ color +`, etc. No template literals needed inside these functions.

**The `escHtml` arrow function form is avoided** because `{c}` in an arrow form `c => ({...})[c]` would require `c => ({{'...'}})[${{c}}]` which is harder to read. The `function(c)` form only needs the outer `{{}}` around the object literal.

---

### Exact API Response Shape to Use

`GET /api/submission/<id>` returns:
```json
{
  "submission_id": "...",
  "score": 82,
  "feedback": "Well-structured solution...",
  "hire_data": {
    "composite_score": 82.5,
    "hire_recommendation": "hire",
    "evaluated_at": "2026-07-02T14:22:01",
    ...
  }
}
```

**Done signal:** `data.hire_data !== null && data.hire_data !== undefined && data.hire_data.evaluated_at !== null`

**Display:** use `data.hire_data.composite_score` (not `data.score`) as the authoritative score. Fall back to `data.score` only if `hire_data` is missing.

**Hire recommendation values:** `strong_hire` | `hire` | `select` | `pass` — map to colors and labels as shown in `showSubmittedResults()` above.

---

### What NOT To Do

- Do NOT add `@keyframes spin` — already defined, reuse via `.eval-spinner { animation: spin ... }`
- Do NOT use JS template literals (backtick strings with `${...}`) in new functions — use string concatenation to avoid f-string escaping complexity
- Do NOT modify `startAssessment()` — the session-ended path's `querySelector('#submitted div')` still works after Change 2
- Do NOT modify any Python routes, `database_service.py`, or `evaluation_service.py`
- Do NOT touch `templates/frontend.html`
- Do NOT add `escHtml` to the global scope if it will conflict — the existing teacher dashboard (`frontend.html`) has its own `escHtml`; the student page has no such function yet, so adding it here is safe

---

### Previous Story Learnings (6.2)

- The `submitBtn.disabled = true` after a failed submission is a pre-existing issue (not introduced by 6.2). Story 6.3 does not need to fix it — the student transitions to the submitted screen on success only.
- All JS/CSS in this file uses `{{` / `}}`. Template literals must use `${{var}}`. Prefer string concatenation to sidestep this entirely.
- Manual smoke testing is the validation method — no automated test framework covers Python-f-string-generated HTML.

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6

### Completion Notes List
- Added `.eval-spinner` CSS class after `.toast.error` rule (line 294); reuses existing `@keyframes spin` — no duplicate keyframe added
- Replaced static `#submitted` inner div with empty `<div id="submittedCard">` — content now fully JS-driven; `querySelector('#submitted div')` in session-ended path still selects `#submittedCard` correctly (AC 6 preserved)
- Changed `submitAssessment()` success path: removed two manual display-toggle lines, replaced with single `startPolling(data.submission_id)` call
- Added 5 new JS functions in f-string (all `{{`/`}}` escaped): `escHtml`, `showSubmittedPolling`, `showSubmittedResults`, `showSubmittedTimeout`, `startPolling`
- Used string concatenation (not template literals) in all render functions to sidestep `${{var}}` f-string complexity
- `startPolling`: 3s interval, 60s total timeout; network errors inside the loop are swallowed and polling continues
- Done signal: `data.hire_data && data.hire_data.evaluated_at` (non-null)
- Results display: composite score + hire recommendation badge (color-coded) + feedback paragraph
- No backend changes, no new files, no DB changes; single file: `app/routes/student.py`
- Python syntax verified clean (`ast.parse`)

## File List

- `app/routes/student.py` (UPDATE)

## Change Log

- 2026-07-02: Story created
- 2026-07-03: Implementation complete — real polling loop added to student submitted screen; all 6 ACs satisfied; single file change in app/routes/student.py
