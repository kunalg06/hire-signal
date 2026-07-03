# Story 7.2: Unit test — `extract_container_files()`

Status: done

## Story

As a platform maintainer,
I want unit tests for `EvaluationService.extract_container_files()` with Docker fully mocked,
so that the workspace-snapshot guarantees (never blocks on Docker, text-only filter, 50KB cap) are locked in and regressions are caught before merge.

## Acceptance Criteria

1. **Mock Docker** — no test touches a real Docker daemon or subprocess. `DockerService.get_archive` is monkeypatched in every test; tar fixtures are built in-memory with `tarfile` + `io.BytesIO`.
2. **Docker unavailable → `{}`** — when `get_archive` returns `b''` (its own failure mode) AND when it raises, the result is `{}` (never an exception — callers must always proceed).
3. **Text-only filter** — only files with extensions in the TEXT_EXTS set (`.py .js .ts .md .txt .json .yaml .yml .sh .sql .toml .cfg`) are included; binary/other extensions (e.g. `.png`, `.exe`) and extension-less files are excluded; the match is case-insensitive (`.PY` included).
4. **50KB cap** — total content is capped at 51200 bytes: the file that would exceed the remaining budget is truncated to fit, gets `\n[TRUNCATED]` appended, and iteration stops (later files silently dropped).
5. **Path normalization** — tar member `workspace/solution.py` appears in the result as key `solution.py` (leading `workspace/` prefix and slashes stripped).
6. **Robustness paths** — directory members are skipped; non-UTF-8 bytes in a text-extension file decode via `errors='replace'` (no exception).
7. Full suite (`python -m pytest tests/ -v`) green from project root; existing 12 Story-7.1 tests unaffected.

## Tasks / Subtasks

- [x] Task 1: Tar fixture builder in `tests/test_extract_container_files.py` (AC: 1)
  - [x] Helper `make_tar(files: dict[str, bytes]) -> bytes` — builds an in-memory tar whose member names are `workspace/<name>` (matching `docker cp container:/workspace -` output); include a `workspace/` directory member to exercise the dir-skip branch
  - [x] Helper `mock_archive(monkeypatch, payload_or_exc)` — patches `DockerService.get_archive` via `monkeypatch.setattr(DockerService, "get_archive", lambda *a, **k: payload)` (shape-robust per Story 7.1 learning)
- [x] Task 2: Docker-unavailable tests (AC: 2)
  - [x] `get_archive` returns `b''` → `{}`
  - [x] `get_archive` raises `RuntimeError` → `{}` (caught by the outer except)
- [x] Task 3: Text-filter tests (AC: 3, 5)
  - [x] Mixed tar: `solution.py`, `notes.md`, `image.png`, `binary.exe`, `Makefile` (no ext) → only `.py` and `.md` in result, keys normalized (no `workspace/` prefix)
  - [x] Uppercase extension `REPORT.PY` → included (ext lowercased before match)
- [x] Task 4: 50KB cap tests (AC: 4)
  - [x] First file 50000 bytes, second 5000 bytes, third 100 bytes → first intact, second truncated to 1200 bytes + `\n[TRUNCATED]` suffix, third absent
  - [x] Single file larger than 51200 bytes → truncated to exactly 51200 chars + `\n[TRUNCATED]`
- [x] Task 5: Robustness tests (AC: 6)
  - [x] Directory member in tar → skipped, no key, no crash
  - [x] File with invalid UTF-8 bytes (e.g. `b'\xff\xfe caf\xe9'` in a `.txt`) → included with U+FFFD replacement chars, no exception
- [x] Task 6: Run and verify (AC: 7)
  - [x] Full suite green: all Story 7.1 tests + new tests

### Review Findings

