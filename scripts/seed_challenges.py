"""
Seed 10 hand-crafted challenges into the challenge catalog.

Usage (from project root):
    python scripts/seed_challenges.py           # skip existing titles
    python scripts/seed_challenges.py --force   # delete by title then re-insert

Prerequisite: the Flask app must have been started at least once so that
init_db() has created the challenges table, OR run:
    python -c "from app.models.database import Database; Database().init_db()"
"""

import argparse
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

from app.services.database_service import DatabaseService
from app.utils.helpers import IDGenerator


# ---------------------------------------------------------------------------
# Challenge starter-code definitions (one per variable for readability)
# ---------------------------------------------------------------------------

_SC_TOKEN_BUCKET = """\
import time
import threading
from typing import Optional


class TokenBucketRateLimiter:
    \"\"\"Token bucket rate limiter for API endpoint protection.\"\"\"

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
    \"\"\"Simulated API gateway with per-client rate limiting.\"\"\"

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
"""

_SC_LLM_CHAIN = """\
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModerationResult:
    raw_text: str
    entities: list[str] = field(default_factory=list)
    tone: str = ''
    severity: str = ''
    confidence: float = 0.0
    decision: str = ''
    rationale: str = ''


def get_llm_client():
    from openai import OpenAI
    return OpenAI(
        base_url='https://openrouter.ai/api/v1',
        api_key=os.getenv('OPENROUTER_API_KEY', ''),
    )


def stage1_extract(client, text: str) -> dict:
    \"\"\"Stage 1: extract named entities and detect tone.\"\"\"
    prompt = (
        'Extract named entities (people, places, organisations) and classify tone '
        '(positive/neutral/negative/hostile) from the text below.\\n'
        'Return JSON only: {"entities": [...], "tone": "..."}\\n\\n'
        f'Text: {text}'
    )
    resp = client.chat.completions.create(
        model='anthropic/claude-haiku-4-5',
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=256,
    )
    return json.loads(resp.choices[0].message.content)


def stage2_assess_severity(client, stage1_result: dict, original_text: str) -> str:
    # TODO: implement stage 2 using entities and tone from stage1_result
    # Should return one of: 'low', 'medium', 'high', 'critical'
    # Prompt must reference stage1_result['entities'] and stage1_result['tone']
    raise NotImplementedError('Stage 2 severity assessment not implemented')


def stage3_decision(client, stage1_result: dict, severity: str, original_text: str) -> dict:
    # TODO: implement stage 3 -- produce structured moderation decision
    # Return: {"decision": "allow|flag|block", "confidence": 0.0-1.0, "rationale": "..."}
    # Must use severity and entities from earlier stages in the prompt
    raise NotImplementedError('Stage 3 decision not implemented')


def _call_with_backoff(fn, *args, max_retries: int = 3, **kwargs):
    # TODO: implement exponential backoff
    # Catch openai.RateLimitError and retry with delay = 2**attempt seconds
    return fn(*args, **kwargs)


def moderate(text: str) -> ModerationResult:
    \"\"\"Run the full 3-stage moderation pipeline.\"\"\"
    client = get_llm_client()
    result = ModerationResult(raw_text=text)

    stage1 = _call_with_backoff(stage1_extract, client, text)
    result.entities = stage1.get('entities', [])
    result.tone = stage1.get('tone', 'unknown')

    result.severity = _call_with_backoff(stage2_assess_severity, client, stage1, text)

    verdict = _call_with_backoff(stage3_decision, client, stage1, result.severity, text)
    result.decision = verdict.get('decision', 'unknown')
    result.confidence = float(verdict.get('confidence', 0.0))
    result.rationale = verdict.get('rationale', '')
    return result


if __name__ == '__main__':
    samples = [
        'The weather today is quite pleasant.',
        'John Smith at Acme Corp is threatening to leak customer data.',
    ]
    for text in samples:
        print(f'Input: {text[:70]}')
        try:
            r = moderate(text)
            print(f'  Entities: {r.entities}, Tone: {r.tone}')
            print(f'  Severity: {r.severity}, Decision: {r.decision} ({r.confidence:.0%})')
        except NotImplementedError as e:
            print(f'  Not yet implemented: {e}')
"""

