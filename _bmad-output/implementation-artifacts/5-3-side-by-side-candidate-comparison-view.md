# Story 5.3: Side-by-Side Candidate Comparison View

Status: done

## Story

As an employer evaluating candidates,
I want to select two candidates from the comparison tab and view their dimension scores side-by-side with an overlaid radar and butterfly chart,
so that I can make a precise, evidence-based decision between two finalists.

## Acceptance Criteria

1. In Tab 5 (Compare Candidates), each ranked table row has a checkbox in the leftmost column. Selecting exactly 2 checkboxes enables the "Compare Selected (2/2)" button; any other count keeps it disabled.
2. Clicking "Compare Selected" reveals a comparison panel below the ranked table containing:
   - (a) A 300×300 overlaid radar SVG: Candidate A in solid purple (`#667eea`), Candidate B as a dashed ghost polygon in pink (`#f06292`), on the same 8-spoke axes.
   - (b) A butterfly chart: 8 dimension rows, Candidate A's bar grows LEFT from center, Candidate B's bar grows RIGHT from center. Each bar is color-coded by quartile relative to `dimension_averages` from the cohort.
   - (c) A rationale section: each of the 8 dimensions is a `<details>` element showing Candidate A's rationale and Candidate B's rationale side-by-side when expanded.
3. Selecting a 3rd checkbox automatically unchecks the oldest selection so that exactly 2 are always selected.
4. If the user loads a new assignment ID while a comparison is showing or candidates are selected, a warning modal ("Loading a new assignment will clear your current comparison. Continue?") must be confirmed before the load proceeds.
5. A "✕ Close" button in the comparison panel header hides it and returns focus to the ranked table.
6. No backend changes required — all needed data (`dimensions`, `dimension_averages`, per-dimension `rationale`) is already returned by `GET /api/assignments/<id>/candidates`.

## Tasks / Subtasks

- [x] Add CSS for new UI components inside `<style>` (AC: 1, 2, 4)
  - [x] `.selected-row` — `background: #f0f0ff` on checked table rows
  - [x] `.compare-checkbox` — 16×16, `accent-color: #667eea`, cursor pointer
  - [x] `#cmpCompareBtn:disabled` — `opacity: 0.4; cursor: not-allowed`
  - [x] `.butterfly-chart` — `width: 100%`
  - [x] `.butterfly-row` — flex row, `gap:8px; padding:7px 0; border-bottom:1px solid #f4f4fb`
  - [x] `.butterfly-half` — `flex:1; display:flex`; `.butterfly-half-a { justify-content:flex-end; }` `.butterfly-half-b { justify-content:flex-start; }`
  - [x] `.butterfly-bar` — `height:18px; border-radius:3px; min-width:2px`
  - [x] `.center-divider` — `width:2px; background:#ddd; flex-shrink:0; height:22px; align-self:center`
  - [x] `#cmpWarningOverlay` — `position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:1000; display:none; align-items:center; justify-content:center`

- [x] Add Tab 5 state variables near the existing Tab 5 JS state section (after line ~983)  (AC: 1, 3)
  - [x] `let _cmpSelected = [];` — array of up to 2 submission_ids currently checked
  - [x] `let _cmpCandidatesMap = {};` — map submission_id → full candidate object from last load
  - [x] `let _cmpDimAverages = {};` — `dimension_averages` from last `loadCandidates()` call
  - [x] `let _cmpAssignId = null;` — assignment ID currently loaded in Tab 5

- [x] Update Tab 5 HTML — warning modal + compare button + comparison panel (AC: 1, 2, 4, 5)
  - [x] Add `<button id="cmpCompareBtn" disabled …>Compare Selected (0/2)</button>` next to "Load Candidates" button in the Tab 5 card
  - [x] Add checkbox `<th style="width:36px;"></th>` as the FIRST column in compare table `<thead>`
  - [x] Update empty-state colspan from 14 to 15
  - [x] Add `#comparisonPanel` div (hidden) AFTER the `#comparePanel` div (see HTML spec below)
  - [x] Add `#cmpWarningOverlay` modal div INSIDE `.shell` BEFORE `</div><!-- /shell -->` (see HTML spec below)

