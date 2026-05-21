# Project Structure & File Guide

## Overview

Claude Assignment Platform is a complete educational system with 10+ interconnected components. Below is the complete file structure and what each file does.

```
claude-assignment-platform/
├── main.py                    # Core FastAPI backend application
├── Dockerfile                 # Student VS Code environment (code-server)
├── Dockerfile.backend         # Lightweight backend service container
├── docker-compose.yml         # Orchestration for all services
├── requirements.txt           # Python dependencies
├── frontend.html              # Teacher dashboard (pure HTML+JS)
├── client.py                  # Python SDK for API interaction
├── quickstart.sh              # Automated setup script
├── README.md                  # Main documentation
├── INSTALLATION.md            # Detailed setup & deployment guide
├── .gitignore                 # Git ignore rules
├── .env.example               # Example environment variables
└── (Optional)
    ├── docker-compose.prod.yml    # Production configuration
    ├── prometheus.yml             # Monitoring (optional)
    └── k8s/                       # Kubernetes manifests (optional)
```

---

## File Descriptions

### Core Application Files

#### `main.py` (1000+ lines)
**What it does**: The complete FastAPI backend server

**Key components**:
- Database initialization (SQLite/PostgreSQL)
- Assignment CRUD operations
- Docker container management
- Link generation and session tracking
- Code submission handling
- Claude API integration for evaluation
- Background task cleanup

**Key endpoints**:
- `POST /api/assignments` - Create assignment
- `POST /api/generate-link/{id}` - Generate student link
- `POST /api/submit/{link_id}` - Submit code for evaluation
- `GET /api/submission/{id}` - View evaluation results

**Dependencies**:
- `fastapi` - Web framework
- `docker` - Container management
- `anthropic` - Claude API client
- `sqlite3` - Database (default)

---

#### `Dockerfile` (50 lines)
**What it does**: Container image for student coding environment

**Includes**:
- VS Code (code-server)
- Python 3 + pip
- Claude Python SDK (anthropic package)
- Development tools (git, curl, nano, vim)
- VS Code extensions (Python, Pylance)
- Pre-configured settings

**Exposed port**: 8080 (VS Code)

---

#### `Dockerfile.backend` (25 lines)
**What it does**: Lightweight container for FastAPI backend

**Includes**:
- Python 3.11 slim image
- All Python dependencies from requirements.txt
- Application code

**Exposed port**: 8000

---

#### `docker-compose.yml` (50 lines)
**What it does**: Orchestrates all services

**Services**:
1. `backend` - FastAPI server (port 8000)
2. `postgres` - Database (optional, port 5432)
3. `redis` - Caching (optional, port 6379)

**Volumes**:
- Docker socket for container management
- Data directory for persistence
- Assignment code storage

---

#### `requirements.txt` (12 lines)
**What it does**: Lists all Python package dependencies

**Key packages**:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `anthropic` - Claude API
- `docker` - Container management
- `sqlalchemy` - ORM (for PostgreSQL)
- `pydantic` - Data validation

---

### Frontend & Client Files

#### `frontend.html` (400+ lines)
**What it does**: Complete web dashboard for teachers

**Features**:
1. Create assignments form
2. Generate student links
3. Submit code for evaluation
4. View submission history
5. Display evaluation results with scoring

**No backend required**: Uses only JavaScript + REST API calls

**Styling**: 
- Gradient purple theme
- Responsive grid layout
- Animated result cards

---

#### `client.py` (300+ lines)
**What it does**: Python SDK for programmatic API access

**Classes**:
- `AssignmentClient` - Main API client class

**Methods**:
- `create_assignment()` - Create new assignment
- `generate_link()` - Generate student link
- `submit_code()` - Submit code for evaluation
- `get_submission()` - Retrieve results
- `create_assignment_batch()` - Bulk operations

**Usage**:
```python
from client import AssignmentClient
client = AssignmentClient()
assignment = client.create_assignment(...)
link = client.generate_link(assignment['id'])
```

**Helper functions**:
- `demo_workflow()` - Complete workflow example
- `create_sample_assignment()` - Test data

---

### Configuration & Setup Files

#### `docker-compose.yml`
**Environment services**:
- FastAPI backend
- PostgreSQL (optional)
- Redis (optional)

**Network**: Creates `assignment-network` for service communication

**Volumes**: Persistent storage for assignments and database

---

#### `requirements.txt`
```
fastapi==0.104.1
uvicorn==0.24.0
anthropic==0.7.1
docker==7.0.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
redis==5.0.1
pytest==7.4.3
```

---

#### `.env.example`
**Required variables**:
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**Optional variables**:
```bash
DB_PASSWORD=secure_password
DATABASE_URL=sqlite:///./assignments.db
DOCKER_HOST=unix:///var/run/docker.sock
PORT=8000
```

---

#### `.gitignore`
**Excludes**:
- Virtual environments
- Python cache files
- `.env` files (secrets)
- SQLite databases
- Docker build artifacts
- IDE files (.vscode, .idea)
- Temporary assignment data

