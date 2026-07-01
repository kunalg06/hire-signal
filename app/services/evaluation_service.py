import json
import os
import io
import tarfile
from app.config import Config
from app.services.llm_service import LLMService
from app.services.session_log_service import SessionLogService

class EvaluationService:
    """Code evaluation service — LLM calls routed through LLMService."""

    # ── 8-Dimension scoring weights (must sum to 1.0) ─────────────────────
    DIMENSION_WEIGHTS = {
        "problem_decomposition":     0.15,
        "first_principles_thinking": 0.15,
        "creative_problem_solving":  0.10,
        "iteration_quality":         0.15,
        "debugging_with_ai":         0.15,
        "architecture_decisions":    0.10,
        "communication_clarity":     0.10,
        "token_efficiency":          0.10,
    }

    HIRE_THRESHOLDS = {
        "strong_hire": 85,
        "hire":        70,
        "select":      55,
    }

    @staticmethod
    def extract_container_files(container_id: str,
                                workspace: str = '/workspace') -> dict:
        """
        Extract all text files from a Docker container workspace.
        Returns {relative_path: content}. Returns {} on any failure so the
        caller can always proceed without blocking on Docker availability.
        """
        TEXT_EXTS = {'.py', '.js', '.ts', '.md', '.txt', '.json',
                     '.yaml', '.yml', '.sh', '.sql', '.toml', '.cfg'}
        MAX_TOTAL_BYTES = 50 * 1024  # 50 KB hard cap sent to Claude

        try:
            import docker
            from app.config import Config

            docker_host = Config.DOCKER_HOST or os.getenv('DOCKER_HOST')
            client = (docker.DockerClient(base_url=docker_host)
                      if docker_host else docker.from_env())

            container = client.containers.get(container_id)
            bits, _ = container.get_archive(workspace)
            tar_stream = io.BytesIO(b''.join(bits))

            files = {}
            total_bytes = 0

            with tarfile.open(fileobj=tar_stream) as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    _, ext = os.path.splitext(member.name)
                    if ext.lower() not in TEXT_EXTS:
                        continue
                    f = tar.extractfile(member)
                    if not f:
                        continue
                    raw = f.read()
                    rel = member.name.replace('workspace/', '', 1).lstrip('/')
                    if total_bytes + len(raw) > MAX_TOTAL_BYTES:
                        content = raw[:MAX_TOTAL_BYTES - total_bytes].decode(
                            'utf-8', errors='replace') + '\n[TRUNCATED]'
                        files[rel] = content
                        break
                    files[rel] = raw.decode('utf-8', errors='replace')
                    total_bytes += len(raw)

            return files

        except Exception as e:
            print(f"Warning: workspace extraction failed for {container_id}: {e}")
            return {}

    @staticmethod
    def score_8_dimensions(session_logs: list,
                           file_snapshot: dict,
                           assignment: dict) -> dict:
        """
        Call Claude once to score all 8 AI-collaboration dimensions.
        Returns the full parsed result dict.  On any failure returns a
        safe default (all dimensions score=0, recommendation='pass').
        """
        # ── Format session logs ──────────────────────────────────────────
        if session_logs:
            log_lines = []
            for i, log in enumerate(session_logs[:80], 1):  # cap at 80 interactions
                prompt = (log.get('prompt') or '')[:400]
                response = (log.get('response_summary') or '')[:400]
                log_lines.append(
                    f"[{i}] Candidate prompt: {prompt}\n"
                    f"    AI response summary: {response}\n"
                    f"    File changes: {log.get('file_changes_count', 0)}"
                )
            logs_text = '\n'.join(log_lines)
        else:
            logs_text = "No Claude session logs recorded for this submission."

        # ── Format file snapshot ─────────────────────────────────────────
        if file_snapshot:
            file_sections = []
            for path, content in file_snapshot.items():
                file_sections.append(f"### {path}\n```\n{content}\n```")
            files_text = '\n\n'.join(file_sections)
        else:
            files_text = "No workspace files retrieved."

        # ── Build prompt ─────────────────────────────────────────────────
        weights = EvaluationService.DIMENSION_WEIGHTS
        scoring_prompt = f"""You are a senior engineering hiring assessor evaluating a candidate's \
AI-assisted coding competency. Score the candidate across 8 dimensions based on their session \
logs and submitted files.

## Assignment Context
Title: {assignment.get('title', 'N/A')}
Description: {assignment.get('description', 'N/A')}
Evaluation Criteria: {assignment.get('evaluation_criteria', 'N/A')}

## AI Session Logs (candidate prompts → AI responses, chronological)
{logs_text}

## Submitted Workspace Files
{files_text}

## Scoring Task
Score each dimension 0-100 using the rubric below. Cite specific evidence from the logs or \
files in your rationale (2 sentences max per dimension).

### Dimension Rubrics
- **problem_decomposition** (weight {weights['problem_decomposition']}): Did the candidate break \
the problem into sub-problems before prompting? 0=asked for full solution immediately, \
50=some decomposition, 100=systematic breakdown before any coding.
- **first_principles_thinking** (weight {weights['first_principles_thinking']}): Did prompts \
reflect understanding of underlying concepts vs copying symptoms? 0=pure copy-paste symptom \
fixes, 100=first-principles derivation explaining the why.
- **creative_problem_solving** (weight {weights['creative_problem_solving']}): Did the candidate \
explore non-obvious approaches? 0=took the most obvious path, 100=discovered a novel or \
significantly better approach.
- **iteration_quality** (weight {weights['iteration_quality']}): Did follow-up prompts \
meaningfully improve on prior context? 0=repetitive rephrasing of the same question, \
100=each iteration added new information and narrowed scope.
- **debugging_with_ai** (weight {weights['debugging_with_ai']}): Did the candidate verify AI \
output, catch AI errors, and write tests? 0=accepted all AI output blindly, \
100=systematic verification with test cases and error correction.
- **architecture_decisions** (weight {weights['architecture_decisions']}): Does the submitted \
code show good structural judgment? 0=monolithic, no separation of concerns, no error handling, \
100=clean modular design with proper abstractions and error handling.
- **communication_clarity** (weight {weights['communication_clarity']}): Were prompts specific, \
context-rich, and unambiguous? 0=vague one-liners with no context, 100=precise prompts with \
relevant context and explicit constraints every time.
- **token_efficiency** (weight {weights['token_efficiency']}): Did the candidate accomplish \
goals with focused, targeted prompts? 0=verbose/redundant/off-topic prompts wasting cycles, \
100=minimal concise prompts achieving maximum quality output.

## Hire Recommendation Thresholds
Compute composite = weighted average using the weights shown above.
- strong_hire: composite >= 85
- hire: composite >= 70
- select: composite >= 55
- pass: composite < 55

## Output Format
Respond ONLY with valid JSON — no markdown fences, no prose:
{{
  "dimensions": {{
    "problem_decomposition":     {{"score": 0, "rationale": ""}},
    "first_principles_thinking": {{"score": 0, "rationale": ""}},
    "creative_problem_solving":  {{"score": 0, "rationale": ""}},
    "iteration_quality":         {{"score": 0, "rationale": ""}},
    "debugging_with_ai":         {{"score": 0, "rationale": ""}},
    "architecture_decisions":    {{"score": 0, "rationale": ""}},
    "communication_clarity":     {{"score": 0, "rationale": ""}},
    "token_efficiency":          {{"score": 0, "rationale": ""}}
  }},
  "recommendation_rationale": "3-4 sentence employer-facing summary"
}}"""

        # ── Safe default returned on any failure ─────────────────────────
        def _default_result(reason: str) -> dict:
            dims = {d: {"score": 0, "rationale": reason}
                    for d in EvaluationService.DIMENSION_WEIGHTS}
            return {
                "dimensions": dims,
                "composite_score": 0.0,
                "hire_recommendation": "pass",
                "recommendation_rationale": reason,
            }

        try:
            response_text = LLMService.chat(scoring_prompt, max_tokens=2000)

            # Strip markdown fences if present
            if response_text.startswith("```"):
                response_text = response_text.split("```json")[-1].split("```")[0].strip()

            result = json.loads(response_text)

        except Exception as e:
            print(f"8-dimension scoring error: {e}")
            return _default_result(f"Scoring error: {str(e)[:120]}")

        # ── Validate all 8 keys present ──────────────────────────────────
        dims = result.get("dimensions", {})
        for dim in EvaluationService.DIMENSION_WEIGHTS:
            if dim not in dims:
                dims[dim] = {"score": 0, "rationale": "dimension missing from response"}
        result["dimensions"] = dims

        # ── Python-enforced composite + thresholds (never trust Claude's) ─
        composite = sum(
            dims[d]["score"] * w
            for d, w in EvaluationService.DIMENSION_WEIGHTS.items()
        )
        composite = min(100.0, max(0.0, composite))

        thresholds = EvaluationService.HIRE_THRESHOLDS
        if composite >= thresholds["strong_hire"]:
            recommendation = "strong_hire"
        elif composite >= thresholds["hire"]:
            recommendation = "hire"
        elif composite >= thresholds["select"]:
            recommendation = "select"
        else:
            recommendation = "pass"

        result["composite_score"]      = round(composite, 2)
        result["hire_recommendation"]  = recommendation

        return result

    @staticmethod
    def evaluate_code(code: str, assignment: dict, session_logs: list = None,
                      container_created_at: str = None, container_id: str = None,
                      file_snapshot: dict = None) -> dict:
        """
        Evaluate a submission using the 8-dimension AI-collaboration framework.
        Returns combined result with both new 8-dim fields and legacy fields
        for backward compatibility.
        """
        # Use file_snapshot passed in; fall back to extracting from container
        if file_snapshot is None and container_id:
            file_snapshot = EvaluationService.extract_container_files(container_id)
        if file_snapshot is None:
            file_snapshot = {}

        # Inject solution code into snapshot under a canonical key if not present
        if code and 'solution.py' not in file_snapshot:
            file_snapshot['solution.py'] = code

        result = EvaluationService.score_8_dimensions(
            session_logs=session_logs or [],
            file_snapshot=file_snapshot,
            assignment=assignment,
        )

        dims        = result["dimensions"]
        composite   = result["composite_score"]
        rec         = result["hire_recommendation"]
        narrative   = result.get("recommendation_rationale", "")

        # Build human-readable feedback (legacy field)
        dim_lines = "\n".join(
            f"  {d.replace('_', ' ').title()}: {dims[d]['score']}/100 — {dims[d]['rationale']}"
            for d in EvaluationService.DIMENSION_WEIGHTS
        )
        feedback = (
            f"{narrative}\n\n"
            f"--- 8-DIMENSION BREAKDOWN ---\n{dim_lines}\n\n"
            f"Composite Score: {composite:.1f}/100  |  Recommendation: {rec.upper()}"
        )

        return {
            # ── New 8-dim fields ────────────────────────────────────────
            "hire_recommendation":    rec,
            "composite_score":        composite,
            "recommendation_rationale": narrative,
            "dimensions":             dims,
            # ── Legacy fields (kept for backward compat) ────────────────
            "score":                  composite,
            "feedback":               feedback,
            "evaluation_details":     dims,
            "code_quality_score":     composite,
            "approach_score":         0,
            "efficiency_score":       0,
            "combined_score":         composite,
        }

    @staticmethod
    def generate_challenge(problem_statement: str, difficulty: str,
                           challenge_type: str = 'feature_extension',
                           skill_area: str = 'api_integration',
                           ai_assistance_mode: str = 'unguarded') -> dict:
        """Generate a market-aligned coding challenge using Claude AI"""
        mode_instruction = (
            "The starter code must contain deliberate gaps marked with TODO comments and partial "
            "logic that rewards candidates who use AI tools strategically to fill them. Leave "
            "meaningful blanks — don't hand-hold, but give enough structure that the candidate "
            "understands what to build."
            if ai_assistance_mode == 'unguarded'
            else
            "The starter code must be self-contained and clear enough to reason through without AI "
            "assistance. Evaluation should emphasise the candidate's own reasoning and explanation "
            "over the final output."
        )

        type_instruction = {
            'bug_fix': (
                "Insert 2-4 realistic bugs into otherwise working code. Do NOT add comments "
                "marking the bugs or hinting at their location. Bugs should be subtle — "
                "off-by-one errors, wrong variable names, missing edge-case handling, incorrect "
                "logic conditions. The candidate must find and fix them."
            ),
            'feature_extension': (
                "Provide a working partial implementation. The candidate must add a clearly "
                "specified new feature or capability. Use TODO comments only at the exact "
                "insertion points. Existing code should be complete and correct."
            ),
            'refactoring': (
                "Provide working but poorly structured code — mixed concerns, long functions, "
                "no error handling, magic numbers, repeated logic. The candidate must improve "
                "structure, readability, and maintainability without changing behaviour."
            ),
            'optimization': (
                "Provide correct but inefficient code — naive loops, redundant DB calls, "
                "missing caching, O(n²) where O(n log n) is possible. The candidate must "
                "improve performance while preserving correctness. Include a simple benchmark "
                "or timing block in the starter code."
            ),
        }.get(challenge_type, '')

        skill_imports = {
            'api_integration':   'import httpx\nimport json\nfrom typing import Optional',
            'rate_limiting':     'import time\nimport threading\nfrom collections import defaultdict',
            'data_pipeline':     'import json\nimport csv\nfrom typing import Iterator, Generator',
            'llm_usage':         'import anthropic\nimport os\nfrom typing import Optional',
            'server_monitoring': 'import httpx\nimport time\nfrom datetime import datetime',
            'game_logic':        'from dataclasses import dataclass\nfrom typing import List, Optional\nimport random',
        }.get(skill_area, 'import json\nfrom typing import Optional')

        generation_prompt = f"""You are a senior engineering hiring manager at a top technology company.
Generate a realistic, market-relevant coding challenge for a technical interview assessment.

## Challenge Parameters
- Problem Context: {problem_statement}
- Difficulty: {difficulty}
  - easy = junior level (1-2 years exp), straightforward implementation
  - medium = mid level (3-5 years exp), requires design judgment
  - hard = senior/staff level, requires architectural thinking and edge-case mastery
- Challenge Type: {challenge_type}
  {type_instruction}
- Skill Area: {skill_area}
- AI Assistance Mode: {ai_assistance_mode}
  {mode_instruction}

## Market Context
Mirror the style of real 2024-2025 engineering interviews at companies like Stripe, Anthropic,
Vercel, Linear, or Cloudflare. Focus on pragmatic, production-adjacent problems — NOT LeetCode
puzzles or abstract algorithms. The problem should test engineering judgment and practical skill.

## Starter Code Requirements
- Begin with these imports (add others as needed for {skill_area}):
{skill_imports}
- Minimum 40 lines of meaningful scaffolding
- Use type hints throughout
- Include a realistic class or function structure matching production code style
- End with a `if __name__ == "__main__":` block that demonstrates usage
- For bug_fix type: bugs must already be present in the code — do NOT add comments like "bug here"
- For feature_extension type: TODO comments only at exact insertion points

## Output Format
Respond ONLY with valid JSON — no markdown fences, no prose before or after:
{{
  "title": "concise challenge title (max 60 chars, action-oriented)",
  "description": "full scenario with business context, exact deliverable, constraints, and success criteria (200-350 words)",
  "evaluation_criteria": "semicolon-separated list of 4-6 specific measurable criteria",
  "starter_code": "complete Python file ready to be placed in the candidate workspace"
}}"""

        try:
            response_text = LLMService.chat(generation_prompt, max_tokens=3000)

            # Strip markdown fences if model wrapped the JSON anyway
            if response_text.startswith("```"):
                response_text = response_text.split("```json")[-1].split("```")[0].strip()
                if not response_text:
                    response_text = response_text.split("```")[-2].strip()

            challenge = json.loads(response_text)

            required_fields = ['title', 'description', 'evaluation_criteria', 'starter_code']
            missing = [f for f in required_fields if f not in challenge]
            if missing:
                raise ValueError(f"Missing fields in Claude response: {missing}")

            return challenge

        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse Claude response as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"Challenge generation failed: {str(e)}")
