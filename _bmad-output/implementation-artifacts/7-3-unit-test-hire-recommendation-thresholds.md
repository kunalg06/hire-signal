# Story 7.3: Unit test — hire recommendation thresholds

Status: done

## Story

As a platform maintainer,
I want unit tests that pin the exact boundary values of the hire-recommendation threshold logic,
so that a regression at any threshold (`>=85`, `>=70`, `>=55`, `<55`) is caught even though Story 7.1 only exercised interior composite values, not the boundaries themselves.

## Acceptance Criteria

1. **`strong_hire` boundary** — composite `== 85.0` exactly → `hire_recommendation == "strong_hire"`; composite `== 84.0` (just under) → `"hire"`.
2. **`hire` boundary** — composite `== 70.0` exactly → `"hire"`; composite `== 69.0` (just under) → `"select"`.
3. **`select` boundary** — composite `== 55.0` exactly → `"select"`; composite `== 54.0` (just under) → `"pass"`.
4. **`pass` — everything below `select`** — a composite well below 55 (e.g. `0.0`) → `"pass"` (sanity check that the `else` branch is reachable, not just the adjacent-to-55 case from AC3).
5. Thresholds are asserted against **literal numbers** (`85`, `70`, `55`), never against `EvaluationService.HIRE_THRESHOLDS` — asserting against the dict under test would make the test tautological (a regression that changes both the code and the dict would still pass).
6. Full suite (`python -m pytest tests/ -v`) green from project root; the 28 pre-existing tests from Stories 7.1–7.2 unaffected.

## Tasks / Subtasks

- [x] Task 1: Test helpers in `tests/test_hire_recommendation_thresholds.py` (AC: 5)
  - [x] `mock_chat(monkeypatch, payload)` — same shape-robust pattern as Story 7.1 (`lambda *args, **kwargs: payload`)
  - [x] `make_uniform_response(score)` — build a Claude-shaped JSON payload where **all 8 dimensions get the same score**, so `composite == score` exactly (weights sum to 1.0) with no hand-computed weighted arithmetic needed
  - [x] `assignment` fixture: minimal dict `{"title": "T", "description": "D", "evaluation_criteria": "C"}`
- [x] Task 2: `strong_hire` boundary tests (AC: 1)
  - [x] All dims = 85 → `composite_score == 85.0`, `hire_recommendation == "strong_hire"`
  - [x] All dims = 84 → `composite_score == 84.0`, `hire_recommendation == "hire"`
- [x] Task 3: `hire` boundary tests (AC: 2)
  - [x] All dims = 70 → `composite_score == 70.0`, `hire_recommendation == "hire"`
  - [x] All dims = 69 → `composite_score == 69.0`, `hire_recommendation == "select"`
- [x] Task 4: `select` boundary tests (AC: 3)
  - [x] All dims = 55 → `composite_score == 55.0`, `hire_recommendation == "select"`
  - [x] All dims = 54 → `composite_score == 54.0`, `hire_recommendation == "pass"`
- [x] Task 5: `pass` sanity test (AC: 4)
  - [x] All dims = 0 → `composite_score == 0.0`, `hire_recommendation == "pass"`
- [x] Task 6: Run and verify (AC: 6)
  - [x] `python -m pytest tests/ -v` green, 34 total tests (28 existing + 6 new minimum)

### Review Findings

- [x] [Review][Patch] Non-uniform weighted composite landing exactly on a boundary untested — uniform-score trick alone doesn't prove the real weighted-sum path classifies correctly at a threshold [tests/test_hire_recommendation_thresholds.py]
- [x] [Review][Patch] `round(composite, 2)` fractional behavior never pinned; also demonstrates the stored composite_score/recommendation inconsistency — add a documenting test [tests/test_hire_recommendation_thresholds.py]
- [x] [Review][Patch] File lacks the autouse LLM-env hermeticity fixture its sibling (`test_score_8_dimensions.py`) has — a future test added here without an explicit mock would hit `.env`-loaded `OPENROUTER_API_KEY` [tests/test_hire_recommendation_thresholds.py]
- [x] [Review][Defer] `hire_recommendation` branches on the pre-round composite while `composite_score` stores the post-round value — near a boundary (e.g. composite 84.996) the displayed score (85.0) can contradict the recommendation ("hire") [app/services/evaluation_service.py:224-233] — deferred, pre-existing; confirmed empirically (raw 84.996 → False for `>=85`, `round(84.996,2)==85.0`)

