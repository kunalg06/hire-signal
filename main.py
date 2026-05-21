from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import secrets
import uuid
import sqlite3
import docker
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
import anthropic
import os
import re
import ast
from collections import defaultdict
from time import time as current_time

# ============================================================================
# Initialize FastAPI App & Docker Client
# ============================================================================

app = FastAPI(title="Claude Assignment Platform")

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (for development; restrict in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods including OPTIONS
    allow_headers=["*"],  # Allow all headers
)

# Rate limiting for challenge generation (max 5 requests per minute per IP)
_rate_limit_store = defaultdict(list)
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW = 60

def check_rate_limit(client_ip: str) -> bool:
    """Check if client exceeds rate limit. Returns True if allowed."""
    now = current_time()
    timestamps = _rate_limit_store[client_ip]
    # Remove old entries outside the window
    _rate_limit_store[client_ip] = [ts for ts in timestamps if now - ts < RATE_LIMIT_WINDOW]

    if len(_rate_limit_store[client_ip]) < RATE_LIMIT_REQUESTS:
        _rate_limit_store[client_ip].append(now)
        return True
    return False

# Docker client - lazy initialization to avoid startup failure if Docker is unavailable
_docker_client = None

def get_docker_client():
    """Get or initialize Docker client lazily"""
    global _docker_client
    if _docker_client is None:
        try:
            # Check for DOCKER_HOST environment variable (used in docker-compose)
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
            _anthropic_client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
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
    
    conn.commit()
    conn.close()

init_db()

# ============================================================================
# Data Models
# ============================================================================

class Assignment(BaseModel):
    title: str
    description: str
    starter_code: Optional[str] = None
    evaluation_criteria: str

class AssignmentResponse(Assignment):
    id: str

class LinkResponse(BaseModel):
    link_id: str
    assignment_id: str
    access_url: str
    vscode_port: int
    expires_at: str

class FileSubmissionRequest(BaseModel):
    files: dict  # {filename: file_content}
    claude_session_log: Optional[str] = None

class SubmissionFile(BaseModel):
    filename: str
    size: int

class SubmissionWithFiles(BaseModel):
    submission_id: str
    assignment_id: str
    submitted_at: str
    files: List[SubmissionFile]
    score: Optional[float] = None
    feedback: Optional[str] = None
    evaluated_at: Optional[str] = None

class CodeSubmission(BaseModel):
    code: str

class EvaluationResult(BaseModel):
    submission_id: str
    score: float
    feedback: str
    evaluation_details: dict

class ChallengeRequest(BaseModel):
    problem_statement: str
    difficulty: str

class ChallengeResponse(BaseModel):
    title: str
    description: str
    starter_code: str
    evaluation_criteria: str

# ============================================================================
# Assignment Management
# ============================================================================

@app.post("/api/assignments", response_model=AssignmentResponse)
async def create_assignment(assignment: Assignment):
    """Create a new coding assignment"""
    assignment_id = str(uuid.uuid4())
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO assignments (id, title, description, starter_code, evaluation_criteria)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        assignment_id,
        assignment.title,
        assignment.description,
        assignment.starter_code,
        assignment.evaluation_criteria
    ))
    
    conn.commit()
    conn.close()
    
    return AssignmentResponse(
        id=assignment_id,
        title=assignment.title,
        description=assignment.description,
        starter_code=assignment.starter_code,
        evaluation_criteria=assignment.evaluation_criteria
    )

