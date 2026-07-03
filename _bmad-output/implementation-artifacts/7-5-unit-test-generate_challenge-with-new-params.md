# Story 7.5: Unit test — `generate_challenge()` with new params

Status: done

## Story

As a platform maintainer,
I want tests for `POST /api/generate-challenge` covering enum validation and successful persistence,
so that invalid challenge parameters are rejected before an LLM call is ever made, and a valid generation is correctly saved to the catalog as an unpublished draft.

## Acceptance Criteria

1. **Missing required fields → 400** — no `problem_statement` → 400; no `difficulty` → 400. Neither reaches the LLM.
2. **Invalid `difficulty` → 400** — value outside `{easy, medium, hard}`.
3. **Invalid `challenge_type` → 400** — value outside `{bug_fix, feature_extension, refactoring, optimization}`.
4. **Invalid `skill_area` → 400** — value outside `{api_integration, rate_limiting, data_pipeline, llm_usage, server_monitoring, game_logic}`.
5. **Invalid `ai_assistance_mode` → 400** — value outside `{guarded, unguarded}`.
6. **Valid request → 200 + persisted as unpublished draft** — with `LLMService.chat` mocked, a fully valid request returns 200 with the generated challenge fields plus a `challenge_id`, and `db_service.get_challenge(challenge_id)` (queried directly against the isolated test DB) confirms the row exists with `is_published == 0`.
7. **LLM failure → 500** — `LLMService.chat` mocked to raise → `EvaluationService.generate_challenge()` re-raises → route's `except Exception` → 500, and nothing is persisted (no `create_challenge` call reached).
8. **Persist failure degrades gracefully → still 200** — `db_service.create_challenge` mocked to raise → generation already succeeded, so the route still returns 200 with the challenge JSON but `challenge_id: null` (per the route's own existing catch-and-continue behavior).
9. **Enum validation never calls the LLM** — for every 400 case (ACs 1-5), assert the mocked `LLMService.chat` was never invoked (validation happens before generation).
10. Full suite (`python -m pytest tests/ -v`) green from project root; the 51 pre-existing tests from Stories 7.1–7.4 unaffected.

## Tasks / Subtasks

- [x] Task 1: Test infrastructure in `tests/test_generate_challenge_endpoint.py` (AC: 6, 9)
  - [x] Reuse the exact DB-isolation `client`/`db` fixture pattern from Story 7.4 (`tests/test_candidates_endpoint.py`) — `monkeypatch.setattr(challenges_module.db_service, "db", test_db)`, `create_app("testing")`, `db(client)` depends on `client`
  - [x] Add `LLMService.chat` mocking on top (Story 7.1 pattern) — a spy variant that also records whether it was called, for AC 9
  - [x] `VALID_PAYLOAD` fixture/constant: a dict with valid `problem_statement`, `difficulty='medium'`, `challenge_type='bug_fix'`, `skill_area='api_integration'`, `ai_assistance_mode='unguarded'`
  - [x] `make_llm_response()` helper: builds the exact JSON shape `EvaluationService.generate_challenge()` expects (`title`, `description`, `evaluation_criteria`, `starter_code` — all 4 required keys)
- [x] Task 2: Required-field tests (AC: 1)
  - [x] Missing `problem_statement` → 400
  - [x] Missing `difficulty` → 400
- [x] Task 3: Enum validation tests (AC: 2, 3, 4, 5)
  - [x] Invalid `difficulty` → 400
  - [x] Invalid `challenge_type` → 400
  - [x] Invalid `skill_area` → 400
  - [x] Invalid `ai_assistance_mode` → 400
- [x] Task 4: Success + persistence test (AC: 6)
  - [x] Valid payload, mocked `LLMService.chat` returns a well-formed challenge JSON → 200, response has `challenge_id` (non-null), `is_published: false`
  - [x] Query `db_service.get_challenge(challenge_id)` directly → row exists, `is_published == 0` (index 10)
- [x] Task 5: Failure-path tests (AC: 7, 8)
  - [x] `LLMService.chat` raises → 500, `db_service.get_challenge` for any freshly-minted ID returns nothing new (nothing persisted)
  - [x] `db_service.create_challenge` raises (LLM succeeds) → 200, `challenge_id` is `null` in the response
- [x] Task 6: No-LLM-call-on-validation-failure tests (AC: 9)
  - [x] For at least the invalid-`difficulty` and missing-`problem_statement` cases, assert the mocked `chat` was never called
- [x] Task 7: Run and verify (AC: 10)
  - [x] `python -m pytest tests/ -v` green, 51 existing + new tests

### Review Findings

- [x] [Review][Patch] "Nothing persisted" assertion is vacuous — `list_challenges()` filters `WHERE is_published=1`, but drafts always insert `is_published=0`, so the before/after comparison can never fail regardless of whether persistence happened; replace with a `create_challenge` call-spy [tests/test_generate_challenge_endpoint.py]
- [x] [Review][Patch] LLM-failure test never asserts the LLM was actually called — add `len(calls) == 1` to distinguish "genuinely failed" from "never reached"
- [x] [Review][Patch] All 6 validation-failure (400) tests assert status code only, never which field/enum failed — add error-body assertions
- [x] [Review][Patch] Malformed-JSON vs missing-required-field 500 tests don't pin their distinct branches — add error-body assertions (`"Failed to parse"` vs `"Missing fields"`)
- [x] [Review][Patch] Success test never verifies request fields (problem_statement, difficulty, etc.) actually reach the LLM prompt — an endpoint ignoring all input would still pass
- [x] [Review][Patch] "Missing" field tests use empty strings, not truly-absent keys — add one test with an absent key to close the AC1 wording gap definitively
- [x] [Review][Patch] Non-string field values (e.g. `"difficulty": null`) untested — pins a real gap (see Defer below)
- [x] [Review][Patch] Unused `from app.config import Config` import — dead code from copying Story 7.4's fixture
- [x] [Review][Patch] Unused `**overrides` parameter on `make_llm_response` — no test ever supplies overrides
- [x] [Review][Patch] `row[10] == 0` magic column index — add a clarifying comment citing the schema (index already verified correct by two reviewers)
- [x] [Review][Defer] `POST /api/generate-challenge` returns 200 (success) even when persistence silently fails — the client has no way to distinguish a genuinely-saved challenge from one that was generated but lost [app/routes/challenges.py:100-103] — deferred, pre-existing, intentional graceful-degradation design from Story 3.4; worth reconsidering (e.g. a `persisted: bool` response field) but out of scope for a test story
- [x] [Review][Defer] Non-string/null field values crash with an unhandled 500 instead of a clean 400 — `data.get('difficulty', '').strip()` assumes the JSON value is always a string; `{"difficulty": null}` makes `.get()` return `None`, and `None.strip()` raises `AttributeError` before the route's own try/except begins [app/routes/challenges.py:52-56] — deferred, pre-existing, confirmed via code reading by two reviewers

Dismissed as noise (6): "patch-target may be a no-op" (refuted — the test can only pass with `challenge_id: None` if the mock genuinely intercepted the call; confirmed correct independently by Edge Case Hunter), "fixtures duplicated instead of shared via conftest.py" (established, explicit convention across Epic 7 — this is the sprint's final story, so there is no future consumer to justify extracting a shared fixture now), "`app.config['TESTING']=True` after `create_app('testing')` is redundant" (true, but matches Story 7.4's already-reviewed fixture verbatim — fixing only here would create drift between the two files), "201 vs 200 for resource creation" (existing production behavior, out of scope), "misleading fixture name `db`" (matches Story 7.4's already-reviewed precedent), "non-JSON body / wrong content-type untested" (Flask/Werkzeug framework-level behavior, not this app's logic — out of scope).

## Dev Notes

### Why this is a route-level integration test, not a pure unit test of `EvaluationService.generate_challenge()`

Read `app/services/evaluation_service.py:295-407` (`generate_challenge`) carefully: it has **no validation at all**. Unknown `challenge_type`/`skill_area` values just fall through `.get(key, default)` dicts (lines 336, 345) to generic prompt text — they never raise. **All enum validation and all 400 responses live in the Flask route** (`app/routes/challenges.py:47-113`, `POST /generate-challenge`), which validates against the module-level sets `VALID_DIFFICULTIES`, `VALID_CHALLENGE_TYPES`, `VALID_SKILL_AREAS`, `VALID_MODES` (lines 14-17) **before** calling `EvaluationService.generate_challenge()` at all. Persistence (`db_service.create_challenge(...)`, lines 87-103) is also route-level, wrapped in its own try/except that degrades to `challenge_id: None` on failure rather than failing the whole request. This story's real target is `POST /api/generate-challenge`, exercised through a Flask test client — same shape as Story 7.4, plus LLM mocking on top.

### Route anatomy — `POST /api/generate-challenge` (`app/routes/challenges.py:47-113`)

1. Read `problem_statement`, `difficulty` (required, `.strip()`ped) and `challenge_type`/`skill_area`/`ai_assistance_mode` (optional, default `feature_extension`/`api_integration`/`unguarded`) from JSON body
2. Empty `problem_statement` or `difficulty` → 400 (lines 59-62) — **before any enum check**
3. Enum checks in this exact order: `difficulty`, `challenge_type`, `skill_area`, `ai_assistance_mode` (lines 65-72) — each 400s independently, all **before** the LLM call
4. `EvaluationService.generate_challenge(...)` call wrapped in try/except → any exception → 500 with `{'error': str(e)}` (lines 74-83)
5. `IDGenerator.generate_uuid()` for `challenge_id`, then `db_service.create_challenge(...)` wrapped in its own try/except → on failure, `challenge_id = None` but the function **still returns 200** with the generated challenge content (lines 85-103) — generation succeeding is what matters to the caller, persistence is best-effort
6. Response is `{**challenge, challenge_id, challenge_type, skill_area, difficulty, ai_assistance_mode, is_published: False}`, always 200 once generation succeeds (lines 105-113)

### Required LLM response shape (`EvaluationService.generate_challenge`, lines 386-407)

`LLMService.chat(generation_prompt, max_tokens=3000)` response, after optional ` ```json ` fence stripping (lines 389-393, same pattern as Story 7.1 — only the exact `json`-tagged fence is stripped), is `json.loads`'d and must contain all of `title`, `description`, `evaluation_criteria`, `starter_code` (lines 397-400) or a `ValueError` is raised (caught and re-wrapped as a generic `Exception`, which the route's except-block turns into a 500). Any JSON parse failure or missing-field failure → 500 at the route level — this is AC 7's mechanism.

```python
def make_llm_response(**overrides):
    payload = {
        "title": "Fix the Rate Limiter", "description": "...",
        "evaluation_criteria": "...", "starter_code": "def f(): pass",
    }
    payload.update(overrides)
    return json.dumps(payload)
```

### DB isolation — reuse Story 7.4's pattern exactly, do not re-derive it

Story 7.4 (`tests/test_candidates_endpoint.py`, and its own Dev Notes) already discovered and solved the two-layer DB isolation trap in this codebase: (1) `app.routes.challenges.db_service` is an import-time singleton pointed at the real `data/assignments.db` unless monkeypatched directly, and (2) `create_app()` called with no config argument still touches the real DB via its own internal schema-init call — fixed there by calling `create_app("testing")`. **Copy that exact fixture shape** (`client`, `db(client)`) into this story's test file — do not use `create_app()` bare, do not skip the `db_service.db` monkeypatch, and do not add a shared `conftest.py` fixture (per-file duplication is this project's established convention across 7.1-7.4).

### Mocking the LLM — reuse Story 7.1's pattern, add a call-spy

```python
from app.services.llm_service import LLMService

def mock_chat(monkeypatch, payload_or_exc, raises=False):
    calls = []
    def fake(*args, **kwargs):
        calls.append(args)
        if raises:
            raise payload_or_exc
        return payload_or_exc
    monkeypatch.setattr(LLMService, "chat", fake)
    return calls
```

Story 7.1's lesson applies here too: `lambda *args, **kwargs: ...`, never a fixed-arity lambda — `generate_challenge` calls `LLMService.chat(generation_prompt, max_tokens=3000)`, same call shape as `score_8_dimensions`.

### Scope boundaries — do not creep

- **No production code changes.**
- Do not test `GET /api/challenges` (list/filter endpoint) — it shares the same `VALID_*` sets but is a different route, out of scope.
- Do not re-derive the DB-isolation fixture design from scratch — cite and copy Story 7.4's, don't rediscover the same trap.
- Do not test the market-aligned prompt content itself (type_instruction/skill_imports dicts) — that's prompt-engineering content, not a testable contract; Story 3.3 already covers that this content exists.
- If a genuine production gap is found (e.g., another instance of the fence-stripping issue already logged from 7.1, since `generate_challenge` uses the identical stripping code shape at lines 389-393), do not duplicate the deferred-work.md entry — note in Dev Agent Record that it's the same known issue, already tracked from Story 7.1's review.

### Project Structure Notes

- New file: `tests/test_generate_challenge_endpoint.py` only

### References

- [Source: _bmad-output/planning-artifacts/epics-and-stories.md#Epic 7 — story 7.5 line 330]
- [Source: app/routes/challenges.py lines 1-24, 47-113 — route, validation sets]
- [Source: app/services/evaluation_service.py lines 295-407 — generate_challenge(), no internal validation, required response fields, fence-stripping]
- [Source: _bmad-output/implementation-artifacts/7-4-integration-test-get-api-challenges-id-candidates.md — DB isolation fixture pattern, mandatory to reuse]
- [Source: _bmad-output/implementation-artifacts/7-1-unit-test-score_8_dimensions.md — LLM mock pattern, shape-robust lambda lesson]

## Dev Agent Record

### Agent Model Used

claude-fable-5

### Debug Log References

- `python -m pytest tests/test_generate_challenge_endpoint.py -v` — 11 passed in 1.95s, first run green
- `python -m pytest tests/ -v` — 62 passed in 4.24s (11 new + 51 from Stories 7.1-7.4), zero regressions
- Real DB isolation reconfirmed: `data/assignments.db` mtime/size (`1783022402` / `249856`) identical before and after, via raw filesystem stat outside pytest — same proof pattern as Story 7.4

### Completion Notes List

- 11 tests in `tests/test_generate_challenge_endpoint.py` covering all 10 ACs: missing `problem_statement`/`difficulty` (400, LLM never called), all 4 enum validations (400, LLM never called), valid request (200, persisted with `is_published=0`, verified via direct `db.get_challenge()` query), LLM raising (500, nothing persisted — verified via `db.list_challenges()` snapshot before/after), malformed LLM JSON (500), LLM response missing a required field (500), and persist failure degrading gracefully (200, `challenge_id: null`)
- Confirmed during story creation that validation and persistence both live entirely in the Flask route (`app/routes/challenges.py`), not in `EvaluationService.generate_challenge()` — so this is a route-level integration test combining Story 7.1's LLM-mock pattern with Story 7.4's DB-isolation fixtures, reused verbatim (`create_app("testing")`, `db_service.db` monkeypatch, `db(client)` dependency) rather than re-derived
- `test_malformed_llm_json_returns_500` uses unfenced garbage text, so it does not interact with the already-known fence-stripping gap from Story 7.1's review (that gap only affects bare/prose-wrapped fences, not plain non-JSON text) — no new deferred-work.md entry needed, this is expected behavior
- No production code touched
- Code review 2026-07-03 (Blind Hunter + Edge Case Hunter + Acceptance Auditor): all three layers independently converged on the same headline finding — `test_llm_failure_returns_500_and_persists_nothing`'s "nothing persisted" check was vacuous, since `list_challenges()` filters to published-only and drafts always insert unpublished, so the before/after comparison could never fail regardless of whether persistence happened. Fixed with a `create_challenge` call-spy instead. Edge Case Hunter also surfaced a genuine, previously-unknown production gap during review: non-string field values (e.g. `{"difficulty": null}`) crash `.strip()` with an unhandled `AttributeError` rather than a clean 400, since the route's try/except only wraps the LLM call, not field extraction — confirmed empirically (the exception genuinely propagates through Flask's test client under `TESTING=True`) and pinned with a dedicated test plus a deferred-work.md entry. 10 patches total applied (error-body assertions on all 6 validation tests and both malformed-response 500 tests; a prompt-content assertion proving request fields reach the LLM; an absent-key variant of the "missing field" test; an LLM-was-actually-called assertion on the failure test; dead-code cleanup). 2 pre-existing production gaps deferred (the null-value crash above, plus a product-design observation that persist failures return 200 with no visible signal of data loss). 6 findings dismissed, several because they matched Story 7.4's already-reviewed precedent and fixing only here would create drift. Suite now 13 tests in this file (64 total across all of Epic 7), all green in 3.01s; real DB file's mtime/size reconfirmed byte-identical one final time.
- **This is the last story in the entire sprint** — Epic 7 (and therefore the whole `sprint-status.yaml`) is now complete.

### File List

- `tests/test_generate_challenge_endpoint.py` (new)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — 2 entries appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status tracking)
- `_bmad-output/implementation-artifacts/7-5-unit-test-generate_challenge-with-new-params.md` (this file)
