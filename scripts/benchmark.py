"""
Performance benchmark for hire-signal.

Measures, with real numbers (no estimates):
  1. SQLite write/read throughput (isolated temp DB, never touches data/assignments.db)
  2. Flask endpoint latency via the real routes + WSGI stack (in-process test client)
  3. Real Gemini API latency for challenge generation and 8-dimension scoring
  4. Docker container spin-up time (skipped if Docker isn't reachable)

Run: python scripts/benchmark.py
Requires GEMINI_API_KEY in .env for section 3 (skipped with a clear message if absent).
Writes a JSON summary to scripts/benchmark_results.json alongside the printed report.
"""
import json
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import app.routes.challenges as challenges_module
import app.routes.assignments as assignments_module
from app.models.database import Database

ALL_DIMS = [
    "problem_decomposition", "first_principles_thinking", "creative_problem_solving",
    "iteration_quality", "debugging_with_ai", "architecture_decisions",
    "communication_clarity", "token_efficiency",
]

_counter = {"n": 0}


def uid(prefix):
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


def timed_runs(fn, n):
    """Run fn() n times, return (list_of_ms, last_result)."""
    times = []
    result = None
    for _ in range(n):
        t0 = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - t0) * 1000)
    return times, result


def stats(times):
    s = sorted(times)
    p95_idx = min(len(s) - 1, int(len(s) * 0.95))
    return {
        "n": len(s),
        "mean_ms": round(statistics.mean(s), 2),
        "p50_ms": round(statistics.median(s), 2),
        "p95_ms": round(s[p95_idx], 2),
        "min_ms": round(s[0], 2),
        "max_ms": round(s[-1], 2),
    }


def print_row(label, s):
    print(f"  {label:<42} mean {s['mean_ms']:>8.1f}ms   p50 {s['p50_ms']:>8.1f}ms   "
          f"p95 {s['p95_ms']:>8.1f}ms   min {s['min_ms']:>8.1f}ms   max {s['max_ms']:>8.1f}ms   (n={s['n']})")


