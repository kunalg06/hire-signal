# AI Engineering Assessment & Evaluation Platform - Project Requirements Document

## Document Information
- **Project Name:** AI Engineering Assessment & Evaluation Platform
- **Version:** 1.0.0
- **Last Updated:** June 2026
- **Status:** Production Ready

---

## 1. Project Overview

### 1.1 Purpose
The AI Engineering Assessment & Evaluation Platform is a comprehensive educational system designed to:
- Enable teachers to create coding assignments with custom evaluation criteria
- Provide students with isolated, browser-based coding environments
- Automatically evaluate student code using Claude AI
- Track and analyze student problem-solving approaches through Claude CLI session logs
- Generate detailed feedback with multi-dimensional scoring (code quality, approach, efficiency)

### 1.2 Target Users
- **Teachers:** Create assignments, generate student access links, review evaluation results
- **Students:** Code in browser-based IDE, submit solutions, receive AI-powered feedback
- **Administrators:** Manage platform deployment, monitor system health

### 1.3 Key Features
1. **Assignment Management** - Create, store, and manage coding assignments
2. **Student Portal** - Browser-based coding environment with embedded code-server
3. **Isolated Containers** - Docker-based per-student coding environments
4. **Claude Integration** - AI-powered code evaluation and feedback
5. **Session Logging** - Track Claude CLI interactions for approach analysis
6. **Multi-Dimensional Scoring** - Code quality (40%), problem-solving approach (30%), efficiency (30%)
7. **Teacher Dashboard** - View submissions, results, and evaluation analytics

---

## 2. Functional Requirements

### 2.1 Assignment Management

**FR-001: Create Assignment**
- Teachers can create new assignments via REST API
- Required fields: title, evaluation_criteria
- Optional fields: description, starter_code
- System generates unique assignment_id (UUID)
- Assignments persist in SQLite database

**FR-002: Retrieve Assignment**
- Teachers/students can retrieve assignment details via link_id
- Returns: title, description, evaluation criteria, starter code
- Response: 200 OK with assignment data or 404 if not found

**FR-003: Assignment Validation**
- Title must be non-empty string
- Evaluation criteria must be non-empty string
- Description and starter_code optional but recommended

### 2.2 Student Access & Coding

**FR-004: Generate Student Link**
- Teachers generate unique access link per assignment
- System creates isolated Docker container with code-server
- Container auto-assigned port from range 6000-7000
- Link expires after 24 hours
- Returns: link_id, access_url, vscode_port, expires_at

**FR-005: Student Portal Access**
- GET /student/{link_id} returns interactive dashboard
- Dashboard includes:
  - Assignment details (left column)
  - Embedded code-server iframe (right column)
  - Submit button
  - Session timer
  - Results panel (post-submission)

**FR-006: Code Editing**
- Students edit code in browser-based code-server
- Files automatically saved to /workspace in container
- Starter code pre-loaded into solution.py
- Students can create/delete/modify any files

**FR-007: Claude CLI Access**
- Claude CLI pre-installed in code-server container
- Students can run: `claude evaluate solution.py`
- Claude interactions logged to session.log in container

### 2.3 Code Submission & Evaluation

**FR-008: Submit Code**
- POST /api/submit-with-files/{link_id}
- Collects files from container: solution.py, instructions.md, session logs
- Creates submission record with files stored in database
- Returns: submission_id, status, message
- Response: 202 Accepted (evaluation in background)

**FR-009: Session Log Parsing**
- Parse Claude session logs from multiple formats:
  - JSON lines format
  - Plaintext transcript (Prompt: ... Response: ...)
  - Mixed/unstructured logs
- Structured output: [timestamp, interaction_type, prompt, response_summary, file_changes_count]
- Malformed entries skipped with warning

**FR-010: Code Evaluation**
- Claude API evaluates code with prompt including:
  - Assignment title, description, criteria
  - Submitted code
  - Request for JSON response: correctness, code_quality, completeness, score (0-100)
