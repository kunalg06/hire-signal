# Quick Start Guide

## Start the Application (30 seconds)

```bash
# 1. Navigate to project directory
cd E:\project2025\coding_platforms

# 2. Run the Flask application
python run.py
```

You should see:
```
============================================================
AI Engineering Assessment & Evaluation Platform
============================================================
Environment: development
Starting Flask server on http://0.0.0.0:8000
 * Running on http://127.0.0.1:8000
```

## Access the Platform

Open your browser and go to: **http://localhost:8000**

## Test the System (3 minutes)

### Generate a Challenge with AI

1. In the "Generate Challenge with AI" section:
   - **Problem Statement:** `Create a function to calculate the factorial of a number`
   - **Difficulty:** Select `easy`
   - Click `Generate with AI`

2. Wait 10-15 seconds for Gemini to generate the challenge

3. You'll see:
   - Generated title (e.g., "Calculate Factorial of a Number")
   - Description of what candidates need to build
   - Evaluation criteria for grading
   - Starter code in Python

### Save as Assignment

1. Click `Save as Assignment` button
2. Copy the assignment ID (shows in alert)
3. Assignment appears in "Saved Challenges" list

### Generate Candidate Link

1. Click on the assignment in "Saved Challenges"
2. Assignment ID auto-fills
3. Click `Generate Link`
4. You'll get:
   - Candidate URL to share
   - Port number for code-server (7100-7900 range)
   - Expiration time

### View Results

1. In "View Submissions & Results":
   - Enter the link ID from above
   - Click `View`
   - See evaluation results (after the candidate submits)

## API Testing

### Test Health Check
```bash
curl http://localhost:8000/api/system/health
```

### Generate Challenge via API
```bash
curl -X POST http://localhost:8000/api/generate-challenge \
  -H "Content-Type: application/json" \
  -d '{
    "problem_statement": "Write a function to check if a string is a palindrome",
    "difficulty": "easy"
  }'
```

### Create Assignment via API
```bash
curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Palindrome Checker",
    "description": "Create a function that checks if a string is a palindrome",
    "evaluation_criteria": "Must handle both uppercase and lowercase, and ignore spaces",
    "starter_code": "def is_palindrome(s):\n    pass"
  }'
```

### List All Assignments
```bash
curl http://localhost:8000/api/assignments
```

## Features Overview

| Feature | Description | Where to Test |
|---------|-------------|-------|
| **AI Challenge Generation** | Gemini generates challenges from problem statements | Left panel of dashboard |
| **Assignment Management** | Create, list, view assignments | Dashboard |
| **Candidate Links** | Generate unique access links for candidates | Right panel |
| **Code Evaluation** | Gemini scores the submission across 8 AI-collaboration dimensions | After candidate submits |
| **Session Logging** | Track the candidate's Gemini CLI interactions | Submission results |
| **8-Dimension Scoring** | Problem decomposition, first-principles thinking, iteration quality, debugging with AI, and 4 more — see `docs/PROJECT_REQUIREMENTS.md` | Result feedback |
| **System Management** | Monitor health, manage containers | API endpoints |

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 8000
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
PORT=8001 python run.py
```

### API Key Error
```bash
# Verify API key is set
echo $GEMINI_API_KEY

# If not set, export it (temporary)
export GEMINI_API_KEY="..."
python run.py
```

### Database Already Exists
```bash
# Delete old database (will be recreated)
rm data/assignments.db
python run.py
```

## Important Notes

- **Challenge Generation** takes 8-15 seconds (Gemini is thinking!)
- **Candidate Links** work without Docker too — they still generate instantly, just without a live code-server container (graceful degradation, not a hard requirement)
- **Development Mode** has debug enabled - turn off in production
- **No Authentication** currently - add before production use
- **SQLite Database only** - no Postgres/Redis wiring exists in this codebase despite some legacy references in `docker-compose.yml`/`requirements.txt`

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Start the Flask application |
| `requirements.txt` | Python dependencies |
| `.env` | Configuration (API key, etc.) |
| `templates/frontend.html` | Employer dashboard UI |
| `app/` | Flask application code |
| `docs/API_REFERENCE.md` | Complete API documentation |

## Next Steps

1. ✓ **Start the app** - `python run.py`
2. ✓ **Test UI** - Generate challenges and assignments
3. ⚠ **Set up Docker** (optional) - For full candidate container features
4. 📖 **Read CLAUDE.md** - Development customization guide
5. 🔒 **Add authentication** - Before production use
6. 🔐 **Configure HTTPS** - Before production use

## Getting Help

- **README.md** - Full feature overview
- **AGENT.md** - Current implementation state and known deferred issues
- **docs/API_REFERENCE.md** - API endpoint documentation
- **docs/ARCHITECTURE.md** - System design and data flows
- **CLAUDE.md** - Development guide

## Support

For issues or questions:
1. Check `_bmad-output/implementation-artifacts/deferred-work.md` for known issues
2. Review `docs/API_REFERENCE.md` for endpoint details
3. See `CLAUDE.md` for customization options

---

**The system is ready to use!**  
Start with: `python run.py`
