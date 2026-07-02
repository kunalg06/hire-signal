# Deferred Work

## Deferred from: code review of Epic 4 stories 4.1–4.5 (2026-07-02)

- **N+1 DB queries in candidates endpoint** (`app/routes/challenges.py:215`): One `get_dimension_scores()` query per candidate, unbounded. For large cohorts (100+ candidates) this will be slow. Fix: batch-load all dimension scores in one `WHERE submission_id IN (...)` query before building the candidates list. Deferred because Story 4.2 spec accepted this pattern and no pagination AC exists.

- **Flagged candidates unfiltered in candidates ranking** (`app/services/database_service.py` — `get_candidates_for_challenge` query): Flagged submissions appear in the ranked candidate list with no `is_flagged` indicator in the payload. Recruiters cannot distinguish flagged-for-review candidates from clean ones. Future story: add `s.is_flagged` to `get_candidates_for_challenge` SELECT and expose in candidate object.

- **Re-flagging overwrites prior flag metadata** (`app/routes/submissions.py:361`, `app/services/database_service.py`): Second `POST /submissions/<id>/flag` call overwrites `flag_by`, `flag_reason`, `flagged_at` with no history. Unlike overrides (which have `score_overrides` append-only log), flags have no audit trail. Future story: add `flag_events` append-only table; or add `WHERE is_flagged = 0` guard to prevent overwrite.

- **`flagged_by` is caller-supplied with no authentication** (`app/routes/submissions.py:360`): Any caller can claim any identity in `flagged_by`. Deferred — system has no auth by design (CLAUDE.md). Becomes a real issue when auth is added.

- **Concurrent overrides double-count in analytics** (`app/routes/submissions.py:371–410`): Two simultaneous POST requests to `/submissions/<id>/override` both pass the existence check and both insert into `score_overrides`, double-counting one override event. Deferred — single-tenant dev-phase system; no concurrency requirement exists.

## Deferred from: code review of story 1-4-replace-print-with-proper-logging (2026-07-02)

- **Dead `_run()` call in `get_file_from_container`** (`app/services/docker_service.py:73`): First `_run(['cp', container_id:path, '-'])` at line 73 uses `text=True` which causes `UnicodeDecodeError` on binary tar content; the working binary-mode `subprocess.run()` at line 79 is unreachable for plain files. For ASCII Python files the extra call is merely wasteful; for non-UTF-8 content the method silently returns `None`. Fix: remove the dead `_run()` call at line 73–74; the binary-mode call at line 75–79 is the one that actually works.

- **`flask run` entry point produces no INFO-level logging** (`run.py`): `logging.basicConfig()` is only configured in `run.py`. If a developer starts the server with `flask run` (which calls `create_app()` directly), the root logger defaults to WARNING level and all `logger.info()` / `logger.debug()` calls (evaluation completion, container start, file reads) are silently dropped. Fix: add a guard-style `logging.basicConfig()` call in `create_app()` — e.g., `if not logging.root.handlers: logging.basicConfig(...)` — without violating AC4's spirit of not having unconditional logging config inside `app/`.

- **Background evaluation thread does not catch `BaseException`** (`app/routes/submissions.py:17`, `evaluate_submission_files`): The outer `except Exception as e:` block does not catch `BaseException` subclasses (e.g., `MemoryError`, signal delivery). If such an exception escapes the LLM call, the thread dies silently, `update_submission_evaluation()` is never called, and the submission row stays permanently pending (NULL score/feedback) with no log entry. Deferred — very rare failure mode; no timeout/watchdog story exists yet.
