# Story 9.3: Surface Guarded-Mode Injection Failures

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer who configured a challenge to run in guarded mode,
I want to know if the guarded-mode restriction actually took effect for a given candidate's session,
so that I never unknowingly trust a "guarded" assessment result that actually ran fully unguarded because the `GEMINI.md` injection silently failed.

## Acceptance Criteria

1. `DockerService.inject_workspace_files()` returns `{'injected': bool, 'guarded_mode_enforced': bool}` instead of implicitly returning `None` — callers can now detect the outcome instead of it being silently swallowed by the method's internal try/except blocks.
2. `guarded_mode_enforced` is `True` when `ai_assistance_mode != 'guarded'` (nothing to enforce, trivially fine) OR when `ai_assistance_mode == 'guarded'` AND the `GEMINI.md` write succeeded. It is `False` only when guarded mode was requested but the `GEMINI.md` write failed.
3. `session_links` gains two nullable columns (`ai_assistance_mode TEXT`, `guarded_mode_enforced INTEGER DEFAULT 1`) via `ALTER TABLE`, created idempotently, following the exact `try/except sqlite3.OperationalError` pattern already used for the flag columns.
4. `POST /api/generate-link/<assignment_id>` persists both the resolved `ai_assistance_mode` and the ACTUAL `guarded_mode_enforced` result from `inject_workspace_files()` (not an assumed success) onto the new `session_links` row.
5. `GET /api/submission/<id_or_link>` includes `ai_assistance_mode` and `guarded_mode_enforced` in its JSON response, sourced from the submission's `session_links` row via its `link_id`.
6. When `guarded_mode_enforced` is `False`, this is visible in the submission record returned to the employer — an assessment that was supposed to be guarded but silently wasn't is no longer invisible.
7. Existing behavior is unchanged when injection succeeds or the mode is unguarded — `guarded_mode_enforced` defaults to `1`/`True`, `ai_assistance_mode` reflects whatever was actually resolved at link-generation time (unchanged resolution logic from Story 6.5 / the `ai_assistance_mode` whitelist work).
8. No frontend dashboard UI change in this story — the fix is making the data available on the API response (matching the deferred-work.md finding's literal wording: "surface... on the teacher dashboard / submission record"). A future story can add a visual badge if a real need emerges; keep this story's diff to schema + 2 methods + 1 route field addition, matching Stories 9.1/9.2's scope discipline.

## Tasks / Subtasks

- [x] Change `DockerService.inject_workspace_files()` to return a result dict instead of `None` (AC: 1, 2)
  - [x] Track `guarded_mode_enforced` starting at `ai_assistance_mode != 'guarded'` (trivially True when not guarded)
  - [x] Set it to `True` inside the existing inner `try` block right after the `GEMINI.md` `_run(['cp', ...])` call succeeds; set it to `False` inside the existing inner `except Exception as e:` block (the logging line already there stays unchanged)
  - [x] Return `{'injected': True, 'guarded_mode_enforced': guarded_mode_enforced}` at the end of the outer `try` block
  - [x] Return `{'injected': False, 'guarded_mode_enforced': guarded_mode_enforced}` in the outer `except Exception as e:` block (the existing logging line stays unchanged)
- [x] Add the `session_links` schema migration in `app/models/database.py` (AC: 3)
  - [x] Two `ALTER TABLE session_links ADD COLUMN ...` statements, each in its own `try/except sqlite3.OperationalError: pass` block, placed directly after the existing flag-columns migration block
- [x] Update `DatabaseService.create_session_link()` to accept and store the two new fields (AC: 4)
  - [x] Add `ai_assistance_mode=None, guarded_mode_enforced=None` as optional kwargs (backward compatible — nothing else calls this method today, but keep the pattern used elsewhere in this file of optional kwargs for additive fields)
- [x] Update `generate_link()` in `app/routes/links.py` to capture and persist the real injection result (AC: 4)
  - [x] Initialize a default result dict before the port-retry loop, in case no container is ever created
  - [x] Capture `inject_workspace_files()`'s return value inside the loop
  - [x] Pass `ai_assistance_mode=ai_assistance_mode, guarded_mode_enforced=injection_result['guarded_mode_enforced']` into `create_session_link()`
- [x] Add `DatabaseService.get_session_link_assistance_info(link_id)` (AC: 5)
  - [x] One `SELECT ai_assistance_mode, guarded_mode_enforced FROM session_links WHERE link_id = ?`, returning `(None, None)` if no row
- [x] Update `GET /api/submission/<id_or_link>` in `app/routes/submissions.py` to include the two new fields (AC: 5, 6)
  - [x] Call `get_session_link_assistance_info(row[1])` (row[1] is link_id in both the direct-lookup and link_id-fallback code paths)
  - [x] Add `"ai_assistance_mode"` and `"guarded_mode_enforced"` to the response JSON
- [x] Add tests covering: guarded-mode success returns `guarded_mode_enforced=True`; guarded-mode `GEMINI.md` write failure (mocked) returns `guarded_mode_enforced=False`; unguarded mode returns `guarded_mode_enforced=True` trivially; the new fields appear correctly in `GET /api/submission/<id_or_link>`'s response for both outcomes (AC: 1, 2, 5, 6, 7)
- [x] Run the full test suite and confirm no regressions

### Review Findings

- [x] [Review][Patch] Migration `ALTER TABLE session_links ADD COLUMN guarded_mode_enforced INTEGER DEFAULT 1` backfilled every pre-existing row with `1`, contradicting `get_session_link_assistance_info()`'s own docstring contract of `(None, None)` for legacy rows (confirmed by both Blind Hunter and Edge Case Hunter review layers; note AC3's literal wording also specified `DEFAULT 1`, which was itself the source of the contradiction with AC5/6's intent). Fixed by dropping the `DEFAULT 1` clause; regression test added in `tests/test_session_links_migration_legacy_rows.py` [app/models/database.py:213]
- [x] [Review][Patch] `docs/API_REFERENCE.md`'s `GET /api/submission/<id_or_link>` example response was missing the two new fields. [docs/API_REFERENCE.md:166]
- [x] [Review][Defer] `inject_workspace_files()`'s `injected` flag (distinguishes total injection failure from a guarded-mode-only `GEMINI.md` failure) is computed but never persisted or surfaced through the API — a total failure (no instructions.md written at all) currently leaves no audit trail. Out of this story's guarded-mode-specific scope. [app/services/docker_service.py:183] — deferred, pre-existing scope boundary
- [x] [Review][Defer] `/api/challenges/<id>/candidates` doesn't expose `guarded_mode_enforced`, so an employer must open each submission individually to spot an enforcement failure rather than seeing it in the batch/ranked view. [app/routes/challenges.py] — deferred, pre-existing scope boundary

## Dev Notes

### Why this exists

Flagged during the code review of Story 6.5 (2026-07-03): "Guarded-mode injection failure is silent... If the `GEMINI.md` write itself fails (transient Docker/disk issue), the function logs a debug-level warning and link generation proceeds normally. No employer or candidate is told the assessment silently ran unguarded." Re-scoped into Epic 9 during the 2026-07-04 party-mode triage as its own story (9-3), separate from the guarded-mode-is-honor-system-bypassable finding (that one is a settled, accepted v1 decision — do NOT re-open it; this story is purely about VISIBILITY when the injection mechanism itself fails, a distinct, narrower problem).

### Current code — `inject_workspace_files()` (read this before touching anything)

`app/services/docker_service.py`, lines 106–221 (full current method):

```python
    @staticmethod
    def inject_workspace_files(container_id: str, title: str, description: str,
                               criteria: str, starter_code: str,
                               ai_assistance_mode: str = Config.DEFAULT_ASSISTANCE_MODE):
        """
        Write instructions.md and solution.py into /workspace immediately
        after container creation. Story 6.1 three-panel format used for
        instructions.md so the candidate sees a structured brief inside VS Code.

        Story 6.5: when ai_assistance_mode == 'guarded', also writes a
        GEMINI.md into /workspace. ...
        """
        import time
        import tempfile

        time.sleep(2)

        instructions = f"""..."""
        guarded_gemini_md = """..."""

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # instructions.md
                md_path = os.path.join(tmpdir, 'instructions.md')
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(instructions)
                _run(['cp', md_path, f'{container_id}:/workspace/instructions.md'])
                logger.debug("  Injected instructions.md into %s", container_id[:12])

                # solution.py
                code = (starter_code or '').strip()
                if not code:
                    code = f'# {title}\n# Implement your solution here\n'
                py_path = os.path.join(tmpdir, 'solution.py')
                with open(py_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                _run(['cp', py_path, f'{container_id}:/workspace/solution.py'])
                logger.debug("  Injected solution.py into %s", container_id[:12])

                chmod_paths = ['/workspace/instructions.md', '/workspace/solution.py']

                if ai_assistance_mode == 'guarded':
                    try:
                        gemini_md_path = os.path.join(tmpdir, 'GEMINI.md')
                        with open(gemini_md_path, 'w', encoding='utf-8') as f:
                            f.write(guarded_gemini_md)
                        _run(['cp', gemini_md_path, f'{container_id}:/workspace/GEMINI.md'])
                        chmod_paths.append('/workspace/GEMINI.md')
                        logger.debug("  Injected guarded-mode GEMINI.md into %s", container_id[:12])
                    except Exception as e:
                        logger.warning("guarded-mode GEMINI.md injection failed for %s: %s", container_id[:12], e)

                _run([
                    'exec', '-u', 'root', container_id,
                    'chmod', '666',
                    *chmod_paths,
                ], check=False)
                logger.debug("  Permissions set on workspace files in %s", container_id[:12])

        except Exception as e:
            logger.warning("workspace injection failed for %s: %s", container_id[:12], e)
```

Note it currently returns nothing (implicit `None`) on every path — that's the entire bug. This story does NOT change the try/except structure, the chmod logic, the instructions/GEMINI.md content, or any error-handling behavior — it ONLY adds a tracked boolean and two `return` statements.

### Exact change to `inject_workspace_files()`

```python
    @staticmethod
    def inject_workspace_files(container_id: str, title: str, description: str,
                               criteria: str, starter_code: str,
                               ai_assistance_mode: str = Config.DEFAULT_ASSISTANCE_MODE) -> dict:
        """
        ... (existing docstring unchanged, plus:)

        Returns {'injected': bool, 'guarded_mode_enforced': bool} (Story 9.3):
        'injected' is False only if instructions.md/solution.py could not be
        written at all (rare/fatal container issue). 'guarded_mode_enforced'
        is True when ai_assistance_mode != 'guarded' (nothing to enforce) or
        the GEMINI.md write succeeded; False when guarded mode was requested
        but the write failed — meaning the assessment may be running
        unguarded without anyone being told.
        """
        import time
        import tempfile

        time.sleep(2)

        instructions = f"""..."""  # unchanged
        guarded_gemini_md = """..."""  # unchanged

        guarded_mode_enforced = (ai_assistance_mode != 'guarded')

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # instructions.md — unchanged
                ...
                # solution.py — unchanged
                ...
                chmod_paths = ['/workspace/instructions.md', '/workspace/solution.py']

                if ai_assistance_mode == 'guarded':
                    try:
                        gemini_md_path = os.path.join(tmpdir, 'GEMINI.md')
                        with open(gemini_md_path, 'w', encoding='utf-8') as f:
                            f.write(guarded_gemini_md)
                        _run(['cp', gemini_md_path, f'{container_id}:/workspace/GEMINI.md'])
                        chmod_paths.append('/workspace/GEMINI.md')
                        logger.debug("  Injected guarded-mode GEMINI.md into %s", container_id[:12])
                        guarded_mode_enforced = True
                    except Exception as e:
                        logger.warning("guarded-mode GEMINI.md injection failed for %s: %s", container_id[:12], e)
                        guarded_mode_enforced = False

                _run([
                    'exec', '-u', 'root', container_id,
                    'chmod', '666',
                    *chmod_paths,
                ], check=False)
                logger.debug("  Permissions set on workspace files in %s", container_id[:12])

            return {'injected': True, 'guarded_mode_enforced': guarded_mode_enforced}

        except Exception as e:
            logger.warning("workspace injection failed for %s: %s", container_id[:12], e)
            return {'injected': False, 'guarded_mode_enforced': guarded_mode_enforced}
```

### Schema migration — exact code

`app/models/database.py`, directly after the existing flag-columns migration block (currently the last migration block in `init_db()`):

```python
        # Schema migration: surface guarded-mode injection outcome on
        # session_links (Story 9.3)
        for _col_sql in [
            'ALTER TABLE session_links ADD COLUMN ai_assistance_mode TEXT',
            'ALTER TABLE session_links ADD COLUMN guarded_mode_enforced INTEGER DEFAULT 1',
        ]:
            try:
                with self.get_connection() as conn:
                    conn.execute(_col_sql)
                    conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
```

### `create_session_link()` — exact change

Current (`app/services/database_service.py` lines 37–45):

```python
    def create_session_link(self, link_id, assignment_id, container_id, port, expires_at):
        """Create a new session link"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO session_links (link_id, assignment_id, container_id, port, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (link_id, assignment_id, container_id, port, expires_at))
            conn.commit()
```

New:

```python
    def create_session_link(self, link_id, assignment_id, container_id, port, expires_at,
                            ai_assistance_mode=None, guarded_mode_enforced=None):
        """Create a new session link"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO session_links
                    (link_id, assignment_id, container_id, port, expires_at,
                     ai_assistance_mode, guarded_mode_enforced)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (link_id, assignment_id, container_id, port, expires_at,
                  ai_assistance_mode, guarded_mode_enforced))
            conn.commit()
```

`guarded_mode_enforced` is a Python `bool` — sqlite3 binds `bool` as `0`/`1` automatically (it's an `int` subclass), no manual conversion needed.

### New method — `get_session_link_assistance_info()`

Add near `get_link_container_info()`/`get_link_created_time()` in `app/services/database_service.py`:

```python
    def get_session_link_assistance_info(self, link_id):
        """Return (ai_assistance_mode, guarded_mode_enforced) for a session
        link (Story 9.3). Returns (None, None) if the link doesn't exist or
        predates this column (both nullable, no backfill for old links)."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT ai_assistance_mode, guarded_mode_enforced FROM session_links WHERE link_id = ?',
                (link_id,))
            row = cursor.fetchone()
            return row if row else (None, None)
```

### Route changes — exact diff shape

`app/routes/links.py`'s `generate_link()` — current relevant excerpt:

```python
    container_id = None
    port = None
    max_retries = 100
    retry_count = 0

    for port_attempt in range(Config.DOCKER_PORT_RANGE_START, Config.DOCKER_PORT_RANGE_START + max_retries):
        ...
        try:
            container_id, port = DockerService.create_container(assignment_id, port_attempt)
            if container_id:
                logger.info(...)
                DockerService.inject_workspace_files(
                    container_id=container_id, title=title, description=description,
                    criteria=evaluation_criteria or '', starter_code=starter_code or '',
                    ai_assistance_mode=ai_assistance_mode,
                )
                break
            retry_count += 1
        except Exception as e:
            ...

    expires_at = DateTimeHelper.get_future_timestamp(hours=24)
    db_service.create_session_link(link_id, assignment_id, container_id, port, expires_at)
```

New:

```python
    container_id = None
    port = None
    max_retries = 100
    retry_count = 0
    # Default when no container is ever created — nothing was injected, and
    # guarded_mode_enforced stays True only because there's nothing to
    # contradict (no container means no assessment can start at all; this
    # is not the "silently ran unguarded" case this story is about).
    injection_result = {'injected': False, 'guarded_mode_enforced': True}

    for port_attempt in range(Config.DOCKER_PORT_RANGE_START, Config.DOCKER_PORT_RANGE_START + max_retries):
        ...
        try:
            container_id, port = DockerService.create_container(assignment_id, port_attempt)
            if container_id:
                logger.info(...)
                injection_result = DockerService.inject_workspace_files(
                    container_id=container_id, title=title, description=description,
                    criteria=evaluation_criteria or '', starter_code=starter_code or '',
                    ai_assistance_mode=ai_assistance_mode,
                )
                break
            retry_count += 1
        except Exception as e:
            ...

    expires_at = DateTimeHelper.get_future_timestamp(hours=24)
    db_service.create_session_link(
        link_id, assignment_id, container_id, port, expires_at,
        ai_assistance_mode=ai_assistance_mode,
        guarded_mode_enforced=injection_result['guarded_mode_enforced'],
    )
```

`app/routes/submissions.py`'s `get_submission()` — add right before the final `return jsonify(...)`:

```python
    ai_mode, guarded_enforced = db_service.get_session_link_assistance_info(row[1])

    return jsonify({
        # ... all existing fields unchanged ...
        "ai_assistance_mode":    ai_mode,
        "guarded_mode_enforced": bool(guarded_enforced) if guarded_enforced is not None else None,
        # ... rest of existing fields unchanged ...
    })
```

`row[1]` is `link_id` in BOTH code paths of `get_submission()` (the direct `db_service.get_submission(submission_id)` lookup and the link_id-fallback raw-SQL query) — confirmed both SELECT lists put `link_id` at index 1.

### Testing

No existing test file covers `app/routes/links.py`'s `generate_link()` in this session except `tests/test_generate_link_ai_assistance_mode.py` (added earlier this session for the whitelist fix) — extend that file rather than creating a new one, since it already has the exact fixture pattern needed (`DockerService.create_container`/`inject_workspace_files` monkeypatched, no real Docker daemon required).

Add to `tests/test_generate_link_ai_assistance_mode.py`:

```python
def test_guarded_mode_enforced_true_persisted_on_success(client, db):
    c, captured = client
    # Existing fixture mocks inject_workspace_files to just capture kwargs and
    # return nothing — override it here to return a realistic success result.
    monkeypatch_target = links_module.DockerService  # already imported at module level
    ...
```

Actually — the existing `client` fixture in that file monkeypatches `DockerService.inject_workspace_files` with a bare `capture_inject` function that returns `None` implicitly. Since this story changes the CALLER (`links.py`) to read `injection_result['guarded_mode_enforced']` from the return value, the existing fixture's mock MUST be updated to return a realistic dict, or every existing test in that file will crash with `TypeError: 'NoneType' object is not subscriptable`. Update the fixture itself:

```python
@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db = Database(str(tmp_path / "test.db"))
    test_db.init_db()
    monkeypatch.setattr(links_module.db_service, "db", test_db)
    monkeypatch.setattr(DockerService, "create_container",
                        lambda *a, **k: ("fake-container-id", 7100))

    captured = {}
    def capture_inject(*args, **kwargs):
        captured["ai_assistance_mode"] = kwargs.get("ai_assistance_mode")
        return {"injected": True, "guarded_mode_enforced": True}
    monkeypatch.setattr(DockerService, "inject_workspace_files", capture_inject)
    ...
```

Then add new tests to that same file (or a new file if preferred — either is fine, this list assumes extending the existing one):

```python
def test_guarded_mode_enforcement_failure_persisted_when_injection_fails(client, db, monkeypatch):
    c, captured = client
    monkeypatch.setattr(DockerService, "inject_workspace_files",
                        lambda *a, **k: {"injected": True, "guarded_mode_enforced": False})
    assignment_id, _ = make_assignment_with_challenge(db, "guarded")
    resp = c.post(f"/api/generate-link/{assignment_id}")
    assert resp.status_code == 201

    ai_mode, enforced = db.get_session_link_assistance_info(...)  # need the link_id from the response
    assert ai_mode == "guarded"
    assert enforced == 0  # stored as 0/False


def test_submission_response_includes_guarded_mode_enforcement_status(client_for_submissions, ...):
    # New test in a submissions-focused test file (or extend
    # tests/test_submissions_flag_override_field_coercion.py's fixture) —
    # create a session_link with guarded_mode_enforced=0 directly via
    # db.create_session_link(..., ai_assistance_mode="guarded", guarded_mode_enforced=False),
    # create a submission against that link, then GET /api/submission/<id>
    # and assert body["guarded_mode_enforced"] is False and
    # body["ai_assistance_mode"] == "guarded".
```

Also add a direct unit test for `DockerService.inject_workspace_files()`'s return value shape (no existing test file covers this method at all) — mock `_run` (the module-level subprocess helper) to simulate the `GEMINI.md` `_run(['cp', ...])` call raising, and assert the returned dict has `guarded_mode_enforced=False` while `injected=True` (the base files still got copied — only the inner try/except failed).

Then run the full suite (`python -m pytest tests/ -q`) and confirm no regressions — pay special attention to `tests/test_generate_link_ai_assistance_mode.py`'s EXISTING tests, since the fixture change (return value shape) could break them if not updated correctly.

### What NOT to do

- Do NOT touch the guarded-mode-is-honor-system-bypassable finding — that's settled, accepted v1 scope from Story 6.5's review, unrelated to this story.
- Do NOT add a frontend dashboard badge/UI element in this story (see AC 8) — keep the diff to schema + DB methods + one route field addition on both the write side (`links.py`) and read side (`submissions.py`).
- Do NOT change `inject_workspace_files()`'s actual injection behavior, retry logic, or chmod handling — only add the tracked boolean and `return` statements.

### Project Structure Notes

- Schema migration goes in `app/models/database.py`'s existing migration-block section (after the flag-columns block), NOT the main `CREATE TABLE` block — `session_links` already exists, this is new columns on an existing table.
- New DB method goes in `app/services/database_service.py` near the other `session_links`-related methods (`get_link_container_info`, `get_link_created_time`).
- No new files except test additions. No frontend changes.

### References

- Original finding: code review of Story 6.5, 2026-07-03 (`_bmad-output/implementation-artifacts/deferred-work.md`, "Deferred from: code review of 6-5-guarded-mode-claude-restrictions" section, "Guarded-mode injection failure is silent" entry)
- Epic scope: `_bmad-output/implementation-artifacts/sprint-status.yaml` → `epic-9` → `9-3-surface-guarded-mode-injection-failures`
- Current method to modify: `app/services/docker_service.py` lines 106–221 (`inject_workspace_files`)
- Current route to modify (write side): `app/routes/links.py` (`generate_link`, full file, ~94 lines)
- Current route to modify (read side): `app/routes/submissions.py` (`get_submission`, lines 250–335)
- Sibling story for testing-pattern/fixture reference: `9-1-batch-dimension-score-queries-in-candidates-endpoint.md` and `9-2-flag-lifecycle-audit-trail.md` (same red-first discipline, same `client`/`db` fixture style)
- Existing test file to extend for the write-side tests: `tests/test_generate_link_ai_assistance_mode.py` (added this session for the whitelist fix — has the exact `DockerService` mocking pattern needed, but its fixture MUST be updated per the Testing section above)

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Red-first: wrote `tests/test_inject_workspace_files.py` (4 tests, no prior coverage existed for this method at all) before touching
  `inject_workspace_files()`. All 4 failed with `AssertionError: assert None == {...}` as expected — the method returned nothing.
- Implemented exactly per Dev Notes: tracked `guarded_mode_enforced` starting at `ai_assistance_mode != 'guarded'`, flipped to
  `True`/`False` at the existing inner try/except's success/failure points, added two `return` statements. No change to the
  injection logic, chmod handling, or file content.
- Updating `links.py`'s route to subscript the return value immediately broke the existing
  `tests/test_generate_link_ai_assistance_mode.py` fixture (its mock returned `None` implicitly) — fixed the fixture to return a
  realistic `{"injected": True, "guarded_mode_enforced": True}`, exactly as anticipated in this story's own Testing section.
- Full suite: 115/115 passed (104 before this story + 4 inject_workspace_files unit tests + 3 write-side persistence tests + 4
  read-side visibility tests), zero regressions.

### Completion Notes List

- `DockerService.inject_workspace_files()` now returns `{'injected': bool, 'guarded_mode_enforced': bool}` instead of implicitly
  returning `None` on every path.
- `session_links` gained two nullable columns (`ai_assistance_mode TEXT`, `guarded_mode_enforced INTEGER DEFAULT 1`) via the
  standard `try/except sqlite3.OperationalError` migration pattern.
- `DatabaseService.create_session_link()` accepts optional `ai_assistance_mode`/`guarded_mode_enforced` kwargs; `generate_link()`
  in `links.py` now captures the REAL result from `inject_workspace_files()` (previously discarded) and persists it, with a safe
  default (`{'injected': False, 'guarded_mode_enforced': True}`) for the no-container-ever-created case.
- New `DatabaseService.get_session_link_assistance_info(link_id)` — one SELECT, `(None, None)` for missing/pre-migration links.
- `GET /api/submission/<id_or_link>` now includes `ai_assistance_mode` and `guarded_mode_enforced` in its response, sourced via
  the submission's `link_id`.
- No frontend change (per AC8, deliberately out of scope — matches Stories 9.1/9.2's scope discipline).
- All 8 acceptance criteria verified: AC1/AC2 (4 new unit tests on `inject_workspace_files()` itself, covering guarded-success,
  guarded-GEMINI.md-failure, unguarded-trivial, and total-injection-failure), AC3 (migration follows the exact existing pattern),
  AC4 (3 new tests proving the real result — not an assumed success — gets persisted for guarded-success, guarded-failure, and
  unguarded), AC5/AC6 (4 new tests proving `GET /api/submission` surfaces both fields correctly, including the
  guarded-mode-failed-silently case an employer needs to see, and the pre-migration/missing-link case returning `None` instead
  of crashing), AC7 (existing `test_generate_link_ai_assistance_mode.py` tests all still pass unmodified in behavior — only the
  fixture's mock return value needed updating, not any assertion), AC8 (confirmed no frontend files touched).

### File List

- app/services/docker_service.py
- app/models/database.py
- app/services/database_service.py
- app/routes/links.py
- app/routes/submissions.py
- tests/test_inject_workspace_files.py (new file)
- tests/test_generate_link_ai_assistance_mode.py (fixture fix + 3 new tests)
- tests/test_submission_guarded_mode_visibility.py (new file)
