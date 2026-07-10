import json
import logging
import os
import io
import re
import tarfile
from app.config import Config
from app.services.llm_service import LLMService
from app.services.session_log_service import SessionLogService

logger = logging.getLogger(__name__)


class DimensionParseError(Exception):
    """Raised when a Gemini scoring response's top-level shape can't be trusted."""


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

    # ── Human-readable dimension labels, in DIMENSION_WEIGHTS order ────────
    # Shared by generate_challenge()'s prompt and its evaluation_criteria
    # format check, so both always agree on the same 8 names/order.
    DIMENSION_LABELS = [
        "Problem Decomposition", "First-Principles Thinking", "Creative Problem Solving",
        "Iteration Quality", "Debugging with AI", "Architecture Decisions",
        "Communication Clarity", "Token Efficiency",
    ]

    # ── Gemini response_schema for score_8_dimensions() ───────────────────
    _SCORING_RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "dimensions": {
                "type": "OBJECT",
                "properties": {
                    dim: {
                        "type": "OBJECT",
                        "properties": {
                            "score": {"type": "NUMBER"},
                            "rationale": {"type": "STRING"},
                        },
                        "required": ["score", "rationale"],
                    }
                    for dim in DIMENSION_WEIGHTS
                },
                "required": list(DIMENSION_WEIGHTS.keys()),
            },
            "recommendation_rationale": {"type": "STRING"},
        },
        "required": ["dimensions", "recommendation_rationale"],
    }

    # ── Gemini response_schema for generate_challenge() ───────────────────
    _CHALLENGE_RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Concise, action-oriented title grounded in the given problem context"},
            "description": {"type": "STRING", "description": "Full scenario grounded in the given problem context, challenge type, and skill area"},
            "evaluation_criteria": {
                "type": "STRING",
                "description": (
                    "Exactly 8 semicolon-separated criteria, one per AI-collaboration "
                    "dimension (Problem Decomposition, First-Principles Thinking, Creative "
                    "Problem Solving, Iteration Quality, Debugging with AI, Architecture "
                    "Decisions, Communication Clarity, Token Efficiency), each prefixed with "
                    "its dimension name in brackets"
                ),
            },
            "starter_code": {"type": "STRING"},
        },
        "required": ["title", "description", "evaluation_criteria", "starter_code"],
    }

    @staticmethod
    def _call_llm_for_json(prompt: str, max_tokens: int, response_schema: dict,
                            validate=None, max_retries: int = 3) -> dict:
        """
        Call LLMService.chat() and parse the reply as JSON, retrying with a
        fresh generation on parse/validation failure only.

        response_schema (Gemini's structured-output mode) makes malformed
        JSON rare but not eliminated for long string fields (e.g. multi-line
        starter_code) — retrying is far more reliable than trying to repair
        a broken response, since each generation is an independent draw.

        If LLMService.chat() itself raises (network/API error), that
        propagates immediately with NO retry — retrying a genuinely broken
        call adds latency for no benefit, and callers rely on this (e.g. a
        test asserts the LLM is invoked exactly once when the provider is
        down).

        validate: optional callable(dict) -> None, raising ValueError if the
        parsed dict doesn't satisfy caller-specific requirements (e.g.
        missing required keys). Treated the same as a parse failure for
        retry purposes.
        """
        last_error = None
        for attempt in range(max_retries):
            response_text = LLMService.chat(
                prompt, max_tokens=max_tokens, response_schema=response_schema,
            )
            try:
                parsed = EvaluationService._parse_json_response(response_text)
                if validate is not None:
                    validate(parsed)
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning(
                    "Gemini JSON response invalid (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
        raise last_error

    @staticmethod
    def _parse_json_response(response_text: str) -> dict:
        """
        Parse a Gemini response as JSON, tolerating a wrapping code fence.

        Tries the raw text FIRST: most responses (response_schema/JSON mode)
        are unfenced, and parsing raw means a fence-stripping regex never
        touches a response that is already valid — so a ``` that merely
        appears inside a string value (e.g. starter_code containing a
        fenced example in a docstring) can never corrupt otherwise-valid
        JSON. Only on failure does it look for a wrapping fence.

        The closing fence is optional, since max_tokens can truncate a
        response before it. If more than one fenced block is present, the
        LAST one is tried first (a model re-drafting produces its final
        answer last).
        """
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        blocks = re.findall(r"```(?:json)?\s*(.*?)(?:```|\Z)", response_text, re.DOTALL)
        for block in reversed(blocks):
            try:
                return json.loads(block.strip())
            except json.JSONDecodeError:
                continue

        # Nothing recovered — raise the original (unfenced) parse failure.
        return json.loads(response_text)

    @staticmethod
    def _check_dimension_criteria_format(evaluation_criteria: str) -> None:
        """Warn (never raise/retry) if evaluation_criteria doesn't look like
        the requested 'exactly 8, one per dimension, [Bracket]-prefixed'
        format. This is deliberately non-blocking: the field is prose shown
        to employers and interpolated as text into the scoring prompt,
        never parsed structurally anywhere in this codebase — so drift here
        is a content-quality issue to catch in logs, not a correctness bug
        worth spending a retry attempt on."""
        items = [item.strip() for item in evaluation_criteria.split(';') if item.strip()]
        if len(items) != len(EvaluationService.DIMENSION_LABELS):
            logger.warning(
                "generate_challenge(): evaluation_criteria has %d items, expected %d "
                "(one per dimension) — content: %.200s",
                len(items), len(EvaluationService.DIMENSION_LABELS), evaluation_criteria,
            )
            return

        missing_labels = [
            label for label, item in zip(EvaluationService.DIMENSION_LABELS, items)
            if f"[{label}]" not in item
        ]
        if missing_labels:
            logger.warning(
                "generate_challenge(): evaluation_criteria missing/out-of-order "
                "dimension bracket labels: %s", missing_labels,
            )

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
        MAX_TOTAL_BYTES = 50 * 1024  # 50 KB hard cap sent to Gemini

        try:
            from app.services.docker_service import DockerService

            raw = DockerService.get_archive(container_id, workspace)
            if not raw:
                return {}
            tar_stream = io.BytesIO(raw)

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
            logger.warning("workspace extraction failed for %s: %s", container_id, e)
            return {}

    @staticmethod
    def _parse_dimension_response(result) -> dict:
        """
        Validate and coerce a parsed Gemini scoring response into
        {dimension: {"score": number, "rationale": str}} for every required
        dimension.

        Raises DimensionParseError if the top-level shape can't be trusted
        at all (caller falls back to the safe default). A malformed
        individual dimension entry — missing, wrong type, or a non-numeric
        score — is coerced to a zero score with a diagnostic rationale
        instead of raising, so one bad dimension doesn't zero the whole
        submission.
        """
        if not isinstance(result, dict):
            raise DimensionParseError(
                f"top-level response is {type(result).__name__}, expected object")

        raw_dims = result.get("dimensions")
        if not isinstance(raw_dims, dict):
            raw_dims = {}

        dims = {}
        for dim in EvaluationService.DIMENSION_WEIGHTS:
            entry = raw_dims.get(dim)
            if not isinstance(entry, dict):
                dims[dim] = {"score": 0, "rationale": "dimension missing from response"}
                continue
            score = entry.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                dims[dim] = {"score": 0,
                             "rationale": "dimension score was non-numeric in Gemini response"}
                continue
            rationale = entry.get("rationale", "")
            dims[dim] = {"score": score,
                         "rationale": rationale if isinstance(rationale, str) else ""}
        return dims

    @staticmethod
    def score_8_dimensions(session_logs: list,
                           file_snapshot: dict,
                           assignment: dict) -> dict:
        """
        Call Gemini once to score all 8 AI-collaboration dimensions.
        Returns the full parsed result dict.  On any failure returns a
        safe default (all dimensions score=0, recommendation='pass').
        """
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
            # ── Format session logs ────────────────────────────────────────
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
                logs_text = "No Gemini session logs recorded for this submission."

            # ── Format file snapshot ───────────────────────────────────────
            if file_snapshot:
                file_sections = []
                for path, content in file_snapshot.items():
                    file_sections.append(f"### {path}\n```\n{content}\n```")
                files_text = '\n\n'.join(file_sections)
            else:
                files_text = "No workspace files retrieved."

            # ── Build prompt ───────────────────────────────────────────────
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

            def _validate_scoring_shape(parsed) -> None:
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"top-level response is {type(parsed).__name__}, expected object")

            result = EvaluationService._call_llm_for_json(
                scoring_prompt, max_tokens=2000,
                response_schema=EvaluationService._SCORING_RESPONSE_SCHEMA,
                validate=_validate_scoring_shape,
            )
            dims = EvaluationService._parse_dimension_response(result)
        except Exception as e:
            logger.error("8-dimension scoring error: %s", e)
            return _default_result(f"Scoring error: {str(e)[:120]}")

        result["dimensions"] = dims

        # ── Python-enforced composite + thresholds (never trust Gemini's) ─
        # Round once, then classify AND store the same rounded value — a
        # pre-round composite (e.g. 84.996) must not classify as "hire"
        # while the stored, post-round composite reads 85.0 ("strong_hire").
        composite = sum(
            dims[d]["score"] * w
            for d, w in EvaluationService.DIMENSION_WEIGHTS.items()
        )
        composite = round(min(100.0, max(0.0, composite)), 2)

        thresholds = EvaluationService.HIRE_THRESHOLDS
        if composite >= thresholds["strong_hire"]:
            recommendation = "strong_hire"
        elif composite >= thresholds["hire"]:
            recommendation = "hire"
        elif composite >= thresholds["select"]:
            recommendation = "select"
        else:
            recommendation = "pass"

        result["composite_score"]      = composite
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
                           ai_assistance_mode: str = Config.DEFAULT_ASSISTANCE_MODE) -> dict:
        """Generate a market-aligned coding challenge using Gemini"""
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

        dimension_list = "\n".join(
            f"{i+1}. {label}" for i, label in enumerate(EvaluationService.DIMENSION_LABELS)
        )

        generation_prompt = f"""You are a senior engineering hiring manager at a top technology company.
Generate a realistic, market-relevant coding challenge for a technical interview assessment.

## Challenge Parameters — every field you generate below MUST be grounded in
## ALL FOUR of these inputs, not a generic or loosely-related scenario:
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

## Evaluation Criteria Requirements
This challenge will be scored across exactly these 8 AI-collaboration dimensions:
{dimension_list}
For EACH dimension, write ONE specific, measurable criterion describing what "doing
well" looks like FOR THIS SPECIFIC CHALLENGE — not a generic definition of the
dimension. Ground every criterion in the Problem Context, Challenge Type, and Skill
Area above, so a reader recognizes exactly what this particular challenge is testing
for that dimension.

## Output Format
Respond ONLY with valid JSON — no markdown fences, no prose before or after:
{{
  "title": "concise challenge title (max 60 chars, action-oriented), clearly reflecting the Problem Context above",
  "description": "full scenario with business context, exact deliverable, constraints, and success criteria (200-350 words) — directly grounded in the Problem Context, Challenge Type, and Skill Area above",
  "evaluation_criteria": "EXACTLY 8 semicolon-separated criteria, one per dimension in the order listed above, each prefixed with its dimension name in brackets, e.g. '[Problem Decomposition] ...; [First-Principles Thinking] ...; [Creative Problem Solving] ...; [Iteration Quality] ...; [Debugging with AI] ...; [Architecture Decisions] ...; [Communication Clarity] ...; [Token Efficiency] ...'",
  "starter_code": "complete Python file ready to be placed in the candidate workspace, matching the Challenge Type and Skill Area requirements above"
}}"""

        def _validate_challenge_fields(challenge: dict) -> None:
            required_fields = ['title', 'description', 'evaluation_criteria', 'starter_code']
            missing = [f for f in required_fields if f not in challenge]
            if missing:
                raise ValueError(f"Missing fields in Gemini response: {missing}")

            # Warn-only, not a retry trigger: evaluation_criteria is prose
            # shown to employers and interpolated as text into the scoring
            # prompt (see score_8_dimensions()) — nothing anywhere parses it
            # structurally (verified via repo-wide grep), so a malformed
            # count/format here degrades the employer-facing text quality
            # but breaks nothing downstream. Retrying wouldn't fix a
            # cosmetic drift and would just burn latency/cost for no
            # correctness gain (party-mode review, 2026-07-10).
            EvaluationService._check_dimension_criteria_format(
                challenge.get('evaluation_criteria', ''))

        try:
            return EvaluationService._call_llm_for_json(
                # 3000 was too low: complex, multi-requirement problem
                # statements (e.g. a concurrent multiplayer game server)
                # reliably need 3500-4700+ output tokens for title+
                # description+evaluation_criteria+starter_code, so every
                # retry hit finish_reason=MAX_TOKENS identically and the
                # 3x retry in _call_llm_for_json never helped. Verified
                # live: 12000 completes with finish_reason=STOP across
                # repeated draws for the same complex prompt, using well
                # under half the budget.
                generation_prompt, max_tokens=12000,
                response_schema=EvaluationService._CHALLENGE_RESPONSE_SCHEMA,
                validate=_validate_challenge_fields,
            )
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse Gemini response as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"Challenge generation failed: {str(e)}")
