# Story 7.1: Unit test — `score_8_dimensions()`

Status: done

## Story

As a platform maintainer,
I want unit tests for `EvaluationService.score_8_dimensions()` with the LLM fully mocked,
so that the core scoring engine's guarantees (all 8 dimension keys, Python-enforced weighted average, safe failure defaults) are locked in and regressions are caught before merge.

## Acceptance Criteria

1. **Mock Claude** — no test makes a real LLM/network call. `LLMService.chat` is monkeypatched in every test; `OPENROUTER_API_KEY` is never required.
2. **All 8 keys guaranteed** — given a mocked response missing one or more dimensions, the result's `dimensions` dict still contains all 8 keys (`problem_decomposition`, `first_principles_thinking`, `creative_problem_solving`, `iteration_quality`, `debugging_with_ai`, `architecture_decisions`, `communication_clarity`, `token_efficiency`), with missing ones defaulted to `{"score": 0, "rationale": "dimension missing from response"}`.
3. **Python-weighted average used** — given distinct per-dimension scores, `composite_score` equals the hand-computed weighted sum using `DIMENSION_WEIGHTS` (rounded to 2 dp), NOT any composite the mocked Claude response claims.
4. **Claude's recommendation ignored** — a mocked response that embeds `"composite_score": 99` and `"hire_recommendation": "strong_hire"` at the top level is overridden: the returned values are recomputed by Python from the dimension scores.
5. **Failure safety** — when `LLMService.chat` raises, or returns non-JSON garbage, the result is the safe default: all 8 dimensions `score=0`, `composite_score == 0.0`, `hire_recommendation == "pass"`.
6. **Markdown fence stripping** — a mocked response wrapped in ` ```json ... ``` ` fences parses successfully.
7. `pytest` runs green from the project root with no env vars set.

## Tasks / Subtasks

- [x] Task 1: Bootstrap test infrastructure (AC: 7)
  - [x] Create `tests/` directory (no `__init__.py` needed)
  - [x] Create `conftest.py` at **project root** (can be empty) — its presence makes pytest insert the project root into `sys.path` so `from app.services.evaluation_service import EvaluationService` resolves
- [x] Task 2: Shared fixtures/helpers in `tests/test_score_8_dimensions.py` (AC: 1)
  - [x] Helper `make_response(scores: dict, **top_level)` → JSON string in the exact shape `score_8_dimensions` expects (`{"dimensions": {dim: {"score": n, "rationale": ""}}, ...}`)
  - [x] Helper/fixture `mock_chat(monkeypatch, payload_or_exc)` — patches `LLMService.chat` via `monkeypatch.setattr(LLMService, "chat", lambda prompt, max_tokens=2000: payload)`
  - [x] Minimal `assignment` dict fixture: `{"title": "T", "description": "D", "evaluation_criteria": "C"}`
- [x] Task 3: Happy-path tests (AC: 2, 3)
  - [x] All scores 80 → `composite_score == 80.0`, all 8 keys present
  - [x] Distinct scores (see Dev Notes worked example) → `composite_score == 58.0` — proves per-dimension weights are applied, not a plain mean (plain mean of the example is 55.0)
- [x] Task 4: Guarantee tests (AC: 2, 4)
  - [x] Response missing 3 dimensions → all 8 keys present, missing ones score 0, composite computed over the defaulted dict
  - [x] Response with top-level `"composite_score": 99, "hire_recommendation": "strong_hire"` but dims summing to 58.0 → returned `composite_score == 58.0`, `hire_recommendation == "select"`
- [x] Task 5: Failure-path tests (AC: 5, 6)
  - [x] `LLMService.chat` raises `RuntimeError` → default result (`0.0` / `"pass"`, all 8 dims score 0, rationale starts with `"Scoring error:"`)
  - [x] Returns `"I am not JSON"` → default result
  - [x] Returns valid payload wrapped in ` ```json\n...\n``` ` → parses, composite correct
- [x] Task 6: Run and verify (AC: 7)
  - [x] `python -m pytest tests/ -v` green from project root with `OPENROUTER_API_KEY` unset

### Review Findings

