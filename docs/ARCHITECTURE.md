# hire-signal — Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              EMPLOYER BROWSER                            │
│                    templates/frontend.html (single-file JS)              │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ fetch() /api/...
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          FLASK APPLICATION (app/)                        │
│                                                                            │
│   app/__init__.py — create_app(config_name)                              │
│   ├── registers 7 blueprints, each with its own db_service singleton     │
│   └── serves templates/frontend.html at "/"                              │
│                                                                            │
│   ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│   │ assignments │  │  challenges │  │  submissions │  │    student    │  │
│   │    .py      │  │     .py     │  │      .py     │  │      .py      │  │
│   └──────┬──────┘  └──────┬──────┘  └───────┬──────┘  └───────┬───────┘  │
│          │                │                 │                 │          │
│   ┌──────┴────────────────┴─────────────────┴─────────────────┴──────┐  │
│   │                     app/services/                                 │  │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │  │
│   │  │ database_service │  │ evaluation_service│  │  docker_service │  │  │
│   │  │  (raw SQL,       │  │ (8-dim scoring,   │  │ (subprocess     │  │  │
│   │  │   no ORM)        │  │  challenge gen)   │  │  `docker` CLI)  │  │  │
│   │  └────────┬─────────┘  └─────────┬──────────┘  └────────┬────────┘  │
│   └───────────┼──────────────────────┼────────────────────────┼─────────┘  │
└───────────────┼──────────────────────┼────────────────────────┼───────────┘
                │                      │                        │
                ▼                      ▼                        ▼
      ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────┐
      │  SQLite           │   │  OpenRouter API  │   │  Docker daemon     │
      │  data/            │   │  (LLMService,    │   │  (spawns/manages   │
      │  assignments.db   │   │  model swappable │   │  candidate         │
      │  10 tables         │   │  via env var)    │   │  containers)       │
      └──────────────────┘   └──────────────────┘   └──────────┬──────────┘
                                                                 │
                                                                 ▼
                                              ┌────────────────────────────────┐
                                              │  Candidate container            │
                                              │  (docker/Dockerfile.codeserver) │
                                              │  ├── code-server (browser IDE)  │
                                              │  ├── Claude Code CLI            │
                                              │  │   (haiku-4.5, restricted)    │
                                              │  └── /workspace (candidate code)│
                                              │  Port: 7100-7900 (per-container)│
                                              └────────────────────────────────┘
```

## Request/response flow — the four core loops

### 1. Challenge generation

```
Employer → POST /api/generate-challenge (app/routes/challenges.py)
         → validate required fields + 4 enums (challenge_type, skill_area,
           difficulty, ai_assistance_mode) — 400 before any LLM call
         → EvaluationService.generate_challenge()
             → builds a market-aligned prompt (per-type scaffolding hints,
               per-skill-area import suggestions, mode-aware instructions)
             → LLMService.chat(prompt) — the only LLM call surface
             → parses the JSON response, requires title/description/
               evaluation_criteria/starter_code — raises on anything else
         → db_service.create_challenge(...) — persisted to `challenges`
           table as an UNPUBLISHED draft (is_published=0)
         → 200 with the generated content + challenge_id
           (persist failures degrade gracefully — 200 with challenge_id:
           null rather than losing the generated content the LLM already
           produced; see deferred-work.md for the tradeoff this implies)
```

### 2. Link generation → container spin-up

```
Employer → POST /api/generate-link/<assignment_id> (app/routes/links.py)
         → resolve assignment (and its linked challenge, if any, for
           ai_assistance_mode)
         → DockerService.create_container() — finds a free port in
           7100-7900, runs `docker run -d -p PORT:8080 ...`
         → DockerService.inject_workspace_files() writes into the fresh
           container's /workspace:
             - instructions.md (Scenario / Your Task / Evaluation Criteria)
             - solution.py (starter code)
             - CLAUDE.md, only if ai_assistance_mode == 'guarded' —
               asks the in-container Claude Code CLI to restrict itself
               to conceptual guidance (honor-system only, see Constraints)
         → session_links row created; access_url returned
         → Docker unavailable? Link still generates instantly with a
           degraded-mode message — this never blocks the employer flow