@app.get("/api/assignments")
async def list_assignments():
    """List all assignments"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, title, description, starter_code, evaluation_criteria FROM assignments ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    assignments = []
    for row in rows:
        assignments.append({
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "starter_code": row[3],
            "evaluation_criteria": row[4]
        })

    return assignments

@app.get("/api/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(assignment_id: str):
    """Retrieve assignment details"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, title, description, starter_code, evaluation_criteria FROM assignments WHERE id = ?",
        (assignment_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    return AssignmentResponse(
        id=row[0],
        title=row[1],
        description=row[2],
        starter_code=row[3],
        evaluation_criteria=row[4]
    )

# ============================================================================
# Challenge Generation
# ============================================================================

def build_challenge_prompt(problem_statement: str, difficulty: str) -> str:
    """Build the Claude prompt for challenge generation."""
    return f"""You are an expert at creating coding challenges for technical hiring.

Generate a complete coding assignment for: {problem_statement}
Difficulty Level: {difficulty}
Framework: Flask

Create a JSON object with exactly 4 fields:
1. title (string, 1-10 words) - project name
2. description (string, 2-3 paragraphs) - what to build, constraints, example endpoints
3. starter_code (string, 30+ lines of valid Python/Flask code)
4. evaluation_criteria (string, 8+ line checklist of requirements and edge cases)

STARTER CODE MUST:
- Import from flask
- Create Flask app
- Have 2-3 placeholder routes
- Include if __name__ == "__main__"
- Be 100% syntactically valid Python

EVALUATION CRITERIA MUST INCLUDE:
- Core functionality requirements
- Edge cases for difficulty level ({difficulty})
- Code quality standards
- Testing expectations

DIFFICULTY LEVELS:
- EASY: Basic CRUD, simple validation
- MEDIUM: Business rules, error handling, validation
- HARD: Security, auth, rate limiting, concurrency, pagination

OUTPUT: Return ONLY valid JSON (no markdown, no code blocks, no explanations).
JSON structure should have these exact keys: "title", "description", "starter_code", "evaluation_criteria"
Example output (adjust content for the problem):
{{"title": "TODO API", "description": "...", "starter_code": "...", "evaluation_criteria": "..."}}"""

def is_valid_python_code(code: str) -> bool:
    """Validate if a string is syntactically valid Python code."""
    if not code or not code.strip():
        return False
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False

def parse_json_response(response_text: str) -> dict:
    """Parse JSON from response, handling various formats."""
    if not response_text or not response_text.strip():
        raise ValueError("Response text is empty")

    text = response_text.strip()

    # Method 1: Direct JSON parsing
    try:
        result = json.loads(text)
        print(f"DEBUG: Direct JSON parsing succeeded")
        return result
    except json.JSONDecodeError as e:
        print(f"DEBUG: Direct parsing failed: {e}")

    # Method 2: Extract from markdown code blocks
    try:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            json_str = match.group(1).strip()
            print(f"DEBUG: Found markdown block, trying to parse: {json_str[:100]}")
            result = json.loads(json_str)
            print(f"DEBUG: Markdown block parsing succeeded")
            return result
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"DEBUG: Markdown block parsing failed: {e}")

    # Method 3: Extract JSON object with regex
    try:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            json_str = match.group(0)
            print(f"DEBUG: Found JSON object, trying to parse: {json_str[:100]}")
            result = json.loads(json_str)
            print(f"DEBUG: Regex JSON parsing succeeded")
            return result
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"DEBUG: Regex parsing failed: {e}")

    raise ValueError(f"Could not parse JSON from response. First 300 chars: {text[:300]}")

@app.post("/api/generate-challenge", response_model=ChallengeResponse)
async def generate_challenge(challenge_request: ChallengeRequest, request_obj: Request):
    """Generate a coding challenge using Claude API"""
    # Get client IP for rate limiting
    client_ip = request_obj.client.host if request_obj.client else "unknown"

    # Input validation
    if not challenge_request.problem_statement or challenge_request.problem_statement.strip() == "":
        raise HTTPException(status_code=400, detail="Problem statement is required")

    if challenge_request.difficulty not in ["easy", "medium", "hard"]:
        raise HTTPException(status_code=400, detail="Difficulty must be easy, medium, or hard")

    if len(challenge_request.problem_statement) > 2000:
        raise HTTPException(status_code=400, detail="Problem statement must be less than 2000 characters")

    # Rate limiting
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Maximum 5 challenges per minute.")

    anthropic_client = get_anthropic_client()
    if anthropic_client is None:
        raise HTTPException(status_code=503, detail="Claude API is unavailable")

    try:
        prompt = build_challenge_prompt(
            challenge_request.problem_statement,
            challenge_request.difficulty.upper()
        )

        message = anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3500,
            timeout=35.0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        print(f"DEBUG: Message object type: {type(message)}")
        print(f"DEBUG: Message content: {message.content}")

        if not message.content or len(message.content) == 0:
            raise ValueError("Claude returned empty response")

        response_text = message.content[0].text
        print(f"DEBUG: Claude response length: {len(response_text)} chars")
        print(f"DEBUG: Full response: {response_text}")

        try:
            challenge_data = parse_json_response(response_text)
            print(f"DEBUG: Parsed JSON keys: {list(challenge_data.keys())}")
        except Exception as parse_err:
            print(f"DEBUG: JSON parsing failed: {parse_err}")
            raise ValueError(f"Failed to parse response as JSON: {parse_err}")

        # Validate required fields exist and are non-empty
        title = challenge_data.get("title", "").strip()
        description = challenge_data.get("description", "").strip()
        starter_code = challenge_data.get("starter_code", "").strip()
        evaluation_criteria = challenge_data.get("evaluation_criteria", "").strip()

        print(f"DEBUG: title length: {len(title)}, description length: {len(description)}")
        print(f"DEBUG: starter_code length: {len(starter_code)}, criteria length: {len(evaluation_criteria)}")

        if not all([title, description, starter_code, evaluation_criteria]):
            missing = [k for k, v in [("title", title), ("description", description),
                                      ("starter_code", starter_code), ("criteria", evaluation_criteria)] if not v]
            raise ValueError(f"Generated challenge missing required fields: {missing}")

        # Validate starter code is valid Python
        if not is_valid_python_code(starter_code):
            print(f"DEBUG: Code validation failed. First 200 chars: {starter_code[:200]}")
            raise ValueError("Generated starter code is not valid Python syntax")

        return ChallengeResponse(
            title=title,
            description=description,
            starter_code=starter_code,
            evaluation_criteria=evaluation_criteria
        )
    except ValueError as e:
        error_msg = str(e)
        print(f"Validation error: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Invalid challenge: {error_msg}")
    except TimeoutError as e:
        print(f"Timeout error: {str(e)}")
        raise HTTPException(status_code=408, detail="Generation took too long (timeout). Please try again.")
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"Unexpected error [{error_type}]: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Server error: {error_type}. Please try again.")

