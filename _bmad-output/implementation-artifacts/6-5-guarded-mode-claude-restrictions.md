# Story 6.5: Guarded Mode — Claude System Prompt Injection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer running a **guarded** assessment,
I want the candidate's in-container Claude Code CLI restricted to conceptual guidance instead of full solutions,
so that the assessment measures the candidate's own understanding rather than AI-generated code they copy in verbatim.

## Acceptance Criteria

1. When a student container is created for an assignment whose linked challenge has `ai_assistance_mode = 'guarded'`, a `/workspace/CLAUDE.md` file is injected into the container instructing the Claude Code CLI to restrict responses: no complete solutions, no full corrected code blocks — conceptual guidance, hints, and explanations only.
2. When the assignment's linked challenge has `ai_assistance_mode = 'unguarded'`, **or** the assignment has no linked challenge at all (`challenge_id IS NULL`), no restriction file is injected — container setup is byte-for-byte identical to the current (pre-story) behavior.
3. `generate_link()` (`app/routes/links.py`) resolves `ai_assistance_mode` by looking up the assignment's `challenge_id` (index **6** — see Dev Notes) against `db_service.get_challenge()`, defaulting to `'unguarded'` when `challenge_id` is `NULL` or the challenge lookup returns nothing (deleted/soft-deleted challenge).
4. The injected `CLAUDE.md` is chmod 666 after `docker cp`, matching the existing permission fix already applied to `instructions.md` and `solution.py` — the `coder` user (not root) must be able to read it.
5. No regression to Story 6.1–6.4 behavior: `instructions.md` and `solution.py` injection is unchanged; guarded-mode file injection is strictly additive.
6. Manual smoke test confirms: guarded challenge → generate link → `docker exec <id> cat /workspace/CLAUDE.md` shows the restriction text; unguarded challenge or assignment with no `challenge_id` → file is absent from `/workspace`.

## Tasks / Subtasks

- [x] Fix the data-flow gap: `generate_link()` doesn't currently resolve `ai_assistance_mode` at all (AC: 3)
  - [x] In `app/routes/links.py`, after `assignment_row = db_service.get_assignment(assignment_id)`, extract `challenge_id = assignment_row[6] if len(assignment_row) > 6 else None` — **do not reuse the existing `assignment_row[:5]` unpack line**, index 6 is one past where that slice stops
  - [x] If `challenge_id` is truthy, call `db_service.get_challenge(challenge_id)`; if the row exists, `ai_assistance_mode = row[9]` (see column table in Dev Notes); otherwise default to `'unguarded'`
  - [x] If `challenge_id` is falsy, `ai_assistance_mode = 'unguarded'` directly — skip the `get_challenge` call
  - [x] Pass `ai_assistance_mode=ai_assistance_mode` into the existing `DockerService.inject_workspace_files(...)` call

- [x] Extend `DockerService.inject_workspace_files()` to accept and act on `ai_assistance_mode` (AC: 1, 2, 4, 5)
  - [x] Add parameter `ai_assistance_mode: str = 'unguarded'` to the method signature in `app/services/docker_service.py`
  - [x] Leave the existing `instructions.md` / `solution.py` construction and `docker cp` calls completely untouched
  - [x] Inside the same `with tempfile.TemporaryDirectory() as tmpdir:` block, `if ai_assistance_mode == 'guarded':` write CLAUDE.md to `tmpdir`, then `_run(['cp', <path>, f'{container_id}:/workspace/CLAUDE.md'])`
  - [x] Extend the existing chmod call to include `/workspace/CLAUDE.md` **only when it was written** — built via a `chmod_paths` list conditionally appended to, not a second chmod call

- [x] Write the guarded-mode restriction content (AC: 1)
  - [x] Content explicitly instructs Claude Code CLI to never output a complete corrected/working code block; may explain concepts, name relevant methods/APIs/patterns, describe approach, or point out what's wrong — candidate must write the actual code
  - [x] Tone consistent with `evaluation_service.py`'s `guarded` mode_instruction, distinct audience (live system-prompt to Claude Code itself, not evaluation guidance)

