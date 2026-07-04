"""Regression test: create_app() must configure logging even when the
process never went through run.py's logging.basicConfig() call — i.e. when
started via `flask run` (party-mode triage 2026-07-04; see deferred-work.md).
"""
import logging

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