# ============================================================================
# Docker Management
# ============================================================================

def find_available_port(start_port=6000):
    """Find an available port for VS Code"""
    import socket
    for port in range(start_port, start_port + 10000):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports found in range {start_port}-{start_port+10000}")

def cleanup_old_containers():
    """Remove old/exited assignment containers to free ports"""
    try:
        docker_client = get_docker_client()
        if docker_client is None:
            return
        containers = docker_client.containers.list(all=True, filters={"name": "assignment_"})
        for container in containers:
            if container.status in ["exited", "created"]:
                try:
                    container.remove()
                except:
                    pass
    except:
        pass

def copy_to_container(container, file_data: bytes, target_path: str):
    """
    Copy file data into a container at the specified path.
    target_path should be relative to /workspace (e.g., 'instructions.md' or 'solution.py')
    """
    import io
    import tarfile

    # Create a tar archive with the file
    tar_data = io.BytesIO()
    with tarfile.open(fileobj=tar_data, mode='w') as tar:
        # Create a TarInfo object for the file
        tarinfo = tarfile.TarInfo(name=target_path)
        tarinfo.size = len(file_data)
        tar.addfile(tarinfo, io.BytesIO(file_data))

    tar_data.seek(0)
    # Copy the tar archive to the container's /workspace directory
    container.put_archive('/workspace', tar_data)

def start_docker_container(assignment_id: str, assignment_details=None, link_id: str = None) -> tuple[str, int]:
    """
    Start a Docker container with code-server and Claude CLI.
    assignment_details can be either a dict with assignment details or a string (legacy).
    link_id is the student session link ID.
    Returns: (container_id, port)
    """
    # Clean up old containers before starting new one
    cleanup_old_containers()

    # Create the initial code file in the assignments volume
    assignment_subdir = f'assignment_{assignment_id}'
    code_dir = Path(f'/app/assignments/{assignment_subdir}')
    code_dir.mkdir(parents=True, exist_ok=True)

    # Handle both old and new formats
    if isinstance(assignment_details, dict):
        # New format with full assignment details
        title = assignment_details.get("title", "Assignment")
        description = assignment_details.get("description", "")
        starter_code = assignment_details.get("starter_code", "")
        evaluation_criteria = assignment_details.get("evaluation_criteria", "")

        # Create instructions.md
        instructions_content = f"""# {title}

## Description
{description}

## Evaluation Criteria
{evaluation_criteria}

## How to Submit
1. Complete the implementation in `solution.py`
2. Test your code thoroughly
3. Submit via the assignment platform when ready
"""
        (code_dir / 'instructions.md').write_text(instructions_content)

        # Create solution.py with starter code
        if starter_code:
            (code_dir / 'solution.py').write_text(starter_code)
        else:
            (code_dir / 'solution.py').write_text('# Write your solution here\n')
    else:
        # Legacy format - assignment_details is a string (starter_code)
        starter_code = assignment_details
        if starter_code:
            (code_dir / 'solution.py').write_text(starter_code)
        else:
            (code_dir / 'solution.py').write_text('# Write your solution here\n')

    # Use the named volume 'assignments_volume' for the codeserver container
    # The volume is defined in docker-compose.yml and is shared across containers
    volumes = {
        'assignments_volume': {'bind': '/workspace', 'mode': 'rw'}
    }

    # Container environment
    environment = {
        'CODE_SERVER_AUTH': 'none',  # For demo; use auth in production
        'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),  # Pass API key from host
        'ASSIGNMENT_ID': assignment_id,
        'LINK_ID': link_id or '',
    }

    # Try multiple ports in case one is already in use
    for attempt in range(20):
        port = find_available_port(start_port=6000 + (attempt * 10))

        try:
            docker_client = get_docker_client()
            if docker_client is None:
                raise HTTPException(status_code=503, detail="Docker daemon is not available")

            print(f"Attempt {attempt + 1}: Starting container for assignment {assignment_id} on port {port}")
            print(f"Using volumes: {volumes}")

            container = docker_client.containers.run(
                'code-server-http:latest',
                command=[],
                ports={f'8080/tcp': port},
                volumes=volumes,
                environment=environment,
                detach=True,
                name=f'assignment_{assignment_id}_{uuid.uuid4().hex[:8]}',
                remove=False
            )
            print(f"Container started successfully: {container.id} on port {port}")

            # Copy assignment files into container workspace
            if isinstance(assignment_details, dict):
                # Copy instructions.md
                instructions_path = code_dir / 'instructions.md'
                if instructions_path.exists():
                    with open(instructions_path, 'rb') as f:
                        data = f.read()
                    try:
                        # Copy file to container workspace root
                        copy_to_container(container, data, 'instructions.md')
                    except Exception as e:
                        print(f"Warning: Could not copy instructions.md to container: {e}")

                # Copy solution.py
                solution_path = code_dir / 'solution.py'
                if solution_path.exists():
                    with open(solution_path, 'rb') as f:
                        data = f.read()
                    try:
                        # Copy file to container workspace root
                        copy_to_container(container, data, 'solution.py')
                    except Exception as e:
                        print(f"Warning: Could not copy solution.py to container: {e}")

            return container.id, port
        except Exception as e:
            error_str = str(e)
            print(f"Attempt {attempt + 1} failed: {error_str}")
            # If it's a port allocation error, try the next port
            if "port is already allocated" in error_str or "Address already in use" in error_str:
                continue
            # Otherwise, it's a real error
            raise HTTPException(status_code=500, detail=f"Failed to start container: {error_str}")

    # If we get here, we couldn't find any available port
    raise HTTPException(status_code=500, detail="Could not find available port after 20 attempts")

