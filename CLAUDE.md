# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🎯 Project Overview

**Claude Assignment Platform** is a production-ready educational system where teachers create coding assignments and Claude AI automatically evaluates student submissions. Students access browser-based VS Code environments (code-server) running in isolated Docker containers.

### Core Flow
1. Teachers create assignments via REST API or HTML dashboard
2. Generate unique access links for students
3. Each link spins up an isolated Docker container with VS Code
4. Students code in the browser and submit for evaluation
5. Claude evaluates code and provides feedback
6. Results stored in SQLite database and shown in teacher dashboard

---

## 🗂️ Project Architecture

### Three-Tier System

**Frontend Layer** (`frontend.html`)
- Pure HTML/CSS/JavaScript dashboard
- No backend required for UI rendering
- Makes REST API calls to backend
- Teacher-facing: create assignments, generate links, view results

**Backend Layer** (`main.py`)
- FastAPI application (Python 3.11)
- REST API endpoints for all operations
- Database management (SQLite auto-initialized)
- Docker container orchestration
- Claude API integration for code evaluation
- Runs on port 8000

**Student Environment Layer** (`Dockerfile`)
- Isolated container per student session
- code-server (browser-based VS Code)
- Python 3 + development tools
- Anthropic SDK pre-installed
- Auto-assigned port (6000-7000 range)

### Database Schema

Three SQLite tables (auto-created on startup):
- **assignments**: Title, description, starter code, evaluation criteria
- **session_links**: Maps unique link_id to assignment_id, container, port, expiration
- **submissions**: Stores submitted code, evaluation results, score, feedback

### Key Dependencies
- **fastapi**: Web framework
- **docker**: Python Docker SDK for container management
- **anthropic**: Claude API client
- **pydantic**: Request/response validation
- **uvicorn**: ASGI server
- **sqlalchemy**: (optional) Database ORM for PostgreSQL

---

## 🚀 Common Development Tasks

### Starting Services

```bash
# Development with hot reload
docker-compose up --build

# Services run on:
# - Backend API: http://localhost:8000
# - Frontend: open frontend.html in browser
# - API docs: http://localhost:8000/docs
```

### Running Individual Components

```bash
# Just the backend (assumes Docker available)
python main.py

# Serve frontend locally (Python)
python -m http.server 8080
# Then visit http://localhost:8080/frontend.html
```

### Building & Testing

```bash
# Run automated setup (includes Docker build)
chmod +x quickstart.sh
./quickstart.sh

# Rebuild containers without cache
docker-compose build --no-cache

# View logs in real-time
docker-compose logs -f backend

# Check running containers
docker-compose ps
```

### Testing the API

```bash
# View auto-generated API documentation
# Open http://localhost:8000/docs in browser

# Create assignment via curl
curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","description":"Test","evaluation_criteria":"Test"}'

# Generate student link
curl -X POST http://localhost:8000/api/generate-link/{assignment_id}

# Submit code
curl -X POST http://localhost:8000/api/submit/{link_id} \
  -H "Content-Type: application/json" \
  -d '{"code":"def hello(): pass"}'

# Get submission results
curl http://localhost:8000/api/submission/{submission_id}
```

### Accessing Student Containers

```bash
# List all running assignment containers
docker ps | grep assignment

# Access a container's shell
docker exec -it {container_id} bash

# View container logs
docker logs {container_id}

# Check file contents in container
docker exec {container_id} cat /workspace/solution.py
```

---

## 📁 Critical File Guide

### Backend Implementation (`main.py` - 1000+ lines)

**Key sections**:
- Lines 17-63: FastAPI app initialization, Docker/Anthropic client setup
- Lines 65-140: Database initialization with three tables
- Lines 200-300: Assignment CRUD endpoints (`/api/assignments`)
- Lines 400-500: Link generation (`/api/generate-link/{assignment_id}`)
- Lines 600-700: Docker container management
- Lines 800-900: Submission handling (`/api/submit/{link_id}`)
- Lines 1000+: Claude API evaluation (`evaluate_code_with_claude()`)

**Key functions**:
- `init_db()`: Auto-creates SQLite tables on startup
- `get_docker_client()`: Lazy initialization of Docker connection
- `get_anthropic_client()`: Lazy initialization of Claude API client
- `evaluate_code_with_claude()`: Sends code to Claude for evaluation with prompt engineering

### Frontend (`frontend.html` - 400+ lines)

**Key sections**:
- Styles: Purple gradient theme with responsive grid layout
- Create Assignment form: Collects title, description, starter code, evaluation criteria
- Generate Link form: Takes assignment ID, returns unique access URL
- Submit Code form: Student submission interface
- Results display: Shows score, feedback, evaluation details

**Key JavaScript functions**:
- `createAssignment()`: POST to `/api/assignments`
- `generateLink()`: POST to `/api/generate-link/{id}`
- `submitCode()`: POST to `/api/submit/{link_id}`
- `getSubmission()`: GET from `/api/submission/{id}`

### Docker Configuration

**`Dockerfile`**: Student environment
- Base: Python 3.11 + code-server
- Pre-installs: Anthropic SDK, git, development tools
- Exposes: Port 8080 for code-server UI
- Loads: Starter code into `/workspace/solution.py`

