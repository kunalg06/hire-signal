import anthropic
import json
import os
from app.config import Config
from app.services.session_log_service import SessionLogService

class EvaluationService:
    """Code evaluation service using Claude API"""

    _client = None

    @classmethod
    def get_client(cls):
        """Get or initialize Anthropic client lazily"""
        if cls._client is None:
            try:
                cls._client = anthropic.Anthropic()
            except Exception as e:
                print(f"Warning: Could not initialize Anthropic client: {e}")
                return None
        return cls._client

    @staticmethod
    def evaluate_code(code: str, assignment: dict, session_logs: list = None, container_created_at: str = None) -> dict:
        """Evaluate code using Claude API with session log scoring"""
        client = EvaluationService.get_client()
        if not client:
            return {
                "score": 0,
                "feedback": "Claude API client not available",
                "evaluation_details": {"error": "API unavailable"},
                "code_quality_score": 0,
                "approach_score": 0,
                "efficiency_score": 0,
                "combined_score": 0
            }

        # Build evaluation prompt
        evaluation_prompt = f"""You are an expert code evaluator. Analyze the following code submission.

## Assignment
Title: {assignment.get('title', 'N/A')}
Description: {assignment.get('description', 'N/A')}
Evaluation Criteria: {assignment.get('evaluation_criteria', 'N/A')}

## Submitted Code
```python
{code}
```

Provide evaluation in JSON format with these fields:
- correctness (status, details)
- code_quality (status, strengths[], weaknesses[])
- completeness (status, details)
- overall_feedback (string)
- score (0-100)

Return ONLY valid JSON, no other text."""

        try:
            message = client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": evaluation_prompt}]
            )

            response_text = message.content[0].text
            evaluation = json.loads(response_text)

        except Exception as e:
            print(f"Claude evaluation error: {e}")
            evaluation = {
                "correctness": {"status": "ERROR", "details": str(e)},
                "code_quality": {"status": "ERROR", "strengths": [], "weaknesses": [str(e)]},
                "completeness": {"status": "ERROR", "details": str(e)},
                "overall_feedback": f"Error during evaluation: {str(e)}",
                "score": 0
            }

        # Get code quality score
        code_quality_score = evaluation.get("score", 0)

        # Calculate approach and efficiency scores from session logs
        approach_score, efficiency_score = SessionLogService.calculate_scores(session_logs, container_created_at)

        # Calculate combined score: 40% code quality + 30% approach + 30% efficiency
        combined_score = (code_quality_score * 0.4) + (approach_score * 0.3) + (efficiency_score * 0.3)

        # Build feedback with scoring breakdown
        feedback = f"{evaluation.get('overall_feedback', 'No feedback')}\\n\\n---SCORING BREAKDOWN---\\n"
        feedback += f"Code Quality (40%): {code_quality_score:.1f}/100 = {code_quality_score * 0.4:.1f}\\n"
        feedback += f"Problem-Solving Approach (30%): {approach_score}/30 = {approach_score * 0.3:.1f}\\n"
        feedback += f"Efficiency (30%): {efficiency_score}/30 = {efficiency_score * 0.3:.1f}"

        if not session_logs:
            feedback += " (No Claude interactions recorded)"

        feedback += f"\\nTotal Score: {combined_score:.1f}/100"

        return {
            "score": combined_score,
            "feedback": feedback,
            "evaluation_details": evaluation,
            "code_quality_score": code_quality_score,
            "approach_score": approach_score,
            "efficiency_score": efficiency_score,
            "combined_score": combined_score
        }