```

### 3. Candidate submission → evaluation

```
Candidate → POST /api/submit-with-files/<link_id> (app/routes/submissions.py)
          → submission row inserted, background thread started:
              → EvaluationService.extract_container_files(container_id)
                  - `docker cp <id>:/workspace -` → tar archive
                  - text-extension filter, 50KB total cap, per-file
                    truncation with a [TRUNCATED] marker
              → EvaluationService.score_8_dimensions(session_logs,
                file_snapshot, assignment)
                  - single LLMService.chat() call, full rubric prompt
                  - ALL 8 dimension keys guaranteed in the parsed result,
                    even if the LLM's response is missing some
                  - composite = Python-computed weighted sum (never the
                    LLM's own claimed composite/recommendation)
                  - hire_recommendation from Python-enforced thresholds
              → dimension_scores + hire_evaluations rows persisted
          → GET /api/submission/<id> polled by the candidate's browser
            every 3s (real polling, not a fixed wait) until evaluated_at
            is set
```

### 4. Employer review → hiring decision

```
Employer → GET /api/challenges/<id>/candidates (app/routes/challenges.py)
         → ranked list, sort_by any of the 8 dimension keys or
           composite_score, asc/desc
         → visibility floor: un-evaluated candidates ALWAYS sort last,
           regardless of direction (never hidden, just ranked lowest)
         → dimension_averages computed only over evaluated candidates
Employer → radar chart + side-by-side comparison view (frontend-only,
           templates/frontend.html — no backend changes for this view)
Employer → POST /api/submissions/<id>/flag  — manual-review marker
         → POST /api/submissions/<id>/override — human hire-recommendation
           override; the ORIGINAL AI composite_score/recommendation are
           NEVER modified, only override_* columns are written
         → every override also appends a row to score_overrides (a
           permanent, append-only calibration audit log)
```

## Key architectural decisions and why

| Decision | Why |
|---|---|
| SQLite, no ORM, raw SQL everywhere | Single-tenant dev-phase system; ORM overhead buys nothing here. `CREATE TABLE IF NOT EXISTS` + guarded `ALTER TABLE` is the entire migration story. |
| LLM calls routed through `LLMService`, never a direct SDK call | One swap point for model/provider. Currently OpenRouter; started as a direct Anthropic SDK integration and was migrated. |
| Docker via subprocess CLI, not the `docker` Python SDK | The `docker` SDK's `requests` dependency is incompatible with `requests>=2.32` under Python 3.14 in this environment. |
| Hire thresholds computed in Python, never trusted from the LLM | An LLM can be prompted to also emit a composite/recommendation, but that number must never be authoritative — it's recomputed from the raw per-dimension scores every time. |
| `score_overrides` append-only, `hire_evaluations`'s original score read-only | Human overrides are calibration data, not corrections that erase the AI's original call — both signals need to coexist for auditability. |
| Visibility floor (never hide, always rank last) | An unscored candidate is not the same as a bad candidate; hiding them would be a silent, unaccountable filter. |
| Guarded mode is a `CLAUDE.md` file, not a network-level restriction | v1 scope decision — a candidate with shell access can bypass it. Accepted tradeoff, documented in `deferred-work.md`; real enforcement (proxying/validating the container's Claude Code CLI calls) is a future story if assessment integrity requirements demand it. |
| Each Flask blueprint constructs its own `db_service` at **import time** | Pre-existing pattern from early development; means the DB path is fixed the moment a route module is first imported, not per-request or per-`create_app()` call — a real trap for anyone writing tests against these routes. See `CLAUDE.md`'s "Critical Trap" section. |

## Testing architecture

64 tests across 5 files (`tests/`), all invokable with `python -m pytest tests/ -v` and requiring **no** `OPENROUTER_API_KEY` or Docker daemon:

- **Unit tests** (`test_score_8_dimensions.py`, `test_extract_container_files.py`, `test_hire_recommendation_thresholds.py`) mock `LLMService.chat` / `DockerService.get_archive` directly and call service methods without touching Flask at all.
- **Integration tests** (`test_candidates_endpoint.py`, `test_generate_challenge_endpoint.py`) drive a real Flask test client against a real, but fully isolated, per-test SQLite file — see `CLAUDE.md`'s "Critical Trap" section for why this isn't as simple as `create_app("testing")` alone.

## Related docs

- `CLAUDE.md` — dev workflow, architecture constraints, debugging
- `docs/API_REFERENCE.md` — full endpoint reference with examples
- `docs/PROJECT_REQUIREMENTS.md` — product requirements and scoring rubric
- `AGENT.md` — current sprint state and known deferred issues
