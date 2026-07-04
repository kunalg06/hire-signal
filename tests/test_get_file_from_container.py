"""Regression test for DockerService.get_file_from_container() — party-mode
triage 2026-07-04 (see deferred-work.md).

The function used to make a dead first call via the module's `_run()` helper
(text=True), which raised UnicodeDecodeError on binary/non-UTF-8 tar content
before the real, working binary-mode subprocess.run() call two lines below
ever executed — so the "working" call was unreachable for non-UTF-8 files
and the function silently returned None. subprocess.run is monkeypatched
here; no real Docker daemon is touched.
"""
import io
import tarfile
from types import SimpleNamespace

from app.services.docker_service import DockerService
import app.services.docker_service as docker_service_module


def make_tar_with_file(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def test_non_utf8_file_content_is_still_returned(monkeypatch):
    # 0xFF is not valid UTF-8 on its own — this is exactly the shape of
    # content that made the old text=True dead call crash before the
    # working binary-mode call ever ran.
    non_utf8 = b"before\xff\xfeafter"
    tar_bytes = make_tar_with_file("solution.py", non_utf8)

    def fake_run(args, capture_output=True, check=True):
        assert args == ["docker", "cp", "container-x:/workspace/solution.py", "-"]
        return SimpleNamespace(stdout=tar_bytes)

    monkeypatch.setattr(docker_service_module.subprocess, "run", fake_run)

    result = DockerService.get_file_from_container("container-x", "/workspace/solution.py")

    assert result is not None
    assert "before" in result and "after" in result


def test_no_container_id_returns_none():
    assert DockerService.get_file_from_container(None, "/workspace/solution.py") is None
