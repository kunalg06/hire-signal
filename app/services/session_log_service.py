import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Tuple

logger = logging.getLogger(__name__)

class SessionLogService:
    """Service for parsing and analyzing Gemini session logs"""

    # Auto-injected on every session's first turn by Gemini CLI itself, not
    # something the candidate typed — must never be scored/displayed as a
    # candidate prompt. Detected by prefix since the rest of the text
    # (directory listing, date) varies per session.
    _SESSION_CONTEXT_PREFIX = '<session_context>'

    @staticmethod
    def parse_gemini_chat_sessions(files: dict) -> List[dict]:
        """
        Parse ALL of a candidate's Gemini CLI session transcripts (one
        .jsonl file per `gemini` invocation, as returned by
        DockerService.get_gemini_chat_files()) into the flat, timestamp-
        ordered entry list score_8_dimensions() already expects.

        A candidate may invoke `gemini` more than once during an
        assessment (each invocation is a separate session file) — entries
        from every file are merged and sorted by timestamp so the
        resulting transcript reads as one chronological conversation
        regardless of how many times the CLI was (re)started.
        """
        all_entries = []
        for content in files.values():
            all_entries.extend(SessionLogService.parse_gemini_chat_session(content))
        all_entries.sort(key=lambda e: e.get('timestamp') or '')
        return all_entries

    @staticmethod
    def parse_gemini_chat_session(jsonl_content: str) -> List[dict]:
        """
        Parse ONE Gemini CLI session transcript file into structured
        (prompt, response) entries.

        File format (confirmed empirically against a real running
        container — see AGENT.md's session-log-capture-fix entry, since
        this is undocumented CLI internals, not a published spec): each
        line is an independently-parseable JSON object, one of:
          - a header line (has 'sessionId', no 'id'/'type') — ignored.
          - a bare metadata update, e.g. {"$set": {"lastUpdated": ...}} —
            ignored (no message content).
          - {"$set": {"messages": [...]}} — wraps one or more real message
            objects (used for the session's very first message).
          - a bare message object: {"id", "timestamp", "type": "user" or
            "gemini", "content", ...}.
        A "user" message's `content` is a list of dicts — either
        {"text": "..."} (something the candidate actually typed) or
        {"functionResponse": {...}} (a tool-call result being fed back to
        the model, e.g. a read_file result — not candidate-authored text).
        A "gemini" message's `content` is a plain string; it can be empty
        while the model is still "thinking"/making tool calls, with the
        real visible reply arriving as a later, separate message.

        Messages are paired chronologically: each genuine candidate text
        prompt is matched with the next non-empty Gemini text reply that
        follows it, mirroring the (prompt, response) shape
        score_8_dimensions() already builds its scoring-evidence section
        from. A trailing prompt with no reply yet (session ended mid-turn)
        is dropped rather than persisted with an empty response.
        """
        entries = []
        if not jsonl_content or not jsonl_content.strip():
            return entries

        lines = [l.strip() for l in jsonl_content.split('\n') if l.strip()]
        if not lines:
            return entries

        # The header (first) line carries a 'kind' field: 'main' is a real
        # candidate<->Gemini conversation; 'subagent' is Gemini's own
        # internal tool-use sessions (e.g. spawning a sub-session to run
        # `git status`/`git log` for its own context-gathering) — never
        # something the candidate said or something to score/display.
        # Confirmed empirically: these live in a nested chats/<id>/<id>.jsonl
        # path alongside the real top-level chats/session-*.jsonl files.
        try:
            header = json.loads(lines[0])
        except json.JSONDecodeError:
            header = {}
        if header.get('kind') != 'main':
            return entries

        messages_by_id = {}
        message_order = []
        for line in lines[1:]:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            candidates = []
            if isinstance(obj, dict) and 'id' in obj and 'type' in obj:
                candidates = [obj]
            elif isinstance(obj, dict) and isinstance(obj.get('$set', {}).get('messages'), list):
                candidates = obj['$set']['messages']

            for msg in candidates:
                if not isinstance(msg, dict) or 'id' not in msg:
                    continue
                msg_id = msg['id']
                if msg_id not in messages_by_id:
                    message_order.append(msg_id)
                messages_by_id[msg_id] = msg  # later occurrence wins (more complete)

        ordered_messages = [messages_by_id[mid] for mid in message_order]

        pending_prompt = None
        pending_timestamp = None
        pending_tool_calls = []  # accumulated across every gemini message in this turn,
                                  # since real toolCalls happen on intermediate "thinking"
                                  # messages (empty content), not the final reply itself —
                                  # confirmed empirically: the final reply message rarely
                                  # carries its own toolCalls.
        for msg in ordered_messages:
            msg_type = msg.get('type')
            timestamp = msg.get('timestamp')

            if msg_type == 'user':
                text_parts = [
                    item.get('text', '') for item in (msg.get('content') or [])
                    if isinstance(item, dict) and item.get('text')
                ]
                text = ' '.join(text_parts).strip()
                if not text or text.startswith(SessionLogService._SESSION_CONTEXT_PREFIX):
                    continue  # tool-result turn or the auto-injected context message
                pending_prompt = text
                pending_timestamp = timestamp
                pending_tool_calls = []

            elif msg_type == 'gemini' and pending_prompt is not None:
                pending_tool_calls.extend(msg.get('toolCalls') or [])
                response = msg.get('content')
                if not isinstance(response, str) or not response.strip():
                    continue  # "thinking"/tool-calling turn with no visible reply yet
                file_changes = sum(
                    1 for tc in pending_tool_calls
                    if isinstance(tc, dict)
                    and any(k in str(tc.get('name', '')).lower() for k in ('write', 'edit', 'replace'))
                )
                entries.append({
                    'timestamp': timestamp or pending_timestamp,
                    'interaction_type': 'gemini_cli',
                    'prompt': pending_prompt,
                    'response_summary': response.strip(),
                    'file_changes_count': file_changes,
                    'raw_json': json.dumps({'prompt': pending_prompt, 'response': response.strip()}),
                })
                pending_prompt = None
                pending_timestamp = None
                pending_tool_calls = []

        return entries

    @staticmethod
    def parse_session_log(log_content: str) -> List[dict]:
        """Parse Gemini session log into structured entries. Legacy
        plaintext-transcript fallback, kept as a defensive path — the
        active capture path is parse_gemini_chat_sessions() above, which
        targets Gemini CLI's real .jsonl session-file format."""
        entries = []

        if not log_content or not log_content.strip():
            return entries

        lines = log_content.split('\n')
        json_parsed = False

        # Try JSON lines format first
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    entries.append(entry)
                    json_parsed = True
                    continue
            except json.JSONDecodeError:
                pass

        # If no JSON entries found, parse plaintext transcript format
        if not entries:
            full_text = '\n'.join(lines)

            # Pattern 1: "Prompt: ... Response: ..."
            prompt_response_pattern = r'(?:Prompt|Command|User):\s*(.+?)(?:\n\s*(?:Response|Assistant|Result):\s*(.+?)(?=\n(?:Prompt|Command|User|$)|$))'
            matches = re.findall(prompt_response_pattern, full_text, re.IGNORECASE | re.DOTALL)

            for prompt_text, response_text in matches:
                entry = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'interaction_type': 'gemini_cli',
                    'prompt': prompt_text.strip()[:500],
                    'response_summary': response_text.strip()[:500],
                    'file_changes_count': 0,
                    'raw_json': json.dumps({'prompt': prompt_text.strip(), 'response': response_text.strip()})
                }
                entries.append(entry)

            # Pattern 2: Line-by-line parsing
            if not entries:
                for line in lines:
                    if line.strip() and any(keyword in line.lower() for keyword in ['prompt:', 'command:', 'gemini', 'evaluate']):
                        entry = {
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'interaction_type': 'gemini_cli',
                            'prompt': line.strip()[:500],
                            'response_summary': 'Captured from terminal',
                            'file_changes_count': 0,
                            'raw_json': json.dumps({'raw_line': line})
                        }
                        entries.append(entry)

        return entries

    @staticmethod
    def calculate_scores(session_logs: List[dict], container_creation_time: str = None) -> Tuple[int, int]:
        """Calculate approach and efficiency scores from session logs"""
        approach_score = 0
        efficiency_score = 15  # Default neutral

        if not session_logs:
            return (0, 0)

        # Approach score: based on iterations and self-correction patterns
        iteration_count = len(session_logs)
        approach_score = min(15, iteration_count * 3)

        # Self-correction bonus
        self_correction_count = 0
        for log in session_logs:
            response = log.get('response_summary', '').lower()
            if any(keyword in response for keyword in ['error', 'fix', 'try again', 'corrected', 'fixed', 'failed']):
                self_correction_count += 1

        approach_score = min(30, approach_score + (self_correction_count * 5))

        # Efficiency score: based on time elapsed
        if session_logs and container_creation_time:
            try:
                first_log = session_logs[0]
                last_log = session_logs[-1]

                first_timestamp = datetime.fromisoformat(first_log.get('timestamp', '').replace('Z', '+00:00'))
                last_timestamp = datetime.fromisoformat(last_log.get('timestamp', '').replace('Z', '+00:00'))
                container_time = datetime.fromisoformat(container_creation_time.replace('Z', '+00:00'))

                elapsed_hours = (last_timestamp - container_time).total_seconds() / 3600

                if elapsed_hours <= 0.5:
                    efficiency_score = 30
                elif elapsed_hours <= 1:
                    efficiency_score = 25
                elif elapsed_hours <= 2:
                    efficiency_score = 20
                elif elapsed_hours <= 4:
                    efficiency_score = 10
                else:
                    efficiency_score = 5
            except Exception as e:
                logger.error("Failed to calculate efficiency score: %s", e)
                efficiency_score = 15

        # Clamp to ensure scores stay in 0-30 range
        efficiency_score = max(0, min(30, efficiency_score))
        approach_score = max(0, min(30, approach_score))

        return (approach_score, efficiency_score)
