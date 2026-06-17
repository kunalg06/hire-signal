#!/usr/bin/env python
"""Entry point for the Flask application"""

import os
import sys
from dotenv import load_dotenv
from app import create_app
from app.config import Config

# Load environment variables
load_dotenv()

if __name__ == '__main__':
    # Get Flask environment
    env = os.getenv('FLASK_ENV', 'production')

    # Create app
    app = create_app(env)

    # Get configuration
    host = Config.HOST
    port = Config.PORT

    print(f"🚀 AI Engineering Assessment & Evaluation Platform")
    print(f"Environment: {env}")
    print(f"Starting Flask server on http://{host}:{port}")

    # Run app
    app.run(host=host, port=port, debug=(env == 'development'))
