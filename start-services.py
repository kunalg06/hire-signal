#!/usr/bin/env python3
import os

# Start code-server
os.execvp('code-server', ['code-server', '--bind-addr', '0.0.0.0:8080', '--auth', 'none', '/workspace'])
