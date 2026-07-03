# Docker Setup & Troubleshooting Guide

## Current Status

The system **works without Docker** with graceful degradation:
- ✓ Employer dashboard fully functional
- ✓ Assignment creation and management working
- ✓ Candidate links generate successfully
- ✓ Candidate portal page loads
- ⚠ Code-server (embedded IDE) unavailable without Docker

## Understanding Docker in This System

### What Docker Does
- Runs isolated environments for each candidate
- Provides browser-based VS Code (code-server) on unique ports
- Collects files from the candidate's workspace for evaluation
- Provides security isolation between candidates

### What Happens Without Docker

**When Docker is not running:**
1. Link generation completes instantly (no port assignment)
2. Candidate portal shows assignment details
3. Code-server is not available
4. Candidates cannot submit files directly

**The system detects this automatically** and shows users:
```
Link created but Docker unavailable. 
Student portal will load without code editor.
```

## Setting Up Docker

### Option 1: Docker Desktop (Windows/Mac)

**Install:**
1. Download Docker Desktop from https://www.docker.com/products/docker-desktop
2. Run installer and follow prompts
3. Restart computer
4. Start Docker Desktop (icon in taskbar)

**Verify Installation:**
```bash
docker --version
docker ps
```

Should show Docker version and empty container list.

**In the Platform:**
1. Refresh the page
2. Generate a new link - port number will now appear
3. Candidates can access code-server

### Option 2: Docker via WSL2 (Windows)

**Setup:**
1. Enable WSL2 (Windows Subsystem for Linux 2)
2. Install Docker with WSL2 backend
3. Configure Docker Desktop → Settings → WSL Integration

**Check:**
```bash
docker ps
```

### Option 3: Docker via Linux

**Install on Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install docker.io docker-compose

# Start service
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (optional)
sudo usermod -aG docker $USER
```

## Testing Docker Connection

The app checks Docker availability via the `docker` CLI through a subprocess call (`docker info`), **not** the `docker` Python SDK — that SDK is listed in `requirements.txt` but isn't used at runtime because its `requests` dependency conflicts with `requests>=2.32` under Python 3.14 in this environment. Test the same way the app does:

```bash
docker info
docker ps
```

If both succeed, `DockerService.get_client()` will detect Docker as available.

## Common Docker Errors & Solutions

### Error: "Cannot connect to Docker daemon"

**Causes:**
- Docker Desktop not running
- Docker daemon not started on Linux
- Docker socket permissions issue

**Solutions:**
```bash
# Windows/Mac: Start Docker Desktop application

# Linux: Start Docker service
sudo systemctl start docker

# Check status
docker ps
```

### Error: "permission denied while trying to connect to Docker daemon"

**Cause:** User doesn't have Docker permission

**Solution (Linux):**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Apply new group
newgrp docker

# Verify
docker ps
```

### Error: "Not supported URL scheme http+docker"

**Cause:** Invalid Docker connection configuration

**Solution:**
1. Ensure Docker Desktop is running (Windows/Mac)
2. Check environment variables: `echo $DOCKER_HOST`
3. If set, unset it: `unset DOCKER_HOST`
4. Restart the application

## Building Student Containers

### Verify Dockerfile

Check that the candidate-container Dockerfile exists:
```bash
ls -la docker/Dockerfile.codeserver
```

Should show code-server + Claude Code CLI configuration.

### Build Container Image

```bash
cd docker
docker build -f Dockerfile.codeserver -t coding-platform-student .
```

This creates the image that will be used for candidate containers.

### Verify Image Created

```bash
docker images | grep coding-platform-student
```

## Running the System With Docker

### Full Setup
```bash
# 1. Ensure Docker is running (Windows/Mac: open Docker Desktop)

# 2. Build container image
cd docker
docker build -f Dockerfile.codeserver -t coding-platform-student .

# 3. Start Flask app
cd ..
python run.py

# 4. Generate a link - should now assign a port
```

### Verify Container Created
```bash
# In another terminal
docker ps

# Should show running container like:
# CONTAINER ID   IMAGE                        PORTS
# abc123def456   coding-platform-student:latest   7100->8080/tcp
```

### Access Code-Server
```
http://localhost:7100  (or assigned port, always in the 7100-7900 range)
```

## Docker Compose (Not the primary dev path)

