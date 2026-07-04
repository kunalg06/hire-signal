# hire-signal — Project Requirements

## Document Information
- **Project Name:** hire-signal
- **Last Updated:** 2026-07-03
- **Status:** Phase 1 (MVP scoring loop) + Epics 2-7 all complete. Every story in `_bmad-output/implementation-artifacts/sprint-status.yaml` is `done`.

---

## Problem Statement

Coding interviews haven't caught up to how engineers actually work. Candidates use AI tools on the job now, and the skill that predicts on-the-job success is no longer "can you write this algorithm from memory" — it's "can you collaborate with AI effectively to ship correct, well-reasoned code." Traditional interview platforms don't measure that at all.

hire-signal evaluates candidates on **AI-collaboration competency**, not just output correctness. It is a hiring tool for employers, not an educational platform for students — that framing shapes every product decision below.

---

## Core User Roles

- **Employer** — creates coding challenges, generates candidate access links, reviews ranked results, flags/overrides AI recommendations, makes the final hiring call.
- **Candidate** — receives a link, codes in a browser-based VS Code environment (optionally collaborating with Gemini CLI), submits for evaluation.

There is currently **no authentication** for either role — this is an accepted dev-phase constraint, not an oversight. See `CLAUDE.md`'s Security Considerations before any non-local deployment.

---

## Functional Requirements

### 1. Challenge creation
- Employers generate market-aligned coding challenges via an LLM prompt, parameterized by:
  - **Challenge type**: `bug_fix | feature_extension | refactoring | optimization`
  - **Skill area**: `api_integration | rate_limiting | data_pipeline | llm_usage | server_monitoring | game_logic`
  - **Difficulty**: `easy | medium | hard`
  - **AI assistance mode**: `guarded | unguarded`
- Generated challenges are persisted to a catalog as unpublished drafts; employers publish explicitly before reuse.
- A seed script (`scripts/seed_challenges.py`) provides 10 curated starter challenges across the type/area matrix.

### 2. Candidate assessment environment
- Each generated link spins up an isolated Docker container running code-server (browser-based VS Code) with the Gemini CLI pre-installed, restricted to a fast/cheap model (Gemini 2.5 Flash) for the in-session assistant.
- The container's `/workspace` is pre-populated with a structured brief (`instructions.md`: Scenario / Your Task / Evaluation Criteria) and the starter code.
- **Guarded mode**: a `GEMINI.md` file asks the in-container Gemini CLI to restrict itself to conceptual guidance rather than full solutions. This is honor-system enforcement only — a candidate with shell access can remove it. Accepted v1 scope; see `deferred-work.md` for what hardening would require.
- The platform degrades gracefully without Docker: links still generate, with a clear message that the live environment is unavailable, rather than failing the whole flow.

### 3. Evaluation — 8 AI-collaboration dimensions
Every submission is scored across 8 dimensions (weights sum to 1.0), by a single LLM call over the candidate's session logs and final workspace snapshot:

| Dimension | Weight | What it measures |
|---|---|---|
| Problem Decomposition | 15% | Did the candidate break the problem down before prompting? |
| First-Principles Thinking | 15% | Do prompts reflect understanding of underlying concepts, not just symptom-copying? |
| Creative Problem Solving | 10% | Did the candidate explore non-obvious approaches? |
| Iteration Quality | 15% | Did follow-up prompts meaningfully build on prior context? |
| Debugging with AI | 15% | Did the candidate verify AI output, catch errors, write tests? |
| Architecture Decisions | 10% | Does the submitted code show good structural judgment? |
| Communication Clarity | 10% | Were prompts specific, context-rich, unambiguous? |
| Token Efficiency | 10% | Did the candidate achieve goals with focused, non-redundant prompts? |

All 8 dimension keys are guaranteed present in every result, even if the LLM's own response omits some — missing dimensions default to a score of 0 with an explanatory rationale, so a partial LLM response never silently drops a candidate's overall picture.

### 4. Hire recommendation
- Composite score = Python-computed weighted sum of the 8 dimension scores — **never** the LLM's own self-reported composite, which is discarded even when present in its response.
- Thresholds, enforced entirely in Python: `strong_hire >= 85`, `hire >= 70`, `select >= 55`, `pass < 55`.

### 5. Employer review workflow
- Ranked candidate list per challenge, sortable by composite score or any individual dimension, ascending or descending.
- **Visibility floor**: an un-evaluated candidate is never hidden from the list — it always sorts last, regardless of sort direction, so employers can't accidentally lose track of a pending submission.
- Radar chart (per-candidate) and a side-by-side overlay comparison view (two candidates, butterfly chart + rationale panels).
- Real-time result polling on the candidate side (3s interval, 60s timeout) rather than a fixed wait.

### 6. Human override and calibration
- Employers can **flag** any submission for manual review (reason required) and **override** its hire recommendation (new recommendation + rationale required).
- The AI's original `composite_score`/`recommendation` are immutable once written — an override adds new fields, it never rewrites history.
- Every override is also logged to an append-only `score_overrides` table, intended as a growing calibration dataset for future scoring-prompt tuning. Analytics endpoint (`GET /api/analytics/overrides`) surfaces override direction patterns once enough data exists (≥10 overrides).

### 7. AI-scoring transparency
- The employer dashboard carries a persistent "AI scoring is experimental" banner (dismissible per session), reflecting that this is a beta capability whose calibration is still being built out — not a fully-trusted final verdict.

---

## Non-Functional Requirements

- **Single-tenant, dev-phase scale.** SQLite is sufficient; no plans to migrate to Postgres without a concrete multi-tenant driver.
- **No hard real-time guarantees.** 3s polling interval is a reasonable UX tradeoff, not a latency SLA.
- **Graceful degradation over hard failure.** Docker unavailability, LLM call failures, and catalog-persist failures all have documented fallback behaviors rather than failing the whole request — see `docs/ARCHITECTURE.md`'s decision table.
- **Test coverage over the scoring/ranking core.** 64 tests cover the 8-dimension engine, workspace extraction, hire-threshold boundaries, the candidate-ranking endpoint, and challenge generation — all runnable without a live LLM key or Docker daemon (`python -m pytest tests/ -v`).

---

## Explicitly Out of Scope (current phase)

- Authentication / authorization of any kind
- Multi-tenant isolation
- Hard enforcement of guarded mode (network-level restriction of the candidate's own Gemini CLI calls)
- Postgres/Redis (config classes exist for a future migration but nothing in the current codebase depends on them)
- Email notifications, cloud storage integrations

---

## Where requirements are tracked going forward

Product requirement changes and new features are tracked as epics/stories, not by editing this document ad hoc:

- Full epic/story backlog: `_bmad-output/planning-artifacts/epics-and-stories.md`
- Current sprint state: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- Known gaps found during implementation, not yet scheduled as stories: `_bmad-output/implementation-artifacts/deferred-work.md`
- Session-to-session continuity and current state summary: `AGENT.md`
