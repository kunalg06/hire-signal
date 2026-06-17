# AI Engineering Assessment & Evaluation Platform - Architecture

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SYSTEMS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐         ┌──────────────────────────────┐          │
│  │   Web Browser        │         │   Anthropic Claude API       │          │
│  │  (Teacher/Student)   │         │   (Code Evaluation)          │          │
│  └──────┬───────────────┘         └──────────────┬───────────────┘          │
│         │                                        │                         │
└─────────┼────────────────────────────────────────┼─────────────────────────┘
          │                                        │
          │ HTTP                                   │ HTTPS
          │                                        │
┌─────────▼────────────────────────────────────────▼─────────────────────────┐
│                         FLASK BACKEND (Port 8000)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Routes (Flask Blueprints)                                            │  │
│  │  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐   │  │
│  │  │ assignments.py   │  │ links.py     │  │ submissions.py       │   │  │
│  │  │ - POST /api/...  │  │ - POST /api..│  │ - POST /api/submit   │   │  │
│  │  │ - GET /api/...   │  │              │  │ - GET /api/...       │   │  │
│  │  └──────────────────┘  └──────────────┘  └──────────────────────┘   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │ student.py                                                   │   │  │
│  │  │ - GET /student/{link_id} → HTML Dashboard                   │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Services Layer (Business Logic)                                       │  │
│  │  ┌──────────────────────┐  ┌─────────────────────────────────┐       │  │
│  │  │ DockerService        │  │ EvaluationService               │       │  │
│  │  │ - create_container() │  │ - evaluate_code()              │       │  │
│  │  │ - get_file()         │  │ - Uses Claude API               │       │  │
│  │  │ - cleanup()          │  │ - Returns: score, feedback      │       │  │
│  │  └──────────────────────┘  └─────────────────────────────────┘       │  │
│  │  ┌──────────────────────┐  ┌─────────────────────────────────┐       │  │
│  │  │ SessionLogService    │  │ DatabaseService                 │       │  │
│  │  │ - parse_session_log()│  │ - CRUD operations               │       │  │
│  │  │ - calculate_scores() │  │ - Transactions                  │       │  │
│  │  └──────────────────────┘  └─────────────────────────────────┘       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Data Layer (Database Access)                                          │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │ Database Model (SQLite)                                          │ │  │
│  │  │ - Connection pooling                                            │ │  │
│  │  │ - Table initialization                                          │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────┬──────────────────────────────────────┬──────────────────────┘
               │                                      │
               │ File Archive (tar)                   │ SQL Queries
               │                                      │
┌──────────────▼──────────────────┐   ┌──────────────▼─────────────────────┐
│   Docker Engine (Daemon)          │   │   SQLite Database                  │
│   ┌────────────────────────────┐  │   │   ┌──────────────────────────────┐ │
│   │ Student Code-Server        │  │   │   │ assignments.db               │ │
│   │ Container per Session      │  │   │   │ - assignments                │ │
│   │ ┌────────────────────────┐ │  │   │   │ - session_links              │ │
│   │ │ Port: 6000-7000        │ │  │   │   │ - submissions                │ │
│   │ │ /workspace (code)      │ │  │   │   │ - submission_files           │ │
│   │ │ code-server running    │ │  │   │   │ - session_logs               │ │
│   │ │ Claude CLI installed   │ │  │   │   └──────────────────────────────┘ │
│   │ │ /home/coder/.claude/   │ │  │   │                                    │
│   │ │  logs/session.log      │ │  │   └────────────────────────────────────┘
│   │ └────────────────────────┘ │  │
│   └────────────────────────────┘  │
└────────────────────────────────────┘
```

## Data Flow Diagrams

### 1. Assignment Creation Flow

```
Teacher                    Flask Backend              Database
  │                            │                         │
  ├─ POST /api/assignments ───→ │                        │
  │                            │                        │
  │                            ├─ Validate input        │
  │                            │                        │
  │                            ├─ Generate UUID         │
  │                            │                        │
  │                            ├─ INSERT assignments ──→ │
  │                            │                        │
  │                            ├─ COMMIT              │
  │                            │                        │
  │                            ├─ Return assignment_id  │
  │  ← 201 Created, {id: "..."} │                       │
  │                            │                        │
  └─ Share link with students  │                        │