`docker/docker-compose.yml` exists but is **not** what the running application actually uses — it orchestrates a PostgreSQL + Redis + separate backend container setup that nothing in the current codebase reads from or writes to (the app is SQLite-only, no Redis anywhere). The live dev workflow is `python run.py` directly, with candidate containers spun up ad hoc via `docker_service.py`'s subprocess calls to the `docker` CLI, not `docker-compose`.

If you want to experiment with it anyway:

```bash
cd docker
docker-compose up --build
```

Services it would start (unused by the app today):
- Flask API: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Production Docker Deployment

### Using Docker in Production

```bash
# Build production image
docker build -f docker/Dockerfile.backend -t coding-platform:prod .

# Run with proper configuration
docker run \
  -e OPENROUTER_API_KEY="sk-or-..." \
  -e FLASK_ENV="production" \
  -p 8000:8000 \
  --volume /var/lib/data:/app/data \
  coding-platform:prod
```

### Using Kubernetes

For scaling to multiple instances, use Kubernetes:

```bash
# Build and push image
docker build -t your-registry/coding-platform:v1 .
docker push your-registry/coding-platform:v1

# Deploy with kubectl
kubectl apply -f k8s/deployment.yaml
```

## System Without Docker (Development)

The platform works fine without Docker for:
- **Testing employer workflows** - Create assignments, test UI
- **Testing API endpoints** - All endpoints functional
- **Testing evaluation logic** - AI evaluation works
- **Running the test suite** - `python -m pytest tests/ -v` never needs Docker or an LLM key
- **Development** - Code changes, feature testing

What you **can't test** without Docker:
- Candidate container creation
- Code-server environment
- File collection from containers
- Complete end-to-end candidate workflow

## Recommended Development Setup

### Minimal (No Docker)
```
python run.py
# Test employer dashboard and API
# Port: 8000
```

### Full Development (With Docker)
```bash
# Terminal 1: Start Flask
python run.py

# Terminal 2: Start code-server manually (if needed)
docker run -p 7100:8080 codercom/code-server

# Access:
# Employer: http://localhost:8000
# Candidate: http://localhost:7100
```

### Docker Compose

Not the primary path — see the "Docker Compose (Not the primary dev path)" note above.

## Checking Docker Resources

### Container Logs
```bash
docker logs <container_id>
docker logs -f <container_id>  # Follow logs
```

### Container Resources
```bash
docker stats  # CPU, memory, network
docker top <container_id>  # Running processes
```

### Cleanup
```bash
# Stop all containers
docker stop $(docker ps -q)

# Remove stopped containers
docker system prune

# Remove volumes
docker system prune -v
```

## Docker Networking

### Access Container from Host
```bash
# If container was assigned port 7100
http://localhost:7100
http://127.0.0.1:7100
```

### Access Host from Container
```bash
# Inside container, access host as:
http://host.docker.internal:8000  # Windows/Mac
http://172.17.0.1:8000            # Linux
```

## Environment Variables for Docker

```bash
# .env file
DOCKER_HOST=                                  # Leave empty for default
DOCKER_IMAGE=coding-platform-student:latest   # Image name (default shown)
```

These map directly to `Config.DOCKER_HOST`/`Config.DOCKER_IMAGE` in `app/config.py`. The container port range (7100-7900) is a hardcoded constant, not an env var — it isn't configurable without editing `app/config.py` directly.

## Troubleshooting Workflow

1. **Check Docker Running**
   ```bash
   docker ps
   ```

2. **Check Logs**
   ```bash
   # Flask logs - shown in terminal
   # Docker logs - docker logs <container_id>
   ```

3. **Rebuild Image**
   ```bash
   docker build --no-cache -f docker/Dockerfile.codeserver -t coding-platform-student .
   ```

4. **Test Manually**
   ```bash
   docker run -it coding-platform-student bash
   ```

5. **Clean and Restart**
   ```bash
   docker system prune -v
   python run.py
   ```

## Summary

**Docker Optional Features:**
- ✓ Works great without Docker (degraded mode)
- ✓ Full functionality with Docker
- ✓ Automatic detection and graceful fallback
- ✓ User-friendly error messages

**Getting Docker:** Takes 10-15 minutes for Windows/Mac with Docker Desktop, provides full environment isolation and student portal with code-server.

For questions or issues, check the logs and error messages - they'll guide you to the solution.
