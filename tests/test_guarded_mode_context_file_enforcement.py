"""Story 9.7 — guarded mode is enforced via a read-only Docker bind mount
established at container-creation time, not a post-start `docker cp` into
a world-writable /workspace.

The module-level `_run()` helper (subprocess wrapper) is monkeypatched so no
real Docker daemon is touched. Config.GUARDED_MODE_HOST_TMP_ROOT is
monkeypatched to a tmp_path-based directory so tests can assert on REAL
file content written to a real (test-scoped) location — this is the only
way to prove the mount args reference files containing the correct
restriction text, not just that _run was called with some string.

Residual gap (see story Dev Notes): these tests mock subprocess/Docker
entirely and cannot prove a real read-only bind mount actually blocks
deletion inside a real running container, or that a real installed Gemini
CLI actually reads ~/.gemini/GEMINI.md globally. That needs a live Docker
environment (see Story 9-6).
"""
import json
import os

import pytest

import app.services.docker_service as docker_service_module
from app.config import Config
from app.services.docker_service import DockerService


@pytest.fixture(autouse=True)
def _guarded_tmp_root(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "GUARDED_MODE_HOST_TMP_ROOT", str(tmp_path / "guarded-mode"))


def _fake_run_success(container_id="fake-container-id"):
    calls = []
    def fake_run(args, *a, **k):
        calls.append(args)
        if args[0] == "run":
            class Result:
                stdout = container_id
            return Result()
        return None
    return fake_run, calls


# ── create_container() guarded-mode bind mount ──────────────────────────────

def test_guarded_mode_writes_real_context_files_and_mounts_them_individually(monkeypatch):
    """The mount targets GEMINI.md and settings.json individually, NOT the
    ~/.gemini directory as a whole — a directory-level mount blocks every
    other file Gemini CLI writes there on launch (projects.json,
    installation_id, checkpoint cleanup), crashing the CLI with EROFS.
    File-level mounts leave those sibling writes working while still
    protecting the two restriction files themselves."""
    fake_run, calls = _fake_run_success()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    container_id, port, enforced = DockerService.create_container(
        "assignment-1", 7100, ai_assistance_mode="guarded")

    assert container_id == "fake-container-id"
    assert port == 7100
    assert enforced is True

    run_args = next(a for a in calls if a[0] == "run")
    mount_flags = [a for i, a in enumerate(run_args) if run_args[i - 1] == "-v"]
    assert len(mount_flags) == 2

    # Strip the known container-path+':ro' suffix from the END rather than
    # splitting on the first ':' — a Windows host path itself contains a
    # colon (e.g. "C:\...\gemini"), which naive front-splitting breaks.
    gemini_md_mount = next(m for m in mount_flags if m.endswith(":/home/coder/.gemini/GEMINI.md:ro"))
    settings_mount = next(m for m in mount_flags if m.endswith(":/home/coder/.gemini/settings.json:ro"))

    gemini_md_host_path = gemini_md_mount[: -len(":/home/coder/.gemini/GEMINI.md:ro")]
    settings_host_path = settings_mount[: -len(":/home/coder/.gemini/settings.json:ro")]

    # The mounted files must be REAL files with the correct content, not
    # just a string passed to a mocked _run.
    assert gemini_md_host_path.startswith(Config.GUARDED_MODE_HOST_TMP_ROOT)
    with open(gemini_md_host_path, encoding="utf-8") as f:
        gemini_content = f.read()
    assert "guarded mode" in gemini_content
    assert "Do NOT write or output a complete, working solution" in gemini_content

    with open(settings_host_path, encoding="utf-8") as f:
        settings_content = json.loads(f.read())
    assert settings_content["model"]["name"] == Config.GEMINI_MODEL
    assert settings_content["security"]["auth"]["selectedType"] == "gemini-api-key"


def test_unguarded_mode_adds_no_mount_flags(monkeypatch):
    fake_run, calls = _fake_run_success()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    container_id, port, enforced = DockerService.create_container(
        "assignment-1", 7100, ai_assistance_mode="unguarded")

    assert container_id == "fake-container-id"
    assert enforced is True

    run_args = next(a for a in calls if a[0] == "run")
    assert "-v" not in run_args
    assert not os.path.isdir(Config.GUARDED_MODE_HOST_TMP_ROOT)


def test_unguarded_is_the_default_when_mode_omitted(monkeypatch):
    fake_run, calls = _fake_run_success()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    container_id, port, enforced = DockerService.create_container("assignment-1", 7100)

    assert enforced is True
    run_args = next(a for a in calls if a[0] == "run")
    assert "-v" not in run_args