```

### 2. Student Link Generation Flow

```
Teacher                    Flask Backend              Docker           Database
  │                            │                         │                │
  ├─ POST /api/generate-link──→ │                        │                │
  │                            │                        │                │
  │                            ├─ Get assignment        │                │
  │                            │                        │                │
  │                            ├─ Find available port   │                │
  │                            │                        │                │
  │                            ├─ Create container ────→ │                │
  │                            │                        │ (code-server)  │
  │                            │ ← container_id         │                │
  │                            │                        │                │
  │                            ├─ INSERT session_link ─→                 │
  │                            │                        │                │
  │  ← 201 Created ────────────│                        │                │
  │  {link_id, port}           │                        │                │
```

### 3. Student Coding & Submission Flow

```
Student Browser            code-server Container      Flask Backend        Database
  │                                 │                       │                │
  ├─ GET /student/{link_id} ──────────────────────→ Returns HTML            │
  │                                 │                       │                │
  │ [Embedded iframe points to container]           │                       │
  │                                 │                       │                │
  ├─────────────────────────────────→ Edit code            │                │
  │                                 │ in /workspace         │                │
  │                                 │                       │                │
  ├─────────────────────────────────→ Terminal:            │                │
  │                                 │ claude evaluate ....   │                │
  │                                 │ [Logged to session.log]│                │
  │                                 │                       │                │
  ├─ Click "Submit" button           │                       │                │
  │                                 │                       │                │
  │                                 ├─ POST /api/submit────→ │                │
  │                                 │                       │                │
  │                                 │  [Docker tar API]      │                │
  │                                 │  ← Extract files       │                │
  │                                 │  ← Get solution.py     │                │
  │                                 │  ← Get session.log     │                │
  │                                 │                       │                │
  │                                 │  [Parse & Store] ────→ │
  │                                 │  INSERT submissions    │
  │                                 │  INSERT submission_files
  │                                 │  INSERT session_logs   │
  │                                 │  COMMIT                │
  │                                 │                       │
  │ ← 202 Accepted                  │                       │
  │   {submission_id}               │                       │
  │                                 │  [Background thread]   │
  │                                 │  Evaluate code ──→ Claude API
  │                                 │  Calculate scores      │
  │                                 │  UPDATE submissions ──→ │
  │                                 │                       │
  ├─ Poll GET /api/submission/{id}  │                       │
  │  ← 200 OK {score, feedback}     │                       │
  │                                 │                       │
  │ Display results on portal       │                       │
```

### 4. Code Evaluation Flow

```
Backend                    Claude API              SessionLogService
  │                            │                         │
  ├─ Get code from DB          │                         │
  │                            │                         │
  ├─ Get session logs from DB  │────────────────────────→ │
  │                            │                         │
  │ ← Parse logs, calculate scores                      │
  │                            │                         │
  ├─ Build evaluation prompt   │                         │
  │                            │                         │
  ├─ Send to Claude ──────────→ │                         │
  │                            │                         │
  │ ← Evaluation JSON          │                         │
  │   {correctness, code_quality, completeness, score}  │
  │                            │                         │
  ├─ Combine scores:           │                         │
  │  final = (quality × 0.4) + (approach × 0.3) +        │
  │          (efficiency × 0.3)                          │
  │                            │                         │
  ├─ UPDATE submissions with results                     │
  │                            │                         │
  └─ Results visible to student and teacher             │
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Flask Application                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Routes (HTTP Handlers)                                         │
│       ↓                                                          │
│  Services (Business Logic)                                      │
│    ├─ DockerService ─→ Docker Daemon                           │
│    ├─ EvaluationService ─→ Anthropic API                       │
│    ├─ SessionLogService ─→ Parse & Score                       │
│    └─ DatabaseService ─→ SQLite                                │
│       ↓                                                          │
│  Models (Data Access)                                           │
│       ↓                                                          │
│  SQLite Database                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema Relationships

