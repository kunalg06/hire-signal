from flask import Flask, render_template_string, request, jsonify, send_file
from typing import Optional, List, Tuple
import secrets
import uuid
import sqlite3
import docker
import subprocess
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import anthropic
import os
import re
import ast
from collections import defaultdict
from time import time as current_time
import io
import tarfile

# ============================================================================
# Initialize Flask App & Docker Client
# ============================================================================

app = Flask(__name__, static_folder=None)
app.config['JSON_SORT_KEYS'] = False

# Rate limiting for challenge generation (max 5 requests per minute per IP)
_rate_limit_store = defaultdict(list)
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW = 60

def check_rate_limit(client_ip: str) -> bool:
    """Check if client exceeds rate limit. Returns True if allowed."""
    now = current_time()
    timestamps = _rate_limit_store[client_ip]
    _rate_limit_store[client_ip] = [ts for ts in timestamps if now - ts < RATE_LIMIT_WINDOW]

    if len(_rate_limit_store[client_ip]) < RATE_LIMIT_REQUESTS:
        _rate_limit_store[client_ip].append(now)
        return True
    return False

# Docker client - lazy initialization
_docker_client = None

def get_docker_client():
    """Get or initialize Docker client lazily"""
    global _docker_client
    if _docker_client is None:
        try:
            docker_host = os.getenv('DOCKER_HOST')
            if docker_host:
                _docker_client = docker.DockerClient(base_url=docker_host)
            else:
                _docker_client = docker.from_env()
        except Exception as e:
            print(f"Warning: Could not connect to Docker daemon: {e}")
            return None
    return _docker_client

# Anthropic client - lazy initialization
_anthropic_client = None

def get_anthropic_client():
    """Get or initialize Anthropic client lazily"""
    global _anthropic_client
    if _anthropic_client is None:
        try:
            _anthropic_client = anthropic.Anthropic()
        except Exception as e:
            print(f"Warning: Could not initialize Anthropic client: {e}")
            return None
    return _anthropic_client

# Database setup
DB_PATH = "assignments.db"