- [x] Update `loadCandidates()` to store state and guard cross-assignment loads (AC: 4, 6)
  - [x] Add guard at start: if new assignment ID ≠ `_cmpAssignId` AND (`_cmpSelected.length > 0` OR `#comparisonPanel` is visible), call `showCmpWarningModal(() => loadCandidates())` and return early
  - [x] After successful fetch: set `_cmpAssignId = id`, populate `_cmpCandidatesMap` (keyed by `submission_id`), set `_cmpDimAverages = data.dimension_averages || {}`
  - [x] Clear `_cmpSelected = []`, hide `#comparisonPanel`, call `updateCompareBtnState()`
  - [x] Rebuild table rows with checkbox column prepended (see row template in Dev Notes)
  - [x] Update colspan of empty-state row to 15

- [x] Add `toggleCompareSelect(submissionId)` function (AC: 1, 3)
  - [x] If already in `_cmpSelected`: remove it, uncheck its row's checkbox, remove `.selected-row` class
  - [x] If not in `_cmpSelected` and `_cmpSelected.length < 2`: add it, add `.selected-row`
  - [x] If `_cmpSelected.length === 2` (third checkbox): remove `_cmpSelected[0]`, uncheck its checkbox and remove its `.selected-row`, then add new one
  - [x] Call `updateCompareBtnState()` after every change

- [x] Add `updateCompareBtnState()` function (AC: 1)
  - [x] `const btn = document.getElementById('cmpCompareBtn')`
  - [x] `btn.disabled = _cmpSelected.length !== 2`
  - [x] `btn.textContent = \`Compare Selected (${_cmpSelected.length}/2)\``

- [x] Add `drawCompareRadar(svgId, dimsA, dimsB)` function (AC: 2a)
  - [x] 300×300 canvas: `cx=150, cy=150, r=100, labelR=128`
  - [x] Draw grid rings (4 rings at 0.25/0.5/0.75/1.0), axes, and abbreviation labels (same pattern as existing `drawRadar`)
  - [x] Polygon B (ghost, BEHIND A): fill `rgba(240,98,146,0.15)` stroke `#f06292` strokeWidth 1.5 strokeDasharray `"4 3"`
  - [x] Polygon A (primary, IN FRONT): fill `rgba(102,126,234,0.25)` stroke `#667eea` strokeWidth 2
  - [x] Dots A: r=4 fill `#667eea` with tooltip `<title>`
  - [x] Dots B: r=3.5 fill `#f06292` opacity 0.9 with tooltip `<title>`
  - [x] Draw order: rings → axes+labels → polygon B → polygon A → dots A → dots B (B ghost behind A primary)

- [x] Add `quartileColor(score, avg)` helper (AC: 2b)
  - [x] If `avg == null`: return `'#b39ddb'` (neutral purple)
  - [x] `score >= avg + 15`: return `'#4caf50'` (green — excellent)
  - [x] `score >= avg`: return `'#2196f3'` (blue — above average)
  - [x] `score >= avg - 15`: return `'#ff9800'` (amber — below average)
  - [x] else: return `'#f44336'` (red — weak)

- [x] Add `renderComparisonPanel(idA, idB)` function (AC: 2)
  - [x] Look up `candA = _cmpCandidatesMap[idA]`, `candB = _cmpCandidatesMap[idB]`
  - [x] Set `#cmpPanelTitle` to `"Candidate A (#${candA.rank}) vs Candidate B (#${candB.rank})"`
  - [x] Populate `#cmpScoreSummary` with a two-column score/badge table for both candidates
  - [x] Call `drawCompareRadar('cmpRadarSvg', candA.dimensions || {}, candB.dimensions || {})`
  - [x] Build and set `#cmpButterflyChart` innerHTML using `DIM_ORDER` + `quartileColor()` (see butterfly template below)
  - [x] Build and set `#cmpRationale` innerHTML as `<details>` blocks for each dim (see rationale template below)
  - [x] Set `#comparisonPanel` `display = 'block'`, scroll into view