- [x] [Review][Patch] Tautological dimension set — expected 8 dims derived from code under test; pin literal 8-name set [tests/test_score_8_dimensions.py:13]
- [x] [Review][Patch] Mock signature fragile — replace `lambda prompt, max_tokens=2000` with `*args, **kwargs` shape-robust form [tests/test_score_8_dimensions.py:45]
- [x] [Review][Patch] Prompt content never verified and non-empty logs/snapshot branch unexercised — add prompt-capture test with populated inputs [tests/test_score_8_dimensions.py:48]
- [x] [Review][Patch] Clamp branches and strong_hire recommendation never exercised — add >100 and <0 score tests [app/services/evaluation_service.py:221]
- [x] [Review][Patch] `dimensions` key entirely absent (full 8-dim backfill branch) untested [app/services/evaluation_service.py:210]
- [x] [Review][Patch] No hermeticity guard — add autouse fixture deleting `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` (also addresses `.env` `override=True` caveat) [tests/test_score_8_dimensions.py]
- [x] [Review][Patch] conftest.py relies on pytest default prepend import mode side effect — make `sys.path` insert explicit [conftest.py:1]
- [x] [Review][Patch] Rationale preservation never asserted on success path (per-dim rationale + `recommendation_rationale`) [tests/test_score_8_dimensions.py:66]
- [x] [Review][Defer] Bare ``` fence or prose-wrapped JSON silently zero-scores a candidate — fence stripping only handles exact ```json prefix [app/services/evaluation_service.py:200-201] — deferred, pre-existing
- [x] [Review][Defer] Prompt-building runs outside try/except — malformed `assignment`/`session_logs`/`file_snapshot` crash instead of safe default [app/services/evaluation_service.py:92-183] — deferred, pre-existing
- [x] [Review][Defer] Malformed-JSON result shapes unhandled: non-dict top level, non-dict `dimensions`, dim entry missing `"score"` [app/services/evaluation_service.py:210-220] — deferred, pre-existing (sibling of logged non-numeric-score gap)
- [x] [Review][Defer] Tests transitively import all `app.routes.*` modules via `app/__init__.py` blueprint imports — isolation intent unachievable without production changes [app/__init__.py:14-19] — deferred, pre-existing

Dismissed as noise (4): magic composite numbers (intentional — weights are product spec constants; deriving expected values from `DIMENSION_WEIGHTS` would be tautological), exact float equality (safe — code rounds to 2 dp), threshold boundaries untested (Story 7.3 scope, already tracked), `OPENROUTER_API_KEY=''` vs unset evidence nit (behaviorally identical).

## Dev Notes

### Code under test — exact anatomy

`app/services/evaluation_service.py` — `EvaluationService.score_8_dimensions(session_logs: list, file_snapshot: dict, assignment: dict) -> dict` (staticmethod, lines 82–236):

1. Formats logs/files into a prompt (irrelevant to these tests — pass `[]` and `{}`)
2. Calls `LLMService.chat(scoring_prompt, max_tokens=2000)` ← **the ONLY mock seam**
3. Strips markdown fences **only when response starts with ` ``` `** via `split("```json")[-1].split("```")[0]` — a fence without the `json` tag yields `""` → JSONDecodeError → default result (this is current behavior; test the ` ```json ` path only)
4. `json.loads`; ANY exception in steps 2–4 → `_default_result(...)`: all dims `{"score": 0, "rationale": reason}`, `composite_score: 0.0`, `hire_recommendation: "pass"`
5. Backfills missing dimension keys with `{"score": 0, "rationale": "dimension missing from response"}`
6. Computes `composite = sum(dims[d]["score"] * w)` over `DIMENSION_WEIGHTS`, clamps to [0, 100], applies `HIRE_THRESHOLDS` (`strong_hire>=85, hire>=70, select>=55, else pass`), then **overwrites** `result["composite_score"]` (as `round(composite, 2)`) and `result["hire_recommendation"]` — this overwrite is what AC 4 verifies

`DIMENSION_WEIGHTS` (sums to 1.0): problem_decomposition .15, first_principles_thinking .15, creative_problem_solving .10, iteration_quality .15, debugging_with_ai .15, architecture_decisions .10, communication_clarity .10, token_efficiency .10.

### Worked example for the weighted-average assertion (AC 3)

| dimension | score | weight | contribution |
|---|---|---|---|
| problem_decomposition | 90 | .15 | 13.5 |
| first_principles_thinking | 80 | .15 | 12.0 |
| creative_problem_solving | 70 | .10 | 7.0 |
| iteration_quality | 60 | .15 | 9.0 |
| debugging_with_ai | 50 | .15 | 7.5 |
| architecture_decisions | 40 | .10 | 4.0 |
| communication_clarity | 30 | .10 | 3.0 |
| token_efficiency | 20 | .10 | 2.0 |
| **composite** | | | **58.0 → `select`** |

Plain unweighted mean is 55.0, so this fixture distinguishes weighted from unweighted. Assert `== 58.0` exactly — contributions are exact in binary-adjacent decimal arithmetic and the code rounds to 2 dp; if flakiness appears use `pytest.approx(58.0, abs=1e-9)`.

### Mocking — do it exactly this way

```python
from app.services.llm_service import LLMService

monkeypatch.setattr(LLMService, "chat", lambda prompt, max_tokens=2000: payload)
```

`evaluation_service.py` holds a reference to the same `LLMService` class object, so patching the class attribute is visible there. Replacing the classmethod with a plain function is fine: class-attribute access returns the function and the call site passes `(prompt, max_tokens=...)`. For the raise case: `monkeypatch.setattr(LLMService, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))` or use a small named function.

Do NOT patch `openai.OpenAI` or hit `LLMService.get_client()` — `chat` is the seam; anything deeper couples tests to the OpenRouter client construction (which requires `OPENROUTER_API_KEY` and would fail in CI).

