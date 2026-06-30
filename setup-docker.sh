#!/bin/bash

# Docker Setup Script for Coding Platform

echo "=========================================="
echo "Docker Setup for Coding Platform"
echo "=========================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed"
    echo "Please install Docker from https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if Docker daemon is running
if ! docker ps &> /dev/null; then
    echo "ERROR: Docker daemon is not running"
    echo "Please start Docker Desktop or Docker service"
    exit 1
fi

echo "✓ Docker installed and running"
echo ""

# Build the student environment image
echo "Building Docker image for student environment..."
echo "This may take 5-10 minutes on first run..."
echo ""

cd docker

docker build -f Dockerfile -t coding-platform-student:latest .

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Docker image built successfully: coding-platform-student:latest"
    echo ""
    echo "Verify image:"
    docker images | grep coding-platform-student
    echo ""
    echo "Next steps:"
    echo "1. Start the Flask app: python run.py"
    echo "2. Generate a student link"
    echo "3. The iframe will show code-server on the assigned port"
else
    echo "ERROR: Docker image build failed"
    exit 1
fi

cd ..