_SC_LOG_AGGREGATOR = """\
import re
import json
import urllib.request
from collections import defaultdict


NGINX_PATTERN = re.compile(
    r'(?P<ip>\\S+) \\S+ \\S+ \\[(?P<time>[^\\]]+)\\] '
    r'"(?P<method>\\S+) (?P<path>\\S+) \\S+" (?P<status>\\d{3}) (?P<size>\\d+)'
)
SLACK_WEBHOOK = 'https://hooks.slack.com/services/XXX/YYY/ZZZ'
ERROR_THRESHOLD = 0.05


def process_logs(log_file_path: str) -> None:
    \"\"\"Parse Nginx logs, aggregate errors, and alert via Slack.
    Refactor: split into parse / aggregate / report / alert stages.
    \"\"\"
    total = 0
    errors_by_path: dict[str, int] = defaultdict(int)
    counts_by_path: dict[str, int] = defaultdict(int)
    large_responses: list[str] = []
    ip_counts: dict[str, int] = defaultdict(int)

    with open(log_file_path) as f:
        for line in f:
            m = NGINX_PATTERN.match(line.strip())
            if not m:
                continue
            total += 1
            ip = m.group('ip')
            path = m.group('path').split('?')[0]
            status = int(m.group('status'))
            size = int(m.group('size'))
            ip_counts[ip] += 1
            counts_by_path[path] += 1
            if status >= 400:
                errors_by_path[path] += 1
            if size > 1_000_000:
                large_responses.append(path)

    print(f'Total requests: {total}')

    high_error_paths = []
    for path, count in counts_by_path.items():
        err = errors_by_path.get(path, 0)
        rate = err / count if count else 0
        if rate > ERROR_THRESHOLD:
            high_error_paths.append({'path': path, 'rate': rate, 'errors': err, 'total': count})
            print(f'  High error rate {path}: {rate:.1%} ({err}/{count})')

    top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f'Top IPs: {top_ips}')
    if large_responses:
        print(f'Large responses: {set(large_responses)}')

    if high_error_paths:
        payload = json.dumps({'text': f'Alert: {len(high_error_paths)} paths exceed error threshold'})
        req = urllib.request.Request(
            SLACK_WEBHOOK,
            data=payload.encode(),
            headers={'Content-Type': 'application/json'},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            print('Slack alert sent.')
        except Exception as e:
            print(f'Slack alert failed: {e}')


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python solution.py <nginx_access_log>')
        sys.exit(1)
    process_logs(sys.argv[1])
"""

_SC_BATCH_API = """\
import time
import requests
from typing import Optional


BASE_URL = 'https://api.github.com'
HEADERS = {'Accept': 'application/vnd.github.v3+json'}


def get_user_info(username: str) -> dict:
    \"\"\"Fetch GitHub user metadata. SLOW: no session reuse, no cache.\"\"\"
    response = requests.get(f'{BASE_URL}/users/{username}', headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()


def get_user_repos(username: str) -> list[dict]:
    \"\"\"Fetch all public repos. SLOW: sequential pagination + unnecessary sleep.\"\"\"
    repos: list[dict] = []
    page = 1
    while True:
        response = requests.get(
            f'{BASE_URL}/users/{username}/repos',
            params={'per_page': 100, 'page': page},
            headers=HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
        time.sleep(0.1)   # PERFORMANCE: unnecessary sleep on every page
    return repos


def analyze_users(usernames: list[str]) -> list[dict]:
    \"\"\"Return profile + repo stats for each user.
    PERFORMANCE issues:
    - Sequential loop: one user at a time, no concurrency
    - No caching: duplicate usernames trigger duplicate API calls
    - New TCP connection per call: no session pooling
    Target: run in < 2s for a list of 4-6 users.
    \"\"\"
    results: list[dict] = []
    for username in usernames:
        info = get_user_info(username)
        repos = get_user_repos(username)
        stars = sum(r.get('stargazers_count', 0) for r in repos)
        results.append({
            'username': info.get('login'),
            'name': info.get('name'),
            'followers': info.get('followers', 0),
            'public_repos': info.get('public_repos', 0),
            'total_stars': stars,
        })
    return results


if __name__ == '__main__':
    usernames = ['torvalds', 'gvanrossum', 'torvalds', 'kennethreitz']  # duplicate intentional
    start = time.perf_counter()
    results = analyze_users(usernames)
    elapsed = time.perf_counter() - start
    for r in results:
        print(f"{r['username']}: {r['followers']} followers, {r['total_stars']} stars")
    print(f'\\nCompleted in {elapsed:.2f}s  (target: < 2.0s with concurrency + caching)')
"""

