# Story 8.4: Retry on Gemini JSON Parse Failure (response_schema Alone Wasn't Enough)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer using "Generate with AI",
I want a single bad Gemini generation to not surface as a user-facing error,
so that an intermittent, ~1-in-N malformed response doesn't block challenge generation.

## Background — how this was found

A user hit the **exact same error** reported and believed fixed in Story 8.2 — `Failed to parse Gemini response as JSON: Unterminated string starting at: line 5 column 19 (char 1234)` — a second time, after Story 8.2's `response_schema` fix was already live.

## Investigation

Two things had to be ruled out before concluding `response_schema` itself was insufficient:

1. **Stale server process.** The dev server runs via `python run.py` with Werkzeug's debug reloader (`debug=True` by default). Confirmed two `run.py` processes were running; hit the *actual live* `/api/generate-challenge` endpoint directly with `curl` — it succeeded (200, well-formed challenge), proving the running process **did** have Story 8.2's fix loaded. This ruled out "the fix never actually deployed" as the explanation.
2. **On-disk fix genuinely still present.** `grep` confirmed `response_schema`/`thinking_budget`/`response_mime_type` are all still in `llm_service.py` and `evaluation_service.py`. A fresh-process stress test (8 calls, varied parameters) all succeeded.

Conclusion: `response_schema` genuinely reduced the failure rate (Story 8.2's 22/22 clean run, this story's own fresh 8/8 and 5/5 clean runs), but Gemini's structured-output mode is **not a 100% guarantee** against malformed string escaping for long, code-heavy fields — it's a probabilistic reduction, not an elimination. The user's second report is consistent with hitting the residual, lower-but-nonzero failure rate.

**Fix**: since the underlying failure is probabilistic and independent per generation, retry with a fresh call rather than trying to detect/repair broken JSON. Added `EvaluationService._call_llm_for_json()`, a shared helper used by both `generate_challenge()` and `score_8_dimensions()`, that retries up to 3 times **on JSON-parse or field-validation failure only** — not on genuine API/network errors, which propagate immediately (see AC 4 below; this distinction is load-bearing, not stylistic).

## Acceptance Criteria

1. `EvaluationService._call_llm_for_json(prompt, max_tokens, response_schema, validate=None, max_retries=3)` calls `LLMService.chat()`, strips markdown fences if present, `json.loads()`s the result, and optionally runs a caller-supplied `validate(dict) -> None` (raising `ValueError` on failure).
2. On `json.JSONDecodeError` or `ValueError` (from `validate`), retry with a fresh `LLMService.chat()` call, up to `max_retries` attempts total, before re-raising the last error.
3. If `LLMService.chat()` itself raises (any exception not caught by the JSON/ValueError-specific retry logic — e.g. a network or API error), that propagates **immediately, with no retry**. This is intentional: an existing test (`test_llm_failure_returns_500_and_persists_nothing`) asserts `LLMService.chat` is called exactly once when the provider is down, and retrying a genuinely broken call adds latency for no benefit.
4. `generate_challenge()` and `score_8_dimensions()` both refactored to call the shared helper instead of duplicating fence-stripping + `json.loads()` inline. No change to either method's external return contract or error messages (verified: existing message-substring assertions like `"Failed to parse"` and `"Missing fields"` still hold, since the helper re-raises the *original* exception type/message on final failure).
5. Full existing test suite (64 tests) passes unchanged, including the exact-call-count assertion in AC 3.
6. Live verification: simulate a 2x-malformed-then-valid response sequence and confirm `generate_challenge()` recovers on the 3rd attempt without raising.

## Tasks / Subtasks

- [x] Rule out non-code explanations before touching anything (AC: none — investigation)
  - [x] Confirmed via `grep` that Story 8.2's fix is still present on disk
  - [x] Confirmed via direct `curl` against the live running server that it has the fix loaded and succeeds on that specific call
  - [x] Confirmed via a fresh Python process (bypassing the running server entirely) that the on-disk code succeeds across 8 varied parameter combinations
  - [x] Concluded: genuinely probabilistic residual failure rate, not a stale-process or reverted-fix issue

- [x] Add the shared retry helper (AC: 1, 2, 3)
  - [x] `EvaluationService._call_llm_for_json()` — loops up to `max_retries`, calling `LLMService.chat()` fresh each iteration
  - [x] Fence-stripping logic moved here from both call sites (previously duplicated)
  - [x] Only `json.JSONDecodeError` / `ValueError` (from `validate`) trigger a retry; any other exception from `LLMService.chat()` propagates immediately, uncaught by the retry loop