- Returns evaluation details + code_quality_score

**FR-011: Approach Scoring**
- Analyze session logs for problem-solving patterns
- Iteration count: 3 points per Claude interaction (max 15)
- Self-correction bonus: +5 points per error-fix pattern (keywords: error, fix, try again, etc.)
- Final approach score: 0-30 points

**FR-012: Efficiency Scoring**
- Calculate elapsed time: submission_time - container_creation_time
- 2-hour budget baseline
- Scoring scale:
  - ≤0.5 hours: 30 points
  - ≤1 hour: 25 points
  - ≤2 hours: 20 points
  - ≤4 hours: 10 points
  - >4 hours: 5 points
- Final efficiency score: 0-30 points

**FR-013: Combined Scoring**
- Formula: (code_quality × 0.4) + (approach × 0.3) + (efficiency × 0.3)
- Final score: 0-100 points
- Feedback includes breakdown of all three components

**FR-014: Retrieve Evaluation Results**
- GET /api/submission/{submission_id}
- Returns: score, feedback, evaluation_details, assignment_title, instructions_md
- Response: 200 OK or 404 if not found

### 2.4 Session Log Management

**FR-015: Retrieve Session Logs**
- GET /api/session-logs/{submission_id}
- Returns array of session log entries with timestamps, prompts, responses
- Response: JSON array or empty array if no logs

**FR-016: Session Log Storage**
- Logs stored in session_logs table per submission
- Append-only, not modified after submission
- Fields: log_id (PK), submission_id (FK), timestamp, interaction_type, prompt, response_summary, file_changes_count, raw_json

---

## 3. Non-Functional Requirements

### 3.1 Performance
- **Response Time:** API endpoints should respond within 2 seconds (excluding evaluation)
- **Evaluation:** Background task, user notified when complete (typically 5-10 seconds)
- **Concurrent Users:** Support 10+ simultaneous student sessions
- **Container Startup:** <5 seconds from link generation to accessible code-server

### 3.2 Scalability
- **Database:** SQLite for single-node deployment, PostgreSQL for scaling
- **Containers:** Auto-cleanup after 24 hours, reusable ports
- **File Storage:** Submissions stored in database, expandable to file system

### 3.3 Security
- **Authentication:** link_id as implicit auth (no password required)
- **Container Isolation:** Docker sandbox per student
- **API Security:** Input validation on all endpoints, no SQL injection
- **Secrets:** API keys from environment variables
- **Data Privacy:** Session logs stored plain text for teacher review

### 3.4 Reliability
- **Database:** Transactions committed atomically
- **Error Handling:** Malformed logs skipped gracefully, no crashes
- **Container Cleanup:** Automatic removal after timeout
- **Fallbacks:** If container unavailable, submission still accepted

### 3.5 Usability
- **Interface:** Responsive design (mobile/desktop)
- **Dashboard:** One-page with embedded IDE and results
- **Feedback:** Clear scoring breakdown with reasoning
- **Session Timing:** Visible countdown timer for access window

---

## 4. Technical Specifications

### 4.1 Architecture
```
Student Browser
    ↓
    ├─ GET /student/{link_id} → HTML Dashboard
    ├─ iframe → http://localhost:{port} → code-server Container
    └─ POST /api/submit-with-files/{link_id} → Backend

Backend (Flask)
    ├─ Database Service (SQLite)
    ├─ Docker Service (container management)
    ├─ Evaluation Service (Claude API)
    ├─ Session Log Service (parsing/scoring)
    └─ Routes (REST API endpoints)

Data Storage
    ├─ assignments.db (SQLite)
    ├─ Tables: assignments, session_links, submissions, submission_files, session_logs
    └─ Automatic initialization on startup
```

