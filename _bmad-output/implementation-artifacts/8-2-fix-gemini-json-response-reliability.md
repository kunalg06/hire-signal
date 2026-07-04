# Story 8.2: Fix Gemini JSON Response Reliability (Challenge Generation + Scoring)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer using "Generate with AI" to create a challenge (or waiting on a submission's 8-dimension score),
I want the Gemini call to reliably return parseable JSON every time,
so that challenge generation and scoring don't intermittently fail with a raw JSON-parse error.

## Background — how this was found

Found via live, non-mocked testing of the real `POST /api/generate-challenge` flow after the Phase 2 OpenRouter/Claude → Gemini migration and Story 8.1. A user hit `Error: Failed to parse Gemini response as JSON: Unterminated string starting at: line 5 column 19 (char 1234)` in real use.

## Investigation — two distinct bugs, not one

**Bug 1 — thinking tokens silently eating the output budget.** `gemini-2.5-flash` (and later) is a "thinking" model: by default it spends tokens on an internal reasoning pass *before* writing the visible reply, and those thinking tokens are drawn from the same `max_output_tokens` budget as the visible text. Reproduced directly: a 3000-`max_output_tokens` call returned only 569 characters of visible text, cut off mid-string, because thinking consumed most of the budget. Fixed in this repo's Phase 2 follow-up work by setting `thinking_config=types.ThinkingConfig(thinking_budget=0)` in `llm_service.py`.

**Bug 2 — this story's actual subject.** Even with thinking disabled, prompting the model with "Respond ONLY with valid JSON" (prompt-level instruction only) is not reliable for fields containing multi-line content — specifically `starter_code`, a full Python file embedded as a JSON string value. Reproduced repeatedly (same `easy/bug_fix/game_logic` parameter combination failed 2 times independently, with different exact error positions each time — non-deterministic): the model would sometimes emit a raw, unescaped literal newline inside the `starter_code` string instead of the JSON-escaped `\n`, which is illegal per the JSON spec and breaks `json.loads()` with `"Invalid control character"` or `"Unterminated string"`. Adding `response_mime_type='application/json'` alone did **not** fix this — the same combination still failed after that change was in place.

