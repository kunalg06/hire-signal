# Claude Assignment Platform 🚀

A fully integrated educational platform where students access web-based VS Code environments to solve coding assignments, and Claude AI automatically evaluates their submissions.

## Features

✅ **Assignment Management** - Create coding assignments with starter code and evaluation criteria  
✅ **Unique Access Links** - Generate one-time links that spin up isolated Docker environments  
✅ **Web-Based VS Code** - Students code in a browser-based VS Code (code-server)  
✅ **Claude CLI Integration** - Use Claude from the terminal to get hints and help  
✅ **Automatic Evaluation** - Claude evaluates code quality, correctness, and efficiency  
✅ **Persistent Submissions** - Track all submissions and evaluation results  
✅ **Scalable Architecture** - Docker containers for each student session  

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Teacher Dashboard                         │
│  (HTML + JavaScript Frontend)                               │
├─────────────────────────────────────────────────────────────┤
│ 1. Create Assignment                                         │
│ 2. Generate Student Links                                    │
│ 3. View Submission Results                                   │
└────────────────┬────────────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │   FastAPI Backend  │
        │   (Python 3.11)    │
        ├──────────────────┤
        │ REST API:        │
        │ /assignments     │
        │ /generate-link   │
        │ /submit          │
        │ /submission      │
        └────────┬─────────┘
        ┌────────▼──────────────────────┐
        │   Docker Container (Per Link)  │
        │ ┌──────────────────────────┐  │
        │ │   VS Code (code-server)  │  │
        │ │  - Python environment    │  │
        │ │  - Claude CLI ready      │  │
        │ │  - Starter code loaded   │  │
        │ └──────────────────────────┘  │
        └────────┬──────────────────────┘
                 │
        ┌────────▼────────────┐
        │   Claude API        │
        │   (Evaluation)      │
        └─────────────────────┘
```

---

## Prerequisites

- Docker & Docker Compose
- Python 3.8+
- Anthropic API Key (get from https://console.anthropic.com)
- Git

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone <repo-url>
cd claude-assignment-platform
```

### 2. Set Environment Variables
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export DB_PASSWORD="secure_password_here"
```

Or create a `.env` file:
```bash
ANTHROPIC_API_KEY=sk-ant-...
DB_PASSWORD=secure_password_here
```

### 3. Build and Start Services
```bash
docker-compose up --build
```

This starts:
- **Backend API**: http://localhost:8000
- **Frontend Dashboard**: Open `frontend.html` in your browser
- **PostgreSQL**: localhost:5432 (optional)
- **Redis**: localhost:6379 (optional)

### 4. Verify Services
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok", "service": "Claude Assignment Platform"}
```

---

## Usage Guide

### For Teachers: Create an Assignment

#### Via API (cURL)
```bash
curl -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fibonacci Sequence",
    "description": "Write a function that returns the nth Fibonacci number",
    "starter_code": "def fibonacci(n):\n    pass",
    "evaluation_criteria": "- Must handle base cases (n=0, n=1)\n- Should be efficient\n- Include docstrings"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Fibonacci Sequence",
  "description": "Write a function that returns the nth Fibonacci number",
  "starter_code": "def fibonacci(n):\n    pass",
  "evaluation_criteria": "- Must handle base cases..."
}
```

#### Via Frontend Dashboard
1. Open `frontend.html` in a browser
2. Fill in the assignment form
3. Click "Create Assignment"
4. Copy the Assignment ID

### Generate Student Access Link

#### Via API
```bash
curl -X POST http://localhost:8000/api/generate-link/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "link_id": "ABC123...",
  "assignment_id": "550e8400-e29b-41d4-a716-446655440000",
  "access_url": "http://localhost:6000",
  "vscode_port": 6000,
  "expires_at": "2024-12-31T23:59:59"
}
```

Share the `access_url` with students!

### For Students: Complete Assignment

1. **Access the Environment**
   - Click the link provided by teacher
   - VS Code loads in your browser (no installation needed!)

2. **Code with Claude Help**
   - Open terminal in VS Code (`Ctrl + backtick`)
   - Use Claude CLI:
     ```bash
     export ANTHROPIC_API_KEY="your-key"
     python3 -c "import anthropic; c = anthropic.Anthropic(); m = c.messages.create(model='claude-opus-4-1', max_tokens=1024, messages=[{'role': 'user', 'content': 'Explain how to solve Fibonacci recursion'}]); print(m.content[0].text)"
     ```

3. **View Starter Code**
   - Starter code is in `solution.py`
   - Edit it to write your solution

4. **Submit for Evaluation**
   - Use the dashboard form or API:
     ```bash
     curl -X POST http://localhost:8000/api/submit/ABC123 \
       -H "Content-Type: application/json" \
       -d '{"code": "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)"}'
     ```

### View Evaluation Results

#### Via API
```bash
curl http://localhost:8000/api/submission/submission-id-123
```

**Response:**
```json
{
  "submission_id": "submission-id-123",
  "score": 87.5,
  "feedback": "Good solution! Consider using memoization for efficiency...",
  "evaluation_result": {
    "correctness": "✓ Handles all test cases",
    "code_quality": "Good readability, could optimize",
    "completeness": "✓ Full implementation"
  },
  "submitted_at": "2024-12-20T10:30:00"
}
```