- [x] Add `closeComparisonPanel()` function (AC: 5)
  - [x] Set `document.getElementById('comparisonPanel').style.display = 'none'`

- [x] Add `showCmpWarningModal(onConfirm)` and `closeCmpModal()` functions (AC: 4)
  - [x] `showCmpWarningModal` stores callback in `_cmpModalCallback`, sets overlay `display = 'flex'`, wires confirm button
  - [x] `closeCmpModal` sets overlay `display = 'none'`

## Dev Notes

### Only File Changed: `templates/frontend.html`

No Python files touched. No new files.

| File | Action |
|------|--------|
| `templates/frontend.html` | ADD CSS, UPDATE Tab 5 HTML, UPDATE Tab 5 JS |

---

### CSS to ADD Inside `<style>` Block (after line ~185)

```css
/* ── Comparison Tab Additions ── */
.selected-row { background: #f0f0ff; }
.compare-checkbox { width: 16px; height: 16px; cursor: pointer; accent-color: #667eea; }
#cmpCompareBtn:disabled { opacity: 0.4; cursor: not-allowed; }
.butterfly-chart { width: 100%; }
.butterfly-row { display:flex; align-items:center; gap:8px; padding:7px 0; border-bottom:1px solid #f4f4fb; }
.butterfly-half { flex:1; display:flex; }
.butterfly-half-a { justify-content:flex-end; }
.butterfly-half-b { justify-content:flex-start; }
.butterfly-bar { height:18px; border-radius:3px; min-width:2px; }
.center-divider { width:2px; background:#ddd; flex-shrink:0; height:22px; align-self:center; }
```

---

### Tab 5 HTML — Updated Input Row (around line 628)

Current:
```html
<button class="btn" onclick="loadCandidates()">Load Candidates</button>
```

Replace with:
```html
<button class="btn" onclick="loadCandidates()">Load Candidates</button>
<button class="btn" id="cmpCompareBtn" disabled
    style="margin-left:8px;"
    onclick="renderComparisonPanel(..._cmpSelected)">Compare Selected (0/2)</button>
```

---

### Tab 5 HTML — Compare Table Header (around line 644)

Current first row in `<thead>`:
```html
<tr>
    <th>#</th>
    <th>Submission</th>
    ...
```

Add checkbox column as FIRST `<th>`:
```html
<tr>
    <th style="width:36px;"></th>
    <th>#</th>
    <th>Submission</th>
    ...
```

---

### Tab 5 HTML — Comparison Panel (add AFTER `<!-- Cohort averages -->` card, around line 671)