---

### Documentation Files

#### `README.md` (500+ lines)
**Comprehensive guide covering**:
- Features overview
- Architecture diagram
- Installation steps
- Usage guide (teacher & student views)
- Complete API reference
- Docker environment details
- Configuration options
- Troubleshooting guide
- Scaling considerations
- Security notes
- FAQ

---

#### `INSTALLATION.md` (600+ lines)
**Detailed deployment covering**:
- System requirements
- Local development setup
- Docker deployment
- Production deployment options:
  - AWS EC2
  - Kubernetes
  - Docker Swarm
- Database configuration
- Monitoring & logging
- Troubleshooting
- Performance tuning
- Maintenance tasks

---

### Automation Files

#### `quickstart.sh` (100+ lines)
**What it does**: Automated setup script

**Steps**:
1. Checks Docker/Docker Compose installation
2. Validates Anthropic API key
3. Creates `.env` file
4. Builds and starts containers
5. Waits for services to be ready
6. Provides access instructions

**Usage**:
```bash
chmod +x quickstart.sh
./quickstart.sh
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    TEACHER                                   │
│            (Uses frontend.html)                              │
└─────────────┬───────────────────────────────────────────────┘
              │
              │ 1. Create Assignment
              ▼
    ┌─────────────────────┐
    │  FastAPI Backend    │
    │  (main.py port:8000)│
    └──────────┬──────────┘
              │
              │ 2. Generate Link
              ▼
    ┌─────────────────────────────────────┐
    │  Docker Container (Per Student)     │
    │  ┌─────────────────────────────┐    │
    │  │ VS Code (code-server)       │    │
    │  │ Port: 6000-7000             │    │
    │  │ - Python environment        │    │
    │  │ - Claude CLI available      │    │
    │  │ - Starter code loaded       │    │
    │  └─────────────────────────────┘    │
    └──────────┬─────────────────────────┘
              │
              │ 3. Student codes & submits
              ▼
    ┌─────────────────────┐
    │  FastAPI Backend    │
    │  (Receives code)    │
    └──────────┬──────────┘
              │
              │ 4. Request evaluation
              ▼
    ┌─────────────────────┐
    │   Claude API        │
    │   (Evaluation)      │
    └──────────┬──────────┘
              │
              │ 5. Return feedback
              ▼
    ┌─────────────────────┐
    │  Database           │
    │  (Store results)    │
    └──────────┬──────────┘
              │
              │ 6. Show to teacher
              ▼
    ┌─────────────────────┐
    │  frontend.html      │
    │  (Results display)  │
    └─────────────────────┘
```

---

## Quick Reference: File Usage

### For Getting Started
1. Read `README.md` - Overview
2. Run `quickstart.sh` - Automatic setup
3. Open `frontend.html` - Access dashboard

### For Development
1. Edit `main.py` - Backend logic
2. Edit `frontend.html` - UI changes
3. Edit `Dockerfile` - Student environment
4. Run `docker-compose up --build`

### For Deployment
1. Read `INSTALLATION.md` - Detailed guide
2. Update `docker-compose.yml` - Production settings
3. Create `docker-compose.prod.yml` - Production override
4. Deploy to cloud (AWS, Kubernetes, etc.)

### For Integration
1. Use `client.py` - Python SDK
2. Call REST API endpoints in `main.py`
3. Or use `frontend.html` as template

---

## Database Schema

### Generated automatically by `main.py`:

**assignments** table:
```sql
id (TEXT PRIMARY KEY)
title (TEXT)
description (TEXT)
starter_code (TEXT)
evaluation_criteria (TEXT)
created_at (TIMESTAMP)
```

**session_links** table:
```sql
link_id (TEXT PRIMARY KEY)
assignment_id (TEXT)
container_id (TEXT)
port (INTEGER)
created_at (TIMESTAMP)
expires_at (TIMESTAMP)
```

**submissions** table:
```sql
submission_id (TEXT PRIMARY KEY)
link_id (TEXT)
assignment_id (TEXT)
code (TEXT)
submitted_at (TIMESTAMP)
evaluation_result (JSON)
score (REAL)
feedback (TEXT)
```

---

## Configuration & Customization

### Change Claude Model
In `main.py`, find:
```python
message = anthropic_client.messages.create(
    model="claude-opus-4-1",  # Change this
    ...
)
```

### Add More Tools to VS Code Container
In `Dockerfile`:
```dockerfile
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    scikit-learn  # Add here
```

### Change Database
Update `main.py` database connection or `docker-compose.yml`

### Modify Evaluation Criteria
Edit the evaluation prompt in `main.py` `evaluate_code_with_claude()` function

---

## Support & Resources

- **Anthropic API Docs**: https://docs.claude.com
- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **Docker Documentation**: https://docs.docker.com
- **code-server GitHub**: https://github.com/coder/code-server

---

**Last Updated**: May 2026  
**Version**: 1.0.0