def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create assignments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            starter_code TEXT,
            evaluation_criteria TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create session links table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_links (
            link_id TEXT PRIMARY KEY,
            assignment_id TEXT NOT NULL,
            container_id TEXT,
            port INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY(assignment_id) REFERENCES assignments(id)
        )
    ''')

    # Create submissions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id TEXT PRIMARY KEY,
            link_id TEXT NOT NULL,
            assignment_id TEXT NOT NULL,
            code TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluation_result TEXT,
            score REAL,
            feedback TEXT,
            files_json TEXT,
            evaluated_at TIMESTAMP,
            FOREIGN KEY(link_id) REFERENCES session_links(link_id),
            FOREIGN KEY(assignment_id) REFERENCES assignments(id)
        )
    ''')

    # Create submission files table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submission_files (
            file_id TEXT PRIMARY KEY,
            submission_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_content TEXT,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
        )
    ''')

    # Create session logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_logs (
            log_id TEXT PRIMARY KEY,
            submission_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            interaction_type TEXT,
            prompt TEXT,
            response_summary TEXT,
            file_changes_count INTEGER DEFAULT 0,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(submission_id) REFERENCES submissions(submission_id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# ============================================================================
# Helper Functions
# ============================================================================

def get_client_ip(req):
    """Extract client IP from request"""
    if req.environ.get('HTTP_X_FORWARDED_FOR'):
        return req.environ['HTTP_X_FORWARDED_FOR'].split(',')[0]
    return req.remote_addr or "unknown"

def parse_claude_session_log(log_content: str) -> list:
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

def score_from_session_logs(session_logs: list, container_creation_time: str = None) -> Tuple[int, int]:
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
            print(f"Error calculating efficiency score: {e}")
            efficiency_score = 15

    # Clamp to ensure scores stay in 0-30 range
    efficiency_score = max(0, min(30, efficiency_score))
    approach_score = max(0, min(30, approach_score))

    return (approach_score, efficiency_score)

def evaluate_code_with_claude(code: str, assignment: dict, session_logs: list = None, container_created_at: str = None) -> dict:
    """Evaluate code using Claude API with session log scoring"""
    anthropic_client = get_anthropic_client()
    if not anthropic_client:
        return {
            "score": 0,
            "feedback": "Claude API client not available",
            "evaluation_details": {"error": "API unavailable"},
            "code_quality_score": 0,
            "approach_score": 0,
            "efficiency_score": 0,
            "combined_score": 0
        }

    # Evaluate code quality with Claude
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
        message = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
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
    approach_score, efficiency_score = score_from_session_logs(session_logs, container_created_at)

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

def evaluate_submission_files(submission_id: str, assignment: dict, session_logs: list = None, container_created_at: str = None):
    """Evaluate submitted files with session log scoring"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get solution.py content
        cursor.execute('''
            SELECT file_content FROM submission_files
            WHERE submission_id = ? AND filename = 'solution.py'
        ''', (submission_id,))

        solution_row = cursor.fetchone()
        code = solution_row[0] if solution_row else "# No solution.py found"

        # If session_logs not provided, retrieve from database
        if session_logs is None:
            cursor.execute('''
                SELECT timestamp, interaction_type, prompt, response_summary, file_changes_count
                FROM session_logs
                WHERE submission_id = ?
                ORDER BY timestamp ASC
            ''', (submission_id,))

            rows = cursor.fetchall()
            session_logs = [
                {
                    'timestamp': row[0],
                    'interaction_type': row[1],
                    'prompt': row[2],
                    'response_summary': row[3],
                    'file_changes_count': row[4]
                }
                for row in rows
            ] if rows else []

        # If container_created_at not provided, get from session_links
        if container_created_at is None:
            cursor.execute('''
                SELECT sl.created_at FROM submissions s
                JOIN session_links sl ON s.link_id = sl.link_id
                WHERE s.submission_id = ?
            ''', (submission_id,))

            time_row = cursor.fetchone()
            container_created_at = time_row[0] if time_row else None

        # Evaluate with Claude
        evaluation = evaluate_code_with_claude(code, assignment, session_logs, container_created_at)

        # Update submission with evaluation results
        cursor.execute('''
            UPDATE submissions
            SET score = ?, feedback = ?, evaluation_result = ?, evaluated_at = ?
            WHERE submission_id = ?
        ''', (
            evaluation["score"],
            evaluation["feedback"],
            json.dumps(evaluation["evaluation_details"]),
            datetime.now().isoformat(),
            submission_id
        ))

        conn.commit()
        print(f"Evaluation complete for submission {submission_id}: score={evaluation['score']:.1f}")

    except Exception as e:
        print(f"Error evaluating submission {submission_id}: {e}")
    finally:
        conn.close()

def cleanup_container(container_id: str):
    """Clean up Docker container after submission"""
    try:
        docker_client = get_docker_client()
        if docker_client:
            container = docker_client.containers.get(container_id)
            container.stop(timeout=5)
            print(f"Stopped container {container_id[:12]}")
    except Exception as e:
        print(f"Error cleaning up container {container_id}: {e}")

# ============================================================================
# API Routes
# ============================================================================

@app.route('/api/assignments', methods=['POST'])
def create_assignment():
    """Create a new assignment"""
    data = request.get_json()

    if not data or not data.get('title') or not data.get('evaluation_criteria'):
        return jsonify({"detail": "Missing required fields"}), 400

    assignment_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO assignments (id, title, description, starter_code, evaluation_criteria)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        assignment_id,
        data.get('title'),
        data.get('description', ''),
        data.get('starter_code', ''),
        data.get('evaluation_criteria')
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "id": assignment_id,
        "title": data.get('title'),
        "description": data.get('description', ''),
        "starter_code": data.get('starter_code', ''),
        "evaluation_criteria": data.get('evaluation_criteria')
    })

@app.route('/api/assignments/<assignment_id>', methods=['GET'])
def get_assignment(assignment_id):
    """Get assignment details"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM assignments WHERE id = ?', (assignment_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"detail": "Assignment not found"}), 404

    return jsonify({
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "starter_code": row[3],
        "evaluation_criteria": row[4]
    })

@app.route('/api/generate-link/<assignment_id>', methods=['POST'])
def generate_link(assignment_id):
    """Generate student access link"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get assignment
    cursor.execute('SELECT * FROM assignments WHERE id = ?', (assignment_id,))
    assignment_row = cursor.fetchone()

    if not assignment_row:
        conn.close()
        return jsonify({"detail": "Assignment not found"}), 404

    # Create unique link
    link_id = secrets.token_urlsafe(32)

    # Create Docker container
    docker_client = get_docker_client()
    port = None
    container_id = None

    if docker_client:
        for port_attempt in range(6000, 7000):
            try:
                volumes = {
                    'assignments_volume': {
                        'bind': '/workspace',
                        'mode': 'rw'
                    }
                }

                print(f"Attempt {port_attempt - 5999}: Starting container for assignment {assignment_id} on port {port_attempt}")

                container = docker_client.containers.create(
                    "code-server-http:latest",
                    name=f"assignment_{assignment_id}_{secrets.token_hex(4)}",
                    ports={'8080/tcp': port_attempt},
                    volumes=volumes,
                    environment={},
                    detach=True
                )

                container.start()
                port = port_attempt
                container_id = container.id
                print(f"Container started successfully: {container_id[:12]} on port {port}")
                break
            except Exception as e:
                if "already allocated" in str(e):
                    continue
                print(f"Container creation failed: {e}")
                break

    # Store link
    expires_at = datetime.now() + timedelta(hours=24)
    cursor.execute('''
        INSERT INTO session_links (link_id, assignment_id, container_id, port, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (link_id, assignment_id, container_id, port, expires_at.isoformat()))

    conn.commit()
    conn.close()

    return jsonify({
        "link_id": link_id,
        "assignment_id": assignment_id,
        "access_url": f"http://localhost:{port}" if port else "N/A",
        "vscode_port": port,
        "expires_at": expires_at.isoformat()
    })

