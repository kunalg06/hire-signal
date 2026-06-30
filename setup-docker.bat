@echo off
REM Docker Setup Script for Coding Platform (Windows)

echo ==========================================
echo Docker Setup for Coding Platform
echo ==========================================
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

REM Check if Docker daemon is running
docker ps >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker daemon is not running
    echo Please start Docker Desktop application
    pause
    exit /b 1
)

echo [OK] Docker installed and running
echo.

REM Build the student environment image
echo Building Docker image for student environment...
echo This may take 5-10 minutes on first run...
echo.

cd docker

docker build -f Dockerfile -t coding-platform-student:latest .

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Docker image built successfully: coding-platform-student:latest
    echo.
    echo Verify image:
    docker images | findstr coding-platform-student
    echo.
    echo Next steps:
    echo 1. Start the Flask app: python run.py
    echo 2. Generate a student link
    echo 3. The iframe will show code-server on the assigned port
) else (
    echo ERROR: Docker image build failed
    pause
    exit /b 1
)

cd ..
pause
