# Claude Assignment Platform - Installation & Deployment Guide

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Local Development Setup](#local-development-setup)
3. [Docker Deployment](#docker-deployment)
4. [Production Deployment](#production-deployment)
5. [Troubleshooting](#troubleshooting)
6. [Performance Tuning](#performance-tuning)

---

## System Requirements

### Minimum Requirements
- **CPU**: 2+ cores
- **RAM**: 4GB (8GB recommended for production)
- **Disk**: 20GB free space
- **OS**: Linux, macOS, or Windows 10+ (with WSL2)

### Software Requirements
- Docker 20.10+
- Docker Compose 1.29+
- Python 3.8+ (for client library)
- Git
- curl or wget

### Internet Requirements
- Stable internet connection (for Claude API calls)
- Ability to reach api.anthropic.com

---

## Local Development Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/claude-assignment-platform.git
cd claude-assignment-platform
```

### Step 2: Set Up Environment Variables

```bash
# Copy the example .env file
cp .env.example .env

# Edit with your Anthropic API key
nano .env
# Or use your preferred editor
```

Add these to your `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-[your-key-here]
DB_PASSWORD=dev_password_123
```

### Step 3: Install Docker

**macOS:**
```bash
# Using Homebrew
brew install docker docker-compose

# Or download Docker Desktop
# https://www.docker.com/products/docker-desktop
```

**Ubuntu/Debian:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add current user to docker group
sudo usermod -aG docker $USER
```

**Windows:**
- Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Enable WSL2 backend

### Step 4: Verify Docker Installation

```bash
docker --version
docker-compose --version
docker run hello-world
```

### Step 5: Build and Start Services

**On Linux/macOS:**
```bash
# Make quickstart script executable
chmod +x quickstart.sh

# Run the quickstart
./quickstart.sh

# Or manually start
docker-compose up --build
```

**On Windows (PowerShell):**
```powershell
# Run the quickstart script directly (no chmod needed)
.\quickstart.sh

# Or run with bash if using WSL2/Git Bash
bash quickstart.sh

# Or manually start
docker-compose up --build
```

### Step 6: Verify Services Are Running

```bash
# Check running containers
docker-compose ps

# Test the API
curl http://localhost:8000/health

# Expected output:
# {"status":"ok","service":"Claude Assignment Platform"}
```

### Step 7: Access the Dashboard

Open in your browser:
- **Frontend**: `file://$(pwd)/frontend.html`
- **API Docs**: `http://localhost:8000/docs`
- **Redoc**: `http://localhost:8000/redoc`

---

## Docker Deployment

### Build Custom Images

```bash
# Build all images
docker-compose build

# Build specific service
docker-compose build backend

# Build without cache
docker-compose build --no-cache
```

### Run Containers

```bash
# Start all services in background
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f backend

# Stop services
docker-compose stop

# Stop and remove
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

### Container Management

```bash
# List all containers
docker-compose ps

# Execute command in running container
docker-compose exec backend bash

# View container details
docker-compose inspect backend
```

### Network Inspection

```bash
# List networks
docker network ls

# Inspect assignment network
docker network inspect claude-assignment_assignment-network

# Check container IPs
docker-compose ps --format "table {{.Service}}\t{{.Networks}}"
```

---

## Production Deployment

### Option 1: Cloud Deployment (AWS EC2)

#### Prerequisites
- AWS account with EC2 and RDS access
- SSH key pair created

#### Steps

1. **Launch EC2 Instance**
```bash
# Create t3.large instance (ubuntu 20.04)
# - Security group: Allow 80, 443, 22, 6000-7000 (VS Code ports)
# - Attach IAM role with S3, CloudWatch access
```

2. **SSH into Instance**
```bash
ssh -i your-key.pem ubuntu@your-instance-ip
```

3. **Install Docker**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
```

4. **Clone Repository**
```bash
git clone https://github.com/yourusername/claude-assignment-platform.git
cd claude-assignment-platform
```

5. **Configure Environment**
```bash
nano .env
# Set all variables for production
# - Real ANTHROPIC_API_KEY
# - Real DB_PASSWORD
# - Production database URL (RDS)
```

6. **Update docker-compose for Production**
```yaml
# docker-compose.yml - Production variant
services:
  backend:
    image: my-registry/assignment-backend:latest
    restart: always
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=postgresql://user:pass@rds-endpoint/db
    ports:
      - "8000:8000"
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G
```

7. **Start Services**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

8. **Set Up Reverse Proxy (Nginx)**
```bash
sudo apt-get install nginx
sudo systemctl start nginx

# Create nginx config
sudo nano /etc/nginx/sites-available/assignment-platform
```

```nginx
upstream api {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        root /path/to/frontend;
        try_files $uri /index.html;
    }

    location /api {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/assignment-platform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

9. **Set Up SSL (Let's Encrypt)**
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Option 2: Kubernetes Deployment

#### Prerequisites
- kubectl installed
- Kubernetes cluster (EKS, GKE, or local minikube)
- Container registry (Docker Hub, ECR, GCR)

#### Steps

1. **Push Images to Registry**
```bash
# Build and push
docker build -f Dockerfile.backend -t your-registry/assignment-backend:latest .
docker push your-registry/assignment-backend:latest
```

2. **Create Kubernetes Manifests**

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: assignment-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: assignment-backend
  template:
    metadata:
      labels:
        app: assignment-backend
    spec:
      containers:
      - name: backend
        image: your-registry/assignment-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: anthropic-secret
              key: api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

```yaml
# k8s/backend-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: assignment-backend
spec:
  type: LoadBalancer
  selector:
    app: assignment-backend
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
```

3. **Deploy to Kubernetes**
```bash
# Create namespace
kubectl create namespace assignment-platform

# Create secret
kubectl create secret generic anthropic-secret \
  --from-literal=api-key=$ANTHROPIC_API_KEY \
  -n assignment-platform

# Deploy
kubectl apply -f k8s/ -n assignment-platform

# Check status
kubectl get deployments -n assignment-platform
kubectl get pods -n assignment-platform
```

4. **Monitor and Scale**
```bash
# View logs
kubectl logs -f deployment/assignment-backend -n assignment-platform

# Scale deployment
kubectl scale deployment assignment-backend --replicas=5 -n assignment-platform

# Watch resources
kubectl top nodes
kubectl top pods -n assignment-platform
```

### Option 3: Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Create service
docker service create \
  --name assignment-backend \
  --publish 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  --replicas 3 \
  your-registry/assignment-backend:latest

# View services
docker service ls

# Scale service
docker service scale assignment-backend=5

# Monitor
docker service logs -f assignment-backend
```

---

## Database Configuration

### Using PostgreSQL in Production

1. **Create RDS Instance (AWS)**
   - Engine: PostgreSQL 13+
   - Multi-AZ for reliability
   - Backup: 30 day retention

2. **Update Connection String**
```bash
DATABASE_URL=postgresql://user:password@rds-endpoint.amazonaws.com:5432/assignments
```

3. **Run Migrations**
```bash
# Inside backend container
docker-compose exec backend python -c "from main import init_db; init_db()"
```

### Backup Strategy

```bash
# Automated daily backups
0 2 * * * docker-compose exec -T postgres pg_dump -U assignment_user assignments > /backups/assignments_$(date +\%Y\%m\%d).sql
```

---

## Monitoring & Logging

### Container Logs

```bash
# Real-time logs
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend

# Filter by time
docker-compose logs --since 30m backend
```

### Prometheus Monitoring (Optional)

```yaml
# docker-compose.yml addition
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
```

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'docker'
    static_configs:
      - targets: ['localhost:9323']
```

---

## Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Find process using port
lsof -i :8000
lsof -i :6000

# Kill process
kill -9 <PID>

# Or use different port in .env
BACKEND_PORT=8001
```

#### Docker Socket Permission Denied
```bash
# Grant permissions
sudo chmod 666 /var/run/docker.sock

# Or add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

#### Claude API Key Invalid
```bash
# Test API key
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model":"claude-opus-4-1",
    "max_tokens":100,
    "messages":[{"role":"user","content":"test"}]
  }'
```

#### Container Won't Start
```bash
# Check logs
docker-compose logs backend

# Try rebuilding
docker-compose build --no-cache backend

# Check Docker daemon
systemctl status docker

# Restart Docker
sudo systemctl restart docker
```

#### Database Connection Issues
```bash
# Test database connection
docker-compose exec postgres psql -U assignment_user -d assignments -c "SELECT 1"

# Check PostgreSQL logs
docker-compose logs postgres

# Reinitialize database
docker-compose down -v
docker-compose up -d postgres
```

### Health Checks

```bash
#!/bin/bash
# health-check.sh

API_UP=$(curl -s http://localhost:8000/health | grep -c "ok")
DB_UP=$(docker-compose exec -T postgres pg_isready)
CONTAINERS=$(docker-compose ps --services --filter "status=running" | wc -l)

if [ $API_UP -eq 1 ] && [ $CONTAINERS -eq 4 ]; then
    echo "✓ All systems operational"
    exit 0
else
    echo "✗ System check failed"
    exit 1
fi
```

---

## Performance Tuning

### Backend Optimization

```python
# main.py - Connection pooling
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
)
```

### Database Optimization

```sql
-- Add indexes for faster queries
CREATE INDEX idx_submissions_link_id ON submissions(link_id);
CREATE INDEX idx_sessions_assignment_id ON session_links(assignment_id);
CREATE INDEX idx_submissions_submitted_at ON submissions(submitted_at);
```

### Container Resource Limits

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G
```

### Load Testing

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Test API
ab -n 1000 -c 10 http://localhost:8000/health

# Or use locust
pip install locust

# Create locustfile.py and run
locust -f locustfile.py --host=http://localhost:8000
```

---

## Maintenance

### Regular Tasks

```bash
# Weekly: Check logs for errors
docker-compose logs --since 7d | grep ERROR

# Monthly: Clean up unused images
docker image prune -a

# Monthly: Update containers
docker-compose pull
docker-compose up -d

# Quarterly: Database optimization
docker-compose exec postgres vacuumdb -U assignment_user assignments
```

### Updating the Platform

```bash
# Pull latest changes
git pull origin main

# Rebuild images
docker-compose build --pull

# Test in staging
docker-compose -f docker-compose.staging.yml up -d

# Deploy to production
docker-compose down
docker-compose -f docker-compose.prod.yml up -d
```

---

## Support

For issues or questions:
- Check [README.md](README.md) for overview
- Review logs: `docker-compose logs -f`
- Consult [Anthropic API Docs](https://docs.claude.com)
- Open GitHub issue with:
  - Docker version
  - Container logs
  - Error messages
  - Steps to reproduce

---

**Happy Deploying! 🚀**
