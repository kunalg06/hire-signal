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

    @staticmethod
    def get_file_from_container(container_id: str, file_path: str):
        """Extract a single file from a running container. Returns text or None."""
        if not container_id:
            return None
        try:
            result = _run(['cp', f'{container_id}:{file_path}', '-'])
            # docker cp - streams a tar archive to stdout (bytes via text=False needed)
            result2 = subprocess.run(
                ['docker', 'cp', f'{container_id}:{file_path}', '-'],
                capture_output=True, check=True,
            )
            with tarfile.open(fileobj=io.BytesIO(result2.stdout)) as tar:
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
                               criteria: str, starter_code: str,
                               ai_assistance_mode: str = 'unguarded'):
        """
        Write instructions.md and solution.py into /workspace immediately
        after container creation. Story 6.1 three-panel format used for
        instructions.md so the candidate sees a structured brief inside VS Code.

        Story 6.5: when ai_assistance_mode == 'guarded', also writes a
        GEMINI.md into /workspace. Gemini CLI (installed in the student
        container, see docker/Dockerfile.codeserver) auto-loads GEMINI.md
        from its working directory as a context file, attempting to
        restrict the candidate's in-session Gemini responses to conceptual
        guidance only. This is a prompt-level request, not enforced access
        control — the candidate has shell access and can edit or delete the
        file (see Story 6.5 Review Findings for the accepted v1 tradeoff).
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

        guarded_gemini_md = """# Assessment Mode: Guarded

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

                # Story 6.5: guarded mode restricts the candidate's in-session
                # Gemini CLI via an auto-loaded GEMINI.md in the workdir.
                # Isolated in its own try/except so a failure here can't skip
                # the chmod below for the already-copied instructions.md/solution.py.
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
