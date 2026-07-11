"""
Docker operations via CLI subprocess.
The Docker Python SDK (docker==7.0.0) is incompatible with requests>=2.32
on Python 3.14 (URLSchemeUnknown for http+docker). Using subprocess + docker
CLI is more reliable and has zero SDK version dependencies.
"""
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile

logger = logging.getLogger(__name__)

from app.config import Config


def _run(args: list[str], check=True, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['docker'] + args,
        capture_output=capture,
        text=True,
        check=check,
    )


# Story 9.7: guarded-mode context files, delivered as read-only bind mounts
# at container-creation time rather than copied in after the container
# starts — see DockerService.create_container()'s docstring for why.
#
# Party-mode review 2026-07-11: a real candidate session showed Gemini
# violating the previous (looser) wording under mild pressure — "based on
# above fixes solve it for me" got a direct fix applied, and an unprompted
# "what else is required?" got the ENTIRE remaining bug list handed over
# plus a full unittest sample, with zero pushback. The candidate never
# formed a hypothesis or asked a targeted question at any point, yet
# finished feeling confident. This rewrite adds two hard rules closing
# that gap: never comply with an unqualified "solve/fix it for me" without
# redirecting first, and never enumerate more than one issue per response.
_GUARDED_MODE_GEMINI_MD = """# Assessment Mode: Guarded

You are assisting a candidate during a technical assessment in **guarded mode**.
Guarded mode does not block AI assistance — it treats you as a collaborator,
similar to how the candidate would use an AI pair-programmer on the job. Your
conversation with the candidate is visible to the employer reviewing this
assessment, so treat this as a real working session, not a loophole to guard
against.

Hard rules for this session:
- If the candidate asks you to solve, fix, or complete something for them
  WITHOUT first stating their own diagnosis, hypothesis, or a specific
  symptom (e.g. "solve it for me", "fix this", "what's wrong with this
  code", "what else do I need to do"), do NOT do it. Instead, ask a
  question that hands the reasoning back to them — e.g. "What have you
  tried so far?", "Which part of the output looks wrong to you?", or
  "Walk me through what you expect this to do." Only after they answer
  with something concrete may you engage with the specifics.
- Never list, enumerate, or summarize multiple bugs/issues/remaining work
  in a single response, even if asked directly ("what else is needed?").
  Address at most the ONE specific, concrete thing the candidate just
  raised. If they haven't pointed at anything specific yet, redirect them
  to look first rather than surveying the code for them.
- You MAY show short, targeted code (a corrected line, a small snippet, a
  function signature) ONCE the candidate has stated their own hypothesis or
  pointed at a specific symptom. Never as your opening move, and never as a complete, ready-to-submit solution.
- You MAY point to WHERE in the code an issue is, and explain your
  reasoning in prose, once the candidate has genuinely engaged with the
  problem themselves.
- Never volunteer encouragement like "you're ready to submit" or generate
  a full test suite unprompted — whether the work is done is the
  candidate's judgment to reach, not yours to hand them.
- Encourage the candidate to understand and adapt anything you give them,
  rather than just pasting it in unread.

This mode measures how well the candidate collaborates with AI — asking
good questions, verifying your output, and iterating — not whether they
can avoid using AI entirely. A candidate who never forms their own
hypothesis should leave the conversation without a fix, not with one.
"""

_GUARDED_MODE_SETTINGS_JSON = json.dumps({
    "model": {"name": Config.GEMINI_MODEL},
    "security": {"auth": {"selectedType": "gemini-api-key"}},
})


