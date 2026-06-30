# API Reference

Complete documentation of all REST API endpoints for the AI Engineering Assessment & Evaluation Platform.

---

## 📋 Table of Contents

1. [Assignments](#assignments)
2. [Student Links](#student-links)
3. [Submissions](#submissions)
4. [Session Logs](#session-logs)
5. [Student Portal](#student-portal)
6. [System Management](#system-management)

---

## Assignments

### Create Assignment

**POST** `/api/assignments`

Create a new coding assignment for students.

**Request:**
```json
{
  "title": "Temperature Converter",
  "description": "Write a function to convert Celsius to Fahrenheit",
  "evaluation_criteria": "Function should correctly convert temperature values",
  "starter_code": "def celsius_to_fahrenheit(celsius):\n    pass"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid-string",
  "title": "Temperature Converter",
  "description": "Write a function to convert Celsius to Fahrenheit",
  "evaluation_criteria": "Function should correctly convert temperature values",
  "starter_code": "def celsius_to_fahrenheit(celsius):\n    pass",
  "created_at": "2026-06-17T10:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Missing required fields (title, evaluation_criteria)
- `500 Internal Server Error` - Database error

---

### Get Assignment

**GET** `/api/assignments/{assignment_id}`

Retrieve details of a specific assignment.

**Response:** `200 OK`
```json
{
  "id": "uuid-string",
  "title": "Temperature Converter",
  "description": "Write a function to convert Celsius to Fahrenheit",
  "evaluation_criteria": "Function should correctly convert temperature values",
  "starter_code": "def celsius_to_fahrenheit(celsius):\n    pass",
  "created_at": "2026-06-17T10:30:00Z"
}
```

**Error Responses:**
- `404 Not Found` - Assignment does not exist
- `500 Internal Server Error` - Database error

---

## Student Links

### Generate Student Link

**POST** `/api/generate-link/{assignment_id}`

Generate a unique access link for a student to work on an assignment. Creates an isolated Docker container.

**Parameters:**
- `assignment_id` (path) - UUID of the assignment

**Response:** `201 Created`
```json
{
  "link_id": "random-string-key",
  "assignment_id": "uuid-string",
  "access_url": "http://localhost:8000/student/random-string-key",
  "code_server_url": "http://localhost:6000",
  "port": 6000,
  "expires_at": "2026-06-18T10:30:00Z",
  "container_id": "docker-container-id"
}
```

**Error Responses:**
- `404 Not Found` - Assignment does not exist
- `500 Internal Server Error` - Docker or database error
- `503 Service Unavailable` - No available ports (max 1000 containers)

---

## Submissions

### Submit Code for Evaluation

**POST** `/api/submit-with-files/{link_id}`

Submit code for evaluation. Collects files from the student's container and starts background evaluation.

**Parameters:**
- `link_id` (path) - Student access link ID

**Request Body:** `{}` (empty JSON object)

**Response:** `202 Accepted`
```json
{
  "submission_id": "uuid-string",
  "status": "submitted",
  "message": "Evaluation in progress...",
  "session_logs_count": 3
}
```

**Error Responses:**
- `404 Not Found` - Link does not exist
- `400 Bad Request` - Link expired
- `500 Internal Server Error` - Container or database error

**Background Processing:**
- Extracts files from container (solution.py, instructions.md, session.log)
- Parses Claude CLI session logs
- Sends code to Claude API for evaluation
- Calculates scores: code quality (40%) + approach (30%) + efficiency (30%)
- Updates submission with results (5-10 seconds)

---

### Get Submission Results

**GET** `/api/submission/{submission_id}`

Retrieve evaluation results for a submitted assignment.

**Parameters:**
- `submission_id` (path) - UUID of the submission

**Response:** `200 OK`
```json
{
  "submission_id": "uuid-string",
  "link_id": "link-key",
  "assignment_id": "uuid-string",
  "assignment_title": "Temperature Converter",
  "submitted_at": "2026-06-17T10:45:00Z",
  "evaluated_at": "2026-06-17T10:47:00Z",
  "score": 82.5,
  "feedback": "Good solution with clear logic...\n\n---SCORING BREAKDOWN---\nCode Quality: 85/100\nApproach: 75/30\nEfficiency: 25/30\nFinal Score: 82.5/100",
  "evaluation_result": {
    "code_quality_score": 85,
    "approach_score": 25,
    "efficiency_score": 25,
    "combined_score": 82.5,
    "claude_feedback": "..."
  },
  "instructions_md": "...",
  "claude_logs": "..."
}
```

**Pending Evaluation Response:** `200 OK`
```json
{
  "submission_id": "uuid-string",
  "status": "pending",
  "message": "Evaluation in progress..."
}
```

**Error Responses:**
- `404 Not Found` - Submission does not exist
- `500 Internal Server Error` - Database error

---

## Session Logs

### Get Session Logs

**GET** `/api/session-logs/{submission_id}`

Retrieve all Claude CLI session logs for a submission (showing student's problem-solving process).

**Parameters:**
- `submission_id` (path) - UUID of the submission

**Response:** `200 OK`
```json
[
  {
    "log_id": "uuid-string",
    "submission_id": "uuid-string",
    "timestamp": "2026-06-17T10:40:00Z",
    "interaction_type": "claude_evaluate",
    "prompt": "Evaluate this solution: def celsius_to_fahrenheit...",
    "response_summary": "Code quality: Good, handles edge cases",
    "file_changes_count": 2
  },
  {
    "log_id": "uuid-string",
    "submission_id": "uuid-string",
    "timestamp": "2026-06-17T10:42:00Z",
    "interaction_type": "claude_evaluate",
    "prompt": "Fix the conversion formula",
    "response_summary": "Use formula: (C * 9/5) + 32",
    "file_changes_count": 1
  }
]
```

**Error Responses:**
- `404 Not Found` - Submission does not exist
- `500 Internal Server Error` - Database error

---

## Student Portal

### Get Student Dashboard

**GET** `/student/{link_id}`

Access the student portal with embedded code-server IDE and assignment details.

**Parameters:**
- `link_id` (path) - Student access link ID

**Response:** `200 OK` (HTML page with):
- Assignment details (title, description, evaluation criteria, starter code)
- Embedded code-server iframe at port specified
- Submit button to collect code
- Results panel (hidden until submission)
- Session timer countdown

**Error Responses:**
- `404 Not Found` - Link does not exist
- `400 Bad Request` - Link expired
- `500 Internal Server Error` - Database error

---

## System Management

All Docker and system operations integrated into Flask API. No need for separate docker commands.

### Get System Status

**GET** `/api/system/status`

Get current system health status including Docker daemon and running containers.

**Response:** `200 OK`
```json
{
  "timestamp": "2026-06-17T10:50:00Z",
  "status": "healthy",
  "services": {
    "docker": "running"
  },
  "containers": {
    "total_running": 3,
    "assignment_containers": 3,
    "containers": [
      {
        "id": "abc123def456",
        "name": "assignment-uuid-1",
        "status": "running",
        "ports": {
          "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "6000"}]
        }
      }
    ]
  },
  "errors": []
}
```

**Error Responses:**
- `200 OK` with error array - Docker daemon error (still returns status)

---

### Health Check

**GET** `/api/system/health`

Comprehensive health check of all system components (Docker, database, Anthropic API).

**Response:** `200 OK`
```json
{
  "timestamp": "2026-06-17T10:50:00Z",
  "overall": "healthy",
  "components": {
    "docker": "healthy",
    "database": "healthy",
    "anthropic_api": "ready"
  }
}
```

**Component Status Values:**
- `"healthy"` - Component is working correctly
- `"unhealthy: {error}"` - Component has error
- `"ready"` - Component initialized and ready
- `"error: {error}"` - Component initialization failed

---

### Clean Up Old Containers

**POST** `/api/system/cleanup-old?hours=24`

Remove containers older than specified hours. Default: 24 hours.

**Query Parameters:**
- `hours` (optional) - Age threshold in hours (default: 24)

**Response:** `200 OK`
```json
{
  "cleaned": 2,
  "failed": 0,
  "errors": []
}
```

**Error Responses:**
- `200 OK` with errors array - Docker error (still returns cleanup count)

---

### Clean Up All Containers

**POST** `/api/system/cleanup-all`

Force remove all assignment containers immediately (use with caution).

**Response:** `200 OK`
```json
{
  "removed": 5,
  "failed": 0,
  "errors": []
}
```

**Error Responses:**
- `200 OK` with errors array - Docker error (still returns removal count)

---

### Get Container Info

**GET** `/api/system/containers/{container_id}/info`

Get detailed information about a specific container.

**Parameters:**
- `container_id` (path) - Docker container ID (full or short form)

**Response:** `200 OK`
```json
{
  "id": "abc123def456",
  "name": "assignment-uuid-1",
  "status": "running",
  "created": "2026-06-17T10:30:00Z",
  "ports": {
    "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "6000"}]
  },
  "image": "code-server-http:latest",
  "memory_stats": {
    "usage": 128000000,
    "max_usage": 256000000,
    "limit": 1073741824
  }
}
```

**Error Responses:**
- `404 Not Found` - Container does not exist
- `400 Bad Request` - Docker error

---

### Get Container Logs

**GET** `/api/system/containers/{container_id}/logs?lines=100`

Retrieve logs from a specific container.

**Parameters:**
- `container_id` (path) - Docker container ID
- `lines` (query, optional) - Number of log lines to return (default: 100)

**Response:** `200 OK`
```json
{
  "logs": "stdout/stderr output from container...\n..."
}
```

---

### Restart Container

**POST** `/api/system/containers/{container_id}/restart`

Restart a specific running container.

**Parameters:**
- `container_id` (path) - Docker container ID

**Response:** `200 OK`
```json
{
  "success": true,
  "container_id": "abc123def456",
  "status": "restarted"
}
```

**Error Responses:**
- `400 Bad Request` - Container restart failed
- `404 Not Found` - Container does not exist

---

### Stop Container

**POST** `/api/system/containers/{container_id}/stop`

Stop a running container.

**Parameters:**
- `container_id` (path) - Docker container ID

**Response:** `200 OK`
```json
{
  "success": true,
  "container_id": "abc123def456",
  "status": "stopped"
}
```

**Error Responses:**
- `400 Bad Request` - Container stop failed
- `404 Not Found` - Container does not exist

---

## Global Error Responses

All endpoints may return these errors:

### 400 Bad Request
Invalid request parameters or validation failure
```json
{
  "error": "Invalid parameter: {detail}"
}
```

### 401 Unauthorized
Authentication failed (future feature)
```json
{
  "error": "Unauthorized"
}
```

### 404 Not Found
Resource does not exist
```json
{
  "error": "Resource not found"
}
```

### 500 Internal Server Error
Server-side error
```json
{
  "error": "Internal server error: {detail}"
}
```

### 503 Service Unavailable
Service temporarily unavailable (e.g., Docker unreachable)
```json
{
  "error": "Service unavailable: {detail}"
}
```

---

## Rate Limiting

Rate limiting is applied to prevent abuse:
- **Limit:** 5 requests per 60 seconds per client IP
- **Headers:** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

---

## Authentication

Currently, no authentication is required (development mode). For production:
- Implement JWT token-based authentication
- Validate tokens on all protected endpoints
- Use HTTPS for all API calls

---

## Example Workflows

### Complete Student Submission Workflow

```bash
# 1. Create assignment
ASSIGNMENT_ID=$(curl -s -X POST http://localhost:8000/api/assignments \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","description":"Test","evaluation_criteria":"Works"}' \
  | jq -r '.id')

# 2. Generate student link
LINK=$(curl -s -X POST http://localhost:8000/api/generate-link/$ASSIGNMENT_ID)
LINK_ID=$(echo $LINK | jq -r '.link_id')
PORT=$(echo $LINK | jq -r '.port')

# 3. Student accesses portal
open http://localhost:8000/student/$LINK_ID

# 4. Student submits code
SUBMISSION=$(curl -s -X POST http://localhost:8000/api/submit-with-files/$LINK_ID \
  -H "Content-Type: application/json" \
  -d '{}')
SUBMISSION_ID=$(echo $SUBMISSION | jq -r '.submission_id')

# 5. Poll for results (wait 5-10 seconds)
curl http://localhost:8000/api/submission/$SUBMISSION_ID

# 6. View session logs
curl http://localhost:8000/api/session-logs/$SUBMISSION_ID
```

### System Management Workflow

```bash
# Check system health
curl http://localhost:8000/api/system/health

# Get running containers
curl http://localhost:8000/api/system/status

# View specific container logs
curl http://localhost:8000/api/system/containers/{id}/logs

# Clean up old containers
curl -X POST http://localhost:8000/api/system/cleanup-old?hours=24

# Stop a problematic container
curl -X POST http://localhost:8000/api/system/containers/{id}/stop
```

---

**Last Updated:** June 2026  
**API Version:** 1.0.0