```
assignments
    ↓ (1→N)
session_links
    ↓ (1→N)
submissions
    ├─→ (1→N) submission_files
    └─→ (1→N) session_logs
```

**assignments → session_links:**
- One assignment can have multiple student links
- Each link is unique and expires independently

**session_links → submissions:**
- One link can receive multiple submissions (though typically 1)
- Submissions tied to specific link and student session

**submissions → submission_files:**
- One submission contains multiple files
- Files immutable after submission
- Includes solution.py, instructions.md, session logs

**submissions → session_logs:**
- One submission can have 0 to many Claude interactions
- Logs analyzed to calculate approach and efficiency scores

## Request/Response Cycle

### 1. Assignment Creation
```
REQUEST:
POST /api/assignments
Content-Type: application/json
{
  "title": "Task",
  "evaluation_criteria": "Works",
  "description": "...",
  "starter_code": "..."
}

PROCESSING:
1. Validate required fields
2. Generate UUID
3. Insert into assignments table
4. Commit transaction
5. Return response

RESPONSE:
201 Created
{
  "id": "uuid",
  "title": "Task",
  "evaluation_criteria": "Works",
  "description": "...",
  "starter_code": "..."
}
```

### 2. Student Portal Access
```
REQUEST:
GET /student/link_id

PROCESSING:
1. Lookup session_link by link_id
2. Join with assignments table
3. Generate HTML with:
   - Assignment details (left)
   - Embedded iframe to code-server (right)
   - Submit button
   - Results panel (initially hidden)
4. Inject port, link_id, expires_at into JavaScript

RESPONSE:
200 OK
Content-Type: text/html
[Complete HTML page with embedded IDE]
```

### 3. Submission & Evaluation
```
REQUEST:
POST /api/submit-with-files/link_id
Content-Type: application/json
{}

PROCESSING:
1. Lookup container_id from session_link
2. Extract files via Docker tar API:
   - solution.py
   - instructions.md
   - session.log (if exists)
3. Create submission record
4. Store files in submission_files table
5. Parse session logs if present
6. Store parsed logs in session_logs table
7. Spawn background thread:
   a. Get session logs from DB
   b. Call Claude API with code
   c. Parse Claude response
   d. Calculate approach & efficiency scores
   e. Combine all scores
   f. UPDATE submissions with results
8. Return submission_id immediately

RESPONSE:
202 Accepted
{
  "submission_id": "uuid",
  "status": "submitted",
  "message": "Evaluation in progress...",
  "session_logs_count": 0
}

LATER (Async):
GET /api/submission/submission_id

RESPONSE:
200 OK
{
  "submission_id": "uuid",
  "score": 72.5,
  "feedback": "Detailed feedback with scoring breakdown",
  "evaluation_result": {...},
  "assignment_title": "Task",
  "instructions_md": "...",
  "claude_logs": "..."
}
```

## Error Handling Flow

```
Request
  │
  ├─ Validation Error ─→ 400 Bad Request
  │
  ├─ Not Found ────────→ 404 Not Found
  │
  ├─ Processing Error ─→ 500 Internal Server Error
  │
  ├─ Async Error ──────→ Error logged, submission marked failed
  │
  └─ Success ─────────→ 200/201/202 OK
```

## Scaling Architecture (Future)

```
Load Balancer (Nginx)
    │
    ├─→ Backend Instance 1
    ├─→ Backend Instance 2
    └─→ Backend Instance 3
         │
         └─→ PostgreSQL (replicated)
              └─→ Redis Cache
              └─→ Message Queue (for evaluations)
```

---

**Last Updated:** June 2026
**Version:** 1.0.0
