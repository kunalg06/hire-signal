import json
import logging
import re
from datetime import datetime, timezone
from typing import List, Tuple

logger = logging.getLogger(__name__)

class SessionLogService:
    """Service for parsing and analyzing Claude session logs"""

    @staticmethod
    def parse_session_log(log_content: str) -> List[dict]:
        """Parse Claude session log into structured entries"""
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
                    'interaction_type': 'claude_cli',
                    'prompt': prompt_text.strip()[:500],
                    'response_summary': response_text.strip()[:500],
                    'file_changes_count': 0,
                    'raw_json': json.dumps({'prompt': prompt_text.strip(), 'response': response_text.strip()})
                }
                entries.append(entry)

            # Pattern 2: Line-by-line parsing
            if not entries:
                for line in lines:
                    if line.strip() and any(keyword in line.lower() for keyword in ['prompt:', 'command:', 'claude', 'evaluate']):
                        entry = {
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'interaction_type': 'claude_cli',
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