- [x] [Review][Patch] Call contract unverified — no test asserts `get_archive` receives the container id and workspace path [tests/test_extract_container_files.py:30]
- [x] [Review][Patch] Exact-fit cap boundary (== 51200) unpinned — exact-size file kept intact, next file becomes bare `\n[TRUNCATED]` [app/services/evaluation_service.py:68]
- [x] [Review][Patch] Multibyte truncation untested — cap slice can cut mid-UTF-8-sequence; pin no-crash + replacement-char behavior [app/services/evaluation_service.py:69-70]
- [x] [Review][Patch] Symlink members silently vanish (`isfile()` excludes SYMTYPE) — untested [app/services/evaluation_service.py:58]
- [x] [Review][Patch] Dotfiles (`.env`, `.gitignore`) yield ext `''` and are excluded — common candidate files, behavior unpinned [app/services/evaluation_service.py:60-61]
- [x] [Review][Patch] Zero-byte allowed file and valid-tar-with-no-files paths uncovered [app/services/evaluation_service.py:56-74]
- [x] [Review][Defer] `workspace` parameter ignored by path normalization — `replace('workspace/', '', 1)` hardcoded; non-default workspace keeps wrong prefix and can strip the wrong segment [app/services/evaluation_service.py:67] — deferred, pre-existing (latent; all callers use default)
- [x] [Review][Defer] Cap accounting quirks: counts raw tar bytes but stores decoded text (U+FFFD inflation up to ~3x when re-encoded), `[TRUNCATED]` marker rides above the cap, duplicate tar member names overwrite last-wins and double-count [app/services/evaluation_service.py:68-74] — deferred, pre-existing