**`Dockerfile.backend`**: Backend service
- Base: Python 3.11 slim
- Installs: Dependencies from requirements.txt
- Exposes: Port 8000

**`docker-compose.yml`**: Orchestration
- Services: backend (port 8000), optional postgres/redis
- Volumes: Docker socket for container management
- Network: assignment-network for service communication
- Environment: Sets ANTHROPIC_API_KEY and other env vars

### Support Files

**`client.py`**: Python SDK for programmatic API access
- `AssignmentClient` class with methods: `create_assignment()`, `generate_link()`, `submit_code()`, `get_submission()`
- Helper: `demo_workflow()` shows complete usage example

**`requirements.txt`**: All Python dependencies
- Core: fastapi, uvicorn, anthropic, docker
- Optional: sqlalchemy, psycopg2 (for PostgreSQL), redis

**`quickstart.sh`**: Automated setup script
- Validates Docker/API key
- Creates `.env` file
- Builds and starts services
- Provides access instructions

---

## 🔑 Important Implementation Details

### Environment Variables

**Required**:
- `ANTHROPIC_API_KEY`: Claude API key (format: `sk-ant-...`)

**Optional**:
- `DB_PASSWORD`: Database password (if using PostgreSQL)
- `DATABASE_URL`: Custom DB connection string (defaults to SQLite)
- `DOCKER_HOST`: Docker daemon socket (defaults to Unix socket or Windows pipe)
- `PORT`: Backend port (defaults to 8000)
- `LOG_LEVEL`: Logging level (defaults to INFO)

### API Endpoints Summary

**Assignment Management**:
- `POST /api/assignments` - Create assignment
- `GET /api/assignments/{id}` - Get assignment details

**Link Generation**:
- `POST /api/generate-link/{assignment_id}` - Generate student link
- `GET /api/session/{link_id}` - Get session info

**Submissions**:
- `POST /api/submit/{link_id}` - Submit code for evaluation
- `GET /api/submission/{id}` - Get evaluation results
- `GET /api/health` - Health check

### Docker Container Lifecycle

1. **Link Generation**: When `/api/generate-link` is called, main.py:
   - Finds available port (starting at 6000)
   - Creates Docker container from `Dockerfile`
   - Injects starter code
   - Exposes port via port mapping
   - Stores container_id and port in database

2. **Student Access**: Browser-based code-server accessible at `http://localhost:{port}`

3. **Auto-Cleanup**: Containers stay alive for 24 hours (configurable), then auto-removed

### Claude Evaluation Flow

1. **Submission**: Student submits code via `/api/submit/{link_id}`
2. **Prompt Engineering**: `evaluate_code_with_claude()` builds evaluation prompt including:
   - Submitted code
   - Assignment description
   - Evaluation criteria
   - Request for score (0-100) + feedback
3. **Claude Response**: Parsed for score, feedback, and evaluation details
4. **Storage**: Results stored in submissions table with timestamp
5. **Display**: Teacher views via frontend dashboard

---

## 🛠️ Common Customization Points

### Change Claude Model
In `main.py`, find `evaluate_code_with_claude()` function and modify:
```python
message = anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",  # or claude-haiku-4-5
    ...
)
```

Available models: opus-4-1 (most capable), sonnet-4 (balanced), haiku-4-5 (fastest)

### Add More Tools to Student Container
In `Dockerfile`, add packages:
```dockerfile
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    requests
```

### Switch to PostgreSQL
1. Uncomment postgres service in `docker-compose.yml`
2. Update `DATABASE_URL` environment variable
3. Update connection string in `main.py`

### Customize Evaluation Prompt
In `main.py`, modify the `evaluation_prompt` string in `evaluate_code_with_claude()` to change:
- Evaluation criteria emphasis
- Scoring rubric
- Feedback tone/detail level

---

## 🔍 Debugging & Troubleshooting

### Common Issues

**Port Already in Use**
```bash
# Kill process on port
lsof -i :8000  # (or :6000 for student containers)
kill -9 <PID>

# Or use different port
PORT=8001 docker-compose up
```

**Docker Permission Denied**
```bash
# Linux
sudo chmod 666 /var/run/docker.sock
sudo usermod -aG docker $USER

# Windows: Run as Administrator or check Docker Desktop settings
```

**API Key Invalid**
```bash
# Verify key is set
echo $ANTHROPIC_API_KEY

# Get new key from https://console.anthropic.com
# Set in .env file or export in shell
```

**Container Won't Start**
```bash
# Check backend logs for errors
docker-compose logs backend

# View specific container
docker logs {container_id}

# Rebuild without cache
docker-compose build --no-cache
```

### Debugging Tips

- **API Docs**: Always check http://localhost:8000/docs for live endpoint documentation
- **Database**: Inspect SQLite with `sqlite3 assignments.db "SELECT * FROM submissions;"`
- **Containers**: Use `docker ps` to see running containers, `docker logs` to view output
- **Frontend Console**: Press F12 in browser to see JavaScript errors and network requests

---

