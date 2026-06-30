# Docker Quick Start Guide

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker should be running and accessible

## Step 1: Install Docker

### Windows/Mac
1. Download Docker Desktop: https://www.docker.com/products/docker-desktop
2. Run installer and complete setup
3. Start Docker Desktop application
4. Verify: Open terminal and run `docker ps`

### Linux
```bash
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
sudo usermod -aG docker $USER
```

## Step 2: Build Student Docker Image

The student environment (code-server) needs to be built as a Docker image.

### Windows
```bash
# Navigate to project directory
cd E:\project2025\coding_platforms

# Run setup script
setup-docker.bat
```

### Mac/Linux
```bash
# Navigate to project directory
cd /path/to/coding_platforms

# Run setup script
bash setup-docker.sh
```

### Manual Build
```bash
cd docker
docker build -f Dockerfile -t coding-platform-student:latest .
```

The build takes 5-10 minutes on first run (installs dependencies).

## Step 3: Verify Docker Image

```bash
# List images
docker images | grep coding-platform-student

# Should show something like:
# REPOSITORY                    TAG      IMAGE ID      CREATED       SIZE
# coding-platform-student       latest   abc123def456  2 minutes ago 2.5GB
```

## Step 4: Start Flask Application

```bash
python run.py
```

Flask starts on http://localhost:8000

## Step 5: Test End-to-End

1. **Open Dashboard**: http://localhost:8000

2. **Generate AI Challenge**:
   - Enter problem statement
   - Select difficulty (easy/medium/hard)
   - Click "Generate with AI"

3. **Save as Assignment**:
   - Click "Save as Assignment"
   - Copy the assignment ID

4. **Generate Student Link**:
   - Paste assignment ID
   - Click "Generate Link"
   - You'll see a port number (e.g., 6000-6999)

5. **Access Student Portal**:
   - Click the generated URL
   - On right side: code-server iframe should load
   - On left side: assignment description

6. **Code in VS Code**:
   - Write solution in code-server
   - Terminal available for testing
   - Python, pip, git all available

7. **Submit Code**:
   - Click "Submit Solution" button
   - Wait for Claude evaluation (5-10 seconds)
   - View score and feedback

## Troubleshooting

### Error: "Docker daemon is not running"
**Solution:**
- Windows/Mac: Start Docker Desktop application
- Linux: `sudo systemctl start docker`

### Error: "Cannot connect to Docker daemon"
**Solution:**
- Ensure Docker Desktop is fully running
- Check that Docker socket is accessible
- On Linux: Add user to docker group: `sudo usermod -aG docker $USER`

### Error: "image not found: coding-platform-student:latest"
**Solution:**
- Build the image: `docker build -f docker/Dockerfile -t coding-platform-student:latest .`
- Verify: `docker images | grep coding-platform`

### Container fails to start
**Solution:**
```bash
# Check Docker logs
docker logs <container_id>

# List running containers
docker ps

# Remove old containers
docker container prune
```

### Port already in use
**Solution:**
```bash
# Find process using port
lsof -i :6000  # or specific port

# Kill process
kill -9 <PID>

# Or use different port range in config
```

## How It Works

1. **Link Generation**: When teacher generates a link, system:
   - Creates Docker container from `coding-platform-student:latest` image
   - Assigns port from 6000-6999 range
   - Stores container ID and port in database

2. **Student Access**: Student visits link, system:
   - Loads assignment details on left
   - Embeds code-server iframe on right on assigned port
   - Student codes in browser-based VS Code

3. **File Collection**: When student submits:
   - Backend connects to container via Docker API
   - Extracts `solution.py` and other files
   - Also retrieves Claude interaction logs

4. **Evaluation**: Claude evaluates:
   - Code quality and correctness
   - Problem-solving approach (from Claude logs)
   - Efficiency of solution
   - Returns multi-dimensional score

## Ports

- **Flask API**: 8000 (localhost:8000)
- **Code-server instances**: 6000-6999 (one per student)

Each student gets unique port for their code-server instance.

## Performance

- Image build: 5-10 minutes first time, <1 minute cached
- Container start: <5 seconds
- Challenge generation: 8-15 seconds (Claude API)
- Code evaluation: 5-10 seconds (Claude API)

## System Requirements

- **Disk**: 5GB minimum (for Docker images and containers)
- **Memory**: 4GB minimum (2GB for app, 2GB for containers)
- **CPU**: 2+ cores recommended

## Development vs Production

### Development (Current Setup)
- Single machine with Flask + Docker
- SQLite database
- No authentication
- Debug mode enabled

### Production (Recommended)
- Multiple app servers (load balanced)
- PostgreSQL database
- JWT authentication
- HTTPS/SSL encryption
- Container resource limits
- Monitoring and logging

See SYSTEM_STATUS.md for production checklist.

## Next Steps

1. ✓ Install Docker
2. ✓ Build image: `setup-docker.bat` (Windows) or `setup-docker.sh` (Mac/Linux)
3. ✓ Start Flask: `python run.py`
4. ✓ Test: Generate challenge → Save → Generate link → Code → Submit
5. ✓ View results with evaluation score

## Support

- **Docker docs**: https://docs.docker.com/
- **Code-server docs**: https://coder.com/docs/code-server
- **Platform docs**: See DOCKER_SETUP.md for detailed setup

---

**Status**: Ready for use with Docker!
