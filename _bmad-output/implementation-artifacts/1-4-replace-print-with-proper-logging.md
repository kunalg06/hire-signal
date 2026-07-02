# Story 1.4: Replace print() with proper logging

Status: done

## Story

As a platform operator,
I want all diagnostic output routed through Python's `logging` module,
so that errors and warnings appear in Flask log output (stderr) and can be filtered by level, rather than mixed with stdout.

## Acceptance Criteria

1. Every `print()` call in `app/` and `run.py` is replaced with an appropriate `logging` call at the correct level.
2. `run.py` calls `logging.basicConfig()` before `create_app()` so the root logger is configured for the process lifetime.
3. Each module defines its own logger via `logger = logging.getLogger(__name__)` — no shared global logger.
4. No `logging.basicConfig()` or `logging.setLevel()` calls inside `app/` (route or service files) — configuration is only in `run.py`.
5. Log levels match intent: `DEBUG` for verbose step-by-step ops, `INFO` for operational milestones, `WARNING` for recoverable problems, `ERROR` for caught exceptions and failures.
6. No non-ASCII characters in any log message string (Windows cp1252 console constraint).
7. All existing behaviour is preserved — only the output mechanism changes.

## Tasks / Subtasks

- [x] Configure root logger in `run.py` (AC: 2, 5)
  - [x] Add `import logging` and `logger = logging.getLogger(__name__)`
  - [x] Call `logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')` before `create_app()`
  - [x] Replace 4 `print()` banner calls with `logger.info()` equivalents; drop the `"=" * 60` separator lines (they are formatting noise, meaningless in structured log output)

- [x] Replace print() in `app/routes/links.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 33 `print(f"Max retries...")` → `logger.warning(...)`
  - [x] Line 40 `print(f"Container started successfully...")` → `logger.info(...)`
  - [x] Line 58 `print(f"Container creation error: {e}")` → `logger.error(...)`

- [x] Replace print() in `app/routes/challenges.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 100 `print(f"Warning: could not persist challenge...")` → `logger.warning(...)`

- [x] Replace print() in `app/routes/submissions.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Lines 85-89 `print(f"Evaluation complete for {submission_id}...")` → `logger.info(...)`
  - [x] Line 92 `print(f"Error evaluating submission {submission_id}: {e}")` → `logger.error(...)`
  - [x] Line 140 `print(f"Reading files from container {container_id[:12]}...")` → `logger.info(...)`
  - [x] Lines 146, 152, 166 `print(f"  [ok] ...")` → `logger.debug(...)`
  - [x] Line 172 `print("  [warn] solution.py not found in workspace")` → `logger.warning(...)`
  - [x] Line 207 `print(f"  [ok] Stored {len(session_logs)}...")` → `logger.debug(...)`
  - [x] Line 209 `print(f"Warning: Failed to parse/store session logs: {e}")` → `logger.warning(...)`
  - [x] Line 215 `print(f"  [ok] workspace snapshot: {len(file_snapshot)} files")` → `logger.debug(...)`

- [x] Replace print() in `app/services/docker_service.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 55 `print(f"Container started: ...")` → `logger.info(...)`
  - [x] Lines 61, 63 `print(f"Error creating container: ...")` → `logger.error(...)`
  - [x] Line 85 `print(f"  Could not read {file_path}...")` → `logger.debug(...)`
  - [x] Line 98 `print(f"Warning: get_archive failed...")` → `logger.warning(...)`
  - [x] Lines 150, 160, 169 `print(f"  Injected ..."` / `"  Permissions set..."` → `logger.debug(...)`
  - [x] Line 172 `print(f"Warning: workspace injection failed...")` → `logger.warning(...)`
  - [x] Line 182 `print(f"Cleaned up container {container_id[:12]}")` → `logger.info(...)`
  - [x] Line 184 `print(f"Error cleaning up container {container_id}: {e}")` → `logger.error(...)`