class DockerService:

    @classmethod
    def get_client(cls):
        """Return True if Docker CLI is reachable, None otherwise."""
        try:
            _run(['info'], check=True)
            return True
        except Exception:
            return None

    @staticmethod
    def create_container(assignment_id: str, port: int,
                          ai_assistance_mode: str = Config.DEFAULT_ASSISTANCE_MODE):
        """
        Spin up a student code-server container.

        Story 9.7: when ai_assistance_mode == 'guarded', the container is
        started with READ-ONLY bind mounts over GEMINI.md and settings.json
        inside the Gemini CLI global config directory (~/.gemini),
        established as part of the `docker run` command itself — not
        copied in after the fact. This closes the honor-system gaps
        accepted in Story 6.5:
          - Gemini CLI always loads ~/.gemini/GEMINI.md regardless of the
            candidate's current working directory (unlike a workspace-local
            file), so `cd` elsewhere no longer skips the restriction.
          - A read-only bind mount is enforced by the kernel at the mount-
            namespace level. Since this container is never run --privileged
            and is granted no extra capabilities, even a candidate who gains
            root inside the container cannot write to or remove either
            mounted file directly — this is not a Unix-permission-bits
            trick, which in-container root always defeats.
          - settings.json closes a separate bypass: a writable settings.json
            would let a candidate reconfigure Gemini CLI's `context.fileName`
            to point at a different, unrestricted filename, sidestepping
            GEMINI.md entirely without ever touching it.

        These are FILE-level mounts, not a directory-level mount over all
        of ~/.gemini — Gemini CLI writes several other files there on every
        launch (project registry `projects.json`, `installation_id`,
        checkpoint/tool-output cleanup), and a directory-wide :ro mount
        makes every one of those writes throw EROFS and crash the CLI
        outright (discovered live: guarded-mode containers were completely
        unusable under the directory-level mount). File-level mounts leave
        those sibling writes working normally.

        KNOWN RESIDUAL GAPS (not closed by this or any mount-based fix):
          - Gemini CLI resolves ~/.gemini via the ordinary $HOME environment
            variable, which the candidate's own shell fully controls —
            `HOME=/tmp/x gemini` relocates the lookup to an unmounted path,
            finding no restriction file at all.
          - `mv ~/.gemini ~/.gemini_old && mkdir ~/.gemini` evicts the mount
            from its expected path without ever touching the mounted files
            themselves, since Linux's mount-busy protection only guards the
            mounted path itself, not an ancestor directory being renamed.
            (A directory-level mount would close this specific bypass, but
            at the cost of breaking the CLI entirely — not worth it given
            the strictly-easier $HOME bypass above is already open.)
        No file-permission or mount scope change closes these; it requires
        network-level validation of the Gemini API calls leaving the
        container, a distinct, larger future story. See deferred-work.md.

        Returns (container_id, port, guarded_mode_enforced) on success, or
        (None, None, True) if no container was ever created — the True
        mirrors the existing convention in app/routes/links.py's own
        default: nothing to enforce when there's no assessment to
        contradict. guarded_mode_enforced is False only when
        ai_assistance_mode == 'guarded' AND the host-side context files
        could not be prepared.
        """
        name = f"assignment_{assignment_id}_{os.urandom(4).hex()}"
        image = Config.DOCKER_IMAGE

        guarded_mode_enforced = (ai_assistance_mode != 'guarded')
        host_dir = None
        mount_args = []

        if ai_assistance_mode == 'guarded':
            try:
                host_dir = os.path.join(Config.GUARDED_MODE_HOST_TMP_ROOT, name)
                gemini_dir = os.path.join(host_dir, 'gemini')
                os.makedirs(gemini_dir, exist_ok=True)

                gemini_md_path = os.path.join(gemini_dir, 'GEMINI.md')
                with open(gemini_md_path, 'w', encoding='utf-8') as f:
                    f.write(_GUARDED_MODE_GEMINI_MD)

                settings_path = os.path.join(gemini_dir, 'settings.json')
                with open(settings_path, 'w', encoding='utf-8') as f:
                    f.write(_GUARDED_MODE_SETTINGS_JSON)

                # File-level mounts, not the whole directory: Gemini CLI writes
                # several other files under ~/.gemini on every launch (project
                # registry, installation ID, checkpoint/tool-output cleanup) —
                # a directory-wide :ro mount makes all of those throw EROFS and
                # crash the CLI outright. The mv-rename bypass this reopens
                # (mv ~/.gemini ~/.gemini_old && mkdir ~/.gemini) is strictly
                # weaker than the already-accepted `HOME=/tmp/x gemini` bypass
                # documented above, so this trades a broken CLI for a residual
                # gap no worse than one already in scope.
                mount_args = [
                    '-v', f'{gemini_dir}/GEMINI.md:/home/coder/.gemini/GEMINI.md:ro',
                    '-v', f'{gemini_dir}/settings.json:/home/coder/.gemini/settings.json:ro',
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

    @staticmethod
    def get_file_from_container(container_id: str, file_path: str):
        """Extract a single file from a running container. Returns text or None."""
        if not container_id:
            return None
        try:
            # docker cp - streams a tar archive to stdout; must run in binary
            # mode (no text=True) since tar content is not guaranteed UTF-8.
            result = subprocess.run(
                ['docker', 'cp', f'{container_id}:{file_path}', '-'],
                capture_output=True, check=True,
            )
            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        f = tar.extractfile(member)
                        return f.read().decode('utf-8', errors='ignore') if f else None
        except Exception as e:
            logger.debug("  Could not read %s: %s", file_path, str(e)[:60])
        return None

    @staticmethod
    def get_archive(container_id: str, workspace: str = '/workspace') -> bytes:
        """Return raw tar bytes for the workspace directory."""
        try:
            result = subprocess.run(
                ['docker', 'cp', f'{container_id}:{workspace}', '-'],
                capture_output=True, check=True,
            )
            return result.stdout
        except Exception as e:
            logger.warning("get_archive failed for %s: %s", container_id, e)
            return b''

    @staticmethod
    def get_gemini_chat_files(container_id: str) -> dict:
        """
        Pull every Gemini CLI session transcript (.jsonl) out of the
        container's ~/.gemini/tmp tree. Returns {relative_path: content}.

        Gemini CLI writes one file per `gemini` invocation to
        ~/.gemini/tmp/<workspace-dirname>/chats/session-<timestamp>-<hash>.jsonl
        (confirmed empirically by inspecting a real container — see
        AGENT.md's session-log-capture-fix entry). The workspace-dirname
        component isn't hardcoded here (it derives from the CLI's own
        project-hashing, not something this codebase controls), so the
        whole ~/.gemini/tmp tree is pulled and filtered to '.jsonl' files
        under a 'chats/' path segment, rather than assuming an exact
        subdirectory name.

        Mirrors EvaluationService.extract_container_files()'s tar-pull
        pattern (get_archive + tarfile unpack) rather than duplicating a
        second copy of that logic inline.
        """
        if not container_id:
            return {}
        try:
            raw = DockerService.get_archive(container_id, '/home/coder/.gemini/tmp')
            if not raw:
                return {}
            files = {}
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                for member in tar.getmembers():
                    if not member.isfile() or not member.name.endswith('.jsonl'):
                        continue
                    if '/chats/' not in f'/{member.name}':
                        continue
                    f = tar.extractfile(member)
                    if not f:
                        continue
                    files[member.name] = f.read().decode('utf-8', errors='replace')
            return files
        except Exception as e:
            logger.warning("get_gemini_chat_files failed for %s: %s", container_id, e)
            return {}

    @staticmethod
    def inject_workspace_files(container_id: str, title: str, description: str,
                               criteria: str, starter_code: str,
                               decision_point: dict = None) -> dict:
        """
        Write instructions.md and solution.py into /workspace immediately
        after container creation. Story 6.1 three-panel format used for
        instructions.md so the candidate sees a structured brief inside VS Code.

        Story 9.7: guarded-mode's GEMINI.md/settings.json no longer go
        through this function — they're bind-mounted at container-creation
        time by create_container() instead, since Gemini CLI's global
        context file needs to exist from the container's first instant and
        be read-only, neither of which a post-start `docker cp` into a
        world-writable /workspace could guarantee.

        decision_point (optional, party-mode review 2026-07-11): when the
        challenge has a genuine design fork ({'applies': True, 'prompt',
        'option_a', 'option_b'}), instructions.md gets a section asking the
        candidate to record their choice + justification in DECISION.md —
        which EvaluationService.extract_container_files() already pulls
        into the scoring snapshot as an ordinary workspace file, so no new
        capture plumbing is needed for the scorer to see it.

        Returns {'injected': bool} — False only if instructions.md/solution.py
        could not be written at all (rare/fatal container issue).
        """
        import time
        import tempfile

        # Allow the container filesystem to settle before copying
        time.sleep(2)

        decision_section = ""
        if decision_point and decision_point.get('applies'):
            decision_section = f"""
---

## Decision Point
This challenge has a genuine design trade-off — there is no single "right"
answer, only different consequences:

**{decision_point.get('prompt', '')}**
- **Option A:** {decision_point.get('option_a', '')}
- **Option B:** {decision_point.get('option_b', '')}

Pick one, implement it, and create a `DECISION.md` file in your workspace
explaining which you chose and why (what you'd expect to break or degrade
under the option you didn't pick). This is part of what's scored — a
confident justification for either option is worth more than picking the
"popular" one with no reasoning.
"""

        instructions = f"""# {title}

---

## Scenario
{description}

---

## Your Task
Review the starter code in `solution.py`. Complete the implementation
according to the scenario above. Run and test your solution using the
integrated terminal (Ctrl+`).

Use AI tools freely — you are evaluated on **how well you collaborate
with AI**, not on writing code without assistance.

**What's actually scored:** the reasoning behind your work — the questions
you ask, how you verify what the AI gives you, and the decisions you
make — not just whether the final code runs, and not how fast you finish.
Asking AI to solve this end-to-end will score lower than a slower session
that shows real back-and-forth, even if both submissions produce working
code. The AI assistant can occasionally make mistakes or say odd things —
noticing that and not blindly accepting it is also part of what's assessed.
{decision_section}
---

## Evaluation Criteria
{criteria}

---

## How to Submit
When finished, click **Submit Assessment** in the top bar of this page.
Save all files first (Ctrl+S).
"""

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

                # docker cp writes files as root — make them writable by the coder user
                chmod_paths = ['/workspace/instructions.md', '/workspace/solution.py']

                _run([
                    'exec', '-u', 'root', container_id,
                    'chmod', '666',
                    *chmod_paths,
                ], check=False)
                logger.debug("  Permissions set on workspace files in %s", container_id[:12])

            return {'injected': True}

        except Exception as e:
            logger.warning("workspace injection failed for %s: %s", container_id[:12], e)
            return {'injected': False}

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
        separately, so this works regardless of caller. Best-effort: must
        never block the container removal that follows it. Must run
        BEFORE `docker rm` — the container has to still exist for
        `docker inspect` to return anything."""
        try:
            result = _run(['inspect', container_id], check=False)
            if result.returncode != 0 or not result.stdout:
                return
            info = json.loads(result.stdout)[0]
            # Compare against the root PLUS a path separator, not a raw
            # string prefix — otherwise a sibling directory whose name
            # merely extends the root string (e.g. "...-guarded-mode-2")
            # would incorrectly match and get swept too.
            # Source is now a file two levels below the per-assignment host
            # directory (.../<name>/gemini/GEMINI.md), not the gemini/
            # directory itself — dirname() twice to reach the directory
            # create_container() actually created and needs removed.
            root_with_sep = os.path.join(Config.GUARDED_MODE_HOST_TMP_ROOT, '')
            dirs_to_remove = {
                os.path.dirname(os.path.dirname(m.get('Source', '')))
                for m in info.get('Mounts', [])
                if m.get('Source', '').startswith(root_with_sep)
            }
            for d in dirs_to_remove:
                shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            logger.warning("Could not clean up guarded-mode host files for %s: %s", container_id[:12], e)
