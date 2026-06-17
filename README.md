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
- **REST API** - Full API for programmatic access

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API Key

### Installation

```bash
git clone <repo>
cd coding_platforms
cp .env.example .env
# Edit .env with ANTHROPIC_API_KEY
docker-compose up --build
```

Access at: http://localhost:8000

## 📊 Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture diagrams and flows.

## 📖 Documentation

- [PROJECT_REQUIREMENTS.md](PROJECT_REQUIREMENTS.md) - Complete requirements specification
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and data flows
- [CLAUDE.md](CLAUDE.md) - Development guide

## 💻 Usage

### Create Assignment
```bash
curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Temperature Converter",
    "description": "Convert Celsius to Fahrenheit",
    "evaluation_criteria": "Function works correctly",
    "starter_code": "def celsius_to_fahrenheit(c):\n    pass"
  }'
```

### Generate Student Link
```bash
curl -X POST http://localhost:8000/api/generate-link/{assignment_id}
```

### Get Evaluation Results
```bash
curl http://localhost:8000/api/submission/{submission_id}
```

## 📁 Project Structure

```
app/
├── routes/          # API endpoints
├── services/        # Business logic
├── models/          # Database models
└── utils/           # Helper utilities

run.py              # Application entry point
requirements.txt    # Dependencies
```

## 🔧 Configuration

Environment variables in `.env`:
- `ANTHROPIC_API_KEY` - Claude API key
- `FLASK_ENV` - Environment (development/production)
- `DB_PATH` - SQLite database location

## 🧪 Testing

```bash
pytest
```

## 📈 Scoring System

Final Score = (Code Quality × 0.4) + (Approach × 0.3) + (Efficiency × 0.3)

- **Code Quality (40%)** - Claude evaluation of correctness, style, completeness
- **Approach (30%)** - Analysis of problem-solving from Claude CLI interactions
- **Efficiency (30%)** - Time spent relative to 2-hour budget

## 🔒 Security Features

- Docker isolation per student
- Input validation on all endpoints
- API keys from environment variables
- No hardcoded secrets

## 📞 Support

See documentation files for detailed information.

---

**Version:** 1.0.0 | **Status:** Production Ready ✅