- [x] Replace print() in `app/services/evaluation_service.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 76 `print(f"Warning: workspace extraction failed...")` → `logger.warning(...)`
  - [x] Line 203 `print(f"8-dimension scoring error: {e}")` → `logger.error(...)`

- [x] Replace print() in `app/services/management_service.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 21 `print(f"Error: Could not connect to Docker: {e}")` → `logger.error(...)`

- [x] Replace print() in `app/services/session_log_service.py` (AC: 1, 5)
  - [x] Add `import logging` + `logger = logging.getLogger(__name__)` at module level
  - [x] Line 113 `print(f"Error calculating efficiency score: {e}")` → `logger.error(...)`

- [x] Verify: zero remaining print() calls in app/ and run.py (AC: 1)
  - [x] `grep -rn "\bprint(" app/ run.py --include="*.py"` returns zero matches (confirmed)

## Dev Notes

### The Pattern — Apply Identically Across All 8 Files

Every file gets the same treatment at the top of its imports section:

```python
import logging
logger = logging.getLogger(__name__)
```

Then every `print(...)` becomes `logger.<level>(...)` with the message unchanged (same f-string, same arguments). Do NOT rewrite or reword the messages — this is a mechanical substitution, not a prose edit.

### Level Mapping Table — Follow Exactly

| Print message starts with / contains | `logging` level |
|--------------------------------------|-----------------|
| `"Error..."` / `"Error: ..."` / exception in except block | `logger.error(...)` |
| `"Warning: ..."` / `"[warn]"` | `logger.warning(...)` |
| `"[ok] ..."` / `"Injected ..."` / `"Permissions set..."` | `logger.debug(...)` |
| `"Container started"` / `"Cleaned up container"` / `"Evaluation complete"` / `"Reading files from container"` | `logger.info(...)` |

### run.py — Startup Banner Conversion

Current `run.py` has a 4-line print() banner:
```python
print("=" * 60)
print("AI Engineering Assessment & Evaluation Platform")
print("=" * 60)
print(f"Environment: {env}")
print(f"Starting Flask server on http://{host}:{port}")
```

Convert to:
```python
import logging
logger = logging.getLogger(__name__)

# (before create_app())
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s'
)

# (in __main__ block, replacing the 5 print() lines)
logger.info("AI Engineering Assessment & Evaluation Platform")
logger.info("Environment: %s | Server: http://%s:%s", env, host, port)
```

Drop both `"=" * 60` separator lines — separators have no meaning when each log line already has a timestamp prefix.

### What Must NOT Change

- No changes to `templates/frontend.html`, `app/__init__.py` (no print() calls there)
- No changes to message logic, route behaviour, error handling, or return values
- Do not add `logging.basicConfig()` inside any `app/` file — configuration is `run.py`-only
- Do not change the text of existing messages (keep same f-strings)
- `app/routes/analytics.py` has zero print() calls — do not touch it (double-check first with grep)

### Windows cp1252 Constraint — Architecture Rule

The existing print() messages are already ASCII-only (`[ok]`, `[warn]`, etc.). Do not introduce any non-ASCII characters (no arrows `→`, no bullets `•`, no ellipsis `…`) in log strings. The format string in `logging.basicConfig` must also be ASCII-only — the suggested format above already is.

### No Functional Risk

