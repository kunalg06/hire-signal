# AI Engineering Assessment & Evaluation Platform

> A comprehensive educational system for automated code assessment using Claude AI

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0.0-green.svg)

## 🎯 Features

- **Automated Code Evaluation** - Claude AI evaluates student code with detailed feedback
- **Browser-Based IDE** - Students code in isolated Docker containers with code-server
- **Session Logging** - Track all Claude CLI interactions for problem-solving analysis
- **Multi-Dimensional Scoring** - Code quality (40%) + approach (30%) + efficiency (30%)
- **Teacher Dashboard** - Create assignments, generate links, review results
- **Student Portal** - Embedded IDE, submit directly from platform
- **REST API** - Full API for programmatic access with integrated Docker management
- **System Management API** - Monitor and manage containers without CLI commands

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API Key (get from https://console.anthropic.com)
- Python 3.11+ (optional, for local development)

### Installation

```bash
# Clone repository
git clone <repo>
cd coding_platforms

# Copy environment template
cp .env.example .env

# Edit .env with your Anthropic API Key
# ANTHROPIC_API_KEY=sk-ant-...

# Start services with Docker Compose
cd docker
docker-compose up --build

# OR from root directory
docker-compose -f docker/docker-compose.yml up --build

# Access the platform
# Teacher Dashboard: http://localhost:8000
# API Documentation: http://localhost:8000/api/docs
# API Reference: docs/API_REFERENCE.md
```

## 📊 Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture diagrams and system flows.

## 📖 Documentation

### Main Documentation
- **[FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md)** - Project organization and file layout
- **[docs/PROJECT_REQUIREMENTS.md](docs/PROJECT_REQUIREMENTS.md)** - Complete functional and non-functional requirements
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture, data flows, component diagrams
- **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** - Complete REST API endpoint documentation with examples
- **[CLAUDE.md](CLAUDE.md)** - Development guide and customization points

### Additional Resources
- **[docs/problem_statements.txt](docs/problem_statements.txt)** - Assignment example problems
- **[docker/](docker/)** - Docker configuration files and Dockerfiles
- **[scripts/](scripts/)** - Utility scripts (quickstart.sh)
- **[tools/](tools/)** - SDK and client utilities (Python SDK)
- **[tests/](tests/)** - Test files (currently empty, ready for tests)
- **[data/](data/)** - Database files (auto-created)

## 💻 Usage

### Teacher Dashboard

1. Access http://localhost:8000
2. Create assignments with title, description, evaluation criteria, and starter code
3. Generate unique student links for each assignment
4. Students submit code and get AI-powered feedback
5. View results and session logs for each submission

### API Examples

#### Generate Challenge with AI
```bash
curl -X POST http://localhost:8000/api/generate-challenge \
  -H "Content-Type: application/json" \
  -d '{
    "problem_statement": "Create a function that calculates factorial of a number",
    "difficulty": "easy"
  }'
```

Claude AI generates complete challenge with title, description, evaluation criteria, and starter code.

#### Create Assignment
```bash
curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Temperature Converter",
    "description": "Write a function to convert Celsius to Fahrenheit",
    "evaluation_criteria": "Function should correctly convert temperature values",
    "starter_code": "def celsius_to_fahrenheit(c):\n    pass"
  }'
```

#### Generate Student Link
```bash
curl -X POST http://localhost:8000/api/generate-link/{assignment_id}
```

Response includes unique `link_id` to share with students and port number.

#### Student Submits Code
```bash
curl -X POST http://localhost:8000/api/submit-with-files/{link_id} \
  -H "Content-Type: application/json" \
  -d '{}'
```

Returns submission_id - results available after 5-10 seconds.

#### Get Evaluation Results
```bash
curl http://localhost:8000/api/submission/{submission_id}
```

Returns score, feedback with breakdown, and Claude evaluation details.

#### Get Session Logs
```bash
curl http://localhost:8000/api/session-logs/{submission_id}
```

Returns array of Claude CLI interactions showing student's problem-solving approach.

### System Management API

All Docker operations integrated into REST API. No CLI commands needed:

```bash
# System Status
curl http://localhost:8000/api/system/status

# Health Check (Docker, Database, API)
curl http://localhost:8000/api/system/health

# Clean containers older than 24 hours
curl -X POST http://localhost:8000/api/system/cleanup-old?hours=24

# Force cleanup all containers
curl -X POST http://localhost:8000/api/system/cleanup-all

# Get container info
curl http://localhost:8000/api/system/containers/{container_id}/info

# View container logs
curl http://localhost:8000/api/system/containers/{container_id}/logs?lines=100

# Restart container
curl -X POST http://localhost:8000/api/system/containers/{container_id}/restart

# Stop container
curl -X POST http://localhost:8000/api/system/containers/{container_id}/stop
```

See **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** for complete API documentation with request/response examples.

## 📁 Project Structure

```
├── app/                      # Flask application
│   ├── routes/              # API endpoint blueprints
│   │   ├── assignments.py   # Assignment CRUD
│   │   ├── links.py         # Student link generation
│   │   ├── submissions.py   # Code submission & evaluation
│   │   ├── student.py       # Student portal page
│   │   └── management.py    # System management
│   ├── services/            # Business logic layer
│   │   ├── docker_service.py       # Docker operations
│   │   ├── evaluation_service.py   # Claude API integration
│   │   ├── session_log_service.py  # Log parsing & scoring
│   │   ├── database_service.py     # Database operations
│   │   └── management_service.py   # System health & monitoring
│   ├── models/              # Data layer
│   │   └── database.py      # SQLite connection & schema
│   ├── utils/               # Utilities
│   │   └── helpers.py       # RateLimiter, IDGenerator, validators
│   └── __init__.py          # App factory
│
├── docker/                   # Docker configuration
│   ├── Dockerfile           # Student environment (code-server)
│   ├── Dockerfile.backend   # Backend service
│   ├── Dockerfile.codeserver # Code-server builder
│   └── docker-compose.yml   # Service orchestration
│
├── docs/                     # Documentation
│   ├── ARCHITECTURE.md              # System design
│   ├── API_REFERENCE.md             # Complete API docs
│   ├── PROJECT_REQUIREMENTS.md      # Specifications
│   ├── FOLDER_STRUCTURE.md          # This structure
│   └── problem_statements.txt       # Example assignments
│
├── data/                     # Data directory
│   ├── assignments.db       # SQLite database (auto-created)
│   └── test_assignments.db  # Test database
│
├── scripts/                  # Utility scripts
│   └── quickstart.sh        # Quick start setup script
│
├── tools/                    # SDK and utilities
│   └── client.py            # Python SDK client
│
├── tests/                    # Test files
│   └── (test files here)
│
├── _deprecated/             # Old implementation files
│   ├── app.py               # Old FastAPI version
│   └── main.py              # Old implementation
│
├── frontend.html            # Teacher dashboard (HTML/CSS/JS)
├── run.py                   # Flask entry point
├── requirements.txt         # Python dependencies
├── .env.example             # Environment template
├── .env                     # Environment config (not in git)
├── CLAUDE.md                # Development guide
└── README.md                # This file
```

## 🔧 Configuration

### Environment Variables (in `.env`)

**Required:**
- `ANTHROPIC_API_KEY` - Claude API key from https://console.anthropic.com

**Optional:**
- `FLASK_ENV` - Environment: `development`, `testing`, `production` (default: development)
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 8000)
- `DB_PATH` - Database file path (default: assignments.db)
- `DOCKER_HOST` - Docker daemon socket (default: auto-detect)
- `SECRET_KEY` - Flask secret key (auto-generated in development)