def test_host_file_write_failure_still_starts_container_unguarded(monkeypatch):
    fake_run, calls = _fake_run_success()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)
    monkeypatch.setattr(
        docker_service_module.os, "makedirs",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    container_id, port, enforced = DockerService.create_container(
        "assignment-1", 7100, ai_assistance_mode="guarded")

    # Container still starts — never block an assessment over this.
    assert container_id == "fake-container-id"
    assert enforced is False
    run_args = next(a for a in calls if a[0] == "run")
    assert "-v" not in run_args


def test_docker_run_failure_cleans_up_orphaned_host_directory(monkeypatch):
    def fake_run(args, *a, **k):
        if args[0] == "run":
            raise RuntimeError("docker run failed")
        return None
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    # create_container() swallows the generic Exception (not a port-conflict
    # CalledProcessError) and returns the (None, None, True) failure
    # contract rather than raising.
    container_id, port, enforced = DockerService.create_container(
        "assignment-2", 7101, ai_assistance_mode="guarded")

    assert container_id is None
    assert port is None
    assert enforced is True  # nothing to contradict — no container exists
    # No orphaned per-container directory left on the host.
    if os.path.isdir(Config.GUARDED_MODE_HOST_TMP_ROOT):
        assert os.listdir(Config.GUARDED_MODE_HOST_TMP_ROOT) == []


# ── cleanup_container() host-file cleanup ───────────────────────────────────

def test_cleanup_container_removes_guarded_mode_host_directory(monkeypatch, tmp_path):
    host_dir = tmp_path / "guarded-mode" / "assignment_x_abcd1234"
    gemini_dir = host_dir / "gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "GEMINI.md").write_text("restricted", encoding="utf-8")
    (gemini_dir / "settings.json").write_text("{}", encoding="utf-8")

    # Mount sources are the individual FILES (matching create_container()'s
    # file-level mounts), not the gemini/ directory as a whole.
    inspect_payload = json.dumps([{
        "Mounts": [
            {"Type": "bind", "Source": str(gemini_dir / "GEMINI.md"), "Destination": "/home/coder/.gemini/GEMINI.md"},
            {"Type": "bind", "Source": str(gemini_dir / "settings.json"), "Destination": "/home/coder/.gemini/settings.json"},
        ]
    }])

    def fake_run(args, check=True, capture=True):
        class Result:
            returncode = 0
            stdout = inspect_payload if args[0] == "inspect" else ""
        return Result()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    assert host_dir.exists()
    DockerService.cleanup_container("some-container-id")
    assert not host_dir.exists()


def test_cleanup_container_does_not_sweep_sibling_directory_with_extending_name(monkeypatch, tmp_path):
    """Regression test for the prefix-boundary bug found in code review:
    a raw string .startswith() on GUARDED_MODE_HOST_TMP_ROOT would also
    match a sibling directory whose name merely extends the root string
    (e.g. "...-guarded-mode-2"), incorrectly sweeping it."""
    real_root = tmp_path / "guarded-mode"
    real_dir = real_root / "assignment_x_abcd1234" / "gemini"
    real_dir.mkdir(parents=True)
    (real_dir / "GEMINI.md").write_text("restricted", encoding="utf-8")

    sibling_root = tmp_path / "guarded-mode-2"
    sibling_dir = sibling_root / "unrelated" / "gemini"
    sibling_dir.mkdir(parents=True)
    (sibling_dir / "GEMINI.md").write_text("unrelated content", encoding="utf-8")

    inspect_payload = json.dumps([{
        "Mounts": [
            {"Type": "bind", "Source": str(sibling_dir / "GEMINI.md"), "Destination": "/home/coder/.gemini/GEMINI.md"},
        ]
    }])

    def fake_run(args, check=True, capture=True):
        class Result:
            returncode = 0
            stdout = inspect_payload if args[0] == "inspect" else ""
        return Result()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    DockerService.cleanup_container("some-container-id")

    # The sibling directory (outside our real root) must NOT be swept.
    assert sibling_dir.exists()


def test_cleanup_container_tolerates_inspect_failure(monkeypatch):
    def fake_run(args, check=True, capture=True):
        class Result:
            returncode = 1
            stdout = ""
        return Result()
    monkeypatch.setattr(docker_service_module, "_run", fake_run)

    # Must not raise even though `docker inspect` "failed".
    DockerService.cleanup_container("some-container-id")


def test_cleanup_container_no_container_id_is_a_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(docker_service_module, "_run", lambda *a, **k: calls.append(a))
    DockerService.cleanup_container(None)
    assert calls == []