_SC_ETL_PIPELINE = """\
import csv
import sqlite3
from datetime import datetime
from typing import Optional


def parse_record(row: dict) -> dict:
    \"\"\"Coerce a raw CSV row into the expected schema. Contains 3 bugs.\"\"\"
    # BUG 1: int('') raises ValueError on empty quantity; should default to 0
    quantity = int(row.get('quantity', '0'))

    # BUG 2: float('1,234.56') raises ValueError; strip commas before converting
    price = float(row.get('price', '0'))

    # BUG 3: date format mismatch -- CSV has YYYY-MM-DD but strptime expects DD/MM/YYYY
    raw_date = row.get('order_date', '').strip()
    order_date = datetime.strptime(raw_date, '%d/%m/%Y').date() if raw_date else None

    return {
        'order_id':   row.get('order_id', '').strip(),
        'product':    row.get('product', '').strip(),
        'quantity':   quantity,
        'unit_price': price,
        'total':      quantity * price,
        'order_date': order_date.isoformat() if order_date else None,
    }


def load_csv(filepath: str) -> list[dict]:
    records: list[dict] = []
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                records.append(parse_record(row))
            except (ValueError, AttributeError) as e:
                print(f'  Row {i+1} skipped: {e}')
    return records


def insert_records(conn: sqlite3.Connection, records: list[dict]) -> int:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id   TEXT PRIMARY KEY,
            product    TEXT NOT NULL,
            quantity   INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total      REAL NOT NULL,
            order_date TEXT
        )
    ''')
    cur = conn.executemany(
        'INSERT OR IGNORE INTO orders VALUES (:order_id,:product,:quantity,:unit_price,:total,:order_date)',
        records,
    )
    conn.commit()
    return cur.rowcount


if __name__ == '__main__':
    import os, tempfile
    sample = (
        'order_id,product,quantity,price,order_date\\n'
        'ORD-001,Widget A,5,9.99,2024-01-15\\n'
        'ORD-002,Widget B,,29.99,2024-01-16\\n'
        'ORD-003,Widget C,3,"1,234.56",2024-01-17\\n'
        'ORD-004,Widget D,1,4.99,\\n'
    )
    tmpfile = os.path.join(tempfile.gettempdir(), 'orders.csv')
    with open(tmpfile, 'w') as f:
        f.write(sample)

    records = load_csv(tmpfile)
    print(f'Parsed {len(records)} records (expected 4 if bugs fixed)')
    conn = sqlite3.connect(':memory:')
    inserted = insert_records(conn, records)
    print(f'Inserted {inserted} rows')
"""

_SC_LEADERBOARD = """\
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Player:
    player_id: str
    username: str
    score: int = 0
    level: int = 1
    wins: int = 0
    losses: int = 0
    joined_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Leaderboard:
    \"\"\"In-memory leaderboard with SQLite persistence.\"\"\"

    def __init__(self, db_path: str = ':memory:') -> None:
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                username  TEXT UNIQUE NOT NULL,
                score     INTEGER DEFAULT 0,
                level     INTEGER DEFAULT 1,
                wins      INTEGER DEFAULT 0,
                losses    INTEGER DEFAULT 0,
                joined_at TEXT NOT NULL
            )
        ''')
        self._conn.commit()

    def add_player(self, player: Player) -> None:
        self._conn.execute(
            'INSERT OR IGNORE INTO players VALUES (?,?,?,?,?,?,?)',
            (player.player_id, player.username, player.score,
             player.level, player.wins, player.losses, player.joined_at),
        )
        self._conn.commit()

    def record_match(self, winner_id: str, loser_id: str, score_delta: int = 10) -> None:
        self._conn.execute(
            'UPDATE players SET score = score + ?, wins = wins + 1 WHERE player_id = ?',
            (score_delta, winner_id),
        )
        self._conn.execute(
            'UPDATE players SET losses = losses + 1 WHERE player_id = ?', (loser_id,)
        )
        self._conn.commit()

    def get_top_players(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            'SELECT player_id,username,score,level,wins,losses FROM players ORDER BY score DESC LIMIT ?',
            (limit,),
        ).fetchall()
        return [{'rank': i+1, 'player_id': r[0], 'username': r[1],
                 'score': r[2], 'level': r[3], 'wins': r[4], 'losses': r[5]}
                for i, r in enumerate(rows)]

    # TODO: implement get_player_rank(self, player_id: str) -> int
    # Return 1-indexed rank by score descending; return -1 if not found.

    # TODO: implement promote_players(self) -> list[str]
    # Level thresholds: 2 >= 100pts, 3 >= 250pts, 4 >= 500pts.
    # Update DB and return list of player_ids that were promoted.

    # TODO: implement get_win_streak(self, player_id: str) -> int
    # Add a match_history table. Track each match (winner_id, loser_id, played_at).
    # Return current consecutive win streak for the given player.
    # Modify record_match() to also write to match_history.


if __name__ == '__main__':
    board = Leaderboard()
    players = [Player(str(uuid.uuid4()), name) for name in ['Alice', 'Bob', 'Carol', 'Dave']]
    for p in players:
        board.add_player(p)
    alice, bob, carol, dave = [p.player_id for p in players]
    board.record_match(alice, bob, 25)
    board.record_match(alice, carol, 30)
    board.record_match(carol, dave, 15)
    print('Leaderboard:')
    for e in board.get_top_players():
        print(f"  #{e['rank']} {e['username']}: {e['score']}pts  W{e['wins']}/L{e['losses']}")
"""