This story has zero functional risk: no DB schema changes, no API changes, no Docker changes. The only observable difference is that diagnostic text appears on stderr (via the `logging` module's default `StreamHandler`) instead of stdout. Flask's development server already captures and displays both streams.

### Architecture Reference

- Architecture constraint: "No non-ASCII in print() on Windows" [Source: AGENT.md#Architecture Constraints]
- Python logging stdlib: `getLogger(__name__)` is the canonical per-module pattern
- Flask logging guidance: Flask recommends modules use `getLogger(__name__)` and the app entry point configure `basicConfig()` — do NOT call `app.logger` from service files

### Verification After Completion

Run this grep to confirm zero remaining print() calls:
```
grep -rn "print(" app/ run.py --include="*.py"
```
Expected: zero matches (Blueprint definition lines like `challenges_bp = Blueprint(...)` have `print` in the identifier but not as a `print(` call — grep pattern is `print(` so false positives won't appear).

### File Count Summary

| File | print() count | Module logger name |
|------|---------------|--------------------|
| `run.py` | 5 | `__main__` |
| `app/routes/links.py` | 3 | `app.routes.links` |
| `app/routes/challenges.py` | 1 | `app.routes.challenges` |
| `app/routes/submissions.py` | 9 | `app.routes.submissions` |
| `app/services/docker_service.py` | 11 | `app.services.docker_service` |
| `app/services/evaluation_service.py` | 2 | `app.services.evaluation_service` |
| `app/services/management_service.py` | 1 | `app.services.management_service` |
| `app/services/session_log_service.py` | 1 | `app.services.session_log_service` |
| **Total** | **33** | |

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `grep -rn "\bprint(" app/ run.py` → zero matches after all substitutions (word-boundary grep distinguishes real `print()` calls from `Blueprint(` false positives)
- `python -c "from app import create_app; app = create_app()"` → imports cleanly; pre-existing SyntaxWarning in `docker_service.py:152` (backtick in template string) is unrelated to this story
- TDD note: mechanical substitution story; no business logic to test-drive. Verification is the grep zero-match check + import smoke test.

### Completion Notes List

- Replaced 33 `print()` calls across 8 files with `logger.<level>()` equivalents
- `run.py`: added `logging.basicConfig()` as root config; dropped `"=" * 60` separator lines (noise in structured log output); banner condensed to 2 `logger.info()` calls
- All 8 files use `logger = logging.getLogger(__name__)` at module level — no shared global logger
- No `logging.basicConfig()` inside any `app/` file — configuration is `run.py`-only (AC: 4 satisfied)
- All log message strings are ASCII-only (AC: 6 satisfied; Windows cp1252 safe)
- Level mapping: ERROR for caught exceptions, WARNING for recoverable failures, INFO for operational milestones, DEBUG for per-step verbose ops

### Review Findings

- [x] [Review][Patch] Redundant severity prefix in logger.warning/error calls — strip "Warning: ", "[warn]", and "Error: " text prefixes from log message strings where the level label already supplies this information [multiple files, 6 call sites]
- [x] [Review][Defer] Dead `_run()` call in `get_file_from_container` — first `_run(['cp', ...])` call at line 76 of `docker_service.py` uses `text=True` causing `UnicodeDecodeError` on binary content; working `subprocess.run()` at line 79 is unreachable — deferred, pre-existing bug predating Story 1.4
- [x] [Review][Defer] `flask run` entry point produces no INFO logging — `basicConfig()` is only in `run.py`; direct `flask run` invocations leave root logger at WARNING level, silently dropping all `logger.info()`/`logger.debug()` calls — deferred, design limitation within AC constraints
- [x] [Review][Defer] Background thread `evaluate_submission_files` does not catch `BaseException` — submission stays permanently pending on MemoryError or C-extension exception — deferred, pre-existing
- [x] [Review][Defer] `hire_row[1]` bounds check missing in `override_submission` — Epic 4 pre-existing code, not in Story 1.4 scope
- [x] [Review][Defer] `float(val)` unguarded in `sort_key` in `get_challenge_candidates` — Epic 4 pre-existing code
- [x] [Review][Defer] `sum(scores)` has no float coercion in `dim_averages` block — Epic 4 pre-existing code
- [x] [Review][Defer] N+1 `get_dimension_scores` queries in `get_challenge_candidates` — Epic 4 pre-existing, already in deferred-work.md

### File List

- run.py
- app/routes/links.py
- app/routes/challenges.py
- app/routes/submissions.py
- app/services/docker_service.py
- app/services/evaluation_service.py
- app/services/management_service.py
- app/services/session_log_service.py
