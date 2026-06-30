#!/usr/bin/env python
"""Entry point for the Flask application"""

import os
from dotenv import load_dotenv

# Load .env variables FIRST
load_dotenv()

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

    print("=" * 60)
    print("AI Engineering Assessment & Evaluation Platform")
    print("=" * 60)
    print(f"Environment: {env}")
    print(f"Starting Flask server on http://{host}:{port}")

    # Run app
    app.run(host=host, port=port, debug=(env == 'development'))