_SC_REST_CLIENT = """\
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Optional


BASE_URL = 'https://jsonplaceholder.typicode.com'
TIMEOUT = 10


def _request(method: str, path: str, body: Optional[dict] = None) -> Any:
    url = f'{BASE_URL}/{path.lstrip(\"/\")}'
    data = json.dumps(body).encode() if body else None
    headers = {'Accept': 'application/json'}
    if data:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {'error': e.reason, 'status': e.code}


def get_users() -> list[dict]:
    return _request('GET', '/users')


def get_user(user_id: int) -> dict:
    return _request('GET', f'/users/{user_id}')


def get_user_posts(user_id: int) -> list[dict]:
    return _request('GET', f'/posts?userId={user_id}')


def get_post(post_id: int) -> dict:
    return _request('GET', f'/posts/{post_id}')


def create_post(user_id: int, title: str, body: str) -> dict:
    return _request('POST', '/posts', {'userId': user_id, 'title': title, 'body': body})


def update_post(post_id: int, title: str, body: str) -> dict:
    return _request('PUT', f'/posts/{post_id}', {'title': title, 'body': body})


def delete_post(post_id: int) -> bool:
    result = _request('DELETE', f'/posts/{post_id}')
    return 'error' not in result


if __name__ == '__main__':
    users = get_users()
    print(f'Users: {len(users)}')

    user = get_user(1)
    print(f'User 1: {user[\"name\"]} ({user[\"email\"]})')

    posts = get_user_posts(1)
    print(f'User 1 posts: {len(posts)}')

    new = create_post(1, 'Clean Architecture', 'Separation of concerns matters.')
    print(f'Created post id: {new[\"id\"]}')

    updated = update_post(new['id'], 'Updated Title', 'Updated body.')
    print(f'Updated title: {updated[\"title\"]}')

    deleted = delete_post(new['id'])
    print(f'Deleted: {deleted}')
"""

_SC_CSV_OPTIMIZER = """\
import csv
import heapq
import time
import random
import os
import tempfile
from collections import defaultdict
from typing import Iterator


def read_sales_csv(filepath: str) -> list[dict]:
    \"\"\"Read entire CSV into memory. PERFORMANCE: loads all rows at once.\"\"\"
    with open(filepath, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def aggregate_by_region(rows: list[dict]) -> dict[str, float]:
    \"\"\"Sum revenue by region.
    PERFORMANCE: O(n * k) -- scans all rows once per unique region.
    Fix: single pass with defaultdict.
    \"\"\"
    regions = {row['region'] for row in rows}
    totals: dict[str, float] = {}
    for region in regions:
        totals[region] = sum(float(row['revenue']) for row in rows if row['region'] == region)
    return totals


def find_top_products(rows: list[dict], n: int = 5) -> list[tuple[str, float]]:
    \"\"\"Top-n products by total revenue.
    PERFORMANCE: sorts all products; use heapq.nlargest instead.
    \"\"\"
    product_totals: dict[str, float] = {}
    for row in rows:
        p = row['product']
        product_totals[p] = product_totals.get(p, 0) + float(row['revenue'])
    return sorted(product_totals.items(), key=lambda x: x[1], reverse=True)[:n]


def month_over_month_growth(rows: list[dict]) -> dict[str, float]:
    \"\"\"MoM revenue growth percentage.
    PERFORMANCE: four separate full scans of rows.
    Fix: single pass aggregation.
    \"\"\"
    months = sorted({row['month'] for row in rows})
    monthly: dict[str, float] = {}
    for month in months:
        monthly[month] = sum(float(row['revenue']) for row in rows if row['month'] == month)
    growth: dict[str, float] = {}
    for i in range(1, len(months)):
        prev, curr = months[i-1], months[i]
        if monthly[prev] > 0:
            growth[curr] = (monthly[curr] - monthly[prev]) / monthly[prev] * 100
    return growth


def full_report(filepath: str) -> dict:
    rows = read_sales_csv(filepath)
    return {
        'total_rows':  len(rows),
        'by_region':   aggregate_by_region(rows),
        'top_products': find_top_products(rows),
        'mom_growth':  month_over_month_growth(rows),
    }


if __name__ == '__main__':
    regions = ['North', 'South', 'East', 'West']
    products = [f'Product_{i}' for i in range(20)]
    months = ['2024-01', '2024-02', '2024-03', '2024-04']
    filepath = os.path.join(tempfile.gettempdir(), 'sales_data.csv')
    with open(filepath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['region', 'product', 'month', 'revenue'])
        for _ in range(50_000):
            w.writerow([random.choice(regions), random.choice(products),
                        random.choice(months), round(random.uniform(10, 1000), 2)])

    start = time.perf_counter()
    report = full_report(filepath)
    elapsed = time.perf_counter() - start
    print(f"Processed {report['total_rows']:,} rows in {elapsed:.3f}s")
    print(f"Top product: {report['top_products'][0]}")
    print(f"Target: < 0.5s using single-pass aggregation and heapq.nlargest")
"""

