# Claude Assignment Platform - Final Folder Structure

**Last Updated**: June 17, 2026  
**Status**: ✅ Production Ready - All services operational

---

## 📁 Directory Tree

```
coding_platforms/
│
├── 🔧 CORE APPLICATION FILES
│   ├── main.py                    # FastAPI backend (66KB) - All endpoints
│   ├── requirements.txt           # Python dependencies
│   ├── frontend.html              # Teacher dashboard (35KB)
│   ├── client.py                  # Python SDK for programmatic access
│   └── README.md                  # Project overview & quick start
│
├── 🐳 DOCKER CONFIGURATION
│   ├── docker-compose.yml         # Service orchestration
│   ├── Dockerfile                 # Student container (code-server)
│   ├── Dockerfile.backend         # Backend service
│   └── Dockerfile.codeserver      # Code-server configuration
│
├── 📋 PROJECT DOCUMENTATION
│   ├── CLAUDE.md                  # Development guide & project instructions
│   └── FOLDER_STRUCTURE.md        # This file - folder organization
│
├── ⚙️ CONFIGURATION
│   ├── .env                       # Environment variables (API key, DB password)
│   ├── .env.example               # Environment template
│   ├── .gitignore                 # Git exclusions
│   └── quickstart.sh              # Automated setup script
│
├── 💾 DATA
│   └── assignments.db             # SQLite database (auto-created)
│
├── 📚 DOCUMENTATION & PLANNING (BMAD)
│   ├── _bmad/                     # BMad configuration files
│   │   ├── config.toml
│   │   ├── config.user.toml
│   │   ├── _config/
│   │   ├── bmm/
│   │   ├── core/
│   │   ├── custom/
│   │   ├── scripts/
│   │   └── tea/
│   │
│   └── _bmad-output/              # BMad project artifacts
│       ├── implementation-artifacts/
│       │   └── spec-ai-challenge-generation.md
│       ├── planning-artifacts/
│       └── test-artifacts/
│
├── 🔗 VCS & CI/CD
│   ├── .git/                      # Git repository
│   ├── .github/
│   │   ├── agents/
│   │   └── workflows/             # GitHub Actions CI/CD
│   │
│   └── .claude/                   # Claude Code settings
│       └── skills/
│
└── 📦 RUNNING SERVICES
    ├── Backend API                (Port 8000)
    ├── PostgreSQL Database        (Port 5432, internal)
    ├── Redis Cache                (Port 6379, internal)
    └── Docker Socket Proxy        (Port 2375, internal)
```

---

## 📊 File Summary

### Essential Application Files
| File | Size | Purpose |
|------|------|---------|
| `main.py` | 66KB | FastAPI backend with all API endpoints |
| `frontend.html` | 35KB | Teacher dashboard UI |
| `client.py` | 11KB | Python SDK for API access |
| `requirements.txt` | 212B | Python dependencies |
| `README.md` | 13KB | Quick start guide |

### Docker Files
| File | Purpose |
|------|---------|
| `docker-compose.yml` | Orchestrates all services (backend, postgres, redis, docker-proxy) |
| `Dockerfile` | Student container image (code-server + Python tools) |
| `Dockerfile.backend` | Backend service image |
| `Dockerfile.codeserver` | Code-server configuration |

### Configuration
| File | Purpose |
|------|---------|
| `.env` | Runtime variables (ANTHROPIC_API_KEY, DB_PASSWORD) |
| `.env.example` | Template for .env file |
| `CLAUDE.md` | Project instructions & development guide |

### Data Storage
| File | Purpose |
|------|---------|
| `assignments.db` | SQLite database (auto-initialized on first run) |

---

## 🚀 Quick Start Commands

```bash
# Navigate to project
cd E:\project2025\coding_platforms

# Start all services
docker-compose up --build

# View logs
docker-compose logs -f backend

# Test API
curl http://localhost:8000/health

# Access dashboard
# Open frontend.html in browser
# or visit http://localhost:8000/docs (API docs)

# Stop services
docker-compose down

# Full cleanup (removes volumes)
docker-compose down -v
```