# ============================================================================
# Link Generation & Session Management
# ============================================================================

@app.post("/api/generate-link/{assignment_id}", response_model=LinkResponse)
async def generate_link(assignment_id: str):
    """Generate a unique link for accessing the coding environment"""

    # Verify assignment exists and fetch all details
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT title, description, starter_code, evaluation_criteria FROM assignments WHERE id = ?",
        (assignment_id,)
    )
    result = cursor.fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Assignment not found")

    title, description, starter_code, evaluation_criteria = result
    conn.close()

    # Generate unique link first
    link_id = secrets.token_urlsafe(32)

    # Start Docker container with assignment details
    assignment_details = {
        "title": title,
        "description": description,
        "starter_code": starter_code,
        "evaluation_criteria": evaluation_criteria
    }
    container_id, port = start_docker_container(assignment_id, assignment_details, link_id=link_id)

    # Calculate expiration time
    expires_at = (datetime.now() + timedelta(hours=24)).isoformat()

    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO session_links (link_id, assignment_id, container_id, port, expires_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (link_id, assignment_id, container_id, port, expires_at))

    conn.commit()
    conn.close()

    return LinkResponse(
        link_id=link_id,
        assignment_id=assignment_id,
        access_url=f"http://localhost:{port}",
        vscode_port=port,
        expires_at=expires_at
    )

@app.get("/api/session/{link_id}")
async def get_session_info(link_id: str):
    """Get session and container information"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT assignment_id, container_id, port, expires_at FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "link_id": link_id,
        "assignment_id": row[0],
        "container_id": row[1],
        "vscode_port": row[2],
        "vscode_url": f"http://localhost:{row[2]}",
        "expires_at": row[3]
    }

# ============================================================================
# Submission & Evaluation
# ============================================================================

def evaluate_code_with_claude(code: str, assignment: AssignmentResponse) -> EvaluationResult:
    """
    Evaluate submitted code using Claude API
    """
    submission_id = str(uuid.uuid4())
    
    evaluation_prompt = f"""
You are an expert code reviewer and educator. Evaluate the following student submission.

ASSIGNMENT:
Title: {assignment.title}
Description: {assignment.description}

EVALUATION CRITERIA:
{assignment.evaluation_criteria}

SUBMITTED CODE:
```python
{code}
```

Provide a structured evaluation including:
1. Correctness (does it solve the problem?)
2. Code quality (readability, efficiency, best practices)
3. Completeness (does it cover all requirements?)
4. Score: Rate from 0-100

