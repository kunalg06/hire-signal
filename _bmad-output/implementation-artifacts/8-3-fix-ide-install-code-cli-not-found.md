# Story 8.3: Fix `/ide install` "VS Code CLI not found" in code-server

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a candidate running `/ide install` inside Gemini CLI to get the IDE companion extension,
I want the install to actually succeed inside code-server,
so that I'm not blocked by an error referencing a `code` binary that doesn't exist in this environment.

## Background — how this was found

Found live: after confirming Story 8.1's auth fix worked (banner showed `Authenticated with gemini-api-key` with no picker), a user ran `/ide install` inside the real interactive `gemini` session in a code-server terminal and got:

```
✕ VS Code CLI not found. Please ensure 'code' is in your system's PATH.
```

## Investigation

Read the installed CLI's own bundled source (`bundle/chunk-VLV2BYPM.js`, the `VsCodeInstaller` class) directly rather than guessing:

- `/ide install` (for a detected VS-Code-family IDE) always searches for a binary literally named `code` (`code.cmd` on Windows) via a `findCommand()` helper that checks `PATH` plus a handful of hardcoded per-OS install locations (e.g. `/usr/share/code/bin/code`, `/snap/bin/code`) — there is no code-server-aware branch at all.
- If found, it runs `spawnSync(commandPath, ["--install-extension", "google.gemini-cli-vscode-ide-companion", "--force"])`.
- The student container (`docker/Dockerfile.codeserver`, `FROM codercom/code-server:latest`) ships `code-server` at `/usr/bin/code-server` — never a binary named `code`. Confirmed via `which code` (empty) / `which code-server` (`/usr/bin/code-server`).
- Confirmed `code-server --help` documents the identical `--install-extension <id> [--force]` flag surface the installer calls with.

**Fix**: symlink `/usr/local/bin/code → /usr/bin/code-server` at image build time. `findCommand()`'s plain PATH lookup for `code` then resolves to code-server, and the subsequent `spawnSync` call works unmodified since the flags are compatible.

## Acceptance Criteria

1. `docker/Dockerfile.codeserver` creates a `code` symlink pointing at `/usr/bin/code-server`.
2. Inside a freshly built container, `which code` resolves and `code --version` runs without error.
3. `code --install-extension google.gemini-cli-vscode-ide-companion --force` succeeds (exit 0, "was successfully installed" message) — verified as both `root` and the actual runtime user `coder`.
4. No regression: `gemini -p "..."` headless mode still works; full pytest suite still passes.

## Tasks / Subtasks

- [x] Diagnose (AC: none — investigation)
  - [x] Located the exact hardcoded `code`-binary search and error message in the installed CLI's own bundled source, not the website
  - [x] Confirmed code-server ships no `code` binary, only `code-server`
  - [x] Confirmed `code-server --help` supports the same `--install-extension`/`--force` flags the installer invokes

- [x] Apply the fix (AC: 1)
  - [x] Added `RUN ln -sf /usr/bin/code-server /usr/local/bin/code` to `docker/Dockerfile.codeserver`, placed while still `USER root` (right after the Gemini CLI npm install), before the `USER coder` switch

- [x] Verify (AC: 2, 3, 4)
  - [x] Rebuilt `coding-platform-student:latest`; fresh container: `which code` → `/usr/local/bin/code`; `code --version` → prints code-server's version banner
  - [x] `code --install-extension google.gemini-cli-vscode-ide-companion --force` succeeded as both `root` and `coder` (the actual runtime user) — "was successfully installed" both times
  - [x] `gemini -p "Reply with exactly: OK"` still returned `OK` post-fix (no regression)
  - [x] Full pytest suite (64 tests) still passes unchanged
  - [x] All test containers removed after verification

## Dev Notes

### Files Changed

| File | Action |
|------|--------|
| `docker/Dockerfile.codeserver` | UPDATE — adds a `code → code-server` symlink |

No Python changes — this is a container-image-only fix, same category as Story 8.1.

### What NOT To Do

- Do NOT assume the companion extension's deeper IDE-integration features (inline diff view, "connected to IDE" status, click-to-open-file) are fully verified — only the *install step* was confirmed to succeed. code-server's extension host is architecturally similar to desktop VS Code's (same Node.js extension host under the hood), so there's good reason to expect it works, but this story only closes the `/ide install` error, not a full IDE-companion functional audit. If deeper integration turns out to misbehave under code-server specifically, that's a separate, not-yet-investigated follow-up.
- Do NOT remove or rename the real `code-server` binary — the symlink is additive, the original binary and its own invocation path (`code-server` command, used by nothing in this codebase directly) are untouched.
- The IDE companion extension is entirely optional to this platform's actual workflow — candidates can ignore `/ide install` and use Gemini CLI purely via chat in the terminal with zero loss of core functionality (challenge instructions, code editing, submission). This fix removes a confusing dead-end error for candidates who try it, not a blocking dependency.

### References

- [Source: installed `@google/gemini-cli@0.49.0` bundled source — `bundle/chunk-VLV2BYPM.js`, `VsCodeInstaller` class]
- [Source: `docker/Dockerfile.codeserver`]
- [Source: `_bmad-output/implementation-artifacts/8-1-pre-authenticate-gemini-cli-in-student-container.md` — same container, same session's prior story, whose fix this user was actively confirming when they hit this new error]

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Live Docker tests: 2 disposable containers (pre-fix diagnosis, post-fix verification) built/run/removed against the real image.
- Read installed CLI's bundled `chunk-VLV2BYPM.js` directly (`VsCodeInstaller`/`findCommand`) to confirm the exact detection mechanism rather than guessing from generic VS Code CLI knowledge.

### Completion Notes List

- Root-caused a live user-reported error to Gemini CLI's `/ide install` hardcoding a search for a `code` binary that code-server never ships.
- Fixed with a one-line symlink (`code → code-server`) in `docker/Dockerfile.codeserver`, since code-server's `--install-extension`/`--force` flags are a drop-in match for what the installer invokes.
- Verified the extension actually installs (not just that the binary resolves) as both `root` and the real runtime user `coder`.
- No regression to headless Gemini CLI usage or the pytest suite.

### File List

- `docker/Dockerfile.codeserver` (UPDATE)

## Change Log

- 2026-07-04: Story created in response to a live user-reported `/ide install` failure, discovered while the user was confirming Story 8.1's auth fix in the real code-server terminal.
- 2026-07-04: Root-caused via the installed CLI's own bundled source; fixed with a `code → code-server` symlink; verified extension install succeeds as both root and the coder runtime user, with no regression to headless mode or the test suite.
