"""Tests for the session-log capture fix (2026-07-10): Gemini CLI's real
on-disk session transcript format was empirically confirmed by inspecting a
live running container (docker exec / find / cat), not guessed at — see
AGENT.md's session-log-capture-fix entry for the full investigation. This
file covers SessionLogService.parse_gemini_chat_session[s]() against
schema-accurate fixtures built from that investigation, and
DockerService.get_gemini_chat_files()'s tar-pull/filter logic.

Real per-line shapes confirmed live:
- header line: {"sessionId", "projectHash", "startTime", "lastUpdated", "kind"}
  - kind="main" is a real candidate<->Gemini conversation.
  - kind="subagent" is Gemini's own internal tool-use session (e.g. it
    spawns one to run `git status`/`git log` for its own context-gathering)
    — never candidate-authored, must be excluded entirely.
- {"$set": {"lastUpdated": ...}} — metadata-only bump, no message content.
- {"$set": {"messages": [...]}} — wraps the session's first message(s).
- bare message: {"id", "timestamp", "type": "user"|"gemini", "content", ...}
  - user content: list of {"text": "..."} (real candidate prompt) or
    {"functionResponse": {...}} (tool-call result being fed back, not
    candidate-authored).
  - gemini content: a plain string, possibly "" while the model is still
    "thinking"/making tool calls (real reply arrives as a later message).
"""
import io
import json
import tarfile

from app.services.docker_service import DockerService
from app.services.session_log_service import SessionLogService


def _line(obj) -> str:
    return json.dumps(obj)


def make_main_session(session_id="s1", messages=None) -> str:
    header = {"sessionId": session_id, "projectHash": "hash1",
              "startTime": "2026-07-10T13:39:31.000Z",
              "lastUpdated": "2026-07-10T13:39:31.000Z", "kind": "main"}
    lines = [_line(header)]
    for m in (messages or []):
        lines.append(_line(m))
        lines.append(_line({"$set": {"lastUpdated": m.get("timestamp", "")}}))
    return "\n".join(lines)


SESSION_CONTEXT_MSG = {
    "id": "ctx-1", "timestamp": "2026-07-10T13:39:31.100Z", "type": "user",
    "content": [{"text": "<session_context>\nThis is the Gemini CLI...\n</session_context>"}],
}


def user_msg(msg_id, timestamp, text):
    return {"id": msg_id, "timestamp": timestamp, "type": "user",
            "content": [{"text": text}]}


def tool_result_msg(msg_id, timestamp):
    return {"id": msg_id, "timestamp": timestamp, "type": "user",
            "content": [{"functionResponse": {"id": "x", "name": "read_file", "response": {"output": "..."}}}]}


def gemini_thinking_msg(msg_id, timestamp, tool_calls=None):
    """A 'thinking'/tool-calling turn: empty content, no visible reply yet."""
    return {"id": msg_id, "timestamp": timestamp, "type": "gemini", "content": "",
            "thoughts": [{"subject": "x", "description": "y", "timestamp": timestamp}],
            "toolCalls": tool_calls or []}


def gemini_reply_msg(msg_id, timestamp, text):
    return {"id": msg_id, "timestamp": timestamp, "type": "gemini", "content": text}


# ── parse_gemini_chat_session(): single-file parsing ────────────────────────