```html
<!-- Side-by-side comparison view -->
<div id="comparisonPanel" style="display:none; margin-top:16px;">
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px; padding:0 4px;">
        <div id="cmpPanelTitle" style="font-weight:700; color:#333; font-size:1.1em;"></div>
        <button class="btn" style="background:#f5f5f5;color:#555;font-size:0.85em;margin-left:auto;"
            onclick="closeComparisonPanel()">&#10005; Close</button>
    </div>
    <div class="grid-2">
        <div class="card" style="display:flex;flex-direction:column;align-items:center;">
            <h2 style="align-self:flex-start;">8-Dimension Overlay</h2>
            <svg id="cmpRadarSvg" width="300" height="300" viewBox="0 0 300 300" style="overflow:visible;"></svg>
            <div style="display:flex;gap:20px;margin-top:10px;font-size:0.82em;color:#555;">
                <span><svg width="12" height="12" style="vertical-align:middle;margin-right:4px;"><rect width="12" height="12" fill="#667eea" rx="2"/></svg>Candidate A</span>
                <span><svg width="12" height="12" style="vertical-align:middle;margin-right:4px;"><rect width="12" height="12" fill="#f06292" rx="2"/></svg>Candidate B</span>
            </div>
        </div>
        <div class="card">
            <h2>Score Summary</h2>
            <div id="cmpScoreSummary"></div>
        </div>
    </div>
    <div class="card">
        <h2>Dimension Breakdown — Butterfly Chart</h2>
        <div style="display:flex;gap:8px;font-size:0.78em;color:#888;margin-bottom:10px;align-items:center;">
            <span style="width:148px;"></span>
            <span style="flex:1;text-align:right;color:#667eea;font-weight:600;">&#8592; Candidate A</span>
            <span style="width:2px;"></span>
            <span style="flex:1;color:#f06292;font-weight:600;">Candidate B &#8594;</span>
        </div>
        <div id="cmpButterflyChart" class="butterfly-chart"></div>
        <div style="margin-top:8px;font-size:0.75em;color:#aaa;">
            Colors: <span style="color:#4caf50;">&#9632;</span> Excellent (score &ge; avg+15)
            <span style="color:#2196f3;margin-left:8px;">&#9632;</span> Above avg
            <span style="color:#ff9800;margin-left:8px;">&#9632;</span> Below avg
            <span style="color:#f44336;margin-left:8px;">&#9632;</span> Weak (score &lt; avg&minus;15)
        </div>
    </div>
    <div class="card">
        <h2>Rationale — Dimension by Dimension</h2>
        <div id="cmpRationale"></div>
    </div>
</div>
```

---

### Tab 5 HTML — Warning Modal (add BEFORE `</div><!-- /shell -->`)

```html
<!-- Comparison cross-assignment warning modal -->
<div id="cmpWarningOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:1000;align-items:center;justify-content:center;">
    <div style="background:white;border-radius:12px;padding:32px;max-width:400px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
        <h3 style="margin-bottom:12px;color:#333;">Clear Current Comparison?</h3>
        <p style="color:#666;margin-bottom:20px;font-size:0.92em;line-height:1.6;">
            Loading a new assignment will clear your current candidate selection and comparison. Continue?
        </p>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button class="btn" style="background:#f5f5f5;color:#555;" onclick="closeCmpModal()">Keep Current</button>
            <button class="btn" id="cmpModalConfirmBtn">Clear &amp; Load</button>
        </div>
    </div>
</div>
```

---

### Updated `loadCandidates()` — Full Replacement

Replace the entire `loadCandidates()` function (currently lines ~1243–1304):

