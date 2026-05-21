#!/bin/bash

# Set up environment for Claude CLI and Chat extension
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"

# Make API key available globally
echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" >> /etc/environment

# Start code-server
exec code-server --bind-addr 0.0.0.0:8080 --auth none
