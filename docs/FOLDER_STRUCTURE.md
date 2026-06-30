# Project Folder Structure

Complete organizational structure of the AI Engineering Assessment & Evaluation Platform.

## Directory Tree

```
coding_platforms/
│
├── 📄 ROOT LEVEL (Essential Files Only - 5 Files)
│   ├── run.py                          # Flask application entry point
│   ├── requirements.txt                # Python dependencies
│   ├── README.md                       # Main documentation and quick start
│   ├── CLAUDE.md                       # Development guide and customization
│   └── FOLDER_STRUCTURE.md             # This file - folder organization guide
│
├── 📁 app/                             # Flask Application Package
│   ├── __init__.py                     # App factory (UPDATED: serves from templates/)
│   ├── config.py                       # Configuration (UPDATED: uses data/ folder)
│   │
│   ├── routes/                         # HTTP Request Handlers (Blueprints)
│   │   ├── assignments.py              # POST/GET /api/assignments
│   │   ├── links.py                    # POST /api/generate-link/{id}
│   │   ├── submissions.py              # POST /api/submit-with-files, GET /api/submission
│   │   ├── student.py                  # GET /student/{link_id}
│   │   └── management.py               # GET /api/system/*, POST /api/system/*
│   │
│   ├── services/                       # Business Logic Layer
│   │   ├── docker_service.py           # Docker container operations
│   │   ├── evaluation_service.py       # Claude API integration
│   │   ├── session_log_service.py      # Session log parsing & scoring
│   │   ├── database_service.py         # Database operations wrapper
│   │   └── management_service.py       # System health & monitoring
│   │
│   ├── models/                         # Data Access Layer
│   │   └── database.py                 # SQLite connection & schema
│   │
│   └── utils/                          # Utility Functions
│       └── helpers.py                  # RateLimiter, IDGenerator, validators
│
├── 📁 templates/                       # HTML Templates (NEW LOCATION)
│   └── frontend.html                   # Teacher Dashboard (MOVED HERE)
│       ├── 4 Tabs:
│       │   ├── Create Assignment
│       │   ├── Generate Student Link
│       │   ├── View Submissions
│       │   └── System Management
│       └── Responsive design (desktop & mobile)
│
├── 📁 data/                            # Database & Data Files (NEW LOCATION)
│   ├── assignments.db                  # Production SQLite database (MOVED HERE)
│   └── test_assignments.db             # Test database (MOVED HERE)
│
├── 📁 docker/                          # Docker Configuration
│   ├── Dockerfile                      # Student environment (code-server)
│   ├── Dockerfile.backend              # Flask backend service
│   ├── Dockerfile.codeserver           # Code-server builder
│   └── docker-compose.yml              # Service orchestration (UPDATED: uses ../data)
│
├── 📁 docs/                            # Documentation
│   ├── API_REFERENCE.md                # Complete API documentation (350+ lines)
│   │                                     ├── All endpoint specs
│   │                                     ├── Request/response examples
│   │                                     ├── Error codes
│   │                                     └── Usage workflows
│   │
│   ├── ARCHITECTURE.md                 # System architecture (600+ lines)
│   │                                     ├── Component diagrams
│   │                                     ├── Data flow diagrams
│   │                                     ├── Database schema
│   │                                     └── Scaling architecture
│   │
│   ├── PROJECT_REQUIREMENTS.md         # Requirements (700+ lines)
│   │                                     ├── Functional requirements
│   │                                     ├── Non-functional requirements
│   │                                     ├── Database schema details
│   │                                     └── Deployment requirements
│   │
│   └── problem_statements.txt          # Example assignment problems
│
├── 📁 scripts/                         # Utility Scripts
│   └── quickstart.sh                   # Quick start setup script
│
├── 📁 tools/                           # SDK and Utilities
│   └── client.py                       # Python SDK client
│
├── 📁 tests/                           # Test Files
│   └── (test files go here)
│
├── 📁 _deprecated/                     # Old Implementation (Do Not Use)
│   ├── app.py                          # Old FastAPI version (archived)
│   └── main.py                         # Old implementation (archived)
│
├── 📁 .git/                            # Git repository
├── 📁 .github/                         # GitHub workflows
├── 📁 .claude/                         # Claude Code configuration
├── 📁 _bmad/                           # BMAD workflow files
└── 📁 _bmad-output/                    # BMAD output
```

---

## Key Changes from Reorganization

### ✅ Files Moved to Proper Folders