```javascript
async function loadCandidates(confirmed = false) {
    const id = document.getElementById('compareAssignId').value.trim();
    if (!id) { showAlert('cmpAlert', 'Enter an assignment ID', 'error'); return; }

    // Guard: warn before clearing an active comparison/selection
    const panelVisible = document.getElementById('comparisonPanel').style.display !== 'none';
    if (!confirmed && id !== _cmpAssignId && (_cmpSelected.length > 0 || panelVisible)) {
        showCmpWarningModal(() => loadCandidates(true));
        return;
    }

    try {
        const res  = await fetch(`${API}/assignments/${id}/candidates`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || data.detail);

        // Store state
        _cmpAssignId     = id;
        _cmpDimAverages  = data.dimension_averages || {};
        _cmpCandidatesMap = {};
        _cmpSelected     = [];
        (data.candidates || []).forEach(c => { _cmpCandidatesMap[c.submission_id] = c; });

        document.getElementById('comparisonPanel').style.display = 'none';
        updateCompareBtnState();
        document.getElementById('cmpTotal').textContent = data.total;

        if (data.total === 0) {
            document.getElementById('compareBody').innerHTML =
                `<tr><td colspan="15" style="text-align:center;padding:30px;color:#aaa;">
                    No submissions yet for this assignment.</td></tr>`;
            document.getElementById('comparePanel').style.display = 'block';
            return;
        }

        document.getElementById('compareBody').innerHTML = data.candidates.map(c => {
            const score = c.composite_score || c.score || 0;
            const dimCells = DIM_ORDER.map(dim => {
                const s = c.dimensions?.[dim]?.score ?? '—';
                const cls = typeof s === 'number' ? scoreClass(s) : '';
                return `<td><span class="mini-score ${cls}">${s}</span></td>`;
            }).join('');
            return `<tr id="cmpRow-${c.submission_id}">
                <td onclick="event.stopPropagation();" style="text-align:center;">
                    <input type="checkbox" class="compare-checkbox"
                        onchange="toggleCompareSelect('${c.submission_id}', this)">
                </td>
                <td style="font-weight:700;color:#667eea;">#${c.rank}</td>
                <td style="font-family:monospace;font-size:0.82em;color:#888;">${c.submission_id.substring(0,8)}…</td>
                <td style="color:#888;">${fmtDate(c.submitted_at)}</td>
                <td style="font-weight:700;font-size:1.05em;">${Math.round(score)}</td>
                <td>${hireBadgeHtml(c.hire_recommendation)}</td>
                ${dimCells}
                <td><button class="btn btn-sm" onclick="viewInResults('${c.submission_id}')">View</button></td>
            </tr>`;
        }).join('');

        // Cohort averages
        const avgs = _cmpDimAverages;
        document.getElementById('avgBars').innerHTML = DIM_ORDER.map(dim => `
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <span style="min-width:220px;font-size:0.87em;color:#555;">
                    <strong>${DIM_SHORT[dim]}</strong> ${DIM_LABELS[dim]}
                </span>
                <div class="bar-bg" style="flex:1;">
                    <div class="bar-fill" style="width:${avgs[dim]||0}%;background:#b39ddb;"></div>
                </div>
                <span style="min-width:36px;text-align:right;font-size:0.87em;color:#555;">${avgs[dim] ?? '—'}</span>
            </div>
        `).join('');

        document.getElementById('comparePanel').style.display = 'block';
        showAlert('cmpAlert', `Loaded ${data.total} candidate(s).`, 'success');
    } catch (err) {
        showAlert('cmpAlert', 'Error: ' + err.message, 'error');
    }
}
```

---

### New JS Functions to ADD in Tab 5 section

Add AFTER `loadCandidates()`:

