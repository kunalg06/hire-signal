"""DockerService.inject_workspace_files() must report its outcome instead
of silently returning None on every path, so a caller can detect that
instructions.md/solution.py failed to write.

Story 9.7: guarded-mode's GEMINI.md/settings.json injection moved out of
this function entirely (now bind-mounted at container-creation time by
create_container() instead — see tests/test_guarded_mode_context_file_enforcement.py).
This file now only covers instructions.md/solution.py, this function's
original Story 6.1 scope.

The module-level `_run()` helper (subprocess wrapper) is monkeypatched so no
real Docker daemon is touched.
"""
import pytest

import app.services.docker_service as docker_service_module
from app.services.docker_service import DockerService


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """inject_workspace_files() sleeps 2s to let the container filesystem
    settle — skip that in tests, it's irrelevant to the logic under test."""
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)


def test_success_returns_injected_true(monkeypatch):
    monkeypatch.setattr(docker_service_module, "_run", lambda *a, **k: None)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code")

    assert result == {"injected": True}


def test_total_injection_failure_returns_injected_false(monkeypatch):
    def fake_run(args, *a, **k):
        raise RuntimeError("docker cp failed for instructions.md")
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code")

    assert result == {"injected": False}