### 4.2 Tech Stack
- **Web Framework:** Flask 3.0.0
- **Language:** Python 3.11
- **Database:** SQLite (development) / PostgreSQL (production)
- **Container Platform:** Docker 7.0.0
- **AI Engine:** Anthropic Claude API
- **Frontend:** HTML5/CSS3/JavaScript (vanilla)
- **IDE:** Code-server (browser-based VS Code)

### 4.3 Database Schema

**assignments table**
```sql
id (PK TEXT) - Assignment UUID
title (TEXT) - Assignment title
description (TEXT) - Full description
starter_code (TEXT) - Initial code template
evaluation_criteria (TEXT) - Grading rubric
created_at (TIMESTAMP) - Creation time
```

**session_links table**
```sql
link_id (PK TEXT) - Unique access link
assignment_id (FK TEXT) - Reference to assignment
container_id (TEXT) - Docker container ID
port (INTEGER) - Assigned port
created_at (TIMESTAMP) - Creation time
expires_at (TIMESTAMP) - Access expiration
```

**submissions table**
```sql
submission_id (PK TEXT) - Submission UUID
link_id (FK TEXT) - Reference to session link
assignment_id (FK TEXT) - Reference to assignment
code (TEXT) - Submitted code (nullable)
submitted_at (TIMESTAMP) - Submission time
evaluation_result (TEXT) - Claude evaluation JSON
score (REAL) - Final score (0-100)
feedback (TEXT) - Feedback text
files_json (TEXT) - JSON array of file names
evaluated_at (TIMESTAMP) - Evaluation completion time
```

**submission_files table**
```sql
file_id (PK TEXT) - File UUID
submission_id (FK TEXT) - Reference to submission
filename (TEXT) - File name
file_content (TEXT) - File contents
file_size (INTEGER) - File size in bytes
created_at (TIMESTAMP) - Upload time
```

**session_logs table**
```sql
log_id (PK TEXT) - Log entry UUID
submission_id (FK TEXT) - Reference to submission
timestamp (TEXT) - ISO 8601 timestamp
interaction_type (TEXT) - Type of interaction
prompt (TEXT) - Claude prompt
response_summary (TEXT) - Claude response summary
file_changes_count (INTEGER) - Number of files changed
raw_json (TEXT) - Raw interaction JSON
created_at (TIMESTAMP) - Log time
```

### 4.4 API Endpoints

**Assignments**
- `POST /api/assignments` - Create assignment
- `GET /api/assignments/{id}` - Get assignment details

**Links**
- `POST /api/generate-link/{assignment_id}` - Generate student access link

**Submissions**
- `POST /api/submit-with-files/{link_id}` - Submit code for evaluation
- `GET /api/submission/{id}` - Get evaluation results
- `GET /api/session-logs/{id}` - Get Claude session logs

**Student**
- `GET /student/{link_id}` - Student dashboard with embedded IDE
- `GET /` - Teacher dashboard frontend

### 4.5 Environment Variables
```
FLASK_ENV=production|development|testing
HOST=0.0.0.0
PORT=8000
ANTHROPIC_API_KEY=sk-ant-...
DOCKER_HOST=unix:///var/run/docker.sock (optional)
SECRET_KEY=<production-only>
```

---

## 5. Data Flow

### 5.1 Assignment Creation Flow
1. Teacher POST /api/assignments with title, criteria, description, starter_code
2. Backend validates, generates UUID, stores in assignments table
3. Returns assignment_id to teacher
4. Teacher can now generate links for this assignment

### 5.2 Student Submission Flow
1. Teacher POST /api/generate-link/{assignment_id}
2. Backend creates Docker container, assigns port, generates link_id
3. Returns link_id and access_url to teacher
4. Teacher shares link with student
5. Student GET /student/{link_id}
6. Backend returns HTML dashboard with embedded code-server iframe at localhost:{port}
7. Student codes in IDE, uses `claude evaluate solution.py` in terminal
8. Claude interactions logged to /home/coder/.claude/logs/session.log in container
9. Student clicks "Submit Solution" button
10. Frontend POST /api/submit-with-files/{link_id}
11. Backend collects files from container (tar API), parses logs, stores in DB
12. Background thread evaluates with Claude, calculates scores, updates submission
13. Frontend polls GET /api/submission/{id} until score available
14. Results displayed on same page with scoring breakdown + session logs