### Flask Configuration

Modify `app/config.py` to customize:
- Rate limiting (requests per window)
- Docker port range (6000-7000)
- Claude model selection
- Session timeout duration
- Database settings

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_assignments.py
```

## 📈 Scoring System

```
Final Score = (Code Quality × 0.4) + (Approach × 0.3) + (Efficiency × 0.3)
```

### Components

- **Code Quality (40%)** 
  - Claude AI evaluation of correctness, style, edge cases, completeness
  - Score: 0-100 points

- **Approach (30%)**
  - Analysis of problem-solving from Claude CLI session logs
  - Iteration count: 3 points per interaction (max 15)
  - Self-correction: +5 points per error-fix pattern (max 15)
  - Score: 0-30 points

- **Efficiency (30%)**
  - Time spent relative to 2-hour baseline
  - ≤0.5 hours: 30 points
  - ≤1 hour: 25 points
  - ≤2 hours: 20 points
  - ≤4 hours: 10 points
  - >4 hours: 5 points

### Example Score Breakdown

```
Student submission for "Temperature Converter" assignment:
  Code Quality:  82/100 (good implementation, handles edge cases)
  Approach:      24/30  (3 iterations, 1 correction)
  Efficiency:    25/30  (submitted in 1.2 hours)
  ─────────────────────────────────────────────
  Final Score:   78.2/100
```

## 🔒 Security Features

- ✅ **Docker Isolation** - Each student gets isolated container
- ✅ **Input Validation** - All endpoints validate and sanitize input
- ✅ **API Key Management** - Keys from environment, never hardcoded
- ✅ **CORS Protection** - Cross-origin request control
- ✅ **Rate Limiting** - 5 requests per 60 seconds per IP
- ✅ **No SQL Injection** - Parameterized queries
- ✅ **Session Management** - 24-hour link expiration

### For Production

- Enable HTTPS/SSL
- Implement JWT authentication
- Restrict CORS to specific domains
- Use strong SECRET_KEY from environment
- Database encryption at rest
- Regular security updates
- Monitor and log all API access

## 🚀 Development

### Local Setup (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment
export ANTHROPIC_API_KEY="sk-ant-..."
export FLASK_ENV=development

# Run Flask app
python run.py
```

### Code Organization

- **routes/** - HTTP request handlers (thin layer)
- **services/** - Business logic (thick layer)
- **models/** - Database access (thin layer)
- **utils/** - Shared utilities

### Adding Features

1. Create API route in `app/routes/`
2. Implement business logic in `app/services/`
3. Add database operations in `app/models/database.py`
4. Update `docs/API_REFERENCE.md`
5. Add tests in `tests/`

## 📞 Support & Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines and customization points.

For bug reports and feature requests: Open an issue in the repository.

---

**Version:** 1.0.0  
**Status:** Production Ready ✅  
**Last Updated:** June 2026  
**License:** MIT
