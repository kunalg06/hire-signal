"""
Seed 6 demo candidates onto a single existing assignment, spanning score
tiers, for the 3-minute leadership-review demo video (see AGENT.md /
party-mode transcript, 2026-07-19).

Bypasses Docker/container lifecycle entirely - calls the same DB/service
layer submit_with_files() and evaluate_submission_files() call, so scores
are genuine (real Gemini calls), not fabricated numbers. Mirrors the
existing scripts/seed_challenges.py import pattern.

Targets the hand-authored "Token Bucket Rate Limiter" challenge
(scripts/seed_challenges.py's _SC_TOKEN_BUCKET) rather than an
AI-generated one - its 3 bugs are verified/unambiguous, unlike a
freshly-generated challenge whose bug comments can be wrong and mislead
the scoring judge (found and abandoned mid-session: an AI-generated
"Sliding Window Rate Limiter" challenge's comments falsely claimed a lock
was missing when it wasn't, tanking every candidate's score regardless of
fix quality).

Usage (from project root, with the target assignment_id):
    python scripts/seed_demo_candidates.py <assignment_id>

Requires GEMINI_API_KEY set (same precondition as the running app).
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator
from app.routes.submissions import evaluate_submission_files

db_service = DatabaseService()

STARTER = '''import time
import threading
from typing import Optional


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API endpoint protection."""

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._buckets: dict[str, dict] = {}

    def _get_bucket(self, client_id: str) -> dict:
        if client_id not in self._buckets:
            self._buckets[client_id] = {'tokens': float(self.capacity), 'last_refill': time.monotonic()}
        return self._buckets[client_id]

    def _refill(self, bucket: dict) -> None:
        now = time.monotonic()
        elapsed = now - bucket['last_refill']
        bucket['tokens'] = min(self.capacity, bucket['tokens'] + elapsed * self.refill_rate)
        bucket['last_refill'] = now

    def is_allowed(self, client_id: str) -> bool:
        bucket = self._get_bucket(client_id)
        self._refill(bucket)
        if bucket['tokens'] > 1:   # BUG 1: should be >= 1
            bucket['tokens'] -= 1
            return True
        return False

    def get_wait_time(self, client_id: str) -> float:
        bucket = self._get_bucket(client_id)
        # BUG 2: _refill() not called here -- stale token count used
        tokens_needed = 1.0 - bucket['tokens']
        if tokens_needed <= 0:
            return 0.0
        return tokens_needed / self.refill_rate

    def reset(self, client_id: str) -> None:
        self._buckets.pop(client_id, None)


class APIGateway:
    """Simulated API gateway with per-client rate limiting."""

    # BUG 3: shared limiter instance has no threading.Lock -- race conditions under concurrency
    _limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)

    @classmethod
    def handle_request(cls, client_id: str, payload: str) -> dict:
        if not cls._limiter.is_allowed(client_id):
            wait = cls._limiter.get_wait_time(client_id)
            return {'status': 429, 'error': 'rate_limit_exceeded', 'retry_after': round(wait, 2)}
        return {'status': 200, 'data': f'Processed: {payload}', 'client': client_id}

    @classmethod
    def bulk_handle(cls, requests: list[tuple[str, str]]) -> list[dict]:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(cls.handle_request, cid, pld) for cid, pld in requests]
            return [f.result() for f in futures]


if __name__ == '__main__':
    print('--- Single client burst test (5 allowed, 2 blocked) ---')
    results = [APIGateway.handle_request('alice', f'req-{i}') for i in range(7)]
    allowed = sum(1 for r in results if r['status'] == 200)
    blocked = sum(1 for r in results if r['status'] == 429)
    print(f'Allowed: {allowed}, Blocked: {blocked}')

    print('--- Concurrent burst test (exposes thread-safety bug) ---')
    reqs = [('bob', f'payload-{i}') for i in range(10)]
    for r in APIGateway.bulk_handle(reqs):
        print(f"  {r['status']}: {r.get('data', r.get('error'))}")
