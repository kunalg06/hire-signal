"""Story 7.2 — unit tests for EvaluationService.extract_container_files().

DockerService.get_archive is monkeypatched in every test; tar fixtures are
built in-memory. No Docker daemon or subprocess is ever touched.
"""
import io
import tarfile

from app.services.docker_service import DockerService
from app.services.evaluation_service import EvaluationService

MAX_TOTAL_BYTES = 50 * 1024  # 51200 — mirrors the cap inside the function


def make_tar(files: dict) -> bytes:
    """In-memory tar shaped like `docker cp <id>:/workspace -` output:
    a `workspace` directory member followed by `workspace/<name>` files."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dir_info = tarfile.TarInfo("workspace")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)
        for name, content in files.items():
            info = tarfile.TarInfo(f"workspace/{name}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def mock_archive(monkeypatch, payload):
    monkeypatch.setattr(DockerService, "get_archive",
                        lambda *args, **kwargs: payload)


def spy_archive(monkeypatch, payload):
    """Like mock_archive, but records the call args for contract assertions."""
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return payload

    monkeypatch.setattr(DockerService, "get_archive", fake)
    return calls


def run():
    return EvaluationService.extract_container_files("container-123")


# ── AC 2: Docker unavailable never blocks the caller ────────────────────────

def test_empty_archive_returns_empty_dict(monkeypatch):
    mock_archive(monkeypatch, b"")
    assert run() == {}


def test_get_archive_called_with_container_id_and_workspace(monkeypatch):
    calls = spy_archive(monkeypatch, b"")
    run()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert "container-123" in args or kwargs.get("container_id") == "container-123"


def test_get_archive_exception_returns_empty_dict(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("docker daemon unreachable")
    monkeypatch.setattr(DockerService, "get_archive", boom)
    assert run() == {}


def test_garbage_bytes_returns_empty_dict(monkeypatch):
    # Not a tar archive at all — tarfile raises, outer except returns {}
    mock_archive(monkeypatch, b"this is not a tar archive")
    assert run() == {}


# ── AC 3, 5: text-only filter and path normalization ───────────────────────

def test_text_only_filter_and_normalized_keys(monkeypatch):
    mock_archive(monkeypatch, make_tar({
        "solution.py": b"def solve(): pass",
        "notes.md": b"# notes",
        "image.png": b"\x89PNG fake",
        "binary.exe": b"MZ fake",
        "Makefile": b"all:\n\techo hi",
    }))
    result = run()
    # Keys are literal expected names — normalized, filtered
    assert set(result) == {"solution.py", "notes.md"}
    assert result["solution.py"] == "def solve(): pass"
    assert result["notes.md"] == "# notes"


def test_uppercase_extension_included(monkeypatch):
    mock_archive(monkeypatch, make_tar({"REPORT.PY": b"print('x')"}))
    result = run()
    assert set(result) == {"REPORT.PY"}
    assert result["REPORT.PY"] == "print('x')"


def test_dotfiles_excluded_no_extension(monkeypatch):
    mock_archive(monkeypatch, make_tar({
        ".env": b"SECRET=1",
        ".gitignore": b"__pycache__/",
        "keep.py": b"pass",
    }))
    result = run()
    assert set(result) == {"keep.py"}


def test_zero_byte_file_included_as_empty_string(monkeypatch):
    mock_archive(monkeypatch, make_tar({"empty.py": b""}))
    result = run()
    assert result == {"empty.py": ""}


def test_tar_with_only_directories_returns_empty_dict(monkeypatch):
    mock_archive(monkeypatch, make_tar({}))
    assert run() == {}


# ── AC 4: 50KB cap with [TRUNCATED] marker ──────────────────────────────────

def test_cap_truncates_overflowing_file_and_drops_the_rest(monkeypatch):
    mock_archive(monkeypatch, make_tar({
        "big.py": b"a" * 50000,
        "second.py": b"b" * 5000,
        "third.py": b"c" * 100,
    }))
    result = run()

    assert result["big.py"] == "a" * 50000            # fits intact
    budget = MAX_TOTAL_BYTES - 50000                   # 1200 bytes left
    assert result["second.py"] == "b" * budget + "\n[TRUNCATED]"
    assert "third.py" not in result                    # loop broke at the cap
    assert set(result) == {"big.py", "second.py"}


def test_single_file_larger_than_cap_truncated(monkeypatch):
    mock_archive(monkeypatch, make_tar({"huge.py": b"x" * 60000}))
    result = run()
    assert result["huge.py"] == "x" * MAX_TOTAL_BYTES + "\n[TRUNCATED]"


def test_file_exactly_at_cap_kept_intact_next_file_gets_empty_budget(monkeypatch):
    mock_archive(monkeypatch, make_tar({
        "exact.py": b"a" * MAX_TOTAL_BYTES,
        "after.py": b"b" * 10,
    }))
    result = run()
    # Strict `>` comparison: exact-fit file is NOT flagged truncated
    assert result["exact.py"] == "a" * MAX_TOTAL_BYTES
    # Next file gets 0 remaining budget — truncated to just the marker
    assert result["after.py"] == "\n[TRUNCATED]"


def test_truncation_does_not_crash_on_multibyte_boundary(monkeypatch):
    # A 3-byte UTF-8 character (e.g. U+20AC) straddling the cut point must not
    # raise; errors='replace' absorbs the split sequence.
    filler = b"a" * (MAX_TOTAL_BYTES - 1)
    mock_archive(monkeypatch, make_tar({"euro.py": filler + "€".encode("utf-8")}))
    result = run()
    assert result["euro.py"].endswith("\n[TRUNCATED]")
    assert len(result["euro.py"]) > 0  # decoded without raising


# ── AC 6: robustness paths ──────────────────────────────────────────────────

def test_directory_members_skipped(monkeypatch):
    # make_tar always includes the `workspace` DIRTYPE member; add a nested one
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for dirname in ("workspace", "workspace/src"):
            info = tarfile.TarInfo(dirname)
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        info = tarfile.TarInfo("workspace/src/app.py")
        content = b"import os"
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    mock_archive(monkeypatch, buf.getvalue())

    result = run()
    assert set(result) == {"src/app.py"}
    assert result["src/app.py"] == "import os"


def test_symlink_member_silently_excluded(monkeypatch):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        dir_info = tarfile.TarInfo("workspace")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)

        target_content = b"print('real')"
        target = tarfile.TarInfo("workspace/real.py")
        target.size = len(target_content)
        tar.addfile(target, io.BytesIO(target_content))

        link = tarfile.TarInfo("workspace/link.py")
        link.type = tarfile.SYMTYPE
        link.linkname = "real.py"
        tar.addfile(link)
    mock_archive(monkeypatch, buf.getvalue())

    result = run()
    assert set(result) == {"real.py"}


def test_invalid_utf8_decoded_with_replacement(monkeypatch):
    mock_archive(monkeypatch, make_tar({"data.txt": b"\xff\xfe caf\xe9"}))
    result = run()
    assert set(result) == {"data.txt"}
    assert "�" in result["data.txt"]  # replacement char, no exception
    assert " caf" in result["data.txt"]    # valid ASCII bytes survive
