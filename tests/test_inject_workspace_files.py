"""Story 9.3 — DockerService.inject_workspace_files() must report its
outcome instead of silently returning None on every path, so a caller can
detect a guarded-mode GEMINI.md injection failure instead of the assessment
silently running unguarded.

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


def test_guarded_mode_success_returns_enforced_true(monkeypatch):
    monkeypatch.setattr(docker_service_module, "_run", lambda *a, **k: None)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code", ai_assistance_mode="guarded")

    assert result == {"injected": True, "guarded_mode_enforced": True}


def test_guarded_mode_gemini_md_failure_returns_enforced_false(monkeypatch):
    def fake_run(args, *a, **k):
        if "GEMINI.md" in " ".join(args):
            raise RuntimeError("docker cp failed for GEMINI.md")
        return None
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code", ai_assistance_mode="guarded")

    # Base files still got copied (instructions.md/solution.py) — only the
    # inner GEMINI.md try/except failed, so injected stays True.
    assert result == {"injected": True, "guarded_mode_enforced": False}


def test_unguarded_mode_returns_enforced_true_trivially(monkeypatch):
    calls = []
    def fake_run(args, *a, **k):
        calls.append(args)
        return None
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code", ai_assistance_mode="unguarded")

    assert result == {"injected": True, "guarded_mode_enforced": True}
    assert not any("GEMINI.md" in " ".join(c) for c in calls)


def test_total_injection_failure_returns_injected_false(monkeypatch):
    def fake_run(args, *a, **k):
        raise RuntimeError("docker cp failed for instructions.md")
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    result = DockerService.inject_workspace_files(
        container_id="container-x", title="T", description="D",
        criteria="C", starter_code="code", ai_assistance_mode="guarded")

    assert result == {"injected": False, "guarded_mode_enforced": False}