_SC_LLM_TOOLS = """\
import json
import os
from typing import Any, Callable


TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'get_weather',
            'description': 'Get current weather for a city.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'city': {'type': 'string'},
                    'units': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                },
                'required': ['city'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_web',
            'description': 'Search the web and return top results.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string'},
                    'max_results': {'type': 'integer'},
                },
                'required': ['query'],
            },
        },
    },
]


def get_weather(city: str, units: str = 'celsius') -> dict:
    return {'city': city, 'temperature': 22, 'units': units, 'condition': 'sunny'}


def search_web(query: str, max_results: int = 5) -> dict:
    return {'query': query, 'results': [f'Result {i} for {query}' for i in range(max_results)]}


TOOL_REGISTRY: dict[str, Callable] = {
    'get_weather': get_weather,
    'search_web': search_web,
}


def run_agent(user_message: str) -> str:
    \"\"\"Agentic loop that uses tools to answer the user. Contains 3 bugs.\"\"\"
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY', ''))
    messages = [{'role': 'user', 'content': user_message}]

    for _ in range(5):
        resp = client.chat.completions.create(
            model='anthropic/claude-haiku-4-5',
            messages=messages,
            tools=TOOLS,
            tool_choice='auto',
        )
        choice = resp.choices[0]

        # BUG 1: should check finish_reason == 'tool_calls', not content is None
        if choice.message.content is not None:
            return choice.message.content

        tool_calls = choice.message.tool_calls or []
        # BUG 2: missing messages.append(choice.message) -- assistant turn required before tool results

        for tc in tool_calls:
            fn_name = tc.function.name
            # BUG 3: tc.function.arguments is a JSON string; must call json.loads() first
            fn_args = tc.function.arguments
            fn = TOOL_REGISTRY.get(fn_name)
            result = fn(**fn_args) if fn else {'error': f'Unknown tool: {fn_name}'}
            messages.append({'role': 'tool', 'tool_call_id': tc.id, 'content': json.dumps(result)})

    return 'Agent exceeded max iterations.'


if __name__ == '__main__':
    queries = [
        'What is the weather in Tokyo in Celsius?',
        'Search for Python 3.13 release notes.',
    ]
    for q in queries:
        print(f'Query: {q}')
        try:
            print(f'Answer: {run_agent(q)}')
        except Exception as e:
            print(f'Error: {e}')
"""

