FROM codercom/code-server:latest

# All install steps need root
USER root

# System dependencies
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

# Python packages available system-wide
RUN pip3 install --no-cache-dir --break-system-packages \
    anthropic \
    openai \
    flask \
    requests \
    numpy \
    pandas \
    pytest \
    black \
    pylint \
    flake8 \
    pydantic \
    httpx \
    || pip3 install --no-cache-dir \
    anthropic \
    openai \
    flask \
    requests \
    numpy \
    pandas \
    pytest \
    black \
    pylint \
    flake8 \
    pydantic \
    httpx

# Workspace
RUN mkdir -p /workspace && chmod 777 /workspace && chown -R 1000:1000 /workspace

# Helper script
RUN printf '#!/bin/bash\necho "hire-signal candidate environment"\necho "Python packages available: anthropic, openai, flask, requests, numpy, pandas"\necho "Use Claude CLI or write Python scripts in /workspace"\n' \
    > /usr/local/bin/hs-help && chmod +x /usr/local/bin/hs-help

# code-server settings (run as root so path is predictable)
RUN mkdir -p /root/.local/share/code-server/User && \
    printf '{\n  "python.defaultInterpreterPath": "/usr/bin/python3",\n  "editor.formatOnSave": true,\n  "workbench.colorTheme": "Default Dark Modern",\n  "terminal.integrated.fontSize": 14\n}\n' \
    > /root/.local/share/code-server/User/settings.json

# Install Python extension (optional — skip on failure so build doesn't break)
RUN code-server --install-extension ms-python.python || true

WORKDIR /workspace

# Drop back to coder user for runtime
USER coder

EXPOSE 8080

CMD ["code-server", "--bind-addr", "0.0.0.0:8080", "--auth", "none", "/workspace"]
