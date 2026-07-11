"""Regression test: create_app() must configure logging even when the
process never went through run.py's logging.basicConfig() call — i.e. when
started via `flask run` (party-mode triage 2026-07-04; see deferred-work.md).
"""
import logging
import sys

from app import create_app


def test_create_app_configures_root_logger_when_unconfigured(monkeypatch):
    # Simulate a fresh process where nothing has touched the root logger yet
    # (run.py's own basicConfig call never ran — the `flask run` scenario).
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)
    try:
        create_app("testing")
        assert root.handlers, "create_app() should configure a handler when none exists"
        assert root.getEffectiveLevel() <= logging.INFO
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


def test_create_app_does_not_duplicate_handlers_when_already_configured():
    root = logging.getLogger()
    logging.basicConfig(level=logging.INFO)  # matches run.py's own call
    handler_count_before = len(root.handlers)
    create_app("testing")
    assert len(root.handlers) == handler_count_before


def test_create_app_reconfigures_stdout_stderr_to_utf8_when_unconfigured(monkeypatch):
    """Party-mode review 2026-07-11: a real Gemini response contained stray
    non-ASCII tokens (Bengali-script transliterations — a known small-model
    artifact). On Windows the console defaults to cp1252, so a logger call
    that ever interpolates raw model text could UnicodeEncodeError and
    abort mid-request. create_app()'s first-time-configuration path must
    reconfigure stdout/stderr to UTF-8 (replacing anything still
    unencodable) so that failure mode can't happen."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)

    calls = []

    class FakeStream:
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", FakeStream())
    monkeypatch.setattr(sys, "stderr", FakeStream())
    try:
        create_app("testing")
        assert calls == [
            {"encoding": "utf-8", "errors": "replace"},
            {"encoding": "utf-8", "errors": "replace"},
        ]
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)


def test_create_app_tolerates_stream_without_reconfigure(monkeypatch):
    """A stream lacking .reconfigure() (e.g. some test-capture wrappers)
    must not crash create_app() — the hasattr guard must actually protect
    this path, not just look like it does."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    root.handlers = []
    root.setLevel(logging.WARNING)

    class StreamWithoutReconfigure:
        pass

    monkeypatch.setattr(sys, "stdout", StreamWithoutReconfigure())
    monkeypatch.setattr(sys, "stderr", StreamWithoutReconfigure())
    try:
        create_app("testing")  # must not raise
        assert root.handlers
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
