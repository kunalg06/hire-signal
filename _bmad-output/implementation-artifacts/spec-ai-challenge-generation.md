---
title: 'Add AI-Powered Challenge Generation'
type: 'feature'
created: '2026-05-20'
status: 'done'
context: ['CLAUDE.md']
baseline_commit: 'NO_VCS'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Teachers must manually create assignments with boilerplate code and evaluation criteria, which is time-consuming and limits the platform's ability to scale for hiring pipelines.

**Approach:** Add a "Generate Challenge" button in the dashboard that uses Claude API to auto-generate complete assignments (title, description, starter code in Flask/FastAPI, edge-case evaluation criteria) from a simple problem statement + difficulty level.

## Boundaries & Constraints

**Always:**
- Use Claude API to generate challenges (not hardcoded templates).
- Generate only one challenge per request; batch generation deferred to future.
- Starter code must be syntactically valid Flask or FastAPI.
- Evaluation criteria must include edge-case handling instructions (e.g., negative amounts, concurrent requests, invalid inputs).
- Treat generated challenges as drafts until teacher reviews and saves them.

**Ask First:**
- If Claude API fails, should the UI show raw error or a friendly message?
- Should teachers be able to edit generated challenges before saving, or auto-save immediately?

**Never:**
- Store generated challenges in the database unless teacher explicitly saves them.
- Use hardcoded prompts; make them configurable for future customization.
- Support non-Python frameworks (Node, Go, etc.) in scope 1.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path: Easy difficulty | `problem_statement="Create a banking transfer API"`, `difficulty="easy"` | Returns challenge with basic CRUD operations, simple validation | N/A |
| Happy path: Hard difficulty | `problem_statement="Create a banking transfer API"`, `difficulty="hard"` | Returns challenge with concurrency, security, pagination, edge cases | N/A |
| Framework selection (Flask) | Generated starter code defaults to Flask if not specified | Code uses Flask patterns, blueprints, jsonify | N/A |
| Framework selection (FastAPI) | Teacher selects FastAPI in request | Code uses async/await, Pydantic models, status codes | N/A |
| Claude API timeout | Request exceeds 30 seconds | Return 408 status with "Generation took too long" message | User sees UI error, can retry |
| Missing problem statement | `problem_statement=""` or null | Return 400 status with "Problem statement required" | Validation error shown in UI |
| Invalid difficulty | `difficulty="expert"` | Return 400 status with "Difficulty must be easy, medium, or hard" | Validation error shown in UI |

</frozen-after-approval>

## Code Map

- `main.py` — Add POST `/api/generate-challenge` endpoint with Claude integration.
- `frontend.html` — Add "Generate Challenge" section with problem statement textarea, difficulty dropdown, and generate button.
- Schema: No DB changes needed; challenges remain in-memory until teacher saves via existing POST `/api/assignments`.

## Tasks & Acceptance

**Execution:**
- [x] `main.py` -- Add Pydantic models `ChallengeRequest` and `ChallengeResponse` for request/response validation.
- [x] `main.py` -- Add Claude prompt template for challenge generation that includes framework selection, problem statement, and difficulty level.
- [x] `main.py` -- Add `POST /api/generate-challenge` endpoint that calls Claude API and returns generated challenge (title, description, starter code, evaluation criteria).
- [x] `frontend.html` -- Add "Generate Challenge" section with textarea for problem statement, dropdown for difficulty (easy/medium/hard), and generate button.
- [x] `frontend.html` -- Add JavaScript function `generateChallenge()` that POSTs to `/api/generate-challenge`, shows loading state, and displays generated challenge with "Save as Assignment" button.
- [x] `frontend.html` -- Wire "Save as Assignment" button to POST existing `/api/assignments` endpoint with generated data.

**Acceptance Criteria:**
- Given a teacher enters a problem statement "Create a banking transfer API" and selects "medium" difficulty, when they click "Generate Challenge", then Claude generates and displays a Flask API assignment with title, description, working starter code, and evaluation criteria covering edge cases (negative amounts, concurrent transfers, invalid accounts).
- Given Claude API fails to respond within 30 seconds, when a teacher clicks "Generate Challenge", then the UI displays "Generation took too long. Please try again." and the request times out gracefully without crashing.
- Given a teacher views a generated challenge and clicks "Save as Assignment", when the save completes, then the challenge appears in the assignments list and students can access it via generated links.
- Given a teacher enters an empty problem statement, when they click "Generate Challenge", then the UI displays "Problem statement is required" and prevents submission.

## Design Notes

**Claude Prompt Design:**
The prompt should instruct Claude to generate challenges with:
1. A clear, actionable project title (e.g., "Banking Transfer System").
2. A detailed description of what the student must build.
3. Starter code in Flask or FastAPI (defaults to Flask; teacher can request FastAPI).
4. Evaluation criteria as a checklist including:
   - Core functionality (happy path).
   - Edge cases (negative amounts, zero, invalid account numbers).
   - Concurrency/async handling (if applicable).
   - Input validation and error responses.
   - Code quality (naming, documentation, performance).

**Difficulty Scaling:**
- **Easy:** Basic CRUD operations, simple validation, no concurrency.
- **Medium:** Validation + business rules (e.g., balance checks), basic error handling.
- **Hard:** Concurrency, security (authentication/authorization), pagination, rate limiting, comprehensive error handling.

## Verification

**Commands:**
- `curl -X POST http://localhost:8000/api/generate-challenge -H "Content-Type: application/json" -d '{"problem_statement":"Create a banking transfer API","difficulty":"medium"}' | jq` -- expected: Returns JSON with title, description, starter_code, evaluation_criteria (all non-empty).
- Open `http://localhost:8000/frontend.html` in browser → UI has "Generate Challenge" section visible with problem statement textarea and difficulty dropdown.

**Manual checks:**
- Generate a challenge and verify the starter code is syntactically valid Python (flask or fastapi).
- Save a generated challenge and verify it appears in the assignments list.
- Verify "Save as Assignment" button triggers the existing `/api/assignments` endpoint.

## Suggested Review Order

**API Endpoint & Design**

- Main challenge generation endpoint with request validation and error handling.
  [`main.py:250`](../../main.py#L250)

**Input Validation & Safety**

- Challenge request model validates problem statement and difficulty level.
  [`main.py:148`](../../main.py#L148)

- Rate limiting prevents API abuse (5 requests per minute per client).
  [`main.py:37`](../../main.py#L37)

- Input length validation caps problem statement at 2000 characters.
  [`main.py:268`](../../main.py#L268)

**Code Generation & Validation**

- Claude prompt template requests well-structured JSON with validation instructions.
  [`main.py:220`](../../main.py#L220)

- Python syntax validation ensures generated starter code is valid.
  [`main.py:277`](../../main.py#L277)

- JSON parsing handles both raw JSON and markdown-wrapped responses.
  [`main.py:285`](../../main.py#L285)

- Claude API call with 30-second timeout prevents service hangs.
  [`main.py:269`](../../main.py#L269)

- Secure error messages hide implementation details from clients.
  [`main.py:302`](../../main.py#L302)

**Frontend UI & Interaction**

- Generate Challenge form with difficulty selection and character limit feedback.
  [`frontend.html:287`](../../frontend.html#L287)

- Challenge generation handler with fetch timeout and double-submit prevention.
  [`frontend.html:559`](../../frontend.html#L559)

- Save to Assignment integrates with existing `/api/assignments` endpoint.
  [`frontend.html:629`](../../frontend.html#L629)
