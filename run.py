#!/usr/bin/env python
"""Entry point for the Flask application"""

import logging
import os
from dotenv import load_dotenv

# Load .env variables FIRST
load_dotenv()

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