'''

# All 3 bugs fixed correctly, with a lock and a docstring explaining each fix.
FULL_FIX = STARTER.replace(
    "    def is_allowed(self, client_id: str) -> bool:\n"
    "        bucket = self._get_bucket(client_id)\n"
    "        self._refill(bucket)\n"
    "        if bucket['tokens'] > 1:   # BUG 1: should be >= 1\n"
    "            bucket['tokens'] -= 1\n"
    "            return True\n"
    "        return False\n"
    "\n"
    "    def get_wait_time(self, client_id: str) -> float:\n"
    "        bucket = self._get_bucket(client_id)\n"
    "        # BUG 2: _refill() not called here -- stale token count used\n"
    "        tokens_needed = 1.0 - bucket['tokens']\n"
    "        if tokens_needed <= 0:\n"
    "            return 0.0\n"
    "        return tokens_needed / self.refill_rate\n",
    "    def is_allowed(self, client_id: str) -> bool:\n"
    "        # Fixed: >= 1 -- a bucket with exactly 1.0 tokens must still be\n"
    "        # allowed to spend that last token, the strict '>' rejected it.\n"
    "        bucket = self._get_bucket(client_id)\n"
    "        self._refill(bucket)\n"
    "        if bucket['tokens'] >= 1:\n"
    "            bucket['tokens'] -= 1\n"
    "            return True\n"
    "        return False\n"
    "\n"
    "    def get_wait_time(self, client_id: str) -> float:\n"
    "        # Fixed: refill before reading tokens, or the wait estimate is\n"
    "        # computed from a stale count and can be wrong by a full elapsed\n"
    "        # interval's worth of refilled tokens.\n"
    "        bucket = self._get_bucket(client_id)\n"
    "        self._refill(bucket)\n"
    "        tokens_needed = 1.0 - bucket['tokens']\n"
    "        if tokens_needed <= 0:\n"
    "            return 0.0\n"
    "        return tokens_needed / self.refill_rate\n"
).replace(
    "    # BUG 3: shared limiter instance has no threading.Lock -- race conditions under concurrency\n"
    "    _limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)\n"
    "\n"
    "    @classmethod\n"
    "    def handle_request(cls, client_id: str, payload: str) -> dict:\n"
    "        if not cls._limiter.is_allowed(client_id):\n"
    "            wait = cls._limiter.get_wait_time(client_id)\n"
    "            return {'status': 429, 'error': 'rate_limit_exceeded', 'retry_after': round(wait, 2)}\n"
    "        return {'status': 200, 'data': f'Processed: {payload}', 'client': client_id}\n",
    "    # Fixed: the bucket dict itself is per-client, but the shared class-\n"
    "    # level _limiter instance means concurrent threads can race inside\n"
    "    # is_allowed()'s read-modify-write of bucket['tokens']. One lock\n"
    "    # protecting the whole request is coarse but correct; per-client\n"
    "    # locks would be the next optimization if contention shows up.\n"
    "    _limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)\n"
    "    _lock = threading.Lock()\n"
    "\n"
    "    @classmethod\n"
    "    def handle_request(cls, client_id: str, payload: str) -> dict:\n"
    "        with cls._lock:\n"
    "            if not cls._limiter.is_allowed(client_id):\n"
    "                wait = cls._limiter.get_wait_time(client_id)\n"
    "                return {'status': 429, 'error': 'rate_limit_exceeded', 'retry_after': round(wait, 2)}\n"
    "            return {'status': 200, 'data': f'Processed: {payload}', 'client': client_id}\n"
)

# Bugs 1 and 3 fixed, bug 2 (stale token count in get_wait_time) missed.
DECENT_FIX = STARTER.replace(
    "        if bucket['tokens'] > 1:   # BUG 1: should be >= 1\n",
    "        if bucket['tokens'] >= 1:  # fixed off-by-one\n",
).replace(
    "    # BUG 3: shared limiter instance has no threading.Lock -- race conditions under concurrency\n"
    "    _limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)\n"
    "\n"
    "    @classmethod\n"
    "    def handle_request(cls, client_id: str, payload: str) -> dict:\n"
    "        if not cls._limiter.is_allowed(client_id):\n"
    "            wait = cls._limiter.get_wait_time(client_id)\n"
    "            return {'status': 429, 'error': 'rate_limit_exceeded', 'retry_after': round(wait, 2)}\n"
    "        return {'status': 200, 'data': f'Processed: {payload}', 'client': client_id}\n",
    "    _limiter: TokenBucketRateLimiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)\n"
    "    _lock = threading.Lock()\n"
    "\n"
    "    @classmethod\n"
    "    def handle_request(cls, client_id: str, payload: str) -> dict:\n"
    "        with cls._lock:\n"
    "            if not cls._limiter.is_allowed(client_id):\n"
    "                wait = cls._limiter.get_wait_time(client_id)\n"
    "                return {'status': 429, 'error': 'rate_limit_exceeded', 'retry_after': round(wait, 2)}\n"
    "            return {'status': 200, 'data': f'Processed: {payload}', 'client': client_id}\n"
)

# Only bug 1 fixed, misidentified the other two as "not real bugs".
WEAK_FIX = STARTER.replace(
    "        if bucket['tokens'] > 1:   # BUG 1: should be >= 1\n",
    "        if bucket['tokens'] >= 1:  # think this was the main bug\n",
)


def make_link(assignment_id, ai_mode="unguarded"):
    link_id = IDGenerator.generate_uuid()
    db_service.create_session_link(
        link_id, assignment_id, container_id=None, port=None,
        expires_at="2099-01-01T00:00:00", ai_assistance_mode=ai_mode,
    )
    return link_id


def make_submission(assignment_id, link_id, code):
    submission_id = IDGenerator.generate_uuid()
    db_service.create_submission(submission_id, link_id, assignment_id, "[\"solution.py\"]")
    db_service.add_submission_file(
        IDGenerator.generate_file_id(), submission_id, "solution.py", code, len(code.encode("utf-8")))
    return submission_id


def add_logs(submission_id, turns):
    for i, (prompt, response, file_changes) in enumerate(turns):
        db_service.add_session_log(
            IDGenerator.generate_log_id(), submission_id,
            f"2026-07-19T10:0{i}:00", "gemini_cli", prompt, response, file_changes, "", 0)


def score_and_report(submission_id, assignment, label):
    print(f"  scoring {label} ({submission_id[:8]})...")
    evaluate_submission_files(submission_id, assignment)
    row = db_service.get_hire_evaluation(submission_id)
    if row:
        print(f"    -> composite={row[0]}  recommendation={row[1]}")
    else:
        print("    -> no hire_evaluation row (check evaluate_submission_files errors)")
    return row


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/seed_demo_candidates.py <assignment_id>")
        sys.exit(1)
    assignment_id = sys.argv[1]

    row = db_service.get_assignment(assignment_id)
    if not row:
        print(f"Assignment {assignment_id} not found.")
        sys.exit(1)

    assignment = {
        "id": assignment_id,
        "title": row[1],
        "description": row[2],
        "starter_code": row[3],
        "evaluation_criteria": row[4],
    }
    print(f"Seeding demo candidates for assignment: {assignment['title']} ({assignment_id})")

    # -- Candidate A: strong hire, clean, un-flagged, reserved for the LIVE
    # override demo beat -- do not flag or override this one here.
    link_a = make_link(assignment_id)
    sub_a = make_submission(assignment_id, link_a, FULL_FIX)
    add_logs(sub_a, [
        ("The rate limiter is letting burst traffic through past its configured "
         "capacity. Before I change anything, can you help me think through where "
         "a token-bucket limiter like this typically has off-by-one or staleness "
         "bugs?",
         "Two classic spots: the comparison operator in the consume check (>  vs "
         ">= against the token threshold changes whether the last available token "
         "can actually be spent), and whether every method that READS the token "
         "count also calls the refill step first, or whether some paths use a "
         "stale count computed before the last refill.",
         0),
        ("Checked is_allowed() -- it refills then checks 'tokens > 1', so a "
         "bucket sitting at exactly 1.0 tokens gets rejected even though it "
         "should be allowed to spend that token. That's bug 1, fixing to >=. Does "
         "get_wait_time() have the same staleness issue you mentioned?",
         "Look at it closely -- does it call _refill() before reading "
         "bucket['tokens'], or does it read the dict directly?",
         1),
        ("It reads bucket['tokens'] directly without refilling first, so "
         "get_wait_time() can report a wait time based on a token count that's "
         "already stale by the time a caller acts on it. Fixed both. Is the "
         "class-level _limiter on APIGateway also a concurrency risk given it's "
         "shared across all requests?",
         "Yes -- a single shared instance with no lock means concurrent threads "
         "can race inside the read-modify-write of a bucket's token count, even "
         "though bug 1 and 2 are unrelated to threading. Worth adding a lock "
         "around the point where handle_request touches the shared limiter.",
         1),
        ("Added a class-level lock around handle_request and wrote a docstring "
         "explaining why each fix was needed. Ran the concurrent burst test from "
         "the starter's __main__ block to confirm no client exceeds capacity "
         "under load.",
         "That covers all three documented bugs with a reasonable locking "
         "granularity for this scale.",
         1),
    ])
    score_and_report(sub_a, assignment, "Candidate A (strong hire, reserved for live override)")

    # -- Candidate B: solid hire, 2 of 3 bugs found and fixed with reasoning,
    # missed the stale-read bug in get_wait_time.
    link_b = make_link(assignment_id)
    sub_b = make_submission(assignment_id, link_b, DECENT_FIX)
    add_logs(sub_b, [
        ("Where should I look for the off-by-one in this token bucket limiter?",
         "Check the comparison operator against the token threshold in the "
         "consume/allow check.",
         0),
        ("Found it -- 'tokens > 1' should be '>= 1'. Also noticed the shared "
         "class-level limiter has no lock, added one around handle_request. "
         "Running low on time, submitting with those two fixes.",
         "Those are two of the documented issues -- worth a final pass on "
         "get_wait_time() if you have a moment, since it reads bucket state too.",
         1),
    ])
    score_and_report(sub_b, assignment, "Candidate B (solid hire, 2/3 bugs)")

    # -- Candidate C: real code change, ZERO session logs -> auto-flagged by
    # no_ai_engagement (do not add logs for this one, that's the point).
    link_c = make_link(assignment_id)
    sub_c = make_submission(assignment_id, link_c, DECENT_FIX)
    score_and_report(sub_c, assignment, "Candidate C (flagged: real fix, zero AI logs)")

    # -- Candidate D: unmodified starter code -> hard 0 via the no-change
    # short-circuit, no LLM call spent.
    link_d = make_link(assignment_id)
    sub_d = make_submission(assignment_id, link_d, STARTER)
    score_and_report(sub_d, assignment, "Candidate D (zero score: unmodified starter)")

    # -- Candidate E: only 1 of 3 bugs fixed, misidentified the rest -> select tier.
    link_e = make_link(assignment_id)
    sub_e = make_submission(assignment_id, link_e, WEAK_FIX)
    add_logs(sub_e, [
        ("fix the rate limiter",
         "Which specific symptom are you seeing -- burst traffic getting "
         "through, or something else? That'll narrow down which of the three "
         "known trouble spots to check first.",
         0),
        ("changed > to >= in is_allowed, think that's the main one",
         "That's one real fix. Have you checked whether get_wait_time() and the "
         "shared limiter's thread-safety are also worth a look, or are you "
         "confident that's the only issue?",
         1),
        ("pretty sure that's it, submitting",
         "Understood -- flagging that get_wait_time()'s staleness and the "
         "missing lock on the shared limiter weren't verified either way.",
         0),
    ])
    score_and_report(sub_e, assignment, "Candidate E (weak/select, 1/3 bugs)")

    # -- Candidate F: decent fix + logs (2/3 bugs, same pattern as B), then a
    # PRE-EXISTING override applied afterward, so the ranked list already has
    # one historical override to point at (independent of the live-override
    # beat on Candidate A).
    link_f = make_link(assignment_id)
    sub_f = make_submission(assignment_id, link_f, DECENT_FIX)
    add_logs(sub_f, [
        ("The limiter over-admits under burst load, where should I look?",
         "Start with the comparison operator in the token-consume check.",
         0),
        ("Fixed 'tokens > 1' to '>= 1', and added a lock around the shared "
         "class-level limiter since it looked unsafe under concurrency.",
         "Good catch on the lock -- that's a real issue even though it's "
         "separate from the off-by-one.",
         1),
    ])
    hire_row = score_and_report(sub_f, assignment, "Candidate F (pre-overridden historical example)")
    if hire_row:
        override_id = IDGenerator.generate_uuid()
        db_service.override_hire_evaluation(
            sub_f, "select", "AI composite understates this candidate -- they "
            "correctly reasoned about and fixed the concurrency bug, which "
            "carries real production risk, even though they missed the "
            "lower-severity staleness bug in get_wait_time(). Keeping for a "
            "follow-up technical screen rather than an outright pass.",
            ai_recommendation=hire_row[1], override_id=override_id)
        print(f"    -> override applied ({hire_row[1]} -> select, historical example)")

    print("\nDone. Ranked candidates for this assignment:")
    for row in db_service.get_candidates_for_assignment(assignment_id):
        print(f"  {row[0][:8]}  composite={row[4]}  rec={row[5]}")


if __name__ == "__main__":
    main()
