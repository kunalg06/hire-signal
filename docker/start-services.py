#!/usr/bin/env python3
"""Start services for code-server container"""

import os
import subprocess
import signal
import sys

def signal_handler(sig, frame):
    print("\nShutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("Starting code-server...")
subprocess.run([
    "code-server",
    "--bind", "0.0.0.0:8080",
    "--auth", "none",
    "/workspace"
], check=False)
