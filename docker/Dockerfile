# Multi-stage build to minimize final image size
FROM codercom/code-server:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    nano \
    vim \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI and Python dependencies
RUN pip install --no-cache-dir \
    anthropic \
    flask \
    fastapi \
    uvicorn \
    requests \
    numpy \
    pandas \
    pytest \
    black \
    pylint \
    flake8 \
    pydantic

# Install VS Code extensions for Python and Claude integration
RUN code-server --install-extension ms-python.python && \
    code-server --install-extension ms-python.vscode-pylance && \
    code-server --install-extension github.copilot

# Create workspace directory with full permissions
RUN mkdir -p /workspace && chmod 777 /workspace && chown -R 1000:1000 /workspace

# SUBMIT.html will be copied and set up by start-services.py

# Set working directory
WORKDIR /workspace

# Create a helper script for Claude CLI usage
RUN cat > /usr/local/bin/claude-help << 'EOF'
#!/bin/bash
echo "Claude CLI Quick Reference"
echo "========================="
echo ""
echo "To use Claude in your terminal:"
echo "  1. Set ANTHROPIC_API_KEY: export ANTHROPIC_API_KEY='your-key-here'"
echo "  2. Create a Python script to use the Claude SDK"
echo ""
echo "Example usage:"
echo "  python3 -c \"import anthropic; c = anthropic.Anthropic(); m = c.messages.create(model='claude-opus-4-1', max_tokens=100, messages=[{'role': 'user', 'content': 'Hello'}]); print(m.content[0].text)\""
echo ""
echo "Or use a Python file:"
echo "  cat > ask_claude.py << 'PYTHON'"
echo "  import anthropic"
echo "  client = anthropic.Anthropic()"
echo "  message = client.messages.create("
echo "      model='claude-opus-4-1',"
echo "      max_tokens=1024,"
echo "      messages=[{'role': 'user', 'content': 'What is 2+2?'}]"
echo "  )"
echo "  print(message.content[0].text)"
echo "  PYTHON"
echo ""
echo "For more info: pip show anthropic"
EOF
chmod +x /usr/local/bin/claude-help

# Create a settings file for code-server to enable some useful features
RUN mkdir -p ~/.local/share/code-server/User
RUN cat > ~/.local/share/code-server/User/settings.json << 'EOF'
{
  "python.defaultInterpreterPath": "/usr/bin/python3",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "ms-python.python",
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true
  },
  "workbench.colorTheme": "Default Dark Modern",
  "terminal.integrated.defaultProfile.linux": "bash",
  "terminal.integrated.fontSize": 14
}
EOF

# Expose port for code-server
EXPOSE 8080

# Default command - start code-server
CMD ["code-server", "--bind", "0.0.0.0:8080", "--auth", "none", "/workspace"]