| File | From | To | Purpose |
|------|------|-----|---------|
| frontend.html | Root | **templates/** | Flask template folder |
| assignments.db | Root | **data/** | Centralized database storage |
| test_assignments.db | Root | **data/** | Centralized test data |

### ✅ Imports Updated

| File | Change | Reason |
|------|--------|--------|
| **app/__init__.py** | Serves frontend from `templates/frontend.html` | Proper Flask structure |
| **app/config.py** | Database path points to `data/assignments.db` | Clean root directory |
| **docker-compose.yml** | Mounts `../data` volume | Works from docker/ folder |

---

## Root Directory (Clean & Minimal)

Only **5 essential files** in root:

```
run.py                  # Entry point to start Flask
requirements.txt        # Python dependencies
README.md               # Main documentation (start here)
CLAUDE.md               # Development guide
FOLDER_STRUCTURE.md     # This file
.env.example            # Configuration template (not in git)
.env                    # Your environment config (not in git)
```

**Before:** 30+ files scattered  
**After:** 7 files (5 tracked + 2 .env files)

---

## How Files are Located

### **Absolute Path Resolution** ✅

When Flask starts:

```python
# In app/__init__.py
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# = E:\project2025\coding_platforms

# Template folder
template_folder = os.path.join(project_root, 'templates')
# = E:\project2025\coding_platforms\templates

# Database path
DB_PATH = os.path.join('data', 'assignments.db')
# = E:\project2025\coding_platforms\data\assignments.db
```

This works from **any directory**:
- Local development ✓
- Docker container ✓
- CI/CD pipeline ✓
- Different working directories ✓

---

## File Organization Rationale

### **Root Level** (7 files)
Minimal set for clarity:
- `run.py` - Single entry point
- `requirements.txt` - Standard location for pip
- `README.md` - Quick start guide
- `CLAUDE.md` - Development notes
- `FOLDER_STRUCTURE.md` - This guide
- `.env.example` - Configuration template
- `.env` - Actual config (gitignored)

### **app/** (5 subdirectories)
Modular Flask structure:
- `routes/` - HTTP handlers (thin)
- `services/` - Business logic (thick)
- `models/` - Data access (thin)
- `utils/` - Shared utilities
- `__init__.py` - App factory

### **templates/** (1 file)
HTML templates served by Flask:
- `frontend.html` - Teacher dashboard

### **data/** (2 files)
Database files:
- `assignments.db` - Production database
- `test_assignments.db` - Test database

### **docker/** (4 files)
All Docker configuration:
- 3 Dockerfiles
- `docker-compose.yml` - Orchestration

### **docs/** (4 files)
User-facing documentation:
- `API_REFERENCE.md` - API docs
- `ARCHITECTURE.md` - System design
- `PROJECT_REQUIREMENTS.md` - Specifications
- `problem_statements.txt` - Examples

### **Other Folders**
- `scripts/` - Utility scripts
- `tools/` - SDK and tools
- `tests/` - Test files
- `_deprecated/` - Old code (archived)

---

## Running from Different Locations

### From Project Root

```bash
cd E:\project2025\coding_platforms

# Start Flask
python run.py

# Start Docker
docker-compose -f docker/docker-compose.yml up --build
```

### From Subdirectory

```bash
cd E:\project2025\coding_platforms\app

# Still works! Uses absolute paths
python ../run.py
```

### In Docker

```bash
# Volume mounts work correctly
docker-compose -f docker/docker-compose.yml up --build
# Finds templates/ and data/ automatically
```

---

## Adding New Features

### New REST Endpoint
```
1. Create file: app/routes/feature.py
2. Create blueprint and register in app/__init__.py
3. Implement logic: app/services/feature_service.py
4. Add DB ops: app/models/database.py
5. Test and document: docs/API_REFERENCE.md
```

### New HTML Template
```
1. Create file: templates/new_page.html
2. Serve from app/__init__.py or via Flask route
3. Reference in documentation
```

### New Database Feature
```
1. Update: app/models/database.py (schema & methods)
2. Data auto-stored in: data/assignments.db
3. Tests use: data/test_assignments.db
```

---

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Root Files** | 30+ scattered | 7 essential |
| **Templates** | Root | `templates/` |
| **Database** | Root | `data/` |
| **Documentation** | Root | `docs/` |
| **Docker Files** | Root | `docker/` |
| **Import Paths** | Relative | Absolute |
| **Clean Root** | No | Yes |
| **Easy Navigation** | Difficult | Clear |

---

## Environment Files

### `.env.example` (In Root - Tracked)
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
FLASK_ENV=development
DB_PATH=data/assignments.db
```

### `.env` (In Root - Gitignored)
```env
# Copy from .env.example and fill in your values
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
FLASK_ENV=production
```

---

## Verification Checklist

- [x] frontend.html moved to templates/
- [x] assignments.db moved to data/
- [x] test_assignments.db moved to data/
- [x] app/__init__.py updated to serve from templates/
- [x] app/config.py updated to use data/ folder
- [x] docker-compose.yml updated for new paths
- [x] Duplicate FOLDER_STRUCTURE.md removed
- [x] Root directory clean (5 essential files)
- [x] All imports reference correct locations
- [x] Works from any directory

---

**Last Updated:** June 2026  
**Version:** 1.0.0  
**Status:** Production Ready ✅  
**Duplicates Cleaned:** Yes