Format your response as JSON with keys: correctness, code_quality, completeness, overall_feedback, score
"""
    
    try:
        client = get_anthropic_client()
        if client is None:
            raise HTTPException(status_code=503, detail="Anthropic API client is not available")
        
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": evaluation_prompt}
            ]
        )
        
        response_text = message.content[0].text
        
        # Parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        
        if json_match:
            eval_data = json.loads(json_match.group())
        else:
            eval_data = {
                "correctness": "Unable to parse",
                "code_quality": "Unable to parse",
                "completeness": "Unable to parse",
                "overall_feedback": response_text,
                "score": 0
            }
        
        return EvaluationResult(
            submission_id=submission_id,
            score=eval_data.get('score', 0),
            feedback=eval_data.get('overall_feedback', ''),
            evaluation_details=eval_data
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

@app.post("/api/submit/{link_id}", response_model=EvaluationResult)
async def submit_assignment(link_id: str, submission: CodeSubmission, background_tasks: BackgroundTasks):
    """Submit code for evaluation"""
    
    # Get session and assignment info
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT assignment_id, container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))
    session = cursor.fetchone()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    assignment_id, container_id = session
    
    # Get assignment details
    cursor.execute('''
        SELECT title, description, evaluation_criteria FROM assignments WHERE id = ?
    ''', (assignment_id,))
    assignment_row = cursor.fetchone()
    
    if not assignment_row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    assignment = AssignmentResponse(
        id=assignment_id,
        title=assignment_row[0],
        description=assignment_row[1],
        evaluation_criteria=assignment_row[2]
    )
    
    # Evaluate code
    evaluation = evaluate_code_with_claude(submission.code, assignment)
    
    # Store submission
    submission_id = evaluation.submission_id
    cursor.execute('''
        INSERT INTO submissions (submission_id, link_id, assignment_id, code, evaluation_result, score, feedback)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        submission_id,
        link_id,
        assignment_id,
        submission.code,
        json.dumps(evaluation.evaluation_details),
        evaluation.score,
        evaluation.feedback
    ))
    
    conn.commit()
    conn.close()
    
    # Clean up container in background
    background_tasks.add_task(cleanup_container, container_id)
    
    return evaluation

def cleanup_container(container_id: str):
    """Stop and remove container"""
    try:
        docker_client = get_docker_client()
        if docker_client is None:
            print(f"Warning: Docker daemon unavailable, cannot cleanup container {container_id}")
            return
        container = docker_client.containers.get(container_id)
        container.stop()
        container.remove()
    except Exception as e:
        print(f"Error cleaning up container {container_id}: {e}")

@app.post("/api/submit-code/{link_id}", response_model=EvaluationResult)
async def submit_code_from_container(link_id: str, background_tasks: BackgroundTasks):
    """Submit code directly from container (retrieves solution.py from container)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT assignment_id, container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    assignment_id, container_id = row
    conn.close()

    # Retrieve solution.py from container
    try:
        docker_client = get_docker_client()
        if docker_client is None:
            raise HTTPException(status_code=500, detail="Docker daemon unavailable")

        container = docker_client.containers.get(container_id)

        # Read solution.py from container
        try:
            result = container.exec_run('cat /workspace/solution.py')
            if result.exit_code != 0:
                code = "# No solution found"
            else:
                code = result.output.decode('utf-8')
        except Exception as e:
            code = f"# Error reading file: {str(e)}"

        # Submit the code using existing submission endpoint
        submission_data = CodeSubmission(code=code)
        return await submit_assignment(link_id, submission_data, background_tasks)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve code: {str(e)}")