def test_skips_the_auto_injected_session_context_message():
    content = make_main_session(messages=[
        {"$set": {"messages": [SESSION_CONTEXT_MSG]}},
        user_msg("u1", "2026-07-10T13:39:32.000Z", "What does is_even do?"),
        gemini_reply_msg("g1", "2026-07-10T13:39:40.000Z", "It checks divisibility by 2."),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["prompt"] == "What does is_even do?"
    assert entries[0]["response_summary"] == "It checks divisibility by 2."


def test_subagent_session_is_excluded_entirely():
    header = {"sessionId": "sub-1", "projectHash": "hash1",
              "startTime": "t", "lastUpdated": "t", "kind": "subagent"}
    content = "\n".join([
        _line(header),
        _line(user_msg("u1", "t1", "run git status")),
        _line(gemini_reply_msg("g1", "t2", "Here is the git status output.")),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert entries == []


def test_functionresponse_turns_are_not_treated_as_candidate_prompts():
    content = make_main_session(messages=[
        user_msg("u1", "t1", "Why does average() crash?"),
        gemini_thinking_msg("g1", "t2", tool_calls=[{"name": "read_file"}]),
        tool_result_msg("u2", "t3"),
        gemini_reply_msg("g2", "t4", "Because len(nums) can be 0."),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["prompt"] == "Why does average() crash?"
    assert entries[0]["response_summary"] == "Because len(nums) can be 0."


def test_thinking_only_turns_with_empty_content_are_skipped_for_the_final_reply():
    """A gemini message with empty content (still 'thinking'/tool-calling)
    must not be captured as the response — only the later, real reply."""
    content = make_main_session(messages=[
        user_msg("u1", "t1", "Fix the bug in is_even"),
        gemini_thinking_msg("g1", "t2"),
        gemini_reply_msg("g2", "t3", "The comparison should check == 0, not == 1."),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["response_summary"] == "The comparison should check == 0, not == 1."


def test_trailing_unpaired_prompt_is_dropped_not_persisted_with_empty_response():
    """Session ends mid-turn (e.g. connection dropped) — the last prompt
    has no reply yet and must not be persisted with a blank response."""
    content = make_main_session(messages=[
        user_msg("u1", "t1", "What does is_even do?"),
        gemini_reply_msg("g1", "t2", "Checks divisibility by 2."),
        user_msg("u2", "t3", "Now fix it"),
        # session ends here — no gemini reply for u2
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["prompt"] == "What does is_even do?"


def test_duplicate_message_id_keeps_last_occurrence():
    """The CLI can append the same message id twice as it streams/finalizes
    a turn — later occurrence must win, not be treated as two entries."""
    content = make_main_session(messages=[
        user_msg("u1", "t1", "Explain the bug"),
        gemini_thinking_msg("g1", "t2"),                      # first occurrence: empty
        gemini_thinking_msg("g1", "t2"),                      # duplicate id, still empty
        gemini_reply_msg("g2", "t3", "It's an off-by-one error."),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["response_summary"] == "It's an off-by-one error."


def test_file_changes_count_accumulated_from_intermediate_thinking_messages():
    """Real toolCalls live on intermediate 'thinking' (empty-content)
    messages, not the final reply — confirmed empirically, the final
    reply message essentially never carries its own toolCalls. A
    different message id is used for the thinking step vs. the final
    reply, matching real captured data (they are NOT the same id
    evolving)."""
    content = make_main_session(messages=[
        user_msg("u1", "t1", "Apply the fix"),
        gemini_thinking_msg("g-thinking", "t2", tool_calls=[{"name": "write_file"}, {"name": "read_file"}]),
        gemini_reply_msg("g-final", "t3", "Applied the fix to solution.py."),
    ])
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1
    assert entries[0]["file_changes_count"] == 1  # only write_file counts, read_file doesn't


def test_empty_content_returns_no_entries():
    assert SessionLogService.parse_gemini_chat_session("") == []
    assert SessionLogService.parse_gemini_chat_session("   ") == []


def test_malformed_json_lines_are_skipped_not_fatal():
    content = make_main_session(messages=[
        user_msg("u1", "t1", "A question"),
        gemini_reply_msg("g1", "t2", "An answer"),
    ]) + "\nnot valid json at all{{{"
    entries = SessionLogService.parse_gemini_chat_session(content)
    assert len(entries) == 1


# ── parse_gemini_chat_sessions(): multi-file merge ──────────────────────────

def test_merges_multiple_session_files_sorted_by_timestamp():
    """A candidate can invoke `gemini` more than once (each is a separate
    session file) — entries from all files must merge into one
    chronological transcript."""
    session_a = make_main_session("a", messages=[
        user_msg("u1", "2026-07-10T14:00:00.000Z", "Second question asked later"),
        gemini_reply_msg("g1", "2026-07-10T14:00:05.000Z", "Second answer"),
    ])
    session_b = make_main_session("b", messages=[
        user_msg("u2", "2026-07-10T13:00:00.000Z", "First question asked earlier"),
        gemini_reply_msg("g2", "2026-07-10T13:00:05.000Z", "First answer"),
    ])
    entries = SessionLogService.parse_gemini_chat_sessions({
        "chats/session-b.jsonl": session_b,
        "chats/session-a.jsonl": session_a,
    })
    assert len(entries) == 2
    assert entries[0]["prompt"] == "First question asked earlier"
    assert entries[1]["prompt"] == "Second question asked later"


def test_merges_excludes_subagent_sessions_mixed_with_main_ones():
    header_sub = {"sessionId": "sub", "projectHash": "h", "startTime": "t",
                  "lastUpdated": "t", "kind": "subagent"}
    subagent_content = "\n".join([
        _line(header_sub),
        _line(user_msg("su1", "t1", "run git log")),
        _line(gemini_reply_msg("sg1", "t2", "internal tool chatter")),
    ])
    main_content = make_main_session(messages=[
        user_msg("u1", "t1", "Real candidate question"),
        gemini_reply_msg("g1", "t2", "Real answer"),
    ])
    entries = SessionLogService.parse_gemini_chat_sessions({
        "chats/session-main.jsonl": main_content,
        "chats/deadbeef/subagent.jsonl": subagent_content,
    })
    assert len(entries) == 1
    assert entries[0]["prompt"] == "Real candidate question"


def test_empty_files_dict_returns_empty_list():
    assert SessionLogService.parse_gemini_chat_sessions({}) == []


# ── DockerService.get_gemini_chat_files(): tar-pull + filter ────────────────

def make_gemini_tmp_tar(files: dict) -> bytes:
    """In-memory tar shaped like `docker cp <id>:/home/coder/.gemini/tmp -`
    output, mirroring test_extract_container_files.py's make_tar()."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(f"tmp/{name}")
            data = content.encode("utf-8")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_get_gemini_chat_files_filters_to_jsonl_under_chats(monkeypatch):
    tar_bytes = make_gemini_tmp_tar({
        "workspace/chats/session-1.jsonl": "real session content",
        "workspace/.project_root": "/workspace",
        "workspace/other-file.txt": "irrelevant",
    })
    monkeypatch.setattr(DockerService, "get_archive", lambda *a, **k: tar_bytes)

    files = DockerService.get_gemini_chat_files("fake-container-id")
    assert list(files.keys()) == ["tmp/workspace/chats/session-1.jsonl"]
    assert files["tmp/workspace/chats/session-1.jsonl"] == "real session content"


def test_get_gemini_chat_files_includes_nested_subagent_paths(monkeypatch):
    """Subagent .jsonl files also live under chats/ (in a nested
    <session-id>/ subdirectory) — get_gemini_chat_files() pulls them too;
    filtering by kind='main' happens later, in the parser, not here."""
    tar_bytes = make_gemini_tmp_tar({
        "workspace/chats/session-1.jsonl": "main session",
        "workspace/chats/deadbeef/subagent-1.jsonl": "subagent session",
    })
    monkeypatch.setattr(DockerService, "get_archive", lambda *a, **k: tar_bytes)

    files = DockerService.get_gemini_chat_files("fake-container-id")
    assert len(files) == 2


def test_get_gemini_chat_files_no_container_id_returns_empty():
    assert DockerService.get_gemini_chat_files(None) == {}


def test_get_gemini_chat_files_empty_archive_returns_empty(monkeypatch):
    monkeypatch.setattr(DockerService, "get_archive", lambda *a, **k: b"")
    assert DockerService.get_gemini_chat_files("fake-container-id") == {}


def test_get_gemini_chat_files_tolerates_archive_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("docker cp failed")
    monkeypatch.setattr(DockerService, "get_archive", boom)
    assert DockerService.get_gemini_chat_files("fake-container-id") == {}
