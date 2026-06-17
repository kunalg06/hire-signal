---
title: 'Session Log Parsing & Scoring Integration with Candidate Portal Enhancement'
type: 'feature'
created: '2026-06-17'
status: 'in-review'
baseline_commit: '24072e5'
completion_commit: '0741082'
context: ['README.md', 'CLAUDE.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Existing system has candidate portal (/student/{link_id}) and file collection from Docker, but Claude session logs are collected but not parsed/structured. Teachers cannot see what Claude prompts candidate used or evaluate problem-solving approach. Scoring only considers code quality, missing efficiency and approach dimensions.

**Approach:** (1) Parse Claude session logs collected from containers into structured JSON format and store in new session_logs DB table, (2) enhance candidate portal to display session log viewer showing candidate's Claude prompts/responses in real-time or on submission, (3) add scoring logic that evaluates approach (from logs) + efficiency (from log iterations) in addition to code quality, (4) extend teacher dashboard to show session log analysis alongside evaluation results.

## Boundaries & Constraints

**Always:**
- Keep FastAPI backend structure; do NOT refactor to Flask (existing code uses FastAPI)
- Preserve existing Docker file collection via get_archive() + tar (working, tested)
- Preserve existing candidate portal at /student/{link_id} (already has submit button, timer, assignment display)
- Session logs stored per submission_id in new session_logs table (append-only, not modified after submission)
- All timestamps UTC; session logs use ISO 8601 format
- Scoring logic reads finalized session logs (no live scoring during session)
- Code-server containers unchanged — embedding remains iframe-based via /codeserver/{link_id}

**Ask First:**
- If session log schema needs additional fields beyond [timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json]
- If scoring weights diverge from [40% code quality, 30% problem-solving approach, 30% efficiency]
- If session log display needs real-time updates during coding (currently show on submit only)

**Never:**
- Do not refactor existing /student/{link_id} route (enhance, don't replace)
- Do not modify Dockerfile or container entrypoint
- Do not add authentication to candidate portal (link_id is implicit auth)
- Do not encrypt session logs (store as plain JSON for teacher review)

**Portal Enhancement:**
- Embed code-server in iframe on /student/{link_id} page (not new tab)
- Add "Submit Solution" button directly on portal (not via localhost:9999)
- Two-column layout: (left) assignment details + submission area, (right) code-server iframe
- Post-submission: show session logs + evaluation results on same page

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| **Student uses Claude CLI** | Student runs `claude evaluate solution.py` in code-server terminal | Interaction captured by container logging mechanism, stored in /home/coder/.claude/logs/session.log or similar path | Claude API errors → logged as error entry, included in session_logs with error flag |
| **Student submits code** | Click "Submit Code" button on /student/{link_id} | (1) Collect files from /workspace via Docker get_archive, (2) Collect Claude session log from container, (3) Parse session log into structured JSON entries, (4) Store entries in session_logs table, (5) Create submission record, (6) Trigger evaluation | Missing session log file → create empty session_logs entries with note "No Claude interactions found" |
| **Parse session log** | Raw Claude session log file (text or structured format) | Parse into JSON array: [{timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json}] | Malformed entries → skip entry, log warning, continue parsing; Empty log → return empty array |
| **Calculate approach score** | Finalized session_logs array for submission | Count: (1) iterations to solution (prompt count), (2) self-correction patterns, (3) feature usage variety → score 0-30 | No Claude interactions → score = 0 with note "No Claude CLI usage detected" |
| **Calculate efficiency score** | session_logs with timestamps, container creation time, submission time | (submission_time - container_creation_time) / 2_hour_budget → efficiency score 0-30. Fewer iterations & less time = higher score | Missing timestamps → default efficiency score to 15 (neutral) |
| **Teacher views results** | GET /api/submission/{submission_id} | Return: code quality (40%), approach score from logs (30%), efficiency score (30%), session log array with all Claude prompts | Session log missing → return approach/efficiency scores as 0, include note "Session log unavailable" |
| **Display session logs in portal** | GET /api/session-logs/{submission_id} after submission | Return JSON array of session log entries, frontend renders chronological list of prompts/responses | Empty array → show "No Claude interactions recorded" message |

</frozen-after-approval>

## Code Map

- `main.py` -- FastAPI backend; lines 942-1060 (submit_with_files) already collect Docker files + claude logs; needs: (1) session log parsing function, (2) session_logs table storage, (3) scoring functions, (4) session log viewer endpoint
- `frontend.html` -- Teacher dashboard (existing); needs: add session log display panel to submission results view
- `assignments.db` -- SQLite DB; needs new session_logs table: (log_id PK, submission_id FK, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json)
- Existing candidate portal: `/student/{link_id}` at lines 1454-1736 in main.py (already working)

## Tasks & Acceptance

**Execution:**
- [x] `assignments.db` -- Create session_logs table schema: log_id (PK UUID), submission_id (FK), timestamp (ISO8601), interaction_type TEXT, prompt TEXT, response_summary TEXT, file_changes_count INT, raw_json TEXT
- [x] `main.py` (new function) -- Add parse_claude_session_log(log_content: str) -> List[dict] that parses raw log text into structured JSON entries with [timestamp, interaction_type, prompt, response_summary, file_changes_count]. Handle multiple log formats (plaintext, JSON lines, mixed)
- [x] `main.py` (lines 1000-1030) -- Enhance submit_with_files: after collecting claude_session.log, parse it with parse_claude_session_log(), store entries in session_logs table via cursor.execute INSERT INTO session_logs
- [x] `main.py` (new function) -- Add score_from_session_logs(session_logs: List[dict], submission_id: str) -> tuple(approach_score 0-30, efficiency_score 0-30) that: (1) counts iterations (len(logs)), (2) detects self-correction patterns (responses with "try again", "fixed"), (3) calculates efficiency from first_log_timestamp to last_log_timestamp vs 2-hour budget
- [x] `main.py` (lines 809-817, evaluate_code_with_claude) -- Extend evaluation to call score_from_session_logs and combine: final_score = code_quality (40%) + approach_score (30%) + efficiency_score (30%); update feedback to include reasoning for each component
- [x] `main.py` (new endpoint) -- Add GET /api/session-logs/{submission_id} that queries session_logs table, returns JSON array with all entries for submission_id, sorted by timestamp
- [x] `main.py` (lines 1454-1736, /student/{link_id}) -- Enhance UI: (1) Add iframe <iframe src="http://localhost:{port}/?folder=/workspace" style="width:100%;height:600px;"></iframe> embedded in right column, (2) Add "Submit Solution" button in left column with onclick handler calling POST /api/submit-with-files/{link_id}, (3) After submission, show results panel with evaluation score + session logs below button
- [x] `frontend.html` (lines near submission results) -- Add session log viewer panel below evaluation feedback: displays fetch(/api/session-logs/{id}), renders each log entry as: timestamp | prompt | response_summary | files changed. Include note if no logs found
- [x] Test end-to-end: create assignment → generate link → open /student/{link_id} → see code-server embedded in iframe on same page → use claude in code-server terminal → click "Submit Solution" button → see results with score breakdown + session logs all on same page

**Acceptance Criteria:**
- Given student opens /student/{link_id}, when page loads, then code-server appears embedded in iframe on right side, assignment details on left side, "Submit Solution" button visible below assignment
- Given student codes in embedded code-server iframe, when student types and saves files, then files are written to /workspace in container (unchanged functionality)
- Given student uses `claude evaluate solution.py` in code-server terminal, when student clicks "Submit Solution" button, then that interaction is captured, parsed, and stored in session_logs table with timestamp, prompt, response_summary
- Given submission has 3 Claude interactions, when scoring evaluates logs, then approach score = 20 (3 iterations × base) and efficiency score is calculated from container_creation_time to submission_time
- Given student submits via "Submit Solution" button, when page shows results, then results panel displays on left column below button showing: code_quality (40%), approach_score (30%), efficiency_score (30%), total_score, and session log panel below with all Claude prompts/responses chronologically
- Given student never uses Claude CLI, when submission evaluated, then approach score = 0, efficiency score = 0, feedback notes "No Claude interactions recorded"
- Given session log parsing encounters malformed entry, when parse_claude_session_log processes log, then malformed entry is skipped with warning, valid entries stored, no crash
- Given candidate portal page loads with results, when teacher views same /student/{link_id}, then results visible with full evaluation and session logs (optional: password protect results view)

## Design Notes

**Session Log Parsing:**
Claude CLI stores session logs in multiple possible locations: `/home/coder/.claude/logs/session.log`, `/root/.claude/logs/session.log`, `/tmp/claude_session.log`. Log format varies: may be JSON lines, plaintext transcript, or mixed. Parser must be resilient:
```python
def parse_claude_session_log(log_content: str):
    # Try JSON lines first
    entries = []
    for line in log_content.split('\n'):
        try:
            entry = json.loads(line)  # Already structured
            entries.append(entry)
        except:
            pass  # Not JSON, try plaintext parsing
    
    # Fallback: parse plaintext transcript (look for patterns like "Prompt: ... Response: ...")
    # Each interaction: extract timestamp, prompt, response, deduce file_changes_count from response
    return entries
```

**Scoring from Session Logs:**
- **Approach Score (30%):** Measure problem-solving quality. Heuristic: (1) iteration_count = len(logs) × 3 (each interaction = 3 pts), (2) self_correction_bonus = +5 for each log with "error|fix|try again" in response, (3) cap at 30. Examples: 1 interaction = 3 pts, 3 interactions = 9 pts, 3 + corrections = 15 pts. Intended: encourages exploration without penalizing multiple attempts.
- **Efficiency Score (30%):** Time-based. elapsed_time = submission_time - container_creation_time. Budget = 2 hours. Efficiency = min(30, (2_hours / elapsed_time) × 30). Faster = higher score. Example: solved in 30 min = 30 pts, 1 hour = 15 pts, 2+ hours = <10 pts.
- **Code Quality (40%):** Existing Claude evaluation (lines 749-817) already provides this score.
- **Total:** (approach/30 + efficiency/30 + code_quality/40) × 100, clamped to 0-100.

**Container Log Collection (Already Working):**
Existing code at lines 978-1030 uses `container.get_archive()` to extract files via Docker API. Log paths checked in order; first found is parsed.

## Verification

**Commands:**
- `curl -X POST http://localhost:8000/api/assignments -d '{"title":"TempConverter","description":"Build temp converter","starter_code":"def celsius_to_f(c): pass","evaluation_criteria":"Works correctly"}' -H 'Content-Type: application/json'` -- expected: returns assignment_id (e.g., "3e2d1c...")
- `curl -X POST http://localhost:8000/api/generate-link/3e2d1c...` -- expected: returns link_id, access_url points to /student/{link_id}
- `curl http://localhost:8000/student/{link_id}` -- expected: 200 HTML with assignment details, "Open VS Code" button, submit instructions
- `curl -X POST http://localhost:8000/api/submit-with-files/{link_id}` -- expected: creates submission, parses session logs, returns submission_id with scores
- `curl http://localhost:8000/api/submission/{submission_id}` -- expected: returns submission details with code, scores (code_quality + approach + efficiency), feedback including scoring breakdown
- `curl http://localhost:8000/api/session-logs/{submission_id}` -- expected: returns JSON array of session log entries with [{timestamp, interaction_type, prompt, response_summary, file_changes_count}]

**Manual checks:**
- Verify session_logs table exists: `SELECT log_id, submission_id, timestamp, prompt FROM session_logs LIMIT 1`
- Open http://localhost:8000/student/{link_id} in browser:
  - Left column shows assignment title, description, evaluation criteria
  - Right column shows code-server embedded in iframe (http://localhost:{port}/?folder=/workspace)
  - "Submit Solution" button visible below assignment details
- In embedded code-server: create/edit solution.py, verify files sync to container
- Use Claude CLI: `claude evaluate solution.py` in code-server terminal
- Click "Submit Solution" button on /student/{link_id} page (no new tabs, no localhost:9999)
- After submission, verify results appear on same page below "Submit Solution" button:
  - Scoring breakdown: Code Quality (40%), Approach (30%), Efficiency (30%), Total (0-100)
  - Session log panel showing all Claude interactions chronologically
- Edge case: submit with no Claude interactions → approach/efficiency = 0, message "No Claude CLI usage"
- Edge case: session log missing → code quality score shown, approach/efficiency default to 0