@app.post("/api/submit-with-files/{link_id}")
async def submit_with_files(link_id: str, background_tasks: BackgroundTasks):
    """Collect files from container workspace and submit"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get session and assignment info
    cursor.execute('''
        SELECT assignment_id, container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    assignment_id, container_id = row

    # Get assignment details
    cursor.execute('''
        SELECT title, description, evaluation_criteria FROM assignments WHERE id = ?
    ''', (assignment_id,))

    assignment_row = cursor.fetchone()
    if not assignment_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment = AssignmentResponse(
        id=assignment_id,
        title=assignment_row[0],
        description=assignment_row[1],
        evaluation_criteria=assignment_row[2]
    )

    files_dict = {}

    # Try to collect files from container
    try:
        docker_client = get_docker_client()
        if docker_client:
            container = docker_client.containers.get(container_id)

            # Helper function to safely read file from container
            def read_file_from_container(file_path):
                try:
                    bits, stat = container.get_archive(file_path)
                    import tarfile
                    import io
                    tar_stream = io.BytesIO(b''.join(bits))
                    tar = tarfile.open(fileobj=tar_stream)
                    extracted = tar.extractall()

                    # Get the filename from path
                    filename = file_path.split('/')[-1]

                    # Read the file content
                    result = container.exec_run(f'cat {file_path}')
                    if result.exit_code == 0:
                        return result.output.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Could not read {file_path}: {e}")
                    return None

            # Get solution.py (most important file)
            solution_content = read_file_from_container('/workspace/solution.py')
            if solution_content:
                files_dict['solution.py'] = solution_content
                print(f"✓ Retrieved solution.py ({len(solution_content)} bytes)")
            else:
                # Fallback: try to get all files in workspace
                try:
                    result = container.exec_run('ls -la /workspace/')
                    print(f"Workspace files: {result.output.decode('utf-8', errors='ignore')}")
                except:
                    pass

            # Get instructions.md
            instructions_content = read_file_from_container('/workspace/instructions.md')
            if instructions_content:
                files_dict['instructions.md'] = instructions_content

            # Try to get claude session log from multiple locations
            claude_log_paths = [
                '/tmp/claude_session.log',
                '/root/.claude/logs/session.log',
                '/home/coder/.claude/logs/session.log',
                '/home/coder/.local/share/claude-code/session.log'
            ]

            for log_path in claude_log_paths:
                log_content = read_file_from_container(log_path)
                if log_content:
                    files_dict['claude_session.log'] = log_content
                    print(f"✓ Retrieved claude logs from {log_path}")
                    break

            # Try to find any .log files in workspace
            if 'claude_session.log' not in files_dict:
                try:
                    result = container.exec_run('find /workspace -name "*.log" -type f 2>/dev/null')
                    if result.exit_code == 0:
                        log_files = result.output.decode('utf-8', errors='ignore').strip().split('\n')
                        for log_file in log_files:
                            if log_file and 'claude' in log_file.lower():
                                log_content = read_file_from_container(log_file)
                                if log_content:
                                    files_dict['claude_session.log'] = log_content
                                    print(f"✓ Found and retrieved {log_file}")
                                    break
                except:
                    pass

    except Exception as e:
        print(f"Warning: Could not collect files from container: {e}")

    # If no solution.py found, create default
    if 'solution.py' not in files_dict:
        files_dict['solution.py'] = "# No solution.py found in workspace"
        print("⚠ solution.py not found, using default")

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

    conn.commit()
    conn.close()

    # Schedule automatic evaluation in background
    background_tasks.add_task(evaluate_submission_files, submission_id, assignment)
    # Schedule container cleanup
    background_tasks.add_task(cleanup_container, container_id)

    return {
        "submission_id": submission_id,
        "status": "submitted",
        "message": "Files submitted successfully. Evaluation in progress..."
    }

@app.post("/api/submit-files/{link_id}")
async def submit_files(link_id: str, request: FileSubmissionRequest, background_tasks: BackgroundTasks):
    """Submit files from student workspace"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get session and assignment info
    cursor.execute('''
        SELECT assignment_id, container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    assignment_id, container_id = row

    # Get assignment details
    cursor.execute('''
        SELECT title, description, evaluation_criteria FROM assignments WHERE id = ?
    ''', (assignment_id,))

    assignment_row = cursor.fetchone()
    if not assignment_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment = AssignmentResponse(
        id=assignment_id,
        title=assignment_row[0],
        description=assignment_row[1],
        evaluation_criteria=assignment_row[2]
    )

    # Create submission record
    submission_id = str(uuid.uuid4())
    files_json = json.dumps(request.files)

    cursor.execute('''
        INSERT INTO submissions (submission_id, link_id, assignment_id, files_json)
        VALUES (?, ?, ?, ?)
    ''', (submission_id, link_id, assignment_id, files_json))

    # Store individual files
    for filename, content in request.files.items():
        file_id = str(uuid.uuid4())
        file_size = len(content.encode('utf-8')) if isinstance(content, str) else len(content)

        cursor.execute('''
            INSERT INTO submission_files (file_id, submission_id, filename, file_content, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_id, submission_id, filename, content, file_size))

    # Store Claude session log if provided
    if request.claude_session_log:
        file_id = str(uuid.uuid4())
        file_size = len(request.claude_session_log)
        cursor.execute('''
            INSERT INTO submission_files (file_id, submission_id, filename, file_content, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_id, submission_id, 'claude_session.log', request.claude_session_log, file_size))

    conn.commit()
    conn.close()

    # Schedule evaluation in background
    background_tasks.add_task(evaluate_submission_files, submission_id, assignment)
    # Schedule container cleanup
    background_tasks.add_task(cleanup_container, container_id)

    return {
        "submission_id": submission_id,
        "status": "submitted",
        "message": "Files submitted successfully. Evaluation in progress..."
    }

def evaluate_submission_files(submission_id: str, assignment: AssignmentResponse):
    """Evaluate submitted files"""
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

        # Get Claude session log if available
        cursor.execute('''
            SELECT file_content FROM submission_files
            WHERE submission_id = ? AND filename = 'claude_session.log'
        ''', (submission_id,))

        log_row = cursor.fetchone()
        claude_log = log_row[0] if log_row else ""

        # Evaluate with Claude
        evaluation = evaluate_code_with_claude(code, assignment)

        # Update submission with evaluation results
        cursor.execute('''
            UPDATE submissions
            SET score = ?, feedback = ?, evaluation_result = ?, evaluated_at = ?
            WHERE submission_id = ?
        ''', (
            evaluation.score,
            evaluation.feedback,
            json.dumps(evaluation.evaluation_details),
            datetime.now().isoformat(),
            submission_id
        ))

        conn.commit()
        print(f"Evaluation complete for submission {submission_id}")

    except Exception as e:
        print(f"Error evaluating submission {submission_id}: {e}")
    finally:
        conn.close()

@app.get("/api/submission/{submission_id}/files")
async def get_submission_files(submission_id: str):
    """Get list of files in a submission"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT submission_id FROM submissions WHERE submission_id = ?
    ''', (submission_id,))

    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Submission not found")

    cursor.execute('''
        SELECT filename, file_size FROM submission_files WHERE submission_id = ?
        ORDER BY created_at DESC
    ''', (submission_id,))

    files = [{"filename": row[0], "size": row[1]} for row in cursor.fetchall()]
    conn.close()

    return {"submission_id": submission_id, "files": files}

