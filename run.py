#!/usr/bin/env python
"""Entry point for the Flask application"""

import logging
import os
import sys
from dotenv import load_dotenv

# Load .env variables FIRST
load_dotenv()

# Party-mode review 2026-07-11: a real Gemini response contained stray
# non-ASCII tokens (Bengali-script transliterations of English words —
# a known small-model token-sampling artifact). On Windows the console is
# cp1252 by default (see CLAUDE.md's "ASCII only in print()/logging"
# constraint); a logger.warning/error call that ever interpolates raw
# model text would UnicodeEncodeError and silently abort execution
# mid-request. Reconfiguring stdout/stderr to UTF-8 (replacing anything
# still unencodable, never crashing) removes that failure mode at its
# root instead of requiring every call site to pre-sanitize model text.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# Configure root logger before any app imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# Then import app
from app import create_app
from app.config import Config

if __name__ == '__main__':
    # Get Flask environment
    env = os.getenv('FLASK_ENV', 'development')

    # Create app
    app = create_app(env)

    # Get configuration
    host = Config.HOST
    port = Config.PORT

    logger.info("AI Engineering Assessment & Evaluation Platform")
    logger.info("Environment: %s | Server: http://%s:%s", env, host, port)

    # Run app
    app.run(host=host, port=port, debug=(env == 'development'))
