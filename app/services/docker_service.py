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
        started with a READ-ONLY bind mount over the ENTIRE Gemini CLI
        global config directory (~/.gemini, containing GEMINI.md and
        settings.json), established as part of the `docker run` command
        itself — not copied in after the fact. This closes the
        honor-system gaps accepted in Story 6.5:
          - Gemini CLI always loads ~/.gemini/GEMINI.md regardless of the
            candidate's current working directory (unlike a workspace-local
            file), so `cd` elsewhere no longer skips the restriction.
          - The mount targets the DIRECTORY, not just the two files inside
            it — mounting only the files would leave the directory itself
            plain and candidate-writable (it's created under `USER coder`
            in the image), letting `mv ~/.gemini ~/.gemini_old && mkdir
            ~/.gemini` evict the mount from its expected path without ever
            touching the mounted files themselves. Linux's mount-busy
            protection only guards the mounted path itself, not an
            ancestor directory being renamed — mounting the directory
            makes ~/.gemini itself the protected boundary.
          - A read-only bind mount is enforced by the kernel at the mount-
            namespace level. Since this container is never run --privileged
            and is granted no extra capabilities, even a candidate who gains
            root inside the container cannot write to, remove, or unmount
            it — this is not a Unix-permission-bits trick, which
            in-container root always defeats.
          - settings.json (inside the mounted directory) closes a separate
            bypass: a writable settings.json would let a candidate
            reconfigure Gemini CLI's `context.fileName` to point at a
            different, unrestricted filename, sidestepping GEMINI.md
            entirely without ever touching it.

        KNOWN RESIDUAL GAP (not closed by this or any mount-based fix):
        Gemini CLI resolves ~/.gemini via the ordinary $HOME environment
        variable, which the candidate's own shell fully controls —
        `HOME=/tmp/x gemini` relocates the lookup to an unmounted path,
        finding no restriction file at all. No file-permission or mount
        scope change can close this; it requires network-level validation
        of the Gemini API calls leaving the container, a distinct, larger
        future story. See deferred-work.md.

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

                # Mount the whole directory, not the two files individually —
                # see docstring: a file-level mount leaves the directory
                # itself candidate-writable, which a parent-rename defeats.
                mount_args = [
                    '-v', f'{gemini_dir}:/home/coder/.gemini:ro',
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
    def inject_workspace_files(container_id: str, title: str, description: str,
                               criteria: str, starter_code: str) -> dict:
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

        Returns {'injected': bool} — False only if instructions.md/solution.py
        could not be written at all (rare/fatal container issue).
        """
        import time
        import tempfile

        # Allow the container filesystem to settle before copying
        time.sleep(2)

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
            root_with_sep = os.path.join(Config.GUARDED_MODE_HOST_TMP_ROOT, '')
            dirs_to_remove = {
                os.path.dirname(m.get('Source', ''))
                for m in info.get('Mounts', [])
                if m.get('Source', '').startswith(root_with_sep)
            }
            for d in dirs_to_remove:
                shutil.rmtree(d, ignore_errors=True)
        except Exception as e:
            logger.warning("Could not clean up guarded-mode host files for %s: %s", container_id[:12], e)
