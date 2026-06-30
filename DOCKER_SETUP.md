# Docker Setup & Troubleshooting Guide

## Current Status

The system **works without Docker** with graceful degradation:
- ✓ Teacher dashboard fully functional
- ✓ Assignment creation and management working
- ✓ Student links generate successfully
- ✓ Student portal page loads
- ⚠ Code-server (embedded IDE) unavailable without Docker

## Understanding Docker in This System

### What Docker Does
- Runs isolated Python environments for each student
- Provides browser-based VS Code (code-server) on unique ports
- Collects files from student workspace for evaluation
- Provides security isolation between students

### What Happens Without Docker

**When Docker is not running:**
1. Link generation completes instantly (no port assignment)
2. Student portal shows assignment details
3. Code-server is not available
4. Students cannot submit files directly

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
3. Students can access code-server

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

### From Python
```bash
cd E:\project2025\coding_platforms
python -c "
import docker
try:
    client = docker.from_env()
    print('Docker connected successfully')
    print(f'Docker version: {client.version()}')
except Exception as e:
    print(f'Docker connection failed: {e}')
"
```

### From Command Line
```bash
docker info
docker ps
```

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

Check that Dockerfile exists:
```bash
ls -la docker/Dockerfile
```

Should show code-server configuration.

### Build Container Image

```bash
cd docker
docker build -f Dockerfile -t coding-platform-student .
```

This creates the image that will be used for student containers.

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
docker build -f Dockerfile -t coding-platform-student .

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
# abc123def456   coding-platform-student:latest   6000->8080/tcp
```

### Access Code-Server
```
http://localhost:6000  (or assigned port)
```

## Docker Compose (Optional)

For full multi-service setup:

```bash
cd docker
docker-compose up --build
```

Services started:
- Flask API: http://localhost:8000
- PostgreSQL: localhost:5432 (if configured)
- Redis: localhost:6379 (if configured)

## Production Docker Deployment

### Using Docker in Production

```bash
# Build production image
docker build -f docker/Dockerfile.backend -t coding-platform:prod .

# Run with proper configuration
docker run \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
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
- **Testing teacher workflows** - Create assignments, test UI
- **Testing API endpoints** - All endpoints functional
- **Testing evaluation logic** - AI evaluation works
- **Development** - Code changes, feature testing

What you **can't test** without Docker:
- Student container creation
- Code-server environment
- File collection from containers
- Complete end-to-end student workflow

## Recommended Development Setup

### Minimal (No Docker)
```
python run.py
# Test teacher dashboard and API
# Port: 8000
```

### Full Development (With Docker)
```bash
# Terminal 1: Start Flask
python run.py

# Terminal 2: Start code-server manually (if needed)
docker run -p 6000:8080 codercom/code-server

# Access:
# Teacher: http://localhost:8000
# Student: http://localhost:6000
```

### Docker Compose (Production-like)
```bash
cd docker
docker-compose up --build
```

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
# If container exposed port 6000
http://localhost:6000
http://127.0.0.1:6000
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
DOCKER_HOST=              # Leave empty for default
DOCKER_IMAGE=coding-platform-student  # Image name
DOCKER_REGISTRY=          # Registry URL if using custom registry
```

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
   docker build --no-cache -f docker/Dockerfile -t coding-platform-student .
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