@app.route('/student/<link_id>')
def student_dashboard(link_id):
    """Serve student dashboard with embedded code-server"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT sl.assignment_id, sl.port, a.title, a.description, a.evaluation_criteria, a.starter_code, sl.expires_at
        FROM session_links sl
        JOIN assignments a ON sl.assignment_id = a.id
        WHERE sl.link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"detail": "Session not found"}), 404

    assignment_id, port, title, description, criteria, starter_code, expires_at = row

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Coding Challenge</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 32px;
                margin-bottom: 10px;
            }}
            .content {{
                padding: 40px;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 40px;
            }}
            .section {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }}
            .section h2 {{
                color: #667eea;
                margin-bottom: 15px;
                font-size: 20px;
            }}
            .section p {{
                color: #555;
                line-height: 1.6;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .editor-section {{
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                min-height: 600px;
            }}
            .editor-section iframe {{
                width: 100%;
                height: 600px;
                border: none;
            }}
            .btn {{
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: 600;
            }}
            .btn-primary {{
                background: #667eea;
                color: white;
                width: 100%;
                margin-top: 15px;
            }}
            .btn-primary:hover {{
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
            }}
            .status {{
                padding: 15px;
                border-radius: 6px;
                text-align: center;
                font-weight: 600;
                display: none;
                margin-top: 15px;
            }}
            .status.success {{
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }}
            .status.error {{
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }}
            .status.loading {{
                background: #e2e3e5;
                color: #383d41;
            }}
            #results {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                max-height: 400px;
                overflow-y: auto;
                margin-top: 20px;
                display: none;
            }}
            #sessionLogsList {{
                font-size: 13px;
                color: #666;
            }}
            .log-entry {{
                background: #f5f5f5;
                padding: 10px;
                margin: 5px 0;
                border-radius: 4px;
                border-left: 3px solid #667eea;
            }}
            .timer {{
                text-align: center;
                padding: 15px;
                background: #fff3cd;
                border-radius: 6px;
                color: #856404;
                font-weight: 600;
                margin-top: 15px;
            }}
            @media (max-width: 768px) {{
                .content {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 {title}</h1>
                <p>AI Engineering Assessment & Evaluation Platform</p>
            </div>

            <div class="content">
                <div>
                    <div class="section">
                        <h2>📋 Assignment</h2>
                        <p>{description}</p>
                    </div>

                    <div class="section" style="margin-top: 20px;">
                        <h2>✅ Evaluation Criteria</h2>
                        <p>{criteria}</p>
                    </div>

                    <button id="submitBtn" class="btn btn-primary">📤 Submit Solution</button>
                    <div id="status" class="status"></div>

                    <div id="results">
                        <h3 style="color: #667eea; margin-bottom: 15px;">✅ Evaluation Results</h3>
                        <div id="scoreDisplay" style="font-size: 18px; font-weight: bold; margin: 15px 0; color: #667eea;">Score: <span id="scoreValue">--</span>/100</div>
                        <div id="feedbackDisplay" style="color: #555; line-height: 1.6; white-space: pre-wrap; word-break: break-word;"></div>
                        <div id="sessionLogsPanel" style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd;">
                            <h4 style="color: #667eea; margin-bottom: 10px;">📝 Claude Session Logs</h4>
                            <div id="sessionLogsList" style="font-size: 13px; color: #666;"></div>
                        </div>
                    </div>

                    <div class="timer">
                        ⏰ Session Expires: <span id="timer">--:--:--</span>
                    </div>
                </div>

                <div>
                    <div class="editor-section">
                        <iframe src="http://localhost:{port}/?folder=/workspace" allow="clipboard-read; clipboard-write" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-presentation"></iframe>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const LINK_ID = "{link_id}";

            function updateTimer() {{
                const expiresAt = new Date('{expires_at}').getTime();
                if (expiresAt > 0) {{
                    const now = new Date().getTime();
                    const remaining = expiresAt - now;

                    if (remaining <= 0) {{
                        document.getElementById('timer').textContent = 'Expired';
                    }} else {{
                        const hours = Math.floor((remaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
                        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);
                        document.getElementById('timer').textContent =
                            `${{hours}}:${{String(minutes).padStart(2, '0')}}:${{String(seconds).padStart(2, '0')}}`;
                    }}
                }}
            }}

            setInterval(updateTimer, 1000);
            updateTimer();

            document.getElementById('submitBtn').addEventListener('click', async () => {{
                const submitBtn = document.getElementById('submitBtn');
                const statusDiv = document.getElementById('status');

                submitBtn.disabled = true;
                statusDiv.textContent = '⏳ Submitting...';
                statusDiv.className = 'status loading';
                statusDiv.style.display = 'block';

                try {{
                    const response = await fetch(`/api/submit-with-files/${{LINK_ID}}`, {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}}
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        statusDiv.textContent = '⏳ Evaluating...';
                        await new Promise(r => setTimeout(r, 2000));

                        const resultRes = await fetch(`/api/submission/${{data.submission_id}}`);
                        const resultData = await resultRes.json();

                        const logsRes = await fetch(`/api/session-logs/${{data.submission_id}}`);
                        const logsData = logsRes.ok ? await logsRes.json() : {{'logs': []}};

                        displayResults(resultData, logsData);

                        statusDiv.textContent = '✅ Submission successful!';
                        statusDiv.className = 'status success';
                    }} else {{
                        statusDiv.textContent = '❌ ' + (data.detail || 'Submission failed');
                        statusDiv.className = 'status error';
                    }}
                }} catch (error) {{
                    statusDiv.textContent = '❌ Error: ' + error.message;
                    statusDiv.className = 'status error';
                }} finally {{
                    submitBtn.disabled = false;
                }}
            }});

            function displayResults(submission, sessionLogs) {{
                const scoreValue = submission.score ? submission.score.toFixed(1) : '0';
                document.getElementById('scoreValue').textContent = scoreValue;
                document.getElementById('feedbackDisplay').textContent = submission.feedback || 'No feedback available';

                const logs = sessionLogs.logs || [];
                const logsList = document.getElementById('sessionLogsList');

                if (logs.length === 0) {{
                    logsList.innerHTML = '<p>No Claude interactions recorded</p>';
                }} else {{
                    logsList.innerHTML = logs.map(log => `
                        <div class="log-entry">
                            <strong>${{log.timestamp}}</strong><br/>
                            <strong>Prompt:</strong> ${{log.prompt}}<br/>
                            <strong>Response:</strong> ${{log.response_summary}}<br/>
                            <strong>Files Changed:</strong> ${{log.file_changes_count}}
                        </div>
                    `).join('');
                }}

                document.getElementById('results').style.display = 'block';
            }}
        </script>
    </body>
    </html>
    """

    return html_content, 200, {'Content-Type': 'text/html'}