_SC_SLIDING_WINDOW = """\
import time
import threading
from collections import deque
from typing import Optional


class FixedWindowRateLimiter:
    \"\"\"Fixed-window rate limiter (baseline -- has boundary burst problem).\"\"\"

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counts: dict[str, int] = {}
        self._window_start: dict[str, float] = {}

    def is_allowed(self, client_id: str) -> bool:
        now = time.monotonic()
        start = self._window_start.get(client_id, 0)
        if now - start >= self.window_seconds:
            self._window_start[client_id] = now
            self._counts[client_id] = 0
        count = self._counts.get(client_id, 0)
        if count < self.max_requests:
            self._counts[client_id] = count + 1
            return True
        return False


class RateLimitMiddleware:
    \"\"\"Wraps any rate limiter; tracks allow/block counts.\"\"\"

    def __init__(self, limiter: FixedWindowRateLimiter) -> None:
        self.limiter = limiter
        self._allowed = 0
        self._blocked = 0

    def process(self, client_id: str, path: str = '/') -> dict:
        if self.limiter.is_allowed(client_id):
            self._allowed += 1
            return {'status': 200, 'path': path}
        self._blocked += 1
        return {'status': 429, 'error': 'rate_limit_exceeded'}

    @property
    def stats(self) -> dict:
        total = self._allowed + self._blocked
        return {'allowed': self._allowed, 'blocked': self._blocked,
                'block_rate': self._blocked / total if total else 0.0}


# TODO: implement SlidingWindowRateLimiter
# Track per-client deque of request timestamps.
# On is_allowed():
#   1. Evict timestamps older than window_seconds from the front of the deque.
#   2. If len(deque) < max_requests: append now and return True.
#   3. Otherwise return False.
# Must be thread-safe: use a threading.Lock per client.
#
# class SlidingWindowRateLimiter:
#     def __init__(self, max_requests: int, window_seconds: int) -> None: ...
#     def is_allowed(self, client_id: str) -> bool: ...
#     def get_remaining(self, client_id: str) -> int: ...
#     def reset(self, client_id: str) -> None: ...


def compare_limiters() -> None:
    \"\"\"Demonstrate boundary burst: fixed window allows 2x burst at window edge.\"\"\"
    print('--- Fixed window (5 req/5s) ---')
    fixed = FixedWindowRateLimiter(5, 5)
    for i in range(12):
        status = 200 if fixed.is_allowed('client') else 429
        print(f'  t+{i:02d}s: {status}')
        time.sleep(1)


if __name__ == '__main__':
    compare_limiters()
    # After implementing SlidingWindowRateLimiter, add:
    # print('\\n--- Sliding window (5 req/5s) ---')
    # sliding = SlidingWindowRateLimiter(5, 5)
    # mw = RateLimitMiddleware(sliding)
    # for i in range(12):
    #     print(f'  t+{i:02d}s: {mw.process(\"client\")[\"status\"]}')
    #     time.sleep(1)
    # print(mw.stats)
"""


# ---------------------------------------------------------------------------
# Challenge catalog records
# ---------------------------------------------------------------------------