@app.get("/api/submission/{submission_id}/file/{filename}")
async def download_submission_file(submission_id: str, filename: str):
    """Download a file from a submission"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT file_content FROM submission_files
        WHERE submission_id = ? AND filename = ?
    ''', (submission_id, filename))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "filename": filename,
        "content": row[0]
    }

@app.post("/api/submission/{submission_id}/evaluate")
async def evaluate_submission_endpoint(submission_id: str):
    """Manually evaluate a submission"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT assignment_id FROM submissions WHERE submission_id = ?
    ''', (submission_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Submission not found")

    assignment_id = row[0]

    # Get assignment details
    cursor.execute('''
        SELECT id, title, description, evaluation_criteria FROM assignments WHERE id = ?
    ''', (assignment_id,))

    assignment_row = cursor.fetchone()
    conn.close()

    if not assignment_row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment = AssignmentResponse(
        id=assignment_row[0],
        title=assignment_row[1],
        description=assignment_row[2],
        evaluation_criteria=assignment_row[3]
    )

    # Evaluate
    evaluate_submission_files(submission_id, assignment)

    return {"status": "Evaluation started"}

@app.post("/api/close-container/{link_id}")
async def close_container_endpoint(link_id: str):
    """Close and cleanup container for a session"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    container_id = row[0]
    cleanup_container(container_id)

    return {"status": "Container closed", "container_id": container_id}

@app.get("/api/submissions/list")
async def list_submissions():
    """List all submissions with summary information"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT s.submission_id, s.submitted_at, s.score, a.title
        FROM submissions s
        JOIN assignments a ON s.assignment_id = a.id
        ORDER BY s.submitted_at DESC
    ''')

    rows = cursor.fetchall()
    conn.close()

    submissions = []
    for row in rows:
        submissions.append({
            "submission_id": row[0],
            "submitted_at": row[1],
            "score": row[2],
            "assignment_title": row[3]
        })

    return submissions

@app.get("/api/submission/{submission_id}")
async def get_submission(submission_id: str):
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
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Try to get instructions from the container
    instructions_md = ""
    try:
        cursor = sqlite3.connect(DB_PATH).cursor()
        cursor.execute('SELECT container_id FROM session_links WHERE link_id = ?', (row[1],))
        container_row = cursor.fetchone()

        if container_row:
            docker_client = get_docker_client()
            if docker_client:
                container = docker_client.containers.get(container_row[0])
                bits, stat = container.get_archive('/workspace/instructions.md')
                import tarfile
                import io
                tar_stream = io.BytesIO(b''.join(bits))
                tar = tarfile.open(fileobj=tar_stream)
                member = tar.getmembers()[0]
                f = tar.extractfile(member)
                instructions_md = f.read().decode('utf-8')
    except Exception as e:
        print(f"Could not retrieve instructions from container: {e}")

    return {
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
        "claude_logs": "Claude session logs would be captured here if Claude API was used for code generation"
    }