### Import-time safety (verified)

`evaluation_service.py` imports `app.config` (env reads with defaults only), `llm_service` (no client construction at import — lazy in `get_client()`), and `session_log_service` (pure staticmethods). Importing `EvaluationService` in a bare test process is safe with zero env vars. `DockerService` is imported lazily inside `extract_container_files()` only — irrelevant here since tests call `score_8_dimensions` directly.

### Scope boundaries — do not creep

- **Threshold boundary matrix (>=85 / >=70 / >=55 / <55) is Story 7.3** — here, only assert the recommendations that fall out of the two composite fixtures used (80.0 → `hire`, 58.0 → `select`, 0.0 → `pass`). Do not write a dedicated threshold-sweep test.
- **`extract_container_files()` is Story 7.2** — do not test it here.
- **Known gap, out of scope:** a syntactically valid JSON response with a non-numeric `"score"` (e.g. `"score": "high"`) raises an uncaught `TypeError` at the composite `sum()` — it is OUTSIDE the try/except. Do not "fix" `score_8_dimensions` in this story; if you confirm it, append a line to `_bmad-output/implementation-artifacts/deferred-work.md` instead.
- No production code changes. This story adds `tests/` + root `conftest.py` only.

### Project constraints that apply

- pytest is already pinned: `pytest==7.4.3` in `requirements.txt` — no new dependencies, no plugins (`pytest-mock` NOT installed; use built-in `monkeypatch`)
- **ASCII only in any `print()`/log output** (Windows cp1252 console) — applies to test code too
- Raw SQL/SQLite project; irrelevant here (no DB touched), but do not import route modules (`app/routes/*`) in tests — they instantiate `DatabaseService()` at module import
- Naming: `tests/test_score_8_dimensions.py`, test functions `test_<behavior>` snake_case

### Project Structure Notes

- New: `tests/test_score_8_dimensions.py`, `conftest.py` (project root, may be empty)
- Follow-on stories 7.2–7.5 will add sibling `tests/test_*.py` files — keep per-story test modules, shared fixtures can move to `tests/conftest.py` later if 7.2+ needs them

### References

- [Source: _bmad-output/planning-artifacts/epics-and-stories.md#Epic 7 — story 7.1 line 326]
- [Source: app/services/evaluation_service.py#score_8_dimensions lines 82–236, DIMENSION_WEIGHTS lines 16–25, HIRE_THRESHOLDS lines 27–31]
- [Source: app/services/llm_service.py#chat lines 27–36 — mock seam]
- [Source: AGENT.md#Architecture Constraints — ASCII-only prints, thresholds Python-enforced]

## Dev Agent Record

### Agent Model Used

claude-fable-5

### Debug Log References

- `python -m pytest tests/ -v` — 7 passed in 2.06s (Python 3.14.5, pytest 9.0.3)
- Rerun with `OPENROUTER_API_KEY=''` and `OPENROUTER_MODEL=''` — 7 passed in 0.77s, proving zero real LLM calls (AC 1, 7)

### Completion Notes List

- 7 tests in `tests/test_score_8_dimensions.py` covering all 7 ACs: happy path (all 80s → 80.0/hire), weighted-vs-plain-mean proof (58.0, not 55.0), 3-missing-dims backfill (49.0/pass with exact backfill rationale), Claude-supplied composite/recommendation overridden (99/strong_hire in payload → 58.0/select returned), chat raises → safe default, non-JSON → safe default, ```json fence stripping
- Mock seam exactly as specified: `monkeypatch.setattr(LLMService, "chat", ...)` — no `openai` patching, no plugins, built-in `monkeypatch` only
- Environment note: installed pytest is 9.0.3, not the 7.4.3 pinned in requirements.txt — tests use no version-sensitive features (plain asserts, `monkeypatch`, one fixture) and pass on 9.x; they will pass on 7.4.3 as well
- Known gap from Dev Notes confirmed by inspection (non-numeric `"score"` in valid JSON → uncaught `TypeError` outside the try/except) — NOT fixed per story scope; logged to `deferred-work.md` under "Deferred from: story 7-1" as instructed
- No production code touched; scope boundaries respected (no threshold sweep — Story 7.3; no `extract_container_files` — Story 7.2)
- Code review 2026-07-03 (Blind Hunter + Edge Case Hunter + Acceptance Auditor): 8 patches applied (literal 8-dim pin, shape-robust mocks, prompt-content test with populated logs/snapshot, clamp tests covering strong_hire, dimensions-key-absent backfill test, autouse env-hermeticity fixture, explicit sys.path in conftest, rationale-preservation asserts), 4 pre-existing production gaps deferred to deferred-work.md, 4 dismissed. Suite now 12 tests, all green in 0.86s.

### File List

- `tests/test_score_8_dimensions.py` (new)
- `conftest.py` (new, project root — sys.path bootstrap)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — 1 entry appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status tracking)
- `_bmad-output/implementation-artifacts/7-1-unit-test-score_8_dimensions.md` (this file)