```javascript
function toggleCompareSelect(submissionId, checkbox) {
    const rowEl = document.getElementById('cmpRow-' + submissionId);
    const idx = _cmpSelected.indexOf(submissionId);

    if (idx !== -1) {
        // Deselecting
        _cmpSelected.splice(idx, 1);
        if (rowEl) rowEl.classList.remove('selected-row');
    } else {
        // Selecting — if already 2, evict the first
        if (_cmpSelected.length === 2) {
            const evicted = _cmpSelected.shift();
            const evictedRow = document.getElementById('cmpRow-' + evicted);
            if (evictedRow) {
                evictedRow.classList.remove('selected-row');
                const cb = evictedRow.querySelector('.compare-checkbox');
                if (cb) cb.checked = false;
            }
        }
        _cmpSelected.push(submissionId);
        if (rowEl) rowEl.classList.add('selected-row');
    }
    updateCompareBtnState();
}

function updateCompareBtnState() {
    const btn = document.getElementById('cmpCompareBtn');
    if (!btn) return;
    btn.disabled = _cmpSelected.length !== 2;
    btn.textContent = `Compare Selected (${_cmpSelected.length}/2)`;
}

function quartileColor(score, avg) {
    if (avg == null) return '#b39ddb';
    if (score >= avg + 15) return '#4caf50';
    if (score >= avg)      return '#2196f3';
    if (score >= avg - 15) return '#ff9800';
    return '#f44336';
}

function drawCompareRadar(svgId, dimsA, dimsB) {
    const svg = document.getElementById(svgId);
    const cx = 150, cy = 150, r = 100, labelR = 128;
    const n = DIM_ORDER.length;
    let html = '';

    // Grid rings
    [0.25, 0.5, 0.75, 1].forEach(frac => {
        html += `<circle cx="${cx}" cy="${cy}" r="${r * frac}" fill="none" stroke="#e8e8f0" stroke-width="1"/>`;
    });

    // Axes + labels
    DIM_ORDER.forEach((dim, i) => {
        const angle = (i * 2 * Math.PI / n) - Math.PI / 2;
        const ax = cx + r * Math.cos(angle), ay = cy + r * Math.sin(angle);
        html += `<line x1="${cx}" y1="${cy}" x2="${ax}" y2="${ay}" stroke="#e0e0e0" stroke-width="1"/>`;
        const lx = cx + labelR * Math.cos(angle), ly = cy + labelR * Math.sin(angle);
        html += `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle"
            font-size="11" font-weight="600" fill="#667eea">
            <title>${DIM_LABELS[dim]}</title>${DIM_SHORT[dim]}</text>`;
    });

    // Polygon B (ghost — behind A)
    const ptsB = DIM_ORDER.map((dim, i) => {
        const s = Math.min(100, Math.max(0, dimsB[dim]?.score || 0));
        const angle = (i * 2 * Math.PI / n) - Math.PI / 2;
        return `${cx + r * (s / 100) * Math.cos(angle)},${cy + r * (s / 100) * Math.sin(angle)}`;
    }).join(' ');
    html += `<polygon points="${ptsB}" fill="rgba(240,98,146,0.15)" stroke="#f06292" stroke-width="1.5" stroke-dasharray="4 3"/>`;

    // Polygon A (primary — in front)
    const ptsA = DIM_ORDER.map((dim, i) => {
        const s = Math.min(100, Math.max(0, dimsA[dim]?.score || 0));
        const angle = (i * 2 * Math.PI / n) - Math.PI / 2;
        return `${cx + r * (s / 100) * Math.cos(angle)},${cy + r * (s / 100) * Math.sin(angle)}`;
    }).join(' ');
    html += `<polygon points="${ptsA}" fill="rgba(102,126,234,0.25)" stroke="#667eea" stroke-width="2"/>`;

    // Dots A (purple)
    DIM_ORDER.forEach((dim, i) => {
        const s = Math.min(100, Math.max(0, dimsA[dim]?.score || 0));
        const angle = (i * 2 * Math.PI / n) - Math.PI / 2;
        const dx = cx + r * (s / 100) * Math.cos(angle), dy = cy + r * (s / 100) * Math.sin(angle);
        html += `<circle cx="${dx}" cy="${dy}" r="4" fill="#667eea"><title>${DIM_LABELS[dim]}: ${s}</title></circle>`;
    });

    // Dots B (pink)
    DIM_ORDER.forEach((dim, i) => {
        const s = Math.min(100, Math.max(0, dimsB[dim]?.score || 0));
        const angle = (i * 2 * Math.PI / n) - Math.PI / 2;
        const dx = cx + r * (s / 100) * Math.cos(angle), dy = cy + r * (s / 100) * Math.sin(angle);
        html += `<circle cx="${dx}" cy="${dy}" r="3.5" fill="#f06292" opacity="0.9"><title>${DIM_LABELS[dim]}: ${s}</title></circle>`;
    });

    svg.innerHTML = html;
}

function renderComparisonPanel(idA, idB) {
    const candA = _cmpCandidatesMap[idA];
    const candB = _cmpCandidatesMap[idB];
    if (!candA || !candB) return;

    const dimsA = candA.dimensions || {};
    const dimsB = candB.dimensions || {};

    // Panel title
    document.getElementById('cmpPanelTitle').textContent =
        `Candidate A (#${candA.rank}) vs Candidate B (#${candB.rank})`;

    // Score summary
    const scoreA = Math.round(candA.composite_score ?? candA.score ?? 0);
    const scoreB = Math.round(candB.composite_score ?? candB.score ?? 0);
    document.getElementById('cmpScoreSummary').innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:4px;">
            <div style="text-align:center;padding:16px;border:2px solid #667eea;border-radius:8px;">
                <div style="font-size:0.75em;font-weight:700;color:#667eea;letter-spacing:.05em;margin-bottom:6px;">CANDIDATE A</div>
                <div style="font-size:2em;font-weight:800;color:#333;">${scoreA}</div>
                <div style="margin-top:6px;">${hireBadgeHtml(candA.hire_recommendation)}</div>
            </div>
            <div style="text-align:center;padding:16px;border:2px solid #f06292;border-radius:8px;">
                <div style="font-size:0.75em;font-weight:700;color:#f06292;letter-spacing:.05em;margin-bottom:6px;">CANDIDATE B</div>
                <div style="font-size:2em;font-weight:800;color:#333;">${scoreB}</div>
                <div style="margin-top:6px;">${hireBadgeHtml(candB.hire_recommendation)}</div>
            </div>
        </div>`;

    // Radar
    drawCompareRadar('cmpRadarSvg', dimsA, dimsB);

    // Butterfly chart
    document.getElementById('cmpButterflyChart').innerHTML = DIM_ORDER.map(dim => {
        const sA  = dimsA[dim]?.score ?? 0;
        const sB  = dimsB[dim]?.score ?? 0;
        const avg = _cmpDimAverages[dim] ?? null;
        const cA  = quartileColor(sA, avg);
        const cB  = quartileColor(sB, avg);
        return `<div class="butterfly-row">
            <div style="width:148px;flex-shrink:0;font-size:0.82em;color:#555;">
                <strong style="color:#667eea;">${DIM_SHORT[dim]}</strong> ${DIM_LABELS[dim]}
            </div>
            <div class="butterfly-half butterfly-half-a">
                <div class="butterfly-bar" style="width:${sA}%;background:${cA};" title="A: ${sA}/100"></div>
            </div>
            <div class="center-divider"></div>
            <div class="butterfly-half butterfly-half-b">
                <div class="butterfly-bar" style="width:${sB}%;background:${cB};" title="B: ${sB}/100"></div>
            </div>
            <span style="font-size:0.8em;color:#888;min-width:60px;text-align:right;">${sA} vs ${sB}</span>
        </div>`;
    }).join('');

    // Expandable rationale
    document.getElementById('cmpRationale').innerHTML = DIM_ORDER.map(dim => {
        const sA = dimsA[dim]?.score ?? 0;
        const sB = dimsB[dim]?.score ?? 0;
        const rA = dimsA[dim]?.rationale || '—';
        const rB = dimsB[dim]?.rationale || '—';
        return `<details style="border-bottom:1px solid #f0f0f8;padding:6px 0;">
            <summary style="cursor:pointer;list-style:none;display:flex;align-items:center;gap:8px;padding:4px 0;">
                <span style="color:#667eea;font-weight:700;font-size:0.85em;min-width:26px;">${DIM_SHORT[dim]}</span>
                <span style="color:#333;font-size:0.88em;">${DIM_LABELS[dim]}</span>
                <span class="mini-score ${scoreClass(sA)}" style="margin-left:auto;">${sA}</span>
                <span style="color:#888;font-size:0.8em;">vs</span>
                <span class="mini-score ${scoreClass(sB)}">${sB}</span>
            </summary>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:10px 0 6px 34px;">
                <div>
                    <div style="font-size:0.72em;font-weight:700;color:#667eea;margin-bottom:4px;">CANDIDATE A</div>
                    <div class="rationale-text">${escHtml(rA)}</div>
                </div>
                <div>
                    <div style="font-size:0.72em;font-weight:700;color:#f06292;margin-bottom:4px;">CANDIDATE B</div>
                    <div class="rationale-text">${escHtml(rB)}</div>
                </div>
            </div>
        </details>`;
    }).join('');

    document.getElementById('comparisonPanel').style.display = 'block';
    document.getElementById('comparisonPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeComparisonPanel() {
    document.getElementById('comparisonPanel').style.display = 'none';
}

let _cmpModalCallback = null;
function showCmpWarningModal(onConfirm) {
    _cmpModalCallback = onConfirm;
    const overlay = document.getElementById('cmpWarningOverlay');
    overlay.style.display = 'flex';
    document.getElementById('cmpModalConfirmBtn').onclick = () => { closeCmpModal(); _cmpModalCallback?.(); };
}
function closeCmpModal() {
    document.getElementById('cmpWarningOverlay').style.display = 'none';
    _cmpModalCallback = null;
}
```

---

### What NOT To Do

- Do NOT modify `drawRadar()` — the existing single-candidate radar in Tab 4 is untouched. `drawCompareRadar()` is a new function.
- Do NOT change Tab 4 (`id="tab-results"`) HTML or JS.
- Do NOT add a new Python route — no backend changes.
- Do NOT call `GET /api/challenges/<id>/candidates` — use the existing assignment endpoint; it already returns `dimension_averages` and `dimensions` with `rationale`.
- Do NOT add a `<th>` checkbox column without also adding the corresponding `<td>` in every table row (structure must stay in sync — currently 14 columns → becomes 15).
- Do NOT forget to update the empty-state `colspan` from 14 → 15 in `loadCandidates()`.

### Existing Reused CSS Classes (no changes needed)

`.card`, `.grid-2`, `.btn`, `.btn-sm`, `.mini-score`, `.score-hi/.score-mid/.score-lo`, `.hire-badge`, `hire-strong_hire/hire/select/pass`, `.rationale-text`, `.bar-bg/.bar-fill` — all defined, reuse directly.

### Key Existing JS to NOT Break

- `loadCandidates()` at line ~1243: replaced entirely (guard + state storage + checkbox rows)
- `viewInResults(submissionId)` at line ~1127: untouched — still works from new table's "View" button
- `drawRadar(svgId, dimensions)` at line ~1186: untouched
- `DIM_ORDER`, `DIM_LABELS`, `DIM_SHORT` at line ~962: untouched — new functions use them directly

## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6

### Debug Log References
- All new symbols grep-verified present in frontend.html: butterfly CSS, cmpCompareBtn, comparisonPanel, cmpWarningOverlay, _cmpSelected, toggleCompareSelect, drawCompareRadar, renderComparisonPanel, etc.
- `colspan="15"` confirmed in loadCandidates empty-state row (Tab 5 only; Tab 4 correctly stays at colspan="13")
- `#comparisonPanel` placed inside `#comparePanel`→`#tab-compare` div; warning modal placed inside `.shell` before closing tag
- Draw order confirmed: rings → axes+labels → polygon B (ghost) → polygon A (primary) → dots A → dots B

### Completion Notes List
- Added 9 CSS classes/rules in `<style>` block for comparison UI (selected-row, compare-checkbox, butterfly-*, center-divider, cmpCompareBtn:disabled)
- Added 4 state variables: `_cmpSelected`, `_cmpCandidatesMap`, `_cmpDimAverages`, `_cmpAssignId`
- Added checkbox `<th>` as first column in compare table header (14 cols → 15)
- Added `#cmpCompareBtn` (disabled by default) next to "Load Candidates" button
- Added full `#comparisonPanel` HTML with: overlaid radar SVG, 2-col score summary, butterfly chart, expandable rationale `<details>` blocks
- Added `#cmpWarningOverlay` modal (fixed, z-index:1000) inside `.shell`
- Replaced `loadCandidates()` entirely: added `confirmed` param, cross-assignment guard, state storage, checkbox row template, colspan=15 empty state
- Added 8 new JS functions: `toggleCompareSelect`, `updateCompareBtnState`, `quartileColor`, `drawCompareRadar`, `renderComparisonPanel`, `closeComparisonPanel`, `showCmpWarningModal`, `closeCmpModal`
- No Python files changed; no new files; purely additive to frontend.html

## File List

- `templates/frontend.html` (UPDATE)

## Change Log

- 2026-07-02: Story created
- 2026-07-02: Implementation complete — side-by-side comparison view added to Tab 5 in templates/frontend.html; all 6 ACs satisfied; purely additive frontend-only change
- 2026-07-02: Code review complete — 4 major issues identified and fixed; story status set to done