---

## 📋 Database Schema

Automatically created on startup with 3 tables:

```sql
assignments:
  - id (UUID PRIMARY KEY)
  - title (TEXT)
  - description (TEXT)
  - starter_code (TEXT)
  - evaluation_criteria (TEXT)

session_links:
  - link_id (TEXT PRIMARY KEY)
  - assignment_id (TEXT FOREIGN KEY)
  - container_id (TEXT)
  - vscode_port (INT)
  - expires_at (TIMESTAMP)

submissions:
  - submission_id (TEXT PRIMARY KEY)
  - link_id (TEXT FOREIGN KEY)
  - assignment_id (TEXT)
  - code (TEXT)
  - submitted_at (TIMESTAMP)
  - score (FLOAT)
  - feedback (TEXT)
  - evaluation_result (JSON)
```

---

## 🔄 End-to-End Flow

1. **Teacher Creates Assignment** → `/api/assignments` POST
   - Stores in `assignments` table
   
2. **Generate Student Link** → `/api/generate-link/{assignment_id}` POST
   - Creates Docker container
   - Allocates port (6000-7000 range)
   - Stores in `session_links` table
   
3. **Student Codes** → Browser at `http://localhost:{port}`
   - code-server running in Docker container
   - Full development environment available
   
4. **Submit Code** → `/api/submit/{link_id}` POST
   - Stores submission in database
   - Calls Claude API for evaluation
   - Stores results in `submissions` table
   
5. **View Results** → `/api/submission/{submission_id}` GET
   - Returns full evaluation with score, feedback, details

---

## 🔐 Security Checklist

- ✅ API key stored in .env (not hardcoded)
- ✅ Database password in .env
- ✅ CORS enabled for development
- ✅ Input validation via Pydantic
- ✅ Containers isolated per student
- ⚠️ Production: Add authentication, HTTPS, rate limiting

---

## 📦 Dependencies

### Backend (Python)
- fastapi==0.104.1
- uvicorn==0.24.0
- anthropic==0.28.0
- docker==7.0.0
- sqlalchemy==2.0.23
- psycopg2-binary==2.9.9
- redis==5.0.1
- pydantic==2.5.0
- python-dotenv==1.0.0
- httpx==0.26.0

### Services (Docker)
- postgres:15-alpine
- redis:7-alpine
- code-server:latest (custom image)

---

## 🛠️ Development Notes

- **Backend**: Python 3.11 + FastAPI
- **Frontend**: Pure HTML/CSS/JavaScript (no build step needed)
- **Database**: SQLite (dev) or PostgreSQL (production)
- **Container Management**: Docker SDK for Python
- **Code Evaluation**: Anthropic Claude API
- **Student Environment**: code-server (VS Code in browser)

---

## 📞 Troubleshooting

### Port Already in Use
```bash
# Find process on port 8000
lsof -i :8000
# Kill it or use different port
```

### Container Won't Start
```bash
# Check logs
docker-compose logs backend

# Rebuild without cache
docker-compose build --no-cache
```

### API Key Invalid
```bash
# Verify API key in .env
echo $ANTHROPIC_API_KEY

# Get new key: https://console.anthropic.com
```

### Database Connection Issues
```bash
# Check PostgreSQL
docker-compose logs postgres

# Verify connection
docker-compose exec postgres psql -U claude_user -d assignments -c "SELECT 1"
```

---

## 🔗 API Endpoints Reference

```
POST   /api/assignments                # Create assignment
GET    /api/assignments/{id}           # Get assignment details
POST   /api/generate-link/{id}         # Generate student link
POST   /api/submit/{link_id}           # Submit code for evaluation
GET    /api/submission/{submission_id} # Get evaluation results
GET    /health                         # Health check
```

---

**Version**: 1.0.0  
**Status**: Production Ready ✅
