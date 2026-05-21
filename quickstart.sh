#!/bin/bash

# Claude Assignment Platform - Quick Start Script

echo "🚀 Claude Assignment Platform - Setup"
echo "======================================"
echo ""

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install it first."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker and Docker Compose are installed"
echo ""

# Check API key
echo "🔑 Checking Anthropic API Key..."

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  ANTHROPIC_API_KEY environment variable not set"
    echo ""
    echo "   Get your API key from: https://console.anthropic.com"
    echo "   Then set it:"
    echo "   export ANTHROPIC_API_KEY='sk-ant-...'"
    echo ""
    read -p "Enter your API key (or press Enter to skip): " api_key
    if [ -n "$api_key" ]; then
        export ANTHROPIC_API_KEY="$api_key"
        echo "✓ API key set"
    else
        echo "⚠️  Continuing without API key (evaluations will fail)"
    fi
else
    echo "✓ ANTHROPIC_API_KEY is set"
fi

echo ""

# Create .env file
echo "📝 Creating .env file..."

cat > .env << EOF
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
DB_PASSWORD=claude_assignment_db_secret_123
EOF

echo "✓ .env file created"
echo ""

# Build and start containers
echo "🐳 Building and starting Docker containers..."
echo "   (This may take a few minutes the first time)"
echo ""

docker-compose up --build -d

if [ $? -ne 0 ]; then
    echo "❌ Failed to start Docker containers"
    exit 1
fi

echo "✓ Containers started"
echo ""

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if API is responding
echo ""
echo "🔍 Checking API health..."

for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ API is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  API took a while to start, but continuing..."
    else
        echo -n "."
        sleep 1
    fi
done

echo ""
echo "======================================"
echo "✅ Setup Complete!"
echo "======================================"
echo ""
echo "🌐 Access the platform:"
echo "   Dashboard: Open frontend.html in your browser"
echo "   API:       http://localhost:8000"
echo "   Docs:      http://localhost:8000/docs (auto-generated)"
echo ""
echo "📚 Next steps:"
echo "   1. Open frontend.html in your browser"
echo "   2. Create an assignment"
echo "   3. Generate a student link"
echo "   4. Share the link with students"
echo ""
echo "🛑 To stop services:"
echo "   docker-compose down"
echo ""
echo "📖 For more info, see README.md"
echo ""