- [x] Manual smoke test (AC: 6)
  - [x] Created a guarded challenge + linked assignment directly via `DatabaseService`, then hit the real `POST /api/generate-link/<assignment_id>` route through the Flask test client — `docker exec <container_id> cat /workspace/CLAUDE.md` showed the restriction text, permissions 666
  - [x] Direct `DockerService.inject_workspace_files()` calls with `ai_assistance_mode='unguarded'` and with the argument omitted entirely (default) both produced `/workspace` with only `instructions.md` + `solution.py` — no `CLAUDE.md`, confirming AC2/AC5 byte-for-byte parity with pre-story behavior
  - [x] `instructions.md` and `solution.py` present and unchanged (545 bytes / 8 bytes matching input) in all three test containers
  - [x] All test containers and DB rows cleaned up after verification

## Dev Notes

### Files Changed

| File | Action |
|------|--------|
| `app/routes/links.py` | UPDATE — resolve `ai_assistance_mode`, pass to `inject_workspace_files()` |
| `app/services/docker_service.py` | UPDATE — `inject_workspace_files()` gains `ai_assistance_mode` param + conditional `CLAUDE.md` injection |

No new files, no DB migrations, no new blueprint. `db_service.get_challenge()` already exists (used by Story 6.4's `student_preview`) — reuse it, do not duplicate.

---

### CRITICAL: `assignments` column order (verified against live DB via `PRAGMA table_info`)

```
0: id              1: title            2: description
3: starter_code    4: evaluation_criteria    5: created_at
6: challenge_id    <- appended by ALTER TABLE migration, NOT adjacent to evaluation_criteria
```

`app/routes/links.py` currently does:
```python
_, title, description, starter_code, evaluation_criteria = assignment_row[:5]
```
This correctly grabs indices 0-4 and silently drops `created_at` (5) and `challenge_id` (6) — that's fine, don't touch this line. Just add a **separate** extraction:
```python
challenge_id = assignment_row[6] if len(assignment_row) > 6 else None
```
Do NOT assume `challenge_id` is at index 5 — that's `created_at` (a timestamp string). Passing a timestamp string into `get_challenge()` will just return `None` (no matching row), silently defaulting to `unguarded` with no error — a disaster that looks like the feature works (no crash) but guarded mode never triggers. This exact off-by-one was caught and corrected during story creation — verify column order yourself with `PRAGMA table_info(assignments)` if the schema changes before you implement.

### `challenges` column order (already used correctly in `student.py`'s `student_preview()` from Story 6.4)

```
0: id  1: title  2: domain  3: description  4: evaluation_rubric_json
5: starter_code  6: challenge_type  7: skill_area  8: difficulty
9: ai_assistance_mode  10: is_published  11: created_at
```
`ai_assistance_mode` is index **9**. `db_service.get_challenge(challenge_id)` returns this row or `None`.

---

### `inject_workspace_files()` current signature (app/services/docker_service.py:104-106)

```python
@staticmethod
def inject_workspace_files(container_id: str, title: str, description: str,
                           criteria: str, starter_code: str):
```

New signature:
```python
@staticmethod
def inject_workspace_files(container_id: str, title: str, description: str,
                           criteria: str, starter_code: str,
                           ai_assistance_mode: str = 'unguarded'):
```

Existing chmod call (docker_service.py:166-171) chmods two fixed paths unconditionally:
```python
_run([
    'exec', '-u', 'root', container_id,
    'chmod', '666',
    '/workspace/instructions.md',
    '/workspace/solution.py',
], check=False)
```
When guarded, add `/workspace/CLAUDE.md` to this same list (build the path list conditionally, e.g. a list you append to, then pass via `*paths` or similar) — do not run a second separate chmod call, and do not chmod a path that was never written (unguarded branch).

### Restriction file content — mechanism rationale

The student container (`docker/Dockerfile.codeserver`) has `@anthropic-ai/claude-code` installed globally and `WORKDIR /workspace`. Claude Code CLI auto-loads a `CLAUDE.md` file from its working directory as project instructions on every invocation — this is the exact same mechanism this very repository's root `CLAUDE.md` uses to brief Claude Code sessions working on this codebase. Writing `/workspace/CLAUDE.md` for guarded challenges reuses that built-in behavior with zero new infrastructure: no CLI flag changes, no wrapper scripts, no changes to the `~/.claude/config.yaml` haiku-4.5 model lock (that stays untouched — model restriction and behavioral restriction are separate concerns).

Suggested content (adapt tone, keep the core restriction unambiguous):
```markdown
# Assessment Mode: Guarded

You are assisting a candidate during a technical assessment in **guarded mode**.

Rules for this session:
- Do NOT write or output a complete, working solution — no full functions, no
  complete corrected code blocks the candidate could copy in directly.
- You MAY: explain relevant concepts, name applicable methods/APIs/patterns,
  describe a general approach in prose, point out what's wrong with a piece
  of reasoning or code, or walk through *why* something fails.
- If asked directly for "the code" or "the fix," decline and instead explain
  what the candidate needs to figure out to write it themselves.

This restriction exists so the assessment measures the candidate's own
understanding, not AI-generated code they copy in unchanged.
```

### What NOT To Do

- Do NOT modify `~/.claude/config.yaml` or the `CLAUDE_MODEL` env var baked into `docker/Dockerfile.codeserver` — that's the haiku-4.5 model lock (unrelated concern, already shipped, out of scope).
- Do NOT touch the existing `instructions.md` / `solution.py` construction or their `_run(['cp', ...])` calls.
- Do NOT assume `challenge_id` is adjacent to `evaluation_criteria` in `SELECT *` order — verified index is **6**, not 5.
- Do NOT write `CLAUDE.md` unconditionally (e.g. always writing a neutral/empty one) — AC2 requires the unguarded/no-challenge path to be **byte-for-byte identical** to current behavior, meaning no extra file at all.
- Do NOT add a new `db_service` method — `get_challenge()` already exists and is sufficient.

---

### Previous Story Learnings (6.1-6.4)

- Manual smoke testing is the validation method for Docker-container-touching stories — no automated framework covers live container file injection.
- `_run()` calls that touch the container filesystem via `docker cp`/`docker exec` are wrapped in `try/except Exception` at the top of `inject_workspace_files()` (docker_service.py:174) with a `logger.warning` — a failure here must not crash link generation. Keep the new guarded-mode injection inside that same try block, not a separate one.
- Story 6.4's code review found and fixed a `hire_data`/`hire_evaluation` API-response key-mismatch bug and confirmed the project's established pattern of raw positional-tuple unpacking with **no** try/except around DB calls (matches codebase convention — don't add defensive error handling `get_challenge()` doesn't already have elsewhere).
- A party-mode panel resolved a related data-consistency question for 6.4 (challenge-template vs. live-assignment content can diverge) — not directly relevant to this story's mechanism, but reinforces that `challenge_id` on `assignments` is nullable and genuinely absent for many assignments; the `unguarded`-default path in this story is the common case, not an edge case.

### References

- [Source: `_bmad-output/planning-artifacts/epics-and-stories.md#Story 6.5 — Guarded mode Claude restrictions`]
- [Source: `docker/Dockerfile.codeserver` — Claude Code CLI install + haiku-4.5 model lock]
- [Source: `app/services/evaluation_service.py:295-360` — existing `ai_assistance_mode` handling in challenge generation, for tone reference only]
- [Source: `app/routes/student.py` (Story 6.4) — established pattern for `db_service.get_challenge()` usage and column unpacking]

### Review Findings

- [x] [Review][Patch] Guarded-mode `CLAUDE.md` copy failure skips the shared chmod call, leaving `instructions.md`/`solution.py` root-owned [app/services/docker_service.py:199-207] — fixed: isolated in its own try/except; verified live with a simulated cp failure — instructions.md/solution.py still chmod 666
- [x] [Review][Decision] Guarded mode is enforcement-by-honor-system (CLAUDE.md in a world-writable `/workspace`, candidate has full shell access — trivially bypassable) — resolved: ship as-is for v1, treat as a soft nudge; deferred to `deferred-work.md` — real backend enforcement is a future story, not in scope now.
- [x] [Review][Defer] No whitelist/validation on `ai_assistance_mode` string match — fail-open on typos/case drift [app/routes/links.py:29] — deferred, low practical risk (enum-validated at challenge creation)
- [x] [Review][Defer] Magic string `'unguarded'` duplicated as default in two places [app/routes/links.py:26, app/services/docker_service.py:107] — deferred, pre-existing
- [x] [Review][Defer] No try/except around new `get_challenge()` call [app/routes/links.py:30] — deferred, matches adjacent `get_assignment()` call's own unguarded convention
- [x] [Review][Defer] AC3's "(deleted/soft-deleted challenge)" example is unreachable — `get_challenge()` has no `is_published` filter and the app has no hard-delete path — deferred, spec-wording note not a code defect
- [x] [Review][Defer] `chmod 666` on `CLAUDE.md` — candidate has write access to their own restriction file [app/services/docker_service.py:206] — deferred, component of the honor-system decision above

#### Re-review (2026-07-03, post-patch)

Acceptance Auditor confirmed AC5 now holds and found zero AC violations. One trivial patch applied, one new item deferred; all other findings were repeats of items already triaged above (confirmed, not re-logged).

- [x] [Review][Patch] Docstring overstated the guarantee ("restricting... to conceptual guidance only" stated as fact) [app/services/docker_service.py:113-117] — fixed: reworded to "attempting to restrict," explicit note that it's a prompt-level request, not enforced access control
- [x] [Review][Defer] Guarded-mode injection failure is silent — no teacher-facing signal if the `CLAUDE.md` write fails (transient Docker/disk issue, distinct from deliberate candidate bypass) — deferred, no AC requires this; dashboard surfacing of `ai_assistance_mode`/injection status is scope beyond this story

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `ast.parse()` verified valid Python syntax on both changed files (pre-existing `SyntaxWarning` for `\`` in the untouched `instructions` f-string, not introduced by this story)
- Live smoke test via `docker exec` on 3 real containers (guarded / unguarded / default-arg) — see Completion Notes

### Completion Notes List

- `app/routes/links.py`: `generate_link()` now extracts `challenge_id` from `assignment_row[6]` (verified via live `PRAGMA table_info(assignments)` — NOT index 5, which is `created_at`) and resolves `ai_assistance_mode` via `db_service.get_challenge(challenge_id)[9]`, defaulting to `'unguarded'` when `challenge_id` is falsy or the challenge lookup returns `None`. Passed through to `inject_workspace_files()`.
- `app/services/docker_service.py`: `inject_workspace_files()` gained `ai_assistance_mode: str = 'unguarded'` parameter. When `'guarded'`, writes `/workspace/CLAUDE.md` inside the existing `tempfile.TemporaryDirectory()` block (same try/except as `instructions.md`/`solution.py` — a guarded-mode injection failure logs a warning, doesn't crash link generation) and adds it to the chmod 666 pass via a `chmod_paths` list built conditionally. Existing `instructions.md`/`solution.py` code paths untouched.
- Mechanism: relies on Claude Code CLI's built-in auto-load of `CLAUDE.md` from its working directory (`/workspace`, per `docker/Dockerfile.codeserver`'s `WORKDIR`) — zero new infrastructure, same mechanism this repo's own root `CLAUDE.md` uses.
- No automated test suite exists for `app/` (Epic 7 — Test Coverage — is entirely backlog, consistent with Stories 6.1-6.4). Validated via live Docker smoke tests instead, per the project's established pattern for container-touching stories:
  - Guarded mode, called through the real `POST /api/generate-link/<id>` Flask route (not just the service function directly) — confirmed `/workspace/CLAUDE.md` present with correct content and 666 permissions.
  - Unguarded mode and default-argument (omitted) calls to `inject_workspace_files()` — confirmed `/workspace` contains only `instructions.md` + `solution.py`, byte-identical to pre-story behavior (AC2, AC5).
  - All test containers and DB rows cleaned up after verification.

### File List

- `app/routes/links.py` (UPDATE)
- `app/services/docker_service.py` (UPDATE)

## Change Log

- 2026-07-03: Story created
- 2026-07-03: Implementation complete — `generate_link()` resolves `ai_assistance_mode` via `challenge_id` (index 6, verified against live schema); `inject_workspace_files()` conditionally injects `/workspace/CLAUDE.md` for guarded challenges. Verified end-to-end via real Docker containers through the Flask route; unguarded/default path confirmed unchanged.
- 2026-07-03: Code review — 1 decision resolved (guarded mode ships as honor-system nudge for v1, hardening deferred), 1 patch applied (isolated guarded-mode CLAUDE.md injection in its own try/except so a copy failure can't skip the chmod of instructions.md/solution.py — verified live with a simulated failure), 5 items deferred.
- 2026-07-03: Re-review — Acceptance Auditor confirmed AC5 fix holds, zero AC violations. 1 additional trivial patch applied (docstring wording softened to not overstate the restriction's enforceability), 1 additional item deferred (silent injection-failure visibility).