@app.route('/api/submit-with-files/<link_id>', methods=['POST'])
def submit_with_files(link_id):
    """Submit files from student workspace"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get session and assignment info
    cursor.execute('''
        SELECT sl.container_id, sl.assignment_id, a.title, a.description, a.evaluation_criteria
        FROM session_links sl
        JOIN assignments a ON sl.assignment_id = a.id
        WHERE sl.link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"detail": "Session not found"}), 404

    container_id, assignment_id, title, description, criteria = row

    # Create assignment dict for evaluation
    assignment = {
        "id": assignment_id,
        "title": title,
        "description": description,
        "evaluation_criteria": criteria
    }

    # Collect files from container
    files_dict = {}
    docker_client = get_docker_client()

    if docker_client and container_id:
        try:
            container = docker_client.containers.get(container_id)

            def extract_file_from_tar(file_path: str):
                try:
                    bits, stat = container.get_archive(file_path)
                    tar_stream = b''.join(bits)
                    tar_file = tarfile.open(fileobj=io.BytesIO(tar_stream))

                    for member in tar_file.getmembers():
                        if member.isfile():
                            return tar_file.extractfile(member).read().decode('utf-8', errors='ignore')
                    return None
                except Exception as e:
                    print(f"  Could not read {file_path}: {str(e)[:60]}")
                    return None

            # Get solution.py
            print(f"Reading files from container {container_id[:12]}...")
            solution_content = extract_file_from_tar('/workspace/solution.py')
            if solution_content and solution_content.strip() != "":
                files_dict['solution.py'] = solution_content
                print(f"  ✓ solution.py ({len(solution_content)} bytes)")

            # Get instructions.md
            instructions_content = extract_file_from_tar('/workspace/instructions.md')
            if instructions_content:
                files_dict['instructions.md'] = instructions_content
                print(f"  ✓ instructions.md ({len(instructions_content)} bytes)")

            # Try to get claude session logs
            claude_log_paths = [
                '/tmp/claude_session.log',
                '/root/.claude/logs/session.log',
                '/home/coder/.claude/logs/session.log',
                '/home/coder/.local/share/claude-code/session.log'
            ]

            for log_path in claude_log_paths:
                log_content = extract_file_from_tar(log_path)
                if log_content:
                    files_dict['claude_session.log'] = log_content
                    print(f"  ✓ claude_session.log ({len(log_content)} bytes)")
                    break

        except Exception as e:
            print(f"Warning: Container access issue: {e}")

    # If no solution.py found, create default
    if 'solution.py' not in files_dict:
        files_dict['solution.py'] = "# solution.py not found"
        print("  ⚠ solution.py not found in workspace")

    # Create submission record
    submission_id = str(uuid.uuid4())
    files_json = json.dumps(list(files_dict.keys()))

    cursor.execute('''
        INSERT INTO submissions (submission_id, link_id, assignment_id, files_json)
        VALUES (?, ?, ?, ?)
    ''', (submission_id, link_id, assignment_id, files_json))

    # Store individual files
    for filename, content in files_dict.items():
        file_id = str(uuid.uuid4())
        file_size = len(content.encode('utf-8')) if isinstance(content, str) else len(content)

        cursor.execute('''
            INSERT INTO submission_files (file_id, submission_id, filename, file_content, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_id, submission_id, filename, content, file_size))

    # Parse and store Claude session logs if available
    session_logs = []
    container_created_at = None

    if 'claude_session.log' in files_dict:
        try:
            session_logs = parse_claude_session_log(files_dict['claude_session.log'])

            # Get container creation time
            conn2 = sqlite3.connect(DB_PATH)
            cursor2 = conn2.cursor()
            cursor2.execute('SELECT created_at FROM session_links WHERE link_id = ?', (link_id,))
            time_row = cursor2.fetchone()
            if time_row:
                container_created_at = time_row[0]
            conn2.close()

            # Store parsed logs in session_logs table
            for log_entry in session_logs:
                log_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO session_logs (log_id, submission_id, timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    log_id,
                    submission_id,
                    log_entry.get('timestamp', datetime.now(timezone.utc).isoformat()),
                    log_entry.get('interaction_type', 'claude_cli'),
                    log_entry.get('prompt', ''),
                    log_entry.get('response_summary', ''),
                    log_entry.get('file_changes_count', 0),
                    json.dumps(log_entry)
                ))

            print(f"  ✓ Stored {len(session_logs)} session log entries")
        except Exception as e:
            print(f"Warning: Failed to parse/store session logs: {e}")

    # Commit all changes
    conn.commit()
    conn.close()

    # Schedule evaluation in background
    import threading
    thread = threading.Thread(target=evaluate_submission_files, args=(submission_id, assignment, session_logs, container_created_at))
    thread.daemon = True
    thread.start()

    # Schedule container cleanup
    thread2 = threading.Thread(target=cleanup_container, args=(container_id,))
    thread2.daemon = True
    thread2.start()

    return jsonify({
        "submission_id": submission_id,
        "status": "submitted",
        "message": "Files submitted successfully. Evaluation in progress...",
        "session_logs_count": len(session_logs)
    })

@app.route('/api/submission/<submission_id>')
def get_submission(submission_id):
    """Retrieve submission and evaluation results"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT s.submission_id, s.link_id, s.assignment_id, s.code, s.submitted_at, s.evaluation_result, s.score, s.feedback, a.title, a.evaluation_criteria
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        WHERE s.submission_id = ?
    ''', (submission_id,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"detail": "Submission not found"}), 404

    # Get files from submission_files table
    cursor.execute('''
        SELECT filename, file_content FROM submission_files
        WHERE submission_id = ?
        ORDER BY created_at DESC
    ''', (submission_id,))

    files = cursor.fetchall()
    conn.close()

    instructions_md = ""
    claude_logs = ""

    for filename, content in files:
        if filename == 'instructions.md':
            instructions_md = content
        elif filename == 'claude_session.log':
            claude_logs = content

    return jsonify({
        "submission_id": row[0],
        "link_id": row[1],
        "assignment_id": row[2],
        "code": row[3],
        "submitted_at": row[4],
        "evaluation_result": row[5],
        "score": row[6],
        "feedback": row[7],
        "assignment_title": row[8],
        "instructions_md": instructions_md,
        "claude_logs": claude_logs if claude_logs else "No Claude session logs available"
    })

@app.route('/api/session-logs/<submission_id>')
def get_session_logs(submission_id):
    """Get Claude session logs for a submission"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT timestamp, interaction_type, prompt, response_summary, file_changes_count
        FROM session_logs
        WHERE submission_id = ?
        ORDER BY timestamp ASC
    ''', (submission_id,))

    rows = cursor.fetchall()
    conn.close()

    logs = [
        {
            'timestamp': row[0],
            'interaction_type': row[1],
            'prompt': row[2],
            'response_summary': row[3],
            'file_changes_count': row[4]
        }
        for row in rows
    ]

    return jsonify({
        "submission_id": submission_id,
        "logs": logs,
        "total_interactions": len(logs)
    })

@app.route('/')
def index():
    """Serve frontend dashboard"""
    with open('frontend.html', 'r') as f:
        return f.read(), 200, {'Content-Type': 'text/html'}

# ============================================================================
# Run Flask App
# ============================================================================

if __name__ == '__main__':
    print("🚀 AI Engineering Assessment & Evaluation Platform")
    print("Starting Flask server on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000, debug=False)