**Fix**: pass a `response_schema` (Gemini's structured-output / constrained-decoding schema, not just the mimetype hint) describing the exact JSON shape each caller expects. This forces the model's decoding to stay within valid JSON grammar at the token level, rather than relying on the prompt text alone. Verified: 22/22 live calls succeeded after adding `response_schema` (14 direct SDK calls in a tight repro loop + 8 through the real `EvaluationService.generate_challenge()` code path, including the exact previously-failing parameter combination repeated 3 times in a row) — 0 failures, versus a reproducible failure rate on the same combination beforehand.

## Acceptance Criteria

1. `LLMService.chat()` accepts an optional `response_schema: dict = None` parameter; when provided, it is passed to Gemini's `GenerateContentConfig.response_schema` alongside the existing `response_mime_type='application/json'` and `thinking_config` settings.
2. `EvaluationService.generate_challenge()` passes a schema (`_CHALLENGE_RESPONSE_SCHEMA`) matching its expected `{title, description, evaluation_criteria, starter_code}` shape.
3. `EvaluationService.score_8_dimensions()` passes a schema (`_SCORING_RESPONSE_SCHEMA`) matching its expected `{dimensions: {...8 keys...}, recommendation_rationale}` shape.
4. No change to either method's return contract, error handling, or the Python-enforced composite/threshold logic downstream of the LLM call — this story only makes the LLM response itself reliably parseable.
5. Existing test suite (LLM calls mocked via flexible `lambda *args, **kwargs: ...` signatures) passes unchanged — the new optional parameter must not require updating any existing mock.
6. Live verification: the specific parameter combination that reproducibly failed before the fix (`difficulty=easy, challenge_type=bug_fix, skill_area=game_logic`) succeeds repeatedly after the fix.

## Tasks / Subtasks

- [x] Diagnose the two distinct failure modes (AC: none — investigation)
  - [x] Confirmed thinking-token truncation (Bug 1, already fixed in the Phase 2 follow-up work preceding this story) via a direct SDK call showing 569/3000 chars returned
  - [x] Confirmed `response_mime_type` alone is insufficient for Bug 2 by reproducing the same failure with it already in place
  - [x] Isolated the fix (`response_schema`) via a tight repro loop against the raw SDK (14 calls, 0 failures) before touching application code

- [x] Extend `LLMService.chat()` (AC: 1, 5)
  - [x] Added `response_schema: dict = None` parameter
  - [x] Built `GenerateContentConfig` kwargs conditionally so existing behavior (no schema) is unchanged when the parameter is omitted
  - [x] Confirmed both test files' mocks (`lambda *args, **kwargs: ...`) tolerate the new parameter with no test changes needed

- [x] Wire schemas into both `LLMService.chat()` call sites (AC: 2, 3, 4)
  - [x] `EvaluationService._CHALLENGE_RESPONSE_SCHEMA` (class-level dict) passed into the `generate_challenge()` call
  - [x] `EvaluationService._SCORING_RESPONSE_SCHEMA` (class-level dict, dimension keys built from the existing `DIMENSION_WEIGHTS` dict so the two can't drift) passed into the `score_8_dimensions()` call
  - [x] No changes to either method's fence-stripping fallback, JSON parsing, error messages, or downstream Python-enforced composite/threshold logic

- [x] Verify (AC: 5, 6)
  - [x] Full pytest suite (64 tests) passes unchanged
  - [x] `generate_challenge()` re-run 8 times across varied parameter combinations including 3 repeats of the previously-failing combination — 0 failures
  - [x] `score_8_dimensions()` re-run once against a realistic session-log + file-snapshot payload through the real API — correct structured output, correct downstream composite/recommendation computation

## Dev Notes

### Files Changed

| File | Action |
|------|--------|
| `app/services/llm_service.py` | UPDATE — `chat()` gains optional `response_schema` param |
| `app/services/evaluation_service.py` | UPDATE — two new class-level schema dicts; both `LLMService.chat()` call sites pass their schema |

### What NOT To Do

- Do NOT remove the existing markdown-fence-stripping fallback in `generate_challenge()` / `score_8_dimensions()` — it's now largely dead code with `response_mime_type='application/json'` in place (Gemini shouldn't wrap fenced output when JSON mode is requested), but it's harmless and Story 7.1's `test_json_fenced_response_parses` test still exercises it directly via a mocked response.
- Do NOT make `response_schema` a required parameter on `chat()` — future callers that want free-text (not JSON) responses should be able to omit it; `response_mime_type` and `thinking_config` are unconditional today only because *every current caller* wants JSON, not because the interface should assume that forever.
- Do NOT hand-write the 8 dimension keys twice in the scoring schema — build it from `DIMENSION_WEIGHTS` (already done) so a future dimension-weight change can't silently desync the schema from the scoring rubric.

### References

- [Source: `AGENT.md` Phase 2 — LLM Provider Migration: OpenRouter/Claude → Gemini (2026-07-04)]
- [Source: `_bmad-output/implementation-artifacts/8-1-pre-authenticate-gemini-cli-in-student-container.md` — same session's prior story]
- [Source: `app/services/llm_service.py`, `app/services/evaluation_service.py`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Direct `google-genai` SDK repro loop (bypassing app code): 14/14 successful with `response_schema`, versus a reproducible failure on the identical prompt/params without it.
- Full `EvaluationService.generate_challenge()` repro through app code: 8/8 successful post-fix, including 3 repeats of the specific combination that failed pre-fix.
- `EvaluationService.score_8_dimensions()` verified once against a realistic payload — correct dimensions, rationale, composite, and recommendation.
- Full pytest suite: 64/64 passing, unchanged.

### Completion Notes List

- Root-caused a live user-reported error (`Unterminated string starting at: line 5 column 19 (char 1234)`) to Gemini's JSON-mode reliability for long multi-line string fields, distinct from the earlier thinking-token truncation bug.
- `response_mime_type='application/json'` alone was insufficient — verified by reproducing the same failure with it already active.
- `response_schema` (true structured-output constrained decoding) resolved it — verified with 22 total live calls (14 direct SDK + 8 through app code) and 0 failures post-fix, against a reproducible failure rate pre-fix on the same inputs.
- `data/assignments.db` — one test challenge created during live verification (`POST /api/generate-challenge` through the real Flask test client) was deleted afterward; no residual test data left in the real database.

### File List

- `app/services/llm_service.py` (UPDATE)
- `app/services/evaluation_service.py` (UPDATE)

## Change Log

- 2026-07-04: Story created in response to a live user-reported JSON parse error following the Phase 2 Gemini migration and Story 8.1.
- 2026-07-04: Root-caused to two distinct issues (thinking-token truncation, already mitigated; and JSON-mode string-escaping unreliability, this story's fix). `response_schema` added to `LLMService.chat()` and wired into both `generate_challenge()` and `score_8_dimensions()`. Verified via 22 live calls with 0 failures; full test suite unchanged at 64/64.