Dismissed as noise (8): "float-exactness assumption is High risk" (overstated — empirically refuted: a real non-uniform combo landed exactly on 85.0/strong_hire, and the uniform trick self-detects float dust via a loud assert failure, per Edge Case Hunter), "no assertion chat was invoked"/"mock swallows arguments" (out of scope — already proven by Story 7.1's `test_prompt_includes_assignment_logs_and_files`), "ALL_DIMS derived from code under test is tautological" (already guarded by Story 7.1's `test_weights_define_exactly_the_eight_spec_dimensions`), "network call not enforced beyond class-level patch" (speculative — no alternate LLM call path found with source access), "boundaries probed only at integers" (superseded by the two Patch findings above), "two assertions conflate composite/recommendation" and "suggest parametrize" (style, inconsistent with established per-test convention), "no upper-range/malformed probe" and "recommendation_rationale dead payload" (redundant with Story 7.1 coverage / cosmetic).

## Dev Notes

### Why this story exists despite Story 7.1 already touching recommendations

Story 7.1's tests (`tests/test_score_8_dimensions.py`) produced recommendations as a side effect of testing other guarantees (all-8-keys, weighted-average, override-ignored): composite 80.0→`hire`, 58.0→`select`, 49.0/0.0→`pass`, and (from its review patches) 100.0→`strong_hire`/0.0→`pass` via clamp tests. **None of these sit at or adjacent to an actual threshold value** (85/70/55) — an off-by-one bug (`>` instead of `>=`, or `85` typo'd to `86`) at any boundary would pass every existing test undetected. This story's entire job is closing that gap with boundary-precision tests, per the epics spec (`epics-and-stories.md` line 328: "all 4 boundary conditions").

### Code under test — exact anatomy (same function as 7.1, different focus)

There is **no standalone threshold function** — the logic is inline inside `EvaluationService.score_8_dimensions()` (`app/services/evaluation_service.py` lines 216–234), immediately after the composite is computed and clamped:

```python
composite = sum(dims[d]["score"] * w for d, w in EvaluationService.DIMENSION_WEIGHTS.items())
composite = min(100.0, max(0.0, composite))

thresholds = EvaluationService.HIRE_THRESHOLDS   # {"strong_hire": 85, "hire": 70, "select": 55}
if composite >= thresholds["strong_hire"]:
    recommendation = "strong_hire"
elif composite >= thresholds["hire"]:
    recommendation = "hire"
elif composite >= thresholds["select"]:
    recommendation = "select"
else:
    recommendation = "pass"

result["composite_score"] = round(composite, 2)
result["hire_recommendation"] = recommendation
```

All four comparisons are `>=` (inclusive lower bound) except the implicit `else` for `pass`. Tests must invoke `score_8_dimensions()` end-to-end (same as 7.1) — mock `LLMService.chat`, there is nothing smaller to unit-test in isolation.

### The uniform-score trick — why it gives exact boundary values with no arithmetic