Dismissed as noise (8): cap-constant mirror in tests (legitimate spec pin — expected values computed independently, so a production cap change fails correctly), docker-py tuple-return contract (false premise — this wrapper is subprocess-based and returns bytes), hostile tar names hardening (keys never touch the filesystem; traversal strings are inert dict keys), tar-member ordering fragility (verified guaranteed: dict order → addfile order → getmembers order), empty-vs-garbage same-path claim (mistaken — `b''` hits the early return, garbage hits the outer except; both tested), uppercase-ext justification (case-insensitivity is spec'd in AC3), `extractfile`-None branch (unreachable through this seam), dir-skip test not branch-isolating (AC6 requires observable behavior only).

## Dev Notes

### Code under test — exact anatomy

`app/services/evaluation_service.py` — `EvaluationService.extract_container_files(container_id: str, workspace: str = '/workspace') -> dict` (staticmethod, lines 33–80):

1. `TEXT_EXTS` (local set, lines 41–42): `.py .js .ts .md .txt .json .yaml .yml .sh .sql .toml .cfg`; `MAX_TOTAL_BYTES = 50 * 1024` = **51200**
2. Lazy import INSIDE the try: `from app.services.docker_service import DockerService` — patching the `DockerService` class attribute works because the lazy import fetches the same class object from `sys.modules`
3. `raw = DockerService.get_archive(container_id, workspace)`; `if not raw: return {}` ← **the `b''` path (AC 2a)**
4. `tarfile.open(fileobj=io.BytesIO(raw))`; per member: skip `not member.isfile()` (dirs); ext filter via `os.path.splitext(...)[1].lower()`; `tar.extractfile(member)` None-guard
5. Truncation (lines 68–72): `if total_bytes + len(raw) > MAX_TOTAL_BYTES:` → slice to remaining budget, `decode('utf-8', errors='replace')`, append `'\n[TRUNCATED]'`, `break`. Note `raw` is shadowed here (archive bytes → per-file bytes) — harmless, do not "fix"
6. Key normalization (line 67): `member.name.replace('workspace/', '', 1).lstrip('/')`
7. ANY exception anywhere in the try → `logger.warning(...)`, `return {}` ← **the raise path (AC 2b)**

`app/services/docker_service.py` — `DockerService.get_archive` (staticmethod, lines 92–102): runs `docker cp <id>:/workspace -` via subprocess, returns `result.stdout` bytes, `b''` on any exception. **Mock seam** — never let tests reach subprocess.

### Building tar fixtures

```python
import io, tarfile

def make_tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tar:
        dir_info = tarfile.TarInfo('workspace')
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)
        for name, content in files.items():
            info = tarfile.TarInfo(f'workspace/{name}')
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()
```

`tar.getmembers()` preserves insertion order — cap tests are deterministic. Python dicts preserve insertion order, so `make_tar` fixture ordering is reliable.

### Cap arithmetic (pre-verified)

- 50000 + 5000 > 51200 → second file truncated to `51200 - 50000 = 1200` bytes + `'\n[TRUNCATED]'` → `len == 1212`; `break` fires so the third file never appears. Use ASCII fill bytes (e.g. `b'a'`) so decoded length == byte length.
- Single 60000-byte file: `0 + 60000 > 51200` → content is `60000[:51200]` decoded + marker → `len == 51212`.
- Exact-fit boundary (`==` cap) is NOT truncated (`>` comparison) — fine to note, not required to test.

### Story 7.1 learnings to carry forward

- Shape-robust mocks: `lambda *args, **kwargs: payload` (review patch from 7.1)
- Pin expectations as literals where the suite would otherwise be tautological (e.g. expected keys/filenames are string literals, not derived from TEXT_EXTS)
- Test infra already exists: root `conftest.py` handles `sys.path`; just add `tests/test_extract_container_files.py`
- `import app...` transitively imports all route blueprints and force-loads `.env` — known, deferred, harmless here (no LLM/db calls in this function)
- ASCII only in any print/log output (Windows cp1252)

### Scope boundaries — do not creep

- **No production code changes.** If tests reveal new gaps, log to `deferred-work.md` (pattern established in 7.1); known already-logged items: `get_file_from_container` dead `_run` call (different method — ignore), fence stripping, prompt-building try/except, malformed-JSON shapes
- `score_8_dimensions` is done (7.1); thresholds are 7.3; `generate_challenge` is 7.5
- No integration with a real container — that would be Docker-dependent and belongs nowhere in unit scope

### Project Structure Notes

- New file: `tests/test_extract_container_files.py` only
- Same conventions as 7.1: module-level helpers, `test_<behavior>` names, built-in `monkeypatch` only

### References

- [Source: _bmad-output/planning-artifacts/epics-and-stories.md#Epic 7 — story 7.2 line 327]
- [Source: app/services/evaluation_service.py#extract_container_files lines 33–80]
- [Source: app/services/docker_service.py#get_archive lines 92–102 — mock seam]
- [Source: _bmad-output/implementation-artifacts/7-1-unit-test-score_8_dimensions.md — infra + review learnings]

## Dev Agent Record

### Agent Model Used

claude-fable-5

### Debug Log References

- `python -m pytest tests/ -v` — 21 passed in 0.85s (9 new + 12 Story 7.1, zero regressions), first run green

### Completion Notes List

- 9 tests in `tests/test_extract_container_files.py` covering all 7 ACs: `b''` → `{}`, `get_archive` raises → `{}`, garbage (non-tar) bytes → `{}`, text-only filter with normalized keys (literal expected names), uppercase `.PY` included, three-file cap scenario (intact / truncated-to-1200+marker / dropped), single 60KB file truncated to exactly 51200+marker, nested directory members skipped, invalid UTF-8 decoded with U+FFFD replacement
- Added a third Docker-unavailable variant beyond spec (garbage non-tar bytes → `{}`) since it exercises the outer except via `tarfile.ReadError` — a distinct path from `get_archive` raising
- Mock seam as planned: `monkeypatch.setattr(DockerService, "get_archive", lambda *args, **kwargs: payload)` — shape-robust per 7.1 review learning; lazy import inside the function resolves the same patched class object
- No production code touched; no new gaps found warranting deferred-work entries during dev (the `raw` shadowing noted in Dev Notes is harmless style)
- Code review 2026-07-03 (Blind Hunter + Edge Case Hunter + Acceptance Auditor): Acceptance Auditor verdict "Acceptable" — all 7 ACs and scope constraints satisfied on first pass. 6 patches applied (call-contract spy, exact-fit cap boundary, multibyte truncation, symlink exclusion, dotfile exclusion, zero-byte/empty-tar paths), 2 pre-existing production gaps deferred to deferred-work.md (workspace-param-ignored path normalization; cap byte/char accounting quirks), 8 dismissed (including two refuted Blind Hunter claims — cap-constant mirror is a legitimate spec pin, docker-py tuple-contract concern doesn't apply to this subprocess-based wrapper). Suite now 16 tests in this file (28 total with 7.1), all green in 1.75s.

### File List

- `tests/test_extract_container_files.py` (new)
- `_bmad-output/implementation-artifacts/deferred-work.md` (modified — 2 entries appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — status tracking)
- `_bmad-output/implementation-artifacts/7-2-unit-test-extract_container_files.md` (this file)

