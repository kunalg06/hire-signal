# Story 8.1: Pre-Authenticate Gemini CLI in the Student Container

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a candidate opening a terminal in the browser-based VS Code environment,
I want the in-container Gemini CLI already authenticated with no setup step of my own,
so that I can start collaborating with it immediately instead of hitting an auth-method picker I have no context for.

## Background — how this was found

This story follows directly from the OpenRouter/Claude → Gemini provider migration (`AGENT.md` Phase 2, 2026-07-04). That migration wired `GEMINI_API_KEY`/`GEMINI_MODEL` into the container at creation time (`docker_service.py`'s `create_container()`) and verified — via `gemini -p "..." --output-format json` — that **headless** mode works end-to-end. That verification was necessary but not sufficient: headless mode (`-p` flag) and interactive mode (typing `gemini` at a real terminal prompt, which is how a candidate actually uses it inside code-server) authenticate differently.

## Investigation

Checked directly against the installed CLI's own bundled docs (`/usr/local/lib/node_modules/@google/gemini-cli/bundle/docs/get-started/authentication.md` and `.../reference/configuration.md`, version 0.49.0 — not the website, to avoid any version mismatch):

- **Headless mode** (`gemini -p "..."`) "will use your existing authentication method, if an existing authentication credential is cached... If you have not already signed in with an authentication credential, you must configure authentication using environment variables" — i.e. `GEMINI_API_KEY` alone is sufficient. **Confirmed working** via live container smoke test (see Story context above and Completion Notes below).
- **Interactive mode** (typing `gemini` with no flags — the real candidate path, since code-server's terminal is a genuine TTY) shows a "Choose your authentication method" picker on first launch **even when `GEMINI_API_KEY` is already set in the environment**, unless an auth method has already been selected and cached in `~/.gemini/settings.json` via `security.auth.selectedType`. A first-time candidate would be dropped into a menu they have no context for and no way to complete (no browser-based OAuth flow available from inside the container; picking anything other than "Use Gemini API key" would fail entirely; picking the right one requires knowing the CLI's own internal menu labels).
- Fix: bake `"security": {"auth": {"selectedType": "gemini-api-key"}}` into the image's `~/.gemini/settings.json` at build time (`docker/Dockerfile.codeserver`), analogous to the existing `"model": {"name": "gemini-2.5-flash"}` pin. This is the exact, version-matched field documented in the CLI's own bundled `reference/configuration.md`.

## Acceptance Criteria

1. `docker/Dockerfile.codeserver`'s baked-in `~/.gemini/settings.json` includes `security.auth.selectedType = "gemini-api-key"` alongside the existing `model.name` pin.
2. Rebuilding the image and starting a fresh container with `GEMINI_API_KEY`/`GEMINI_MODEL` env vars set (as `docker_service.py.create_container()` already does) produces a `~/.gemini/settings.json` that Gemini CLI parses without a configuration error.
3. Headless invocation (`gemini -p "..."`) continues to work unchanged post-fix (regression check against the Phase 2 migration's own verification).
4. No change to `docker_service.py` or any backend Python code — this is a container-image-only fix (env vars were already wired in Phase 2).
5. Guarded/unguarded AI-assistance mode is verified to still function correctly on Gemini CLI post-migration: with `/workspace/GEMINI.md` present (guarded), Gemini CLI declines to output complete solution code and instead gives conceptual/prose guidance only; with no `GEMINI.md` present (unguarded), Gemini CLI gives a complete working solution on request.

## Tasks / Subtasks

- [x] Confirm the auth gap exists (AC: none — investigation, not implementation)
  - [x] Read the installed CLI's own bundled `docs/get-started/authentication.md` and `docs/reference/configuration.md` (version-matched to the actual `@google/gemini-cli@0.49.0` baked into the image, not the public website)
  - [x] Confirmed `security.auth.selectedType` is the documented settings.json field, with `"gemini-api-key"` as the value that matches env-var-based auth

- [x] Apply the fix (AC: 1)
  - [x] `docker/Dockerfile.codeserver`: extended the existing `~/.gemini/settings.json` heredoc to include `"security": {"auth": {"selectedType": "gemini-api-key"}}` alongside `"model": {"name": "gemini-2.5-flash"}`
  - [x] Added a comment above the `RUN` line explaining why (first-run auth picker, even with `GEMINI_API_KEY` set)

- [x] Verify the fix (AC: 2, 3)
  - [x] Rebuilt `coding-platform-student:latest` from the updated Dockerfile
  - [x] Started a fresh container with `GEMINI_API_KEY`/`GEMINI_MODEL` env vars (matching what `docker_service.py.create_container()` passes) — `cat ~/.gemini/settings.json` showed the new field, no parse/validation error from the CLI
  - [x] Re-ran the same headless smoke prompt (`gemini -p "Reply with exactly: OK"`) — still returns `OK`, confirming no regression

- [x] Verify guarded/unguarded AI-assistance mode still works on Gemini CLI (AC: 5)
  - [x] Copied the real guarded-mode `GEMINI.md` content (matches `docker_service.py`'s `guarded_gemini_md` string) into a fresh container's `/workspace`
  - [x] Asked for a complete working solution to a coding problem (linked-list reversal) — Gemini CLI **declined** to output complete code, responding with conceptual/prose guidance only, explicitly citing "the guarded assessment rules of this session"
  - [x] Confirmed the inverse: the same prompt against a container **without** `GEMINI.md` present returned a complete, working, directly-runnable solution
  - [x] All test containers removed after verification

## Dev Notes

### Files Changed

| File | Action |
|------|--------|
| `docker/Dockerfile.codeserver` | UPDATE — `~/.gemini/settings.json` gains `security.auth.selectedType: "gemini-api-key"` |

No Python changes. `docker_service.py`'s `create_container()` already passes `GEMINI_API_KEY`/`GEMINI_MODEL` into every container (done in the Phase 2 migration) — this story only fixes what the CLI does with that env var on interactive first launch.

### Why this wasn't caught during the Phase 2 migration

The Phase 2 migration's own smoke test used `gemini -p "..." --output-format json` (headless mode) to validate the provider swap end-to-end quickly and non-interactively — a reasonable choice for automated verification, but headless and interactive auth are genuinely different code paths in Gemini CLI, and only interactive mode is what a candidate actually experiences typing into the code-server terminal. This story exists specifically to close that gap between "the API integration works" and "the candidate's actual first keystroke works."

### What NOT To Do

- Do NOT remove or change the `GEMINI_CLI_TRUST_WORKSPACE=true` env var — that's a separate concern (workspace trust prompt, not auth) and is unaffected by this fix.
- Do NOT change `docker_service.py` — the env vars it passes were already correct; only the baked-in CLI config needed updating.
- Do NOT attempt to disable or bypass Gemini's auth entirely (e.g. faking a cached OAuth token) — `security.auth.selectedType` pointing at the already-provided `GEMINI_API_KEY` is the CLI's own supported mechanism, not a workaround.

### Residual verification gap — CLOSED 2026-07-04

~~Direct capture of the interactive TUI auth picker...~~ Closed: the user confirmed live, in a real code-server terminal, that `gemini` starts straight into the REPL with `Authenticated with gemini-api-key /auth` shown in the banner — no auth-method picker appears. The fix holds in the actual candidate flow, not just in scripted verification.

### References

- [Source: `AGENT.md` Phase 2 — LLM Provider Migration: OpenRouter/Claude → Gemini (2026-07-04)]
- [Source: installed `@google/gemini-cli@0.49.0` bundled docs — `bundle/docs/get-started/authentication.md`, `bundle/docs/reference/configuration.md`]
- [Source: `docker/Dockerfile.codeserver`, `app/services/docker_service.py.create_container()`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Live Docker smoke tests: 5 disposable containers built/run/removed against the real `coding-platform-student:latest` image and a real `GEMINI_API_KEY`, no mocks.

### Completion Notes List

- Confirmed via the installed CLI's own bundled docs (not the website, to guarantee version match) that interactive `gemini` shows an auth-method picker on first launch even with `GEMINI_API_KEY` set, unless `security.auth.selectedType` is already recorded in `~/.gemini/settings.json`.
- Applied the one-line settings.json fix in `docker/Dockerfile.codeserver`; rebuilt the image; verified `cat ~/.gemini/settings.json` shows no parse error and headless mode (`gemini -p ...`) still returns correct output.
- Verified guarded/unguarded mode still functions correctly with Gemini CLI: guarded (`GEMINI.md` present) → Gemini explicitly declines to give complete code, gives conceptual guidance instead, citing "the guarded assessment rules of this session" verbatim; unguarded (no `GEMINI.md`) → Gemini gives a complete, correct, runnable solution. No code changes were needed here — the mechanism ported over from Claude Code CLI's `CLAUDE.md` convention to Gemini CLI's `GEMINI.md` convention cleanly during the Phase 2 migration and needed only verification, not a fix.
- All test containers removed; `coding-platform-student:latest` left rebuilt with the fix as the active image.

### File List

- `docker/Dockerfile.codeserver` (UPDATE)

## Change Log

- 2026-07-04: Story created retroactively to document an investigation + fix performed in response to a direct request to check Gemini CLI pre-authentication status following the Phase 2 provider migration.
- 2026-07-04: Investigation confirmed interactive-mode auth gap (headless mode was already fine); fix applied (`security.auth.selectedType` in baked-in settings.json); verified via rebuild + live container smoke tests; guarded/unguarded mode independently re-verified working correctly on Gemini CLI.
