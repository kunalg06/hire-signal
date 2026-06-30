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

2. Wait 10-15 seconds for Claude to generate the challenge

3. You'll see:
   - Generated title (e.g., "Calculate Factorial of a Number")
   - Description of what students need to build
   - Evaluation criteria for grading
   - Starter code in Python

### Save as Assignment

1. Click `Save as Assignment` button
2. Copy the assignment ID (shows in alert)
3. Assignment appears in "Saved Challenges" list

### Generate Student Link

1. Click on the assignment in "Saved Challenges"
2. Assignment ID auto-fills
3. Click `Generate Link`
4. You'll get:
   - Student URL to share
   - Port number for code-server
   - Expiration time

### View Results

1. In "View Submissions & Results":
   - Enter the link ID from above
   - Click `View`
   - See evaluation results (after student submits)

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
| **AI Challenge Generation** | Claude generates challenges from problem statements | Left panel of dashboard |
| **Assignment Management** | Create, list, view assignments | Dashboard |
| **Student Links** | Generate unique access links for students | Right panel |
| **Code Evaluation** | Claude evaluates submitted code | After student submits |
| **Session Logging** | Track student's Claude CLI interactions | Submission results |
| **Multi-Dimensional Scoring** | Score based on code quality + approach + efficiency | Result feedback |
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
echo $ANTHROPIC_API_KEY

# If not set, export it (temporary)
export ANTHROPIC_API_KEY="sk-ant-..."
python run.py
```

### Database Already Exists
```bash
# Delete old database (will be recreated)
rm data/assignments.db
python run.py
```

## Important Notes

- **Challenge Generation** takes 8-15 seconds (Claude is thinking!)
- **Student Links** require Docker running for full features
- **Development Mode** has debug enabled - turn off in production
- **No Authentication** currently - add before production use
- **SQLite Database** - suitable for development, use PostgreSQL for production

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Start the Flask application |
| `requirements.txt` | Python dependencies |
| `.env` | Configuration (API key, etc.) |
| `templates/frontend.html` | Teacher dashboard UI |
| `app/` | Flask application code |
| `docs/API_REFERENCE.md` | Complete API documentation |

## Next Steps

1. ✓ **Start the app** - `python run.py`
2. ✓ **Test UI** - Generate challenges and assignments
3. ⚠ **Set up Docker** (optional) - For full student container features
4. 📖 **Read CLAUDE.md** - Development customization guide
5. 🔒 **Add authentication** - Before production use
6. 🔐 **Configure HTTPS** - Before production use

## Getting Help

- **README.md** - Full feature overview
- **SYSTEM_STATUS.md** - Detailed system documentation
- **SESSION_SUMMARY.md** - Recent changes and fixes
- **docs/API_REFERENCE.md** - API endpoint documentation
- **docs/ARCHITECTURE.md** - System design and data flows
- **CLAUDE.md** - Development guide

## Support

For issues or questions:
1. Check SYSTEM_STATUS.md for known issues
2. Review API_REFERENCE.md for endpoint details
3. See CLAUDE.md for customization options

---

**The system is ready to use!**  
Start with: `python run.py`