## 📊 Data Model & Flow

### Request/Response Cycle

**Creating Assignment**:
```
Frontend POST → /api/assignments
             → Validate with Pydantic
             → Generate UUID
             → Insert into assignments table
             → Return assignment object
```

**Generating Link**:
```
Frontend POST → /api/generate-link/{id}
             → Find available port
             → Create Docker container
             → Inject starter code
             → Insert into session_links table
             → Return link_id and access_url
```

**Submitting Code**:
```
Student POST → /api/submit/{link_id}
            → Validate submission
            → Insert into submissions table
            → Trigger evaluate_code_with_claude() in background
            → Call Claude API with code + criteria
            → Parse Claude response for score + feedback
            → Update submission with results
            → Return submission_id
```

---

## 🚀 Performance & Scaling

### For Development (Single User)
- Current setup handles fine
- SQLite is sufficient
- No scaling concerns

### For Production (10+ Students)
1. **Use PostgreSQL** instead of SQLite for concurrent access
2. **Add Redis** for caching submission results
3. **Implement rate limiting** to prevent API abuse
4. **Monitor container resources** (CPU/memory limits)
5. **Set container timeout** (currently 24 hours)

### Optimization Tips
- Use Claude Haiku for faster evaluation (trade speed for capability)
- Cache evaluation results for identical submissions
- Implement submission queue if evaluation latency becomes issue
- Use connection pooling for database

---

## 📝 Code Style & Conventions

### Current Patterns
- **Database**: Raw SQL with sqlite3 (no ORM needed for current use)
- **Validation**: Pydantic models for request/response schemas
- **Error Handling**: FastAPI HTTPException with appropriate status codes
- **Async**: Uses BackgroundTasks for container cleanup (not async/await)
- **Logging**: Basic print statements (consider upgrading to logging module)

### Naming Conventions
- Tables: snake_case (assignments, session_links)
- Functions: snake_case (init_db, evaluate_code_with_claude)
- Classes: PascalCase (AssignmentClient)
- IDs: UUIDs for assignments, random strings for link_ids

---

## 🔒 Security Considerations

### Current Implementation (Development)
- ✅ CORS open to all origins (for testing)
- ✅ No authentication required
- ✅ API key in environment (not hardcoded)

### For Production
- 🔐 **Add authentication**: JWT tokens or session-based auth
- 🔐 **Restrict CORS**: Only allow your frontend domain
- 🔐 **Use HTTPS**: SSL/TLS for all connections
- 🔐 **Rate limiting**: Prevent abuse
- 🔐 **Input validation**: Already done via Pydantic
- 🔐 **Container security**: Run as non-root, set resource limits
- 🔐 **Database encryption**: Encrypt sensitive data at rest
- 🔐 **Secrets management**: Use env vars or secrets service (not hardcoded)

See README.md and INSTALLATION.md for detailed security hardening guide.

---

## 📖 Documentation Reference

- **README.md**: Features, installation, usage examples, API reference
- **INSTALLATION.md**: Cloud deployment (AWS, Kubernetes), database setup, monitoring
- **PROJECT_STRUCTURE.md**: Detailed file descriptions and data flow diagrams
- **GETTING_STARTED.md**: Quick summary and learning path

---

## 🎓 Code Entry Points

**For Changes to Backend Logic**:
- Modify endpoints in `main.py` (lines 200-1000+)
- Change evaluation logic in `evaluate_code_with_claude()` (lines 900+)

**For Changes to Teacher Dashboard**:
- Edit `frontend.html` (HTML, CSS, JavaScript form handling)

**For Changes to Student Environment**:
- Modify `Dockerfile` (packages, tools, pre-configuration)
- Pre-load different starter code in main.py container creation

**For Adding APIs**:
- Create new endpoint function with `@app.post()` or `@app.get()`
- Add Pydantic model if needed for request validation
- Database operations use raw SQL with sqlite3

**For Database Changes**:
- Modify table definitions in `init_db()` function
- Update corresponding INSERT/SELECT queries
- Consider migration strategy for existing deployments

---

## ⚡ Quick Reference Commands

```bash
# Start all services
docker-compose up --build

# Restart specific service
docker-compose restart backend

# View logs
docker-compose logs -f backend

# Run one-off command in container
docker-compose exec backend python -c "import sqlite3; ..."

# Stop services
docker-compose down

# Full cleanup (removes volumes)
docker-compose down -v

# Access API docs
curl http://localhost:8000/docs

# Test API health
curl http://localhost:8000/api/health

# View SQLite database
sqlite3 assignments.db ".tables"
sqlite3 assignments.db "SELECT * FROM assignments LIMIT 5;"
```

---

## 🔧 Setup & Dependencies

**System Requirements**:
- Docker & Docker Compose
- Python 3.8+ (for local development)
- Anthropic API key
- 2GB+ available disk space

**Installation**:
```bash
# Clone or navigate to project directory
cd project2025/coding_platforms

# Install Python dependencies (optional, for local testing)
pip install -r requirements.txt

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Start services
docker-compose up --build
```

---

**Last Updated**: May 2026  
**Version**: 1.0.0
