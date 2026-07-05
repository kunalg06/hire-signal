# API Reference

All endpoints are served by the Flask app in `app/`, mounted at `http://localhost:8000` in development (`PORT` env var). No authentication exists yet — see `CLAUDE.md`'s Security Considerations before deploying anywhere non-local.

## Table of Contents

1. [Assignments](#assignments)
2. [Links](#links)
3. [Challenges](#challenges)
4. [Submissions](#submissions)
5. [Analytics](#analytics)
6. [Student](#student)
7. [System / Management](#system--management)

---

## Assignments

`app/routes/assignments.py`

### `GET /api/assignments`
List all assignments.

```json
[
  {"id": "uuid", "title": "...", "description": "...", "starter_code": "...", "evaluation_criteria": "..."}
]
```

### `POST /api/assignments`
Create an assignment. `title` and `evaluation_criteria` are required; `challenge_id` is optional (links the assignment to a catalog challenge).

```json
{"title": "Rate Limiter Bug", "description": "...", "starter_code": "...", "evaluation_criteria": "...", "challenge_id": "uuid-or-null"}
```
→ `201` with the created row, or `400 {"detail": "..."}` if required fields are missing.

### `GET /api/assignments/<id>`
→ `200` with the assignment, or `404 {"detail": "Assignment not found"}`.

### `GET /api/assignments/<id>/candidates`
Simple per-assignment candidate ranking (rank assigned by insertion order of `get_candidates_for_assignment`, no `sort_by`/`order` query params — for the fuller-featured version, see `GET /api/challenges/<id>/candidates` below). → `404` if the assignment doesn't exist.

---

## Links

`app/routes/links.py`

### `POST /api/generate-link/<assignment_id>`
Spins up a candidate container (or degrades gracefully if Docker is unavailable) and returns a shareable access link.

```json
{"link_id": "...", "assignment_id": "...", "access_url": "http://localhost:7123", "vscode_port": 7123, "expires_at": "2026-07-04T12:00:00"}
```
→ `201`, or `404 {"detail": "Assignment not found"}`.

If the assignment is linked to a challenge with `ai_assistance_mode='guarded'`, a `GEMINI.md` restriction file is also injected into the container's `/workspace` (see `docs/ARCHITECTURE.md`).

---

## Challenges

`app/routes/challenges.py`

### `POST /api/generate-challenge`
Generates a market-aligned coding challenge via the LLM and persists it to the catalog as an unpublished draft.

**Request:**
```json
{
  "problem_statement": "Fix a leaking rate limiter under concurrent load",
  "difficulty": "easy | medium | hard",
  "challenge_type": "bug_fix | feature_extension | refactoring | optimization",
  "skill_area": "api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic",
  "ai_assistance_mode": "guarded | unguarded"
}
```
`problem_statement` and `difficulty` are required; the rest default to `feature_extension` / `api_integration` / `unguarded`.

**Response `200`:**
```json
{
  "title": "...", "description": "...", "evaluation_criteria": "...", "starter_code": "...",
  "challenge_id": "uuid-or-null",
  "challenge_type": "bug_fix", "skill_area": "api_integration",
  "difficulty": "medium", "ai_assistance_mode": "unguarded",
  "is_published": false
}
```

**Errors:**
- `400` — a required field is missing or an enum value is invalid (checked *before* any LLM call is made)
- `500` — the LLM call failed, or its response was unparseable / missing a required field
- `challenge_id: null` in a `200` response — generation succeeded but persistence failed (logged server-side, doesn't fail the request)

### `GET /api/challenges`
List published challenges (`is_published=1` only). Optional filters: `challenge_type`, `skill_area`, `difficulty`, `ai_assistance_mode` (each validated against its enum, `400` if invalid).

```json
{"challenges": [...], "total": 3, "filters": {"challenge_type": null, "skill_area": null, "difficulty": null, "ai_assistance_mode": null}}
```

### `GET /api/challenges/<id>`
Fetch a single challenge regardless of publish status. → `200` or `404 {"error": "Challenge not found"}`.

### `POST /api/challenges/<id>/publish`
→ `200 {"challenge_id": "...", "is_published": true, "message": "..."}` or `404`.

### `DELETE /api/challenges/<id>`
Soft-delete (`is_published = -1`, row is never actually removed). → `200 {"challenge_id": "...", "is_published": false, "message": "..."}` or `404`.

### `GET /api/challenges/<id>/candidates`
The full-featured candidate ranking endpoint — sortable, with visibility-floor and dimension averages.

**Query params:**
- `sort_by` — `composite_score` (default) or any of the 8 dimension keys (`problem_decomposition`, `first_principles_thinking`, `creative_problem_solving`, `iteration_quality`, `debugging_with_ai`, `architecture_decisions`, `communication_clarity`, `token_efficiency`)
- `order` — `desc` (default) or `asc`

**Response `200`:**
```json
{
  "challenge_id": "...",
  "candidates": [
    {
      "rank": 1, "submission_id": "...", "link_id": "...", "submitted_at": "...",
      "score": 85.0, "composite_score": 85.0, "hire_recommendation": "strong_hire",
      "recommendation_rationale": "...", "is_evaluated": true,
      "dimensions": {"problem_decomposition": {"score": 90, "rationale": "..."}, "...": "..."}
    }
  ],
  "total": 3,
  "dimension_averages": {"problem_decomposition": 78.5, "...": "..."}
}
```

**Behavior notes:**
- Un-evaluated candidates always sort **last**, in both `asc` and `desc` — they're never hidden, just ranked lowest.
- `dimension_averages` is computed only over evaluated candidates; it's `{}` (not missing) when zero candidates have been evaluated.
- Only submissions whose assignment's `challenge_id` matches are included — candidates from other challenges never leak in.

→ `404 {"error": "Challenge not found"}` if the challenge doesn't exist; `400` for an invalid `sort_by`/`order` (checked *after* the existence check, so a nonexistent challenge with bad query params still 404s).

### `GET /api/challenges/meta/options`
Returns the valid enum value sets for challenge creation/filtering — useful for populating a form's dropdowns without hardcoding the lists client-side.

---

## Submissions

`app/routes/submissions.py`

### `GET /api/submissions`
List all submissions.

### `POST /api/submit-with-files/<link_id>`
Candidate submits their workspace files. Triggers 8-dimension evaluation on a background thread — this endpoint returns immediately with the `submission_id`; poll `GET /api/submission/<id>` for results.

### `GET /api/submission/<id_or_link>`
Accepts either a `submission_id` or a `link_id` (falls back to the most recent submission for that link if the direct lookup misses). Returns the full submission plus its evaluation state.

```json
{
  "submission_id": "...", "link_id": "...", "assignment_id": "...", "code": "...",
  "submitted_at": "...", "score": 85.0, "feedback": "...", "assignment_title": "...",
  "is_flagged": false, "flag_reason": null, "flag_by": null, "flagged_at": null,
  "ai_assistance_mode": "guarded", "guarded_mode_enforced": true,
  "instructions_md": "...", "gemini_logs": "No Gemini session logs available",
  "dimensions": {"problem_decomposition": {"score": 90, "rationale": "...", "scoring_method": "llm_judge"}},
  "hire_evaluation": {
    "composite_score": 85.0, "hire_recommendation": "strong_hire",
    "dimension_weights": {"problem_decomposition": 0.15, "...": "..."},
    "recommendation_rationale": "...", "is_overridden": false,
    "override_recommendation": null, "override_rationale": null, "evaluated_at": "..."
  }
}
```

`hire_evaluation` is `null` if scoring hasn't completed yet — this is what the frontend polls on. → `404 {"detail": "Submission not found"}`.

`ai_assistance_mode`/`guarded_mode_enforced` (Story 9.3) surface whether a "guarded" assessment actually got its `GEMINI.md` restriction applied to the container — `guarded_mode_enforced` is `false` if the injection failed (assessment may have silently run unguarded). Both are `null` for links that predate this tracking.

### `GET /api/session-logs/<submission_id>`
Raw parsed Gemini CLI session log for a submission.

### `POST /api/submissions/<id>/flag`
Marks a submission for manual review. `reason` is required.

```json
{"reason": "Suspicious timing pattern", "flagged_by": "recruiter@example.com"}
```
→ `200 {"submission_id": "...", "is_flagged": true, "flag_reason": "...", "flag_by": "...", "message": "..."}`, `400` if `reason` missing, `404` if the submission doesn't exist.

### `POST /api/submissions/<id>/override`
Applies a human override to the AI hire recommendation. Both `override_recommendation` and `override_rationale` are required; `override_recommendation` must be a valid recommendation value.

```json
{"override_recommendation": "hire", "override_rationale": "Strong communication, weak on iteration but coachable"}
```
→ `200` on success. `400` if fields are missing/invalid, `404` if the submission doesn't exist, `409` if no evaluation exists yet to override.

**Important:** the original AI `composite_score`/`recommendation` in `hire_evaluations` are **never modified** — only `override_recommendation`/`override_rationale`/`is_overridden` columns are written. Every successful override also appends a permanent row to the append-only `score_overrides` table.

---

## Analytics

`app/routes/analytics.py`

### `GET /api/analytics/overrides`
Calibration analytics over the append-only `score_overrides` log: total override count, breakdown by override direction, the 20 most recent overrides, and a pattern summary (directions with ≥20% share, only computed once there are ≥10 total overrides).

---

## Student

`app/routes/student.py`

### `GET /student/<link_id>`
The candidate's actual assessment workspace — an iframe embedding their code-server container plus a submission UI (verification nudge, real-time polling, results view).

### `GET /student/preview/<challenge_id>`
Employer-facing preview of what a candidate would see for a given challenge — **no Docker container is spun up**. Renders the challenge-template content (title/description/criteria/starter code), not a live assignment instance, so it can diverge slightly if an employer edits an assignment after generating it from this challenge.

---

## System / Management

`app/routes/management.py` (all under `/api/system`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/system/status` | Aggregate system status |
| GET | `/api/system/health` | Health check |
| POST | `/api/system/cleanup-old` | Remove containers idle past a threshold |
| POST | `/api/system/cleanup-all` | Remove all managed containers |
| GET | `/api/system/containers/<id>/info` | Single container detail |
| GET | `/api/system/containers/<id>/logs` | Container logs |
| POST | `/api/system/containers/<id>/restart` | Restart a container |
| POST | `/api/system/containers/<id>/stop` | Stop a container |

---

## Related docs

- `docs/ARCHITECTURE.md` — system design and the four core request/response flows
- `CLAUDE.md` — dev workflow and architecture constraints
- `AGENT.md` — current implementation state, including known gaps in some of the behavior documented above (see its "Notable open production gaps" section)