CHALLENGES = [
    {
        'title': 'Token Bucket Rate Limiter',
        'challenge_type': 'bug_fix',
        'skill_area': 'rate_limiting',
        'difficulty': 'medium',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "A fintech startup's API gateway incorrectly allows burst traffic through its token "
            "bucket rate limiter. Three bugs were introduced during a late-night hotfix: the token "
            "consumption check uses the wrong comparison operator, the wait-time calculator reads a "
            "stale token count, and the class-level limiter instance is shared across threads without "
            "a lock. Find and fix all three bugs."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Fix BUG 1: token threshold >= 1 instead of > 1 (2 pts)',
                'Fix BUG 2: call _refill() in get_wait_time() before measuring deficit (2 pts)',
                'Fix BUG 3: add threading.Lock around bucket mutations (3 pts)',
                'Concurrent test passes without race conditions (2 pts)',
                'Explain each bug found in a comment or docstring (1 pt)',
            ]
        },
        'starter_code': _SC_TOKEN_BUCKET,
    },
    {
        'title': 'LLM Prompt Chain Pipeline',
        'challenge_type': 'feature_extension',
        'skill_area': 'llm_usage',
        'difficulty': 'hard',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "You are extending a content moderation system. Stage 1 (entity extraction + tone "
            "detection) is implemented. Add stage 2 (severity assessment using stage 1 metadata) "
            "and stage 3 (structured moderation decision with confidence score). The chain must "
            "pass context between stages, and all LLM calls must use exponential backoff on rate "
            "limit errors."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Stage 2 correctly uses entities and tone from stage 1 result (3 pts)',
                'Stage 3 returns valid decision/confidence/rationale structure (2 pts)',
                '_call_with_backoff implements exponential backoff on RateLimitError (3 pts)',
                'Context flows correctly through all 3 stages (2 pts)',
            ]
        },
        'starter_code': _SC_LLM_CHAIN,
    },
    {
        'title': 'Server Log Aggregator',
        'challenge_type': 'refactoring',
        'skill_area': 'server_monitoring',
        'difficulty': 'medium',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "A production monitoring script has grown to 60+ lines without any structure — parsing, "
            "aggregation, and alerting all happen inside one function with hardcoded magic values and "
            "no separation of concerns. Refactor it into a clean, testable architecture (parser, "
            "aggregator, reporter, alerter) while keeping the observable output identical."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Parsing separated from aggregation from alerting (3 pts)',
                'No duplicated regex patterns or magic numbers (2 pts)',
                'Slack webhook URL extracted to config or constant (1 pt)',
                'Each new function/class is independently testable (2 pts)',
                'Output matches original behaviour (2 pts)',
            ]
        },
        'starter_code': _SC_LOG_AGGREGATOR,
    },
    {
        'title': 'Batch API Client Optimizer',
        'challenge_type': 'optimization',
        'skill_area': 'api_integration',
        'difficulty': 'hard',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "An analytics service fetches GitHub user profiles sequentially with no caching, "
            "no connection pooling, and an unnecessary sleep on each paginated request. With 4-6 "
            "users the function takes 3-5 seconds. Optimize it to run in under 2 seconds using "
            "concurrent requests (ThreadPoolExecutor or asyncio), an LRU cache to skip duplicate "
            "usernames, and a persistent HTTP session."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Concurrent requests via ThreadPoolExecutor or asyncio (3 pts)',
                'LRU cache prevents duplicate API calls for the same username (2 pts)',
                'Persistent requests.Session used for connection pooling (2 pts)',
                'Unnecessary sleep removed (1 pt)',
                'Runtime < 2.0s demonstrated in __main__ block output (2 pts)',
            ]
        },
        'starter_code': _SC_BATCH_API,
    },
    {
        'title': 'ETL Pipeline Type Coercion Bug',
        'challenge_type': 'bug_fix',
        'skill_area': 'data_pipeline',
        'difficulty': 'easy',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "A CSV-to-SQLite ETL pipeline fails silently on real-world data: empty quantity fields "
            "raise ValueError, prices formatted with thousands separators cannot be parsed, and the "
            "date format in the data does not match the strptime format string. Fix all three bugs "
            "so the sample data loads cleanly."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Empty quantity defaults to 0 instead of raising ValueError (2 pts)',
                'Price strings with comma separators parsed correctly (2 pts)',
                'Date format corrected to match YYYY-MM-DD input (2 pts)',
                'All 4 sample rows inserted without skipping (2 pts)',
                'Fix is defensive (handles other edge cases of same type) (2 pts)',
            ]
        },
        'starter_code': _SC_ETL_PIPELINE,
    },
    {
        'title': 'Game Leaderboard Extension',
        'challenge_type': 'feature_extension',
        'skill_area': 'game_logic',
        'difficulty': 'medium',
        'ai_assistance_mode': 'guarded',
        'description': (
            "A SQLite-backed game leaderboard tracks players, scores, wins, and losses. Three "
            "features are missing: player rank lookup, automatic level promotion based on score "
            "thresholds, and win-streak calculation from match history. Implement all three. "
            "The match_history table (for win streaks) does not yet exist — add it."
        ),
        'evaluation_rubric': {
            'criteria': [
                'get_player_rank() returns correct 1-indexed rank or -1 if not found (3 pts)',
                'promote_players() updates level correctly at 100/250/500 thresholds (3 pts)',
                'match_history table created and populated by record_match() (2 pts)',
                'get_win_streak() returns correct consecutive wins from history (2 pts)',
            ]
        },
        'starter_code': _SC_LEADERBOARD,
    },
    {
        'title': 'REST API Client Refactor',
        'challenge_type': 'refactoring',
        'skill_area': 'api_integration',
        'difficulty': 'easy',
        'ai_assistance_mode': 'guarded',
        'description': (
            "A REST client for JSONPlaceholder has grown by copy-pasting request boilerplate into "
            "every function. The code works but each function repeats identical URL construction, "
            "header setup, and JSON decoding. Refactor to eliminate duplication via a shared "
            "_request() helper while keeping the public function signatures identical."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Single _request() helper handles all HTTP methods (3 pts)',
                'No repeated header setup or JSON decode across functions (2 pts)',
                'All public functions (get_users, create_post, etc.) preserved with same signatures (2 pts)',
                'Error handling consistent across all calls (2 pts)',
                'All __main__ assertions still pass after refactor (1 pt)',
            ]
        },
        'starter_code': _SC_REST_CLIENT,
    },
    {
        'title': 'CSV Stream Optimizer',
        'challenge_type': 'optimization',
        'skill_area': 'data_pipeline',
        'difficulty': 'medium',
        'ai_assistance_mode': 'guarded',
        'description': (
            "A sales report generator processes 50,000 CSV rows in ~1.5 seconds because it scans "
            "all rows once per unique region (O(n*k)), sorts all products to find the top-5, and "
            "makes four separate passes for month-over-month calculations. Rewrite each function to "
            "use a single pass with defaultdict aggregation and heapq.nlargest."
        ),
        'evaluation_rubric': {
            'criteria': [
                'aggregate_by_region uses single O(n) pass with defaultdict (3 pts)',
                'find_top_products uses heapq.nlargest instead of full sort (2 pts)',
                'month_over_month_growth uses single pass (2 pts)',
                'Overall runtime < 0.5s on 50k rows (2 pts)',
                'Output identical to original (1 pt)',
            ]
        },
        'starter_code': _SC_CSV_OPTIMIZER,
    },
    {
        'title': 'LLM Tool Call Handler',
        'challenge_type': 'bug_fix',
        'skill_area': 'llm_usage',
        'difficulty': 'hard',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "An agentic loop that calls weather and web-search tools has three bugs that prevent "
            "it from working: the loop exits on content presence instead of checking finish_reason, "
            "the assistant's tool-call message is never appended before tool results (violating the "
            "conversation format), and tool arguments are passed as a raw JSON string instead of a "
            "parsed dict. Fix all three bugs."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Loop continues when finish_reason == \"tool_calls\" regardless of content (3 pts)',
                'Assistant message with tool_calls appended before tool result messages (3 pts)',
                'Tool arguments parsed via json.loads() before function call (2 pts)',
                'Both sample queries return a real answer, not an error (2 pts)',
            ]
        },
        'starter_code': _SC_LLM_TOOLS,
    },
    {
        'title': 'Sliding Window Rate Limiter',
        'challenge_type': 'feature_extension',
        'skill_area': 'rate_limiting',
        'difficulty': 'medium',
        'ai_assistance_mode': 'unguarded',
        'description': (
            "A fixed-window rate limiter is in production but allows boundary bursts: a client can "
            "send max_requests at the end of one window and max_requests at the start of the next, "
            "effectively doubling throughput. Implement SlidingWindowRateLimiter using a per-client "
            "timestamp deque. Also add get_remaining() and reset() methods. The implementation must "
            "be thread-safe."
        ),
        'evaluation_rubric': {
            'criteria': [
                'Sliding window correctly evicts expired timestamps on each call (3 pts)',
                'Thread-safe: per-client threading.Lock used (2 pts)',
                'get_remaining() returns accurate count for current window (2 pts)',
                'reset() clears client state (1 pt)',
                'compare_limiters() demo shows sliding window prevents boundary burst (2 pts)',
            ]
        },
        'starter_code': _SC_SLIDING_WINDOW,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def title_exists(db_service: DatabaseService, title: str) -> bool:
    with db_service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM challenges WHERE title = ? LIMIT 1', (title,))
        return cursor.fetchone() is not None


def delete_by_title(db_service: DatabaseService, title: str) -> None:
    with db_service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM challenges WHERE title = ?', (title,))
        conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed(force: bool = False) -> None:
    db_service = DatabaseService()
    inserted = 0
    skipped = 0
    failed = 0

    for c in CHALLENGES:
        title = c['title']

        if force:
            delete_by_title(db_service, title)

        if title_exists(db_service, title):
            print(f"  Skipped (exists): {title}")
            skipped += 1
            continue

        challenge_id = IDGenerator.generate_uuid()
        try:
            db_service.create_challenge(
                challenge_id=challenge_id,
                title=title,
                domain=c['skill_area'],
                description=c['description'],
                starter_code=c['starter_code'],
                challenge_type=c['challenge_type'],
                skill_area=c['skill_area'],
                difficulty=c['difficulty'],
                ai_assistance_mode=c['ai_assistance_mode'],
                evaluation_rubric_json=json.dumps(c['evaluation_rubric']),
            )
            db_service.publish_challenge(challenge_id)
            print(f"  Seeded: {title}")
            inserted += 1
        except Exception as exc:
            prefix = "deleted but not re-inserted" if force else "failed to insert"
            print(f"  ERROR ({prefix}): {title} -- {exc}")
            failed += 1

    summary = f"\nDone: {inserted} inserted, {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    print(summary + ".")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Seed 10 curated challenges into the challenge catalog.',
        epilog='Run from the project root. The Flask app must have been started at least once.',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Delete challenges matching seeded titles then re-insert (use to refresh content).',
    )
    args = parser.parse_args()
    seed(force=args.force)