def section(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


results = {}


# ── Section 1: SQLite throughput (isolated temp DB) ─────────────────────────

def bench_sqlite():
    section("1. SQLite throughput (isolated temp DB, no ORM)")

    tmp_dir = tempfile.mkdtemp(prefix="hire_signal_bench_")
    db_path = os.path.join(tmp_dir, "bench.db")
    db = Database(db_path)
    db.init_db()

    from app.services.database_service import DatabaseService
    db_service = DatabaseService(db_path)

    challenge_id = uid("challenge")
    db_service.create_challenge(
        challenge_id, title="Bench Challenge", domain="backend",
        description="d", starter_code="c", challenge_type="bug_fix",
        skill_area="rate_limiting", difficulty="medium", ai_assistance_mode="unguarded",
    )
    assignment_id = uid("assignment")
    db_service.create_assignment(
        assignment_id, "Assignment", "Desc", "code", "criteria",
        challenge_id=challenge_id,
    )

    # Write throughput: full submission write path (submission + 8 dimension
    # rows + hire evaluation) — the actual write shape a real evaluation produces.
    def write_one():
        link_id = uid("link")
        submission_id = uid("submission")
        db_service.create_session_link(
            link_id, assignment_id, "container-x", 7100, "2099-01-01T00:00:00")
        db_service.create_submission(submission_id, link_id, assignment_id, "{}")
        for dim in ALL_DIMS:
            db_service.create_dimension_score(uid("dim"), submission_id, dim, 75, "evidence")
        db_service.create_hire_evaluation(
            uid("eval"), submission_id, 75.0, "hire", "{}", "narrative")
        return submission_id

    write_times, last_submission_id = timed_runs(write_one, 200)
    write_stats = stats(write_times)
    print_row("Full submission write (10 rows/op)", write_stats)
    results["sqlite_write_full_submission"] = write_stats

    # Read throughput: fetch a single submission's dimension scores.
    read_times, _ = timed_runs(lambda: db_service.get_dimension_scores(last_submission_id), 200)
    read_stats = stats(read_times)
    print_row("Read dimension scores (8 rows)", read_stats)
    results["sqlite_read_dimension_scores"] = read_stats

    return db_service, challenge_id, assignment_id


# ── Section 2: Flask endpoint latency (real routes, in-process WSGI) ────────

def bench_flask_endpoints(db_service, challenge_id, assignment_id):
    section("2. Flask endpoint latency (real routes, in-process WSGI, no network)")

    # Point the blueprint singletons at the same isolated DB used in section 1
    # (see CLAUDE.md's "Critical Trap" — db_service is an import-time singleton
    # per route module, so this is the only reliable way to redirect it).
    challenges_module.db_service.db = db_service.db
    assignments_module.db_service.db = db_service.db

    from app import create_app
    app = create_app("testing")
    app.config["TESTING"] = True
    client = app.test_client()

    # Seed a realistic candidate pool for the ranking endpoint.
    for i in range(30):
        link_id = uid("link")
        sub_id = uid("submission")
        db_service.create_session_link(
            link_id, assignment_id, "container-x", 7100 + i, "2099-01-01T00:00:00")
        db_service.create_submission(sub_id, link_id, assignment_id, "{}")
        score = 40 + (i * 2)
        for dim in ALL_DIMS:
            db_service.create_dimension_score(uid("dim"), sub_id, dim, score, "evidence")
        db_service.create_hire_evaluation(
            uid("eval"), sub_id, float(score), "hire" if score >= 70 else "select",
            "{}", "narrative")

    # Seed 20 challenges for the catalog list endpoint.
    for i in range(20):
        db_service.create_challenge(
            uid("challenge"), title=f"Challenge {i}", domain="backend",
            description="d", starter_code="c", challenge_type="bug_fix",
            skill_area="rate_limiting", difficulty="medium", ai_assistance_mode="unguarded",
        )

    endpoints = [
        ("GET  /api/challenges  (20 rows)", lambda: client.get("/api/challenges")),
        (f"GET  /api/challenges/<id>/candidates  (30 ranked)",
         lambda: client.get(f"/api/challenges/{challenge_id}/candidates")),
        ("POST /api/assignments  (write)",
         lambda: client.post("/api/assignments", json={
             "title": "Bench Assignment", "evaluation_criteria": "criteria",
         })),
    ]

    for label, call in endpoints:
        times, resp = timed_runs(lambda c=call: c(), 30)
        s = stats(times)
        print_row(label, s)
        results[f"flask_{label.split()[0]}_{label.split()[1]}".lower().replace('/', '_')] = s


# ── Section 3: Real Gemini API latency ───────────────────────────────────────

def bench_gemini():
    section("3. Real Gemini API latency (live network calls, not mocked)")

    if not os.getenv("GEMINI_API_KEY"):
        print("  SKIPPED - GEMINI_API_KEY not set in .env")
        return

    from app.services.llm_service import LLMService
    from app.services.evaluation_service import EvaluationService

    # Raw round-trip: minimal prompt, isolates network + model latency from
    # the heavier structured-generation work below.
    def raw_chat():
        return LLMService.chat("Reply with exactly the word: OK", max_tokens=50)

    times, _ = timed_runs(raw_chat, 5)
    s = stats(times)
    print_row("LLMService.chat() - minimal prompt", s)
    results["gemini_raw_chat"] = s

    # End-to-end challenge generation — the real "Generate with AI" feature.
    def gen_challenge():
        return EvaluationService.generate_challenge(
            problem_statement="Fix a leaking in-memory rate limiter",
            difficulty="medium", challenge_type="bug_fix",
            skill_area="rate_limiting", ai_assistance_mode="unguarded",
        )

    times, _ = timed_runs(gen_challenge, 3)
    s = stats(times)
    print_row("generate_challenge() - full feature", s)
    results["gemini_generate_challenge"] = s

    # End-to-end 8-dimension scoring — the real evaluation feature.
    assignment = {
        "title": "Fix Rate Limiter Leak",
        "description": "A sliding-window rate limiter leaks memory over time.",
        "evaluation_criteria": "Memory leak fixed; logic remains correct; clean code",
    }
    session_logs = [
        {"prompt": "Why does this leak memory?", "response_summary": "It never evicts stale entries.", "file_changes_count": 1},
        {"prompt": "How should I evict old entries?", "response_summary": "Use a deque, pop while stale.", "file_changes_count": 2},
    ]
    file_snapshot = {"solution.py": "class RateLimiter:\n    def __init__(self):\n        self.requests = {}\n"}

    def score():
        return EvaluationService.score_8_dimensions(session_logs, file_snapshot, assignment)

    times, _ = timed_runs(score, 3)
    s = stats(times)
    print_row("score_8_dimensions() - full feature", s)
    results["gemini_score_8_dimensions"] = s


# ── Section 4: Docker container spin-up (skipped if Docker unavailable) ─────

def bench_docker():
    section("4. Docker container spin-up (student environment)")

    from app.services.docker_service import DockerService

    if DockerService.get_client() is None:
        print("  SKIPPED - Docker daemon not reachable")
        return

    create_times = []
    container_ids = []
    for i in range(3):
        t0 = time.perf_counter()
        container_id, port = DockerService.create_container(f"bench-{i}", 7180 + i)
        create_times.append((time.perf_counter() - t0) * 1000)
        if container_id:
            container_ids.append(container_id)

    if create_times:
        s = stats(create_times)
        print_row("create_container()", s)
        results["docker_create_container"] = s

    for cid in container_ids:
        DockerService.cleanup_container(cid)
    print(f"  Cleaned up {len(container_ids)} benchmark container(s).")


def main():
    print("hire-signal performance benchmark")
    print(f"Python {sys.version.split()[0]} | {'GEMINI_API_KEY set' if os.getenv('GEMINI_API_KEY') else 'GEMINI_API_KEY NOT set'}")

    db_service, challenge_id, assignment_id = bench_sqlite()
    bench_flask_endpoints(db_service, challenge_id, assignment_id)
    bench_gemini()
    bench_docker()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    section("Done")
    print(f"Results written to {out_path}")


if __name__ == "__main__":
    main()