---

## API Reference

### Assignments

#### Create Assignment
```
POST /api/assignments
Content-Type: application/json

{
  "title": "string",
  "description": "string",
  "starter_code": "string (optional)",
  "evaluation_criteria": "string"
}
```

#### Get Assignment
```
GET /api/assignments/{assignment_id}
```

### Links & Sessions

#### Generate Link
```
POST /api/generate-link/{assignment_id}
```

#### Get Session Info
```
GET /api/session/{link_id}
```

### Submissions

#### Submit Code
```
POST /api/submit/{link_id}
Content-Type: application/json

{
  "code": "string"
}
```

#### Get Submission Results
```
GET /api/submission/{submission_id}
```

---

## Docker Environment Details

### What's Inside Each Student Container?

- **VS Code (code-server)** - Browser-based editor
- **Python 3 + pip** - Full Python development
- **Claude Python SDK** - `anthropic` package pre-installed
- **Development Tools** - git, curl, nano, vim
- **Extensions** - Python, Pylance, Copilot
- **Pre-loaded Code** - Starter code in `/workspace/solution.py`

### Using Claude in the Terminal

```bash
# Example: Ask Claude for help
cat > ask_claude.py << 'EOF'
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-opus-4-1",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": "Explain how to implement a binary search algorithm"
        }
    ]
)

print(message.content[0].text)
EOF

# Run it
python3 ask_claude.py
```

---

## Configuration

### Backend Settings
Edit `main.py` to customize:

```python
# Change the Claude model
model="claude-opus-4-1"  # or claude-sonnet-4-20250514

# Adjust port range for VS Code
find_available_port(start_port=6000)  # Starts at port 6000
```

### Docker Settings
Edit `Dockerfile` to add/remove tools:

```dockerfile
# Add more Python packages
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    scikit-learn
```

### Database
Default: SQLite (`assignments.db`)

To use PostgreSQL instead:
1. Uncomment the postgres service in `docker-compose.yml`
2. Update `main.py` connection string
3. Create SQLAlchemy models instead of raw SQL

---

## Troubleshooting

### "Permission Denied" on Docker Socket
```bash
sudo chmod 666 /var/run/docker.sock
# Or run with appropriate permissions
```

### VS Code Container Won't Start
```bash
# Check if port is in use
lsof -i :6000

# Kill the process
kill -9 <PID>

# Or use a different port range
```

### Claude API Key Not Working
```bash
# Verify API key is set
echo $ANTHROPIC_API_KEY

# Test the API directly
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-opus-4-1","max_tokens":100,"messages":[{"role":"user","content":"test"}]}'
```

### Container Cleanup
```bash
# Remove all assignment containers
docker ps -a | grep assignment | awk '{print $1}' | xargs docker rm -f

# Clean up volumes
docker volume prune
```

---

## Scaling Considerations

### For Production

1. **Use PostgreSQL** instead of SQLite
2. **Add Redis caching** for submissions
3. **Container orchestration**: Kubernetes for auto-scaling
4. **Load balancing**: Nginx reverse proxy
5. **Authentication**: Add user/teacher login system
6. **Rate limiting**: Prevent abuse
7. **Monitoring**: Prometheus + Grafana

### Docker Compose Scale Example
```bash
# Create multiple backend instances
docker-compose up --scale backend=3
```

---

## Security Notes

⚠️ **For Production Deployment:**

1. **Enable Authentication**
   - Add JWT tokens
   - Restrict teacher endpoints

2. **Secure VS Code**
   - Enable password protection in code-server
   - Use HTTPS/WSS

3. **API Security**
   - Add rate limiting
   - Validate all inputs
   - Use secrets manager for API keys

4. **Container Isolation**
   - Use resource limits (CPU, memory)
   - Run containers as non-root user
   - Use security scanning tools

5. **Data Privacy**
   - Encrypt submissions at rest
   - Comply with GDPR/FERPA if applicable
   - Regular data backups

---

## Environment Variables Reference

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
DB_PASSWORD=secure_password
DATABASE_URL=sqlite:///./assignments.db
DOCKER_HOST=unix:///var/run/docker.sock
LOG_LEVEL=INFO
PORT=8000
```

---

## Support & Contributing

- **Issues**: Open a GitHub issue
- **Contributing**: Fork and submit a pull request
- **Docs**: See `DOCS.md` for detailed documentation

---

## License

MIT License - see LICENSE file

---

## FAQ

**Q: Can students see each other's code?**  
A: No. Each student gets an isolated container. Code is only stored in our database.

**Q: What happens if a student disconnects?**  
A: The container stays alive for 24 hours. They can reconnect with the same link.

**Q: Can I use this for Python only?**  
A: Currently yes, but you can customize the Dockerfile for other languages.

**Q: How does Claude evaluate code?**  
A: We send the code + evaluation criteria to Claude Opus via the API. Claude uses its judgment to score and provide feedback.

**Q: Is there a limit on submissions?**  
A: No hard limit, but you should implement rate limiting for production.

---

**Happy Teaching! 🎓**

For questions, check the [Anthropic API Docs](https://docs.claude.com) or [code-server Docs](https://coder.com/docs/code-server).
