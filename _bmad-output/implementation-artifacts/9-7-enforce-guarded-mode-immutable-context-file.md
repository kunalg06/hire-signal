# Story 9.7: Enforce Guarded Mode via Immutable Global Context File

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an employer running a guarded-mode assessment,
I want the Gemini CLI restriction to be technically unbypassable by the candidate (not deletable, not editable, not skippable by changing directories) and to be delivered without depending on a fragile post-start copy step,
so that "guarded mode" actually means guarded, not a polite request the candidate can shrug off.

## Background — this supersedes a prior accepted decision

Story 6.5's code review (2026-07-03) explicitly decided guarded mode would ship as an honor-system nudge for v1: *"Real backend enforcement (e.g. proxying/validating Gemini API calls from the container, an immutable bind-mount for GEMINI.md) is a future story if assessment integrity requirements demand it."* That future story is this one — the user has now decided assessment integrity does demand it, and considers the honor-system gap to defeat the entire purpose of guarded mode. **Do not re-litigate whether to fix this — the decision is made. This story is the "how."**

## Acceptance Criteria

1. Guarded mode's restriction file is delivered as a **read-only Docker bind mount established at container-creation time** (part of the `docker run` command itself, via `-v host_path:container_path:ro`), not a `docker cp` performed after the container has already started.
2. The restriction is placed at Gemini CLI's **global context-file path**, `/home/coder/.gemini/GEMINI.md` — not `/workspace/GEMINI.md`. Gemini CLI always loads its global context file regardless of the candidate's current working directory (confirmed against Gemini CLI's own docs — see References), so invoking `gemini` from any directory other than `/workspace` no longer skips the restriction the way it did before.
3. `/workspace/GEMINI.md` is no longer written at all for guarded assignments — the mechanism moves entirely off the world-writable `/workspace` directory (which is `chmod 777` at the image level and was the actual reason deletion/editing was possible before, independent of any single file's own permission bits).
4. The candidate cannot delete, edit, replace, or evict (via renaming an ancestor directory) the mounted `~/.gemini` directory from inside the running container, even if the candidate has (or escalates to) root — a read-only bind mount targeting the DIRECTORY itself (not just the files inside it) is enforced at the kernel mount-namespace level, and this container is never run `--privileged` and is granted no extra capabilities, so nothing inside the container can remount, unlink, or rename a busy mount point without `CAP_SYS_ADMIN`, which it doesn't have. **Scope note (added after code review, 2026-07-06):** this closes every bypass that operates on the mounted path or its containing directory. It does NOT close a bypass that never touches the mount at all: overriding the `$HOME` environment variable (`HOME=/tmp/x gemini`) redirects Gemini CLI's lookup to an entirely different, unmounted location. No mount/permission-based fix can close that — it's an accepted residual gap, see Dev Notes and `deferred-work.md`. This AC is scoped to what a read-only bind mount can actually guarantee: the file/directory it targets cannot be tampered with, full stop; it was never a guarantee that Gemini CLI's config lookup itself is un-redirectable.
5. `~/.gemini/settings.json` is **also** bind-mounted read-only for guarded assignments only (same content the Dockerfile already bakes into the image, just sourced from `Config.GEMINI_MODEL` instead of a hardcoded literal). This closes an adjacent bypass this story's own research found: `context.fileName` in `settings.json` is user-configurable and defaults to `GEMINI.md` — an unprotected, writable `settings.json` would let a candidate reconfigure Gemini CLI to look for a different, unrestricted filename, sidestepping AC2–4 entirely without ever touching `GEMINI.md` itself. Unguarded assignments are unaffected — `settings.json` stays exactly as baked into the image today.
6. Unguarded assignments (the default/common case) are behaviorally unchanged: no bind mounts, no new host-side files, `docker run`'s command shape is identical to today except for the two additive `-v` flags that only appear when `ai_assistance_mode == 'guarded'`.
7. `guarded_mode_enforced` (Story 9.3's existing tracking field, unchanged in the DB/API) is now determined at the moment `create_container()` builds and runs the `docker run` command — True only when both host-side context files were written successfully AND are included in the mount flags of the container that actually started. This eliminates the previous failure mode entirely: there is no longer a separate, timing-dependent `docker cp` step after a 2-second sleep that could fail independently of container creation.
8. If writing the host-side context files fails (rare — host disk/permission issue), the container still starts **without** the mount (never block an assessment from starting over this), `guarded_mode_enforced=False` is honestly reported exactly as before, and any partially-created host-side directory from the failed attempt is deleted immediately — no orphaned files from a failed attempt.
9. When a container is torn down via `DockerService.cleanup_container()` (the automatic post-submission path — see `app/routes/submissions.py`), the per-container host-side directory holding the bind-mounted files is also removed, discovered via `docker inspect` rather than tracked separately, so host disk usage from this mechanism doesn't grow unbounded. (Explicitly out of scope: `ManagementService`'s admin-triggered cleanup routes use the Python Docker SDK, a separate pre-existing code path documented in `CLAUDE.md` as incompatible with this environment — extending cleanup there is a different, unrelated problem; see What NOT to Do.)
10. No changes to the `session_links` schema, the `GET /api/submission/<id_or_link>` response shape, or any other Story 9.3 API surface — this story changes the delivery mechanism and its reliability, not the tracking/reporting contract already shipped.

## Tasks / Subtasks

- [x] Add `Config.GUARDED_MODE_HOST_TMP_ROOT` in `app/config.py` — `os.path.join(tempfile.gettempdir(), 'hire-signal-guarded-mode')`, overridable via env var, matching the existing `os.getenv(..., default)` convention used by every other `Config` entry (AC: 1)
- [x] In `app/services/docker_service.py`, promote the guarded-mode Gemini instructions (currently a local variable inside `inject_workspace_files()`) to a module-level constant `_GUARDED_MODE_GEMINI_MD`, and add a new module-level constant `_GUARDED_MODE_SETTINGS_JSON` built from `Config.GEMINI_MODEL` (AC: 1, 5)
- [x] Rewrite `create_container(assignment_id, port, ai_assistance_mode=Config.DEFAULT_ASSISTANCE_MODE)`: when guarded, write both context files to a new per-container host directory (keyed by the `name` variable already generated before `docker run` today), add both as `-v ...:ro` mount args, run the container, and return `(container_id, port, guarded_mode_enforced)`; on any failure path (host-file write fails, `docker run` fails), clean up any partially-created host directory immediately and return the existing failure contract extended to 3-tuple, `(None, None, True)` (AC: 1, 2, 3, 5, 6, 7, 8)
- [x] Simplify `inject_workspace_files()`: remove the `ai_assistance_mode` parameter and the entire guarded-mode `GEMINI.md` `docker cp` block (including its entry in `chmod_paths`) — it goes back to handling only `instructions.md`/`solution.py`, and its return shape drops `guarded_mode_enforced` (that responsibility moved to `create_container()`) (AC: 3, 7)
- [x] Add `DockerService._cleanup_guarded_mode_host_files(container_id)`, called from `cleanup_container()` right after `stop` and before `rm` (container must still exist for `docker inspect` to work): parse `docker inspect`'s JSON output, find any bind-mount `Source` path under `Config.GUARDED_MODE_HOST_TMP_ROOT`, and `shutil.rmtree` its containing per-container directory — best-effort, swallow errors, never block the actual container removal (AC: 9)
- [x] Update `app/routes/links.py`'s `generate_link()`: pass `ai_assistance_mode=ai_assistance_mode` into `create_container(...)` instead of `inject_workspace_files(...)`; unpack the new 3-tuple return; remove the now-nonexistent `ai_assistance_mode` kwarg from the `inject_workspace_files(...)` call; source `guarded_mode_enforced` for `create_session_link(...)` from `create_container()`'s return value instead of `injection_result` (AC: 6, 7, 10). Additionally removed the now-fully-dead `injection_result` variable entirely (its only consumer was the line just removed; it was never read for anything else) rather than leaving an unused assignment.
- [x] Rewrite `tests/test_inject_workspace_files.py`: drop the 3 guarded-mode-specific tests (moved to the new test file below), keep only the base success/total-failure cases, drop `ai_assistance_mode` from every call and `guarded_mode_enforced` from every assertion
- [x] Create `tests/test_guarded_mode_context_file_enforcement.py` covering `create_container()`'s new behavior: guarded-mode success writes real files with the expected content and includes both `-v ...:ro` flags in the `docker run` args, returns `(container_id, port, True)`; unguarded mode adds zero `-v` flags, returns `(container_id, port, True)` trivially; host-file-write failure (mocked) still starts the container without mounts, returns `guarded_mode_enforced=False`, and doesn't return a 5th/broken tuple; `docker run` failure (mocked) cleans up any host directory that was written before the run attempt; `cleanup_container()` removes a mocked-`docker inspect`-reported host directory
- [x] Update `tests/test_generate_link_ai_assistance_mode.py`: `create_container` mock returns a 3-tuple and captures `ai_assistance_mode` from ITS OWN kwargs (not `inject_workspace_files`'s, which no longer receives it); `inject_workspace_files` mock returns `{"injected": True}` only; `test_failed_guarded_injection_persists_enforced_false` simulates failure via the `create_container` mock's 3rd return value, not `inject_workspace_files`'s return dict
- [x] Run the full test suite and confirm no regressions

### Review Findings

All 3 review layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) independently converged on the same critical gap in AC4. This is not a minor patch item — it's a confirmed hole in the story's central security claim.

- [x] [Review][Patch] **Bypass 1 — parent-directory rename evicts the mount.** Only the two individual files (`GEMINI.md`, `settings.json`) inside `/home/coder/.gemini/` are bind-mounted; the directory itself is created plain (`RUN mkdir -p ~/.gemini` under `USER coder`, `docker/Dockerfile.codeserver:29,41`) and is owned/writable by the same `coder` user who runs inside the container. Linux's mount-busy protection only guards operations targeting the mounted path itself (`rm`, `mv GEMINI.md`, `umount`) — it does NOT protect an ancestor directory from being renamed. `mv ~/.gemini ~/.gemini_old && mkdir ~/.gemini && echo unrestricted > ~/.gemini/GEMINI.md` evicts both mounts from Gemini CLI's expected lookup path with zero elevated privilege, silently defeating AC4 and AC5 together, while `guarded_mode_enforced=True` keeps reporting "enforced" the whole time. Fixed: now bind-mounts the WHOLE `/home/coder/.gemini` directory as read-only (one `-v` flag, host-side files now live under a `gemini/` subdirectory) instead of two individual files — the mount point IS the directory, so renaming/moving it hits the same busy-protection a file-level mount gets when targeted directly. Test renamed/rewritten to assert exactly one mount flag targeting the directory. [app/services/docker_service.py, `create_container()`'s `mount_args` construction]
- [x] [Review][Patch] **`_cleanup_guarded_mode_host_files()`'s prefix check has no path-separator boundary.** `Source.startswith(Config.GUARDED_MODE_HOST_TMP_ROOT)` would also match an unrelated sibling directory whose name happens to extend the root string (e.g. a hypothetical `hire-signal-guarded-mode-2`), incorrectly sweeping it. Fixed: now compares against `os.path.join(GUARDED_MODE_HOST_TMP_ROOT, '')` (root + OS-correct separator) instead of a raw string prefix. New regression test `test_cleanup_container_does_not_sweep_sibling_directory_with_extending_name` proves the sibling survives. [app/services/docker_service.py, `_cleanup_guarded_mode_host_files()`]
- [x] [Review][Patch] Cleanup failures in `_cleanup_guarded_mode_host_files()` log at `debug`, not `warning` — for a security-relevant artifact (leftover context files with restriction content on host disk), silent debug-only logging means real failures go unnoticed operationally. Fixed: bumped to `logger.warning(...)`. [app/services/docker_service.py, `_cleanup_guarded_mode_host_files()`]
- [x] [Review][Decision] **Bypass 2 — `HOME` environment variable override cannot be closed by any mount/permission scheme, including the directory-mount fix above.** Gemini CLI (Node.js) resolves `~/.gemini` via `os.homedir()`, which honors the ordinary `$HOME` environment variable — fully under the candidate's own control via their interactive shell (`HOME=/tmp/x gemini` or `export HOME=...`). This bypass never touches the mount at all; it relocates Gemini CLI's *lookup path* elsewhere. Since this story intentionally removed the workspace-local `GEMINI.md` fallback (AC3, to close the original cwd-dependent bypass), overriding `HOME` now means Gemini CLI finds NO restriction file anywhere — a full, silent bypass, requiring zero special privilege. No file-permission or mount-scope fix addresses this; the only actually-robust fix is network-level validation/proxying of the Gemini API calls leaving the container — the same larger future story already named out-of-scope in `deferred-work.md`'s original Story 6.5 finding. **User decision (2026-07-06): accept as a documented residual gap**, same tier as the already-accepted "candidate uses an external AI tool outside the sandbox" bypass — a partial `HOME`-pinning mitigation was considered and rejected as low-confidence (defeatable by a candidate who locates and directly invokes the real `gemini` binary) and not worth the added complexity; the real fix (network-level API validation/proxying) is deferred to a future story if assessment integrity requirements demand it. AC4's wording updated to state precisely what this story does and does not close. [app/services/docker_service.py, `create_container()` — no code change; decision + doc update only]

## Dev Notes

### Why this exists — what's actually wrong with the current mechanism

Traced fully during this story's own research (2026-07-06), not assumed from prior docs:

- `/workspace` is `chmod 777` at the image level (`docker/Dockerfile.codeserver`: `mkdir -p /workspace ... && chmod 777 /workspace`). Directory permissions govern who can unlink/rename entries inside a directory — **the file's own permission bits don't matter for deletion.** `chmod 000` on `GEMINI.md` itself would not stop `rm /workspace/GEMINI.md`. This is why the honor-system gap exists structurally, not just because of a lax `chmod 666`.
- `inject_workspace_files()` writes `GEMINI.md` via `docker cp` into the ALREADY-RUNNING container, after a hardcoded `time.sleep(2)` "to let the container filesystem settle," wrapped in a try/except that can silently fail (Story 9.3 made this failure *visible*, but never *prevented* it).
- Gemini CLI, per its own documentation (see References), always loads a **global** context file at `~/.gemini/GEMINI.md` regardless of current working directory, in addition to any workspace-local one. Since the current mechanism only writes the workspace-local copy, `cd /tmp && gemini` (or any directory outside `/workspace`) skips it entirely.

### Why a bind mount, not a stricter `chmod`

A candidate who has (or can obtain, e.g. via `sudo` if the base image grants it — not confirmed either way in this environment, and deliberately not depended on) root **inside** the container can defeat any pure Unix-permission scheme: `chown`, `chmod +w`, sticky bits, all of it. A read-only bind mount is different in kind: it is enforced by the Linux kernel at the **mount namespace** level. Writing to a read-only-mounted path returns `EROFS` regardless of the writer's UID. Unmounting or remounting it read-write requires `CAP_SYS_ADMIN`, which this container is never granted (no `--privileged`, no `--cap-add`) — so this holds even against in-container root, without needing to know or change anything about the `coder` user's actual privilege level.

### Why `settings.json` needs the same treatment (found during this story's research, not in the original ask)

Gemini CLI's context filename is configurable per `settings.json`'s `context.fileName` (default `"GEMINI.md"`, can be set to any other string or list of strings). Today, `~/.gemini/settings.json` is baked into the image at build time as a **plain, writable file** owned by `coder` (created under `USER coder` in the Dockerfile). A candidate could edit it to point `context.fileName` at some other file that doesn't exist or contains nothing — Gemini CLI would then simply stop looking for `GEMINI.md`, and the read-only bind mount on `GEMINI.md` becomes irrelevant, never touched, restriction silently gone. Locking `settings.json` down the same way (guarded assignments only) closes this before it ships as a known gap.

### Current code — `create_container()` (`app/services/docker_service.py:41-70`)

```python
@staticmethod
def create_container(assignment_id: str, port: int):
    """
    Spin up a student code-server container.
    Returns (container_id, port) or (None, None) on failure.
    """
    name = f"assignment_{assignment_id}_{os.urandom(4).hex()}"
    image = Config.DOCKER_IMAGE

    try:
        result = _run([
            'run', '-d',
            '--name', name,
            '-p', f'{port}:8080',
            '-e', f'GEMINI_API_KEY={Config.GEMINI_API_KEY}',
            '-e', f'GEMINI_MODEL={Config.GEMINI_MODEL}',
            image,
        ])
        container_id = result.stdout.strip()
        if container_id:
            logger.info("Container started: %s on port %s", container_id[:12], port)
            return container_id, port
    except subprocess.CalledProcessError as e:
        err = e.stderr or ''
        if 'already allocated' in err or 'port is already allocated' in err:
            raise  # let caller retry with next port
        logger.error("Failed to create container: %s", err)
    except Exception as e:
        logger.error("Failed to create container: %s", e)

    return None, None
```

**Only caller**: `app/routes/links.py:62`, `container_id, port = DockerService.create_container(assignment_id, port_attempt)` — no other call sites in the codebase or tests to worry about beyond what's listed in Tasks.

### New `create_container()` — exact implementation

```python
@staticmethod
def create_container(assignment_id: str, port: int,
                      ai_assistance_mode: str = Config.DEFAULT_ASSISTANCE_MODE):
    """
    Spin up a student code-server container.

    Story 9.7: when ai_assistance_mode == 'guarded', the container is
    started with READ-ONLY bind mounts over Gemini CLI's global context
    file (~/.gemini/GEMINI.md) and settings.json, established as part of
    the `docker run` command itself — not copied in after the fact. See
    this story's Dev Notes for why: Gemini CLI always loads the global
    context file regardless of the candidate's cwd (unlike a workspace-
    local file), and a read-only bind mount can't be defeated by
    in-container root the way chmod/ownership tricks can.

    Returns (container_id, port, guarded_mode_enforced) on success, or
    (None, None, True) if no container was ever created — the True
    mirrors the existing convention in app/routes/links.py's own default:
    nothing to enforce when there's no assessment to contradict.
    guarded_mode_enforced is False only when ai_assistance_mode == 'guarded'
    AND the host-side context files could not be prepared.
    """
    name = f"assignment_{assignment_id}_{os.urandom(4).hex()}"
    image = Config.DOCKER_IMAGE

    guarded_mode_enforced = (ai_assistance_mode != 'guarded')
    host_dir = None
    mount_args = []

    if ai_assistance_mode == 'guarded':
        try:
            host_dir = os.path.join(Config.GUARDED_MODE_HOST_TMP_ROOT, name)
            os.makedirs(host_dir, exist_ok=True)

            gemini_md_path = os.path.join(host_dir, 'GEMINI.md')
            with open(gemini_md_path, 'w', encoding='utf-8') as f:
                f.write(_GUARDED_MODE_GEMINI_MD)

            settings_path = os.path.join(host_dir, 'settings.json')
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(_GUARDED_MODE_SETTINGS_JSON)

            mount_args = [
                '-v', f'{gemini_md_path}:/home/coder/.gemini/GEMINI.md:ro',
                '-v', f'{settings_path}:/home/coder/.gemini/settings.json:ro',
            ]
            guarded_mode_enforced = True
        except Exception as e:
            logger.warning("Could not prepare guarded-mode context files for %s: %s", name, e)
            if host_dir:
                shutil.rmtree(host_dir, ignore_errors=True)
            host_dir, mount_args, guarded_mode_enforced = None, [], False

    try:
        result = _run([
            'run', '-d',
            '--name', name,
            '-p', f'{port}:8080',
            '-e', f'GEMINI_API_KEY={Config.GEMINI_API_KEY}',
            '-e', f'GEMINI_MODEL={Config.GEMINI_MODEL}',
            *mount_args,
            image,
        ])
        container_id = result.stdout.strip()
        if container_id:
            logger.info("Container started: %s on port %s", container_id[:12], port)
            return container_id, port, guarded_mode_enforced
        if host_dir:
            shutil.rmtree(host_dir, ignore_errors=True)
    except subprocess.CalledProcessError as e:
        if host_dir:
            shutil.rmtree(host_dir, ignore_errors=True)
        err = e.stderr or ''
        if 'already allocated' in err or 'port is already allocated' in err:
            raise  # let caller retry with next port
        logger.error("Failed to create container: %s", err)
    except Exception as e:
        if host_dir:
            shutil.rmtree(host_dir, ignore_errors=True)
        logger.error("Failed to create container: %s", e)

    return None, None, True
```

Note the `raise` for port-conflict still happens BEFORE any late `shutil.rmtree` in that branch executes the `if host_dir` line above it in the same except block — order matters, clean up host_dir first, then re-raise, so the retry loop in `links.py` doesn't leak a directory on every port-conflict retry attempt.

### New module-level constants (add above the `DockerService` class, or as class attributes — match existing file convention)

```python
_GUARDED_MODE_GEMINI_MD = """# Assessment Mode: Guarded

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
"""

_GUARDED_MODE_SETTINGS_JSON = json.dumps({
    "model": {"name": Config.GEMINI_MODEL},
    "security": {"auth": {"selectedType": "gemini-api-key"}},
})
```

The `_GUARDED_MODE_GEMINI_MD` text is byte-for-byte identical to the current local variable in `inject_workspace_files()` — moving it, not rewording it. `_GUARDED_MODE_SETTINGS_JSON` mirrors the Dockerfile's baked-in default (`docker/Dockerfile.codeserver`'s `~/.gemini/settings.json` line) except sourcing the model name from `Config.GEMINI_MODEL` (already imported) instead of a second hardcoded literal, so it can never drift from what `-e GEMINI_MODEL=...` actually passes into the container.

### Simplified `inject_workspace_files()` — exact diff shape

Remove the `ai_assistance_mode` parameter from the signature. Remove this entire block (currently inside the function, guarded by `if ai_assistance_mode == 'guarded':`):

```python
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
```

Remove the `guarded_gemini_md = """..."""` local variable and the `guarded_mode_enforced = (ai_assistance_mode != 'guarded')` line. Change both `return` statements from `{'injected': True/False, 'guarded_mode_enforced': guarded_mode_enforced}` to just `{'injected': True}` / `{'injected': False}`.

### `cleanup_container()` — exact diff shape (`app/services/docker_service.py:239-248`)

Replace:

```python
    @staticmethod
    def cleanup_container(container_id: str):
        """Stop and remove a container (best-effort)."""
        if not container_id:
            return
        try:
            _run(['stop', container_id], check=False)
            _run(['rm', container_id], check=False)
            logger.info("Cleaned up container %s", container_id[:12])
        except Exception as e:
            logger.error("Failed to clean up container %s: %s", container_id, e)
```

with:

```python
    @staticmethod
    def cleanup_container(container_id: str):
        """Stop and remove a container (best-effort). Also removes any
        guarded-mode host-side context-file directory bind-mounted into
        it (Story 9.7)."""
        if not container_id:
            return
        try:
            _run(['stop', container_id], check=False)
            DockerService._cleanup_guarded_mode_host_files(container_id)
            _run(['rm', container_id], check=False)
            logger.info("Cleaned up container %s", container_id[:12])
        except Exception as e:
            logger.error("Failed to clean up container %s: %s", container_id, e)

    @staticmethod
    def _cleanup_guarded_mode_host_files(container_id: str):
        """Remove the host-side directory holding guarded-mode bind
        mounts, if any — discovered via `docker inspect` (Source paths
        under Config.GUARDED_MODE_HOST_TMP_ROOT) rather than tracked
        separately, so this works regardless of caller. Best-effort:
        must never block the container removal that follows it."""
        try:
            result = _run(['inspect', container_id], check=False)
            if result.returncode != 0 or not result.stdout:
                return
            info = json.loads(result.stdout)[0]
            dirs_to_remove = {
                os.path.dirname(m.get('Source', ''))
                for m in info.get('Mounts', [])
                if m.get('Source', '').startswith(Config.GUARDED_MODE_HOST_TMP_ROOT)
            }
            for d in dirs_to_remove:
                shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            logger.debug("Could not clean up guarded-mode host files for %s: %s", container_id[:12], e)
```

Call `_cleanup_guarded_mode_host_files` AFTER `stop` and BEFORE `rm` — the container must still exist for `docker inspect` to return anything.

### `links.py` — exact diff shape (`app/routes/links.py:62-74`)

Replace:

```python
            container_id, port = DockerService.create_container(assignment_id, port_attempt)

            if container_id:
                logger.info("Container started successfully: %s on port %s", container_id[:12], port)
                # Inject starter code + instructions into /workspace
                injection_result = DockerService.inject_workspace_files(
                    container_id=container_id,
                    title=title,
                    description=description,
                    criteria=evaluation_criteria or '',
                    starter_code=starter_code or '',
                    ai_assistance_mode=ai_assistance_mode,
                )
                break
```

with:

```python
            container_id, port, guarded_mode_enforced = DockerService.create_container(
                assignment_id, port_attempt, ai_assistance_mode=ai_assistance_mode)

            if container_id:
                logger.info("Container started successfully: %s on port %s", container_id[:12], port)
                # Inject starter code + instructions into /workspace
                injection_result = DockerService.inject_workspace_files(
                    container_id=container_id,
                    title=title,
                    description=description,
                    criteria=evaluation_criteria or '',
                    starter_code=starter_code or '',
                )
                break
```

The pre-loop default (`injection_result = {'injected': False, 'guarded_mode_enforced': True}`) needs its `guarded_mode_enforced` key removed from `injection_result` and tracked as its own pre-loop variable instead (`guarded_mode_enforced = True`), since it's no longer a key `inject_workspace_files()` returns. The final `db_service.create_session_link(..., guarded_mode_enforced=injection_result['guarded_mode_enforced'])` call must read from the loop-scoped `guarded_mode_enforced` variable instead of `injection_result[...]`.

### What NOT to Do

- Do NOT touch `ManagementService`'s admin cleanup routes (`cleanup_old_containers`, `cleanup_all_containers`, `stop_container` in `app/services/management_service.py`) — these use the Python `docker` SDK directly, a separate, pre-existing architecture split documented in `CLAUDE.md` as an accepted incompatibility on this environment's Python/requests versions. Unifying that split is a different, much larger, unrelated problem. The host-side-file leak risk through THAT path is a known, accepted, narrow gap (see AC9) — log it to `deferred-work.md`, don't fix it here.
- Do NOT attempt to strip or disable `sudo` for the `coder` user as additional hardening. The bind-mount approach is already robust against in-container root without needing to touch user privileges — and doing so risks breaking a candidate's legitimate ability to install packages for their own solution, which is out of scope and unrelated to what was asked.
- Do NOT change `/workspace`'s `chmod 777` or add a sticky bit. Out of scope — not needed since `GEMINI.md` no longer lives there, and `instructions.md`/`solution.py` should remain exactly as freely candidate-editable as before.
- Do NOT attempt to block "use an AI tool/API entirely outside Gemini CLI" (e.g., a candidate curling a different LLM API directly with their own key). This would require container network policy / API proxying — explicitly named as a *separate, much larger* future story in the original `deferred-work.md` entry this story supersedes only the `GEMINI.md`-specific part of. Not in scope here.
- Do NOT change anything about `session_links`'s schema or the `GET /api/submission/<id_or_link>` response shape — `guarded_mode_enforced`'s meaning and API surface (Story 9.3) are unchanged; only how reliably it's computed changes.

### Testing

Mock `_run` (the module-level subprocess wrapper), same convention as every existing `docker_service.py` test (`tests/test_inject_workspace_files.py`, `tests/test_get_file_from_container.py`) — no real Docker daemon required. For `create_container()`'s guarded-mode path, monkeypatch `Config.GUARDED_MODE_HOST_TMP_ROOT` to a `tmp_path`-based test directory so the test can assert on REAL file content written to a real (test-scoped) location, not just mocked calls — this is the only way to actually prove the mount args reference files containing the correct restriction text.

**Important residual gap this story cannot close from this sandbox**: there is no Docker available in this environment. Every test here mocks `_run`/subprocess — none of them can prove that a real read-only bind mount actually blocks deletion inside a real container, or that a real installed Gemini CLI actually reads `~/.gemini/GEMINI.md` globally the way its documentation states. Both are asserted here from Gemini CLI's own published docs (see References) and from general Docker bind-mount/capability semantics, not from a live test in this repo's environment. **Recommend folding a live verification pass into Story 9-6** (which already needs a real Docker deployment for its own auth-picker check): generate a guarded-mode candidate link, open the code-server terminal, attempt `rm ~/.gemini/GEMINI.md` and `cd /tmp && gemini` and confirm both fail to bypass the restriction.

### Project Structure Notes

- `app/config.py`: one new constant, needs `import tempfile` added.
- `app/services/docker_service.py`: two new module-level constants, `create_container()` rewritten (signature gains a parameter, return shape gains a 3rd element), `inject_workspace_files()` simplified (loses a parameter, return shape loses a key), `cleanup_container()` gains one line + one new private helper method. Needs `import shutil` added (not currently imported).
- `app/routes/links.py`: the `create_container`/`inject_workspace_files` call-site diff shown above, plus the pre-loop default and final `create_session_link` call adjusted to read `guarded_mode_enforced` from the right place.
- `tests/test_inject_workspace_files.py`: shrinks from 4 tests to 2 (drops the 3 guarded-mode-specific ones, moved elsewhere).
- New file: `tests/test_guarded_mode_context_file_enforcement.py`.
- `tests/test_generate_link_ai_assistance_mode.py`: mocks updated, no new test cases needed — existing 7 tests' assertions still hold, just against the new call-site shape.
- No DB schema changes. No changes to `templates/frontend.html` or any employer-facing UI.

### References

- Decision this story implements: `deferred-work.md`, "Deferred from: code review of 6-5-guarded-mode-claude-restrictions (2026-07-03)" — "Guarded mode is enforcement-by-honor-system, trivially bypassable" entry, specifically its closing line naming "an immutable bind-mount for GEMINI.md" as the future-story fix.
- Gemini CLI global context-file behavior (verified via web search + fetch during this story's creation, 2026-07-06): [Provide context with GEMINI.md files | Gemini CLI](https://geminicli.com/docs/cli/gemini-md/) — "The CLI loads a global context file at `~/.gemini/GEMINI.md`... which provides default instructions for all your projects," always loaded regardless of cwd; `context.fileName` in `settings.json` is user-configurable (default `"GEMINI.md"`).
- Current code to modify: `app/services/docker_service.py` — `create_container()` (lines 41-70), `inject_workspace_files()` (lines 107-236), `cleanup_container()` (lines 239-248); `app/routes/links.py` — `generate_link()` (lines 14-101); `app/config.py`.
- Image-level context confirming `/workspace` is `chmod 777` and `~/.gemini/settings.json` is baked-in-and-writable: `docker/Dockerfile.codeserver`.
- Only caller of `create_container()`/`inject_workspace_files()`/`cleanup_container()` in the whole codebase: `app/routes/links.py:62`/`67` and `app/routes/submissions.py:237` respectively — confirmed via repo-wide grep, no other call sites to update.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Wrote `tests/test_guarded_mode_context_file_enforcement.py` and rewrote `tests/test_inject_workspace_files.py`/`tests/test_generate_link_ai_assistance_mode.py` against the new contract, then implemented `docker_service.py`/`links.py`/`config.py`. Ran the guarded-mode/link test files first — confirmed they failed against the pre-change code (3-tuple unpack error in `links.py`, missing `Config.GUARDED_MODE_HOST_TMP_ROOT`), the expected red state, before implementing.
- One test bug caught during the first run: `test_guarded_mode_writes_real_context_files_and_mounts_them` used `mount_str.split(":", 1)[0]` to extract the host path, which breaks on Windows since host paths themselves contain a colon (`C:\Users\...`). Not a product bug — Docker's own `-v` flag parser is drive-letter-aware. Fixed by stripping the known container-path+`:ro` suffix from the end instead of splitting from the front.
- Full suite: 131/131 passed (125 before this story; `test_inject_workspace_files.py` shrank from 4→2 tests, new file added 8, net +6), zero regressions.
- Could not live-verify against a real Docker daemon (unavailable in this environment) that the read-only bind mount actually blocks deletion inside a running container, or that a real installed Gemini CLI actually reads `~/.gemini/GEMINI.md` globally as documented — both are asserted from Gemini CLI's own published docs and Docker/Linux capability semantics, not exercised end-to-end here. Flagged in the story's Testing section as a residual gap to fold into Story 9-6's live-verification pass.

### Completion Notes List

- `app/config.py`: added `GUARDED_MODE_HOST_TMP_ROOT` (env-overridable, defaults under the system temp dir).
- `app/services/docker_service.py`: added module-level `_GUARDED_MODE_GEMINI_MD` (moved verbatim from the old local variable) and `_GUARDED_MODE_SETTINGS_JSON` (sourced from `Config.GEMINI_MODEL`, not a second hardcoded literal). `create_container()` now accepts `ai_assistance_mode`, writes both context files to a per-container host directory and bind-mounts them read-only at `docker run` time when guarded, and returns a 3-tuple including `guarded_mode_enforced`. `inject_workspace_files()` lost the `ai_assistance_mode` param and all guarded-mode logic — back to instructions.md/solution.py only, matching its original Story 6.1 scope. `cleanup_container()` gained `_cleanup_guarded_mode_host_files()`, called between `stop` and `rm`, which discovers and removes the host-side directory via `docker inspect`'s own mount metadata rather than separate tracking.
- `app/routes/links.py`: `generate_link()` now passes `ai_assistance_mode` into `create_container()` instead of `inject_workspace_files()`, unpacks the new 3-tuple, and sources `guarded_mode_enforced` for `create_session_link()` from a loop-scoped variable. Also removed the `injection_result` variable entirely — it became fully dead code once its only consumer (`injection_result['guarded_mode_enforced']`) was removed, not left as an unused assignment.
- All 10 acceptance criteria verified: AC1/AC2 (bind mount at creation time, targeting the global `~/.gemini/GEMINI.md` path — new test asserts both the mount flags and the real file content), AC3 (`/workspace/GEMINI.md` no longer written — confirmed by removing that code path entirely and by `inject_workspace_files()`'s tests no longer referencing it), AC4 (kernel-level read-only enforcement — documented in code comments and story Dev Notes; can't be exercised live without Docker, see residual gap), AC5 (`settings.json` also bind-mounted, guarded-only — asserted in the new test), AC6 (unguarded path adds zero mount args — dedicated test), AC7/AC8 (`guarded_mode_enforced` derived at `create_container()` time, honest `False` + no orphaned directory on host-write failure — 2 dedicated tests), AC9 (`cleanup_container()` removes the host directory via `docker inspect` — 3 dedicated tests including the no-container-id no-op case and the tolerate-inspect-failure case), AC10 (no `session_links`/API changes — confirmed via `git diff` scope covering only the 5 files listed).

### Post-Review Follow-Up (2026-07-06)

3-layer code review (Blind Hunter, Edge Case Hunter, Acceptance Auditor) independently found the same critical gap: the original file-level mount (two `-v` flags for `GEMINI.md`/`settings.json` individually) left the containing `~/.gemini` directory itself plain and candidate-writable, since it's created under `USER coder` in the image before any mount exists. A candidate could `mv ~/.gemini ~/.gemini_old && mkdir ~/.gemini` to evict both mounts without touching either mounted file, defeating AC4/AC5 entirely while `guarded_mode_enforced=True` kept reporting success. Fixed same-day: the mount now targets the whole `~/.gemini` directory as one `-v` flag (host-side files moved under a `gemini/` subdirectory) — the mount point itself is now the protected boundary, closed by the same busy-mount protection a file-level mount only gave the individual files. Also fixed: a prefix-boundary bug in `_cleanup_guarded_mode_host_files()`'s sibling-directory matching (new regression test), and cleanup-failure logging bumped from `debug` to `warning`.

A second, structurally different bypass was also found and could NOT be fixed by any mount/permission change: Gemini CLI resolves `~/.gemini` via the `$HOME` environment variable, which the candidate's own shell fully controls (`HOME=/tmp/x gemini`). This never touches the mount at all. User decision (2026-07-06): accept as a documented residual gap, same tier as the already-accepted "external AI tool outside the sandbox" bypass — the real fix requires network-level API validation, a distinct future story. AC4's wording updated to state precisely what a bind mount can and cannot guarantee. Logged to `deferred-work.md`.

Full suite re-verified after all fixes: 132/132 passing (131 before this pass + 1 new regression test for the boundary fix).

### File List

- app/config.py
- app/services/docker_service.py
- app/routes/links.py
- tests/test_inject_workspace_files.py
- tests/test_guarded_mode_context_file_enforcement.py (new file)
- tests/test_generate_link_ai_assistance_mode.py