@app.get("/api/solution/{link_id}")
async def get_solution_file(link_id: str):
    """Retrieve solution.py from the student container"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT container_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    container_id = row[0]

    try:
        docker_client = get_docker_client()
        if docker_client is None:
            raise HTTPException(status_code=503, detail="Docker daemon not available")

        container = docker_client.containers.get(container_id)

        # Read solution.py from container
        try:
            bits, stat = container.get_archive('/workspace/solution.py')
            import tarfile
            import io
            tar_stream = io.BytesIO(b''.join(bits))
            tar = tarfile.open(fileobj=tar_stream)
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            code = f.read().decode('utf-8')
            return {"code": code}
        except Exception as e:
            print(f"Error reading solution.py: {e}")
            raise HTTPException(status_code=500, detail=f"Could not read solution file: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving solution: {str(e)}")

@app.get("/codeserver/{link_id}")
async def open_codeserver(link_id: str):
    """Serve code-server wrapper with submit button"""
    # Verify the session exists
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT link_id FROM session_links WHERE link_id = ?
    ''', (link_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    # Read and serve the wrapper HTML
    wrapper_path = Path("codeserver-submit.html")
    if not wrapper_path.exists():
        raise HTTPException(status_code=404, detail="Wrapper HTML not found")

    html_content = wrapper_path.read_text()
    return HTMLResponse(content=html_content)

@app.get("/student/{link_id}")
async def student_dashboard(link_id: str):
    """Serve student dashboard with instructions and submission interface"""
    # Get session and assignment info
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
        raise HTTPException(status_code=404, detail="Session not found")

    assignment_id, port, title, description, criteria, starter_code, expires_at = row
    vscode_url = f"/codeserver/{link_id}"

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
            .instructions {{
                grid-column: 1;
            }}
            .controls {{
                grid-column: 2;
                display: flex;
                flex-direction: column;
                gap: 15px;
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
            }}
            .btn-primary:hover {{
                background: #5568d3;
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
            }}
            .btn-secondary {{
                background: #17a2b8;
                color: white;
                text-decoration: none;
                text-align: center;
                display: inline-block;
            }}
            .btn-secondary:hover {{
                background: #138496;
                transform: translateY(-2px);
            }}
            .status {{
                padding: 15px;
                border-radius: 6px;
                text-align: center;
                font-weight: 600;
                display: none;
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
            .code-info {{
                background: white;
                padding: 15px;
                border-radius: 6px;
                margin-top: 15px;
                border: 1px solid #ddd;
                font-size: 14px;
                color: #666;
            }}
            .code-info strong {{
                color: #333;
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
                .instructions {{
                    grid-column: 1;
                }}
                .controls {{
                    grid-column: 1;
                }}
                .header h1 {{
                    font-size: 24px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 {title}</h1>
                <p>Coding Challenge</p>
            </div>

            <div class="content">
                <div class="instructions">
                    <div class="section">
                        <h2>📋 Assignment</h2>
                        <p>{description}</p>
                    </div>

                    <div class="section" style="margin-top: 20px;">
                        <h2>✅ Evaluation Criteria</h2>
                        <p>{criteria}</p>
                    </div>
                </div>

                <div class="controls">
                    <div class="section">
                        <h2>🚀 Start Coding</h2>
                        <p>Click below to open VS Code and start working on your solution.</p>
                        <a href="{vscode_url}" target="_blank" class="btn btn-secondary" style="margin-top: 15px;">
                            Open VS Code Editor
                        </a>
                        <div class="code-info">
                            <strong>Files available:</strong>
                            <ul style="margin: 10px 0 0 20px;">
                                <li><code>instructions.md</code> - Full assignment details</li>
                                <li><code>solution.py</code> - Starter code template</li>
                            </ul>
                        </div>
                        <div class="code-info" style="margin-top: 15px; background: #fff3cd; border-left-color: #ffc107;">
                            <strong style="color: #856404;">💡 To Submit from VS Code:</strong>
                            <p style="margin: 8px 0 0 0; color: #856404; font-size: 14px;">
                                Once VS Code opens, open a new tab and go to:<br>
                                <code style="background: white; padding: 4px 8px;">localhost:9999</code><br>
                                You'll see the submit button there!
                            </p>
                        </div>
                    </div>

                    <div class="section">
                        <h2>📤 Submit Solution</h2>
                        <p>When finished, click the <strong>Submit</strong> button in VS Code (top-right corner) to submit your solution for evaluation.</p>
                        <div class="timer" style="margin-top: 20px;">
                            ⏰ Session Expires: <span id="timer">--:--:--</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            // Timer functionality
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

            // Store link_id for submit button script
            window.LINK_ID = "{link_id}";
            localStorage.setItem('assignment_link_id', "{link_id}");

            // Inject submit button script into code-server iframe when user opens it
            const vsCodeLink = document.querySelector('a[href*="localhost"]');
            if (vsCodeLink) {{
                vsCodeLink.addEventListener('click', function(e) {{
                    // Wait for window to open, then inject script
                    setTimeout(() => {{
                        const codeServerScript = document.createElement('script');
                        codeServerScript.src = 'http://localhost:8000/static/submit-button.js';
                        codeServerScript.onload = () => {{
                            console.log('Submit button script loaded');
                        }};
                        // Note: Script will be injected when user accesses code-server
                    }}, 100);
                }});
            }}
        </script>
        <script>
            // This script needs to be loaded in the code-server window
            // It will be loaded dynamically when the VS Code window opens
            console.log('Dashboard ready. Link ID: {link_id}');
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)

@app.get("/session-closed")
async def session_closed():
    """Show message when session is closed"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Session Closed</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                padding: 50px;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 500px;
            }
            .check {
                width: 80px;
                height: 80px;
                margin: 0 auto 30px;
                background: #4caf50;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 50px;
            }
            h1 {
                color: #333;
                margin-bottom: 15px;
                font-size: 28px;
            }
            p {
                color: #666;
                line-height: 1.6;
                margin-bottom: 30px;
            }
            .footer {
                color: #999;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="check">✓</div>
            <h1>Submission Received!</h1>
            <p>Your solution has been successfully submitted for evaluation. Your instructor will review your code shortly and provide feedback.</p>
            <div class="footer">
                <p>Your coding session has been closed.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "Claude Assignment Platform"}

@app.get("/")
async def root():
    """API documentation"""
    return {
        "service": "Claude Assignment Platform",
        "endpoints": {
            "assignments": {
                "POST /api/assignments": "Create new assignment",
                "GET /api/assignments/{id}": "Get assignment details"
            },
            "links": {
                "POST /api/generate-link/{assignment_id}": "Generate access link",
                "GET /api/session/{link_id}": "Get session info"
            },
            "submissions": {
                "POST /api/submit/{link_id}": "Submit code for evaluation",
                "GET /api/submission/{submission_id}": "Get submission results"
            }
        }
    }

@app.get("/frontend.html")
async def get_frontend():
    """Serve the frontend HTML"""
    frontend_path = Path("frontend.html")
    if frontend_path.exists():
        return FileResponse(frontend_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="Frontend not found")

@app.get("/static/{filename}")
async def serve_static(filename: str):
    """Serve static files like submit-button.js"""
    if not filename.endswith('.js'):
        raise HTTPException(status_code=403, detail="Only .js files allowed")

    # Look in current directory and parent directories
    file_path = Path(filename).resolve()
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, media_type="application/javascript")

    # Try relative to current working directory
    cwd_path = Path.cwd() / filename
    if cwd_path.exists():
        return FileResponse(cwd_path, media_type="application/javascript")

    raise HTTPException(status_code=404, detail=f"File not found: {filename}")

# ============================================================================
# Run server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