- [x] Wire both callers through the helper (AC: 4)
  - [x] `generate_challenge()`: required-field check extracted into a local `_validate_challenge_fields()` closure, passed as `validate=`
  - [x] `score_8_dimensions()`: no validate function needed (its own downstream code already backfills missing dimension keys), just parse-retry

- [x] Verify (AC: 5, 6)
  - [x] Full pytest suite: 64/64 passing unchanged, including `test_llm_failure_returns_500_and_persists_nothing`'s `len(chat_calls) == 1` assertion
  - [x] Simulated a `flaky_chat` mock returning malformed JSON on attempts 1-2 and valid JSON on attempt 3 — `generate_challenge()` recovered and returned the correct parsed dict, confirmed via `calls['n'] == 3`
  - [x] Additional live stress runs against the real API post-fix: 5/5 and 8/8 clean across varied parameter combinations

## Dev Notes

### Files Changed

| File | Action |
|------|--------|
| `app/services/evaluation_service.py` | UPDATE — new `_call_llm_for_json()` static method; `generate_challenge()` and `score_8_dimensions()` refactored to use it |

No changes to `llm_service.py` in this story — Story 8.2's `response_schema`/`thinking_config`/`response_mime_type` additions there are unchanged and still doing their job (reducing, not eliminating, the failure rate that this story's retry now absorbs).

### What NOT To Do

- Do NOT retry on exceptions from `LLMService.chat()` itself (network errors, auth errors, rate limits) — only on parse/validation failure of an otherwise-successful response. Conflating the two breaks `test_llm_failure_returns_500_and_persists_nothing`'s explicit single-call assertion and adds latency to a class of failure retrying won't fix.
- Do NOT attempt to "repair" malformed JSON (e.g. regex-patching an unterminated string) — a fresh generation is more reliable and much simpler than reconstructing intent from a broken payload.
- Do NOT assume 3 retries makes this failure mode literally impossible — it converts a per-call failure rate into that rate raised to the 3rd power (roughly), which is a large practical improvement but not a mathematical guarantee. If this recurs a third time, the next escalation should be investigating whether a specific prompt/parameter shape (e.g. very long `starter_code` requirements) correlates with the failure, not just adding more retries.

### References

- [Source: `_bmad-output/implementation-artifacts/8-2-fix-gemini-json-response-reliability.md` — the fix this story hardens further]
- [Source: `tests/test_generate_challenge_endpoint.py::test_llm_failure_returns_500_and_persists_nothing` — the constraint that shaped AC 3]
- [Source: `app/services/evaluation_service.py`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `curl` against the live running server (port 8000) — succeeded, ruling out stale-process theory.
- Fresh-process stress tests: 8/8 then 5/5 clean live calls post-retry-fix.
- Mocked `flaky_chat` simulation: 2 malformed responses then 1 valid — `generate_challenge()` recovered on attempt 3.
- Full pytest suite: 64/64 passing.

### Completion Notes List

- Ruled out "fix didn't deploy" before assuming the code itself was still broken — the live server had Story 8.2's fix and that specific call succeeded, confirming this is a genuinely probabilistic residual failure, not a regression.
- Added `_call_llm_for_json()` as a shared retry-capable JSON-call helper, consolidating previously-duplicated fence-stripping logic in `generate_challenge()` and `score_8_dimensions()`.
- Retry scope deliberately narrow: only JSON-parse/validation failures retry; genuine `LLMService.chat()` exceptions propagate on the first attempt, preserving an existing test's exact-call-count assertion.
- Cleaned up one more test challenge row created in the real `data/assignments.db` during live verification (via direct `curl`).

### File List

- `app/services/evaluation_service.py` (UPDATE)

## Change Log

- 2026-07-04: Story created after a user reported the identical Story 8.2 error a second time.
- 2026-07-04: Ruled out stale-process and reverted-fix explanations; confirmed the failure is a genuine residual probabilistic rate even with `response_schema` in place. Added retry-on-parse-failure logic scoped narrowly to JSON/validation errors (not API errors). Verified via mocked recovery test, live stress tests, and the full (unchanged) pytest suite.