### 5.3 Evaluation Flow
1. Backend extracts solution.py from submission_files
2. Retrieves session_logs from database
3. Calls EvaluationService.evaluate_code() with Claude API
4. Claude returns: correctness, code_quality, completeness, score
5. SessionLogService.calculate_scores() computes approach + efficiency scores
6. Final score = (code_quality × 0.4) + (approach × 0.3) + (efficiency × 0.3)
7. Feedback formatted with scoring breakdown
8. Results stored in submissions table
9. Teacher can view via dashboard or API

---

## 6. Quality Assurance

### 6.1 Testing Requirements
- **Unit Tests:** Models, services, utility functions
- **Integration Tests:** Database transactions, API endpoints
- **End-to-End Tests:** Full workflow from assignment to evaluation
- **Load Tests:** 10+ concurrent submissions
- **Security Tests:** Input validation, SQL injection prevention

### 6.2 Code Quality
- Python 3.11+ type hints
- PEP 8 style compliance
- Docstrings on all functions
- Maximum 20-line function length (prefer smaller)
- DRY principle: no duplicate code

### 6.3 Documentation
- README with features, installation, usage
- Architecture flow diagrams
- API documentation with curl examples
- Database schema documentation
- Deployment instructions

---

## 7. Deployment Requirements

### 7.1 System Requirements
- **OS:** Linux (production), macOS/Windows (development)
- **Docker:** Docker Engine 20.10+, Docker Compose 2.0+
- **Python:** Python 3.11+
- **RAM:** 2GB minimum (4GB recommended)
- **Disk:** 10GB for base images, 1GB per 100 submissions
- **Network:** Internet access for Anthropic Claude API

### 7.2 Installation
```bash
git clone <repo>
cd project2025/coding_platforms
cp .env.example .env
# Edit .env with ANTHROPIC_API_KEY
docker-compose build
docker-compose up -d
# Access at http://localhost:8000
```

### 7.3 Configuration
- `.env.example` - Template with required variables
- `app/config.py` - Environment-specific configuration
- `docker-compose.yml` - Service orchestration
- `Dockerfile.backend` - Backend image definition
- `Dockerfile.codeserver` - Student environment image definition

---

## 8. Success Criteria

### 8.1 Functional Success
- ✅ Teachers can create assignments
- ✅ Students can access portal and code
- ✅ Claude evaluates code automatically
- ✅ Scores calculated from code quality + approach + efficiency
- ✅ Results visible on student portal and teacher dashboard

### 8.2 Performance Success
- ✅ API endpoints respond <2 seconds
- ✅ Evaluation completes in 5-10 seconds
- ✅ Support 10+ concurrent students
- ✅ No data loss on container cleanup

### 8.3 User Experience Success
- ✅ One-click submission from portal
- ✅ Clear feedback with scoring breakdown
- ✅ Session logs visible for review
- ✅ Responsive design on mobile/desktop

---

## 9. Future Enhancements

### 9.1 Short-term (1-2 months)
- [ ] Real-time session log updates during coding
- [ ] Student peer review system
- [ ] Assignment templates library
- [ ] Bulk student import

### 9.2 Medium-term (3-6 months)
- [ ] Leaderboard and progress tracking
- [ ] Plagiarism detection
- [ ] Custom rubric builder
- [ ] PostgreSQL migration for scaling

### 9.3 Long-term (6+ months)
- [ ] Mobile app (iOS/Android)
- [ ] Video/text annotations on code
- [ ] Team/group assignments
- [ ] Certification programs
- [ ] Analytics dashboard with trends

---

## 10. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | June 2026 | Claude | Initial document, Flask architecture, all features |