`DIMENSION_WEIGHTS` sums to exactly 1.0 (verified in 7.1's `test_weights_define_exactly_the_eight_spec_dimensions`). If **every** dimension is scored identically to `X`, then `composite = sum(X * w for w in weights) = X * sum(weights) = X * 1.0 = X` — modulo negligible floating-point noise from summing eight `0.1`/`0.15`-ish products, which `round(composite, 2)` cleans up. This means `make_uniform_response(85)` yields `composite_score == 85.0` exactly, without hand-verifying a weighted sum (contrast with 7.1's `DISTINCT_SCORES` fixture, which intentionally used varied scores to *prove* weighting — a different goal from this story's boundary-precision goal).

### Story 7.1/7.2 learnings to carry forward

- Shape-robust mocks: `lambda *args, **kwargs: payload`, never `lambda prompt, max_tokens=2000: payload`
- Pin expected values as literals, not derived from the code under test (AC5 makes this explicit for thresholds specifically — do not write `assert rec == EvaluationService.HIRE_THRESHOLDS[...]`-style tautologies)
- Test infra already exists: root `conftest.py` handles `sys.path`; add only `tests/test_hire_recommendation_thresholds.py`
- No hermeticity fixture needed here by itself, but do NOT rely on ambient env vars — every test must mock `chat` so no real network call is possible regardless of environment

### Scope boundaries — do not creep

- **No production code changes.** If a real off-by-one is found, that would be a genuine bug — but the current code has been read line-by-line above and the boundaries are correctly `>=`. If a test unexpectedly fails, treat it as a real finding, not a fixture error, and stop to report rather than "fixing" the test to match broken behavior.
- Do not re-test all-8-keys-present, weighted-average-vs-mean, override-ignored, or failure-safety paths — those are Story 7.1's job, already done.
- Do not test `extract_container_files` — Story 7.2, already done.
- `generate_challenge` enum validation is Story 7.5; `GET /api/challenges/<id>/candidates` integration test is Story 7.4 — out of scope here.

### Project Structure Notes

- New file: `tests/test_hire_recommendation_thresholds.py` only
- Same conventions as 7.1/7.2: module-level helpers, `test_<behavior>` names, built-in `monkeypatch` only, no `pytest-mock`

### References

- [Source: _bmad-output/planning-artifacts/epics-and-stories.md#Epic 7 — story 7.3 line 328]
- [Source: app/services/evaluation_service.py#score_8_dimensions lines 216–234 — threshold logic, HIRE_THRESHOLDS lines 27–31]
- [Source: AGENT.md#Architecture Constraints — "Score thresholds: Python-enforced — strong_hire>=85, hire>=70, select>=55, pass<55. Never rely on Claude's threshold logic."]
- [Source: _bmad-output/implementation-artifacts/7-1-unit-test-score_8_dimensions.md — mock pattern, weights-sum-to-1.0 proof, review learnings]

## Dev Agent Record

### Agent Model Used

claude-fable-5

### Debug Log References

- `python -m pytest tests/ -v` — 36 passed in 0.96s (8 new + 28 from Stories 7.1–7.2), first run green, no boundary bug found (all comparisons confirmed correctly `>=`)

### Completion Notes List

- 8 tests in `tests/test_hire_recommendation_thresholds.py` covering all 6 ACs: strong_hire boundary (85 exact / 84 just-under), hire boundary (70 exact / 69 just-under), select boundary (55 exact / 54 just-under), pass sanity (0), and an anti-tautology guard asserting `HIRE_THRESHOLDS` still equals the literal spec dict
- Used the uniform-score trick (`make_uniform_response`) — scoring all 8 dimensions identically makes `composite == score` exactly since `DIMENSION_WEIGHTS` sums to 1.0, avoiding hand-computed weighted arithmetic entirely
- Left a dead helper (`run`) in the file mid-implementation from an earlier draft — removed before running; final file has no unused code
- No production code touched; the threshold logic was read line-by-line during story creation and confirmed correct before writing tests (all four branches use `>=`, matching the spec)
- Code review 2026-07-03 (Blind Hunter + Edge Case Hunter + Acceptance Auditor): Acceptance Auditor verdict "Acceptable" — all 6 ACs satisfied, AC5's anti-tautology guard verified assertion-by-assertion. 3 patches applied (non-uniform 85.0 boundary via real per-dimension weights — empirically verified with a standalone script before writing the assertion; a documenting test for a genuine stored-value inconsistency; autouse hermeticity fixture), 1 pre-existing production gap deferred (recommendation branches on pre-round composite, `composite_score` stores post-round — the two can visibly disagree near a boundary, e.g. raw 84.996 → "hire" but displayed 85.0), 8 dismissed (including Blind Hunter's "High" float-exactness claim, empirically refuted). Suite now 10 tests in this file (38 total with 7.1–7.2), all green in 1.04s.

### File List

- `tests/test_hire_recommendation_thresholds.py` (new)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — 1 entry appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status tracking)
- `_bmad-output/implementation-artifacts/7-3-unit-test-hire-recommendation-thresholds.md` (this file)
