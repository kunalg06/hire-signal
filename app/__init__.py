import logging
import os
import sys
from dotenv import load_dotenv

# LOAD .ENV FIRST (before any other imports)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_project_root, '.env')
load_dotenv(_env_path, override=True)

# NOW import everything else
from flask import Flask
from flask_cors import CORS
from app.config import get_config
from app.models.database import Database
from app.routes.assignments import assignments_bp
from app.routes.links import links_bp
from app.routes.submissions import submissions_bp
from app.routes.student import student_bp
from app.routes.management import management_bp
from app.routes.challenges import challenges_bp
from app.routes.analytics import analytics_bp


def create_app(config_name=None):
    """Application factory with proper template folder"""
    # Guard, not unconditional config: run.py already calls basicConfig()
    # when started via `python run.py`, but `flask run` calls create_app()
    # directly and never touches run.py, leaving the root logger at the
    # default WARNING level with every logger.info()/debug() dropped silently.
    if not logging.root.handlers:
        # Mirrors run.py's stdout/stderr UTF-8 reconfigure (party-mode
        # review 2026-07-11) for the `flask run` path, which never executes
        # run.py's copy of this guard.
        for _stream in (sys.stdout, sys.stderr):
            if hasattr(_stream, 'reconfigure'):
                try:
                    _stream.reconfigure(encoding='utf-8', errors='replace')
                except Exception:
                    pass
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(name)s %(levelname)s %(message)s'
        )

    # Get project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Initialize Flask with templates folder
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, 'templates'),
        static_folder=os.path.join(project_root, 'static')
    )

    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)

    # CORS — allow all origins in development
    CORS(app)

    # Initialize database
    db = Database(config.DB_PATH)
    db.init_db()

    # Register blueprints
    app.register_blueprint(assignments_bp)
    app.register_blueprint(links_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(management_bp)
    app.register_blueprint(challenges_bp)
    app.register_blueprint(analytics_bp)

    # Frontend route - Serve teacher dashboard from templates/frontend.html
    @app.route('/')
    def index():
        """Serve frontend dashboard (Teacher Portal) from templates folder"""
        frontend_path = os.path.join(project_root, 'templates', 'frontend.html')

        try:
            with open(frontend_path, 'r', encoding='utf-8') as f:
                return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
        except FileNotFoundError:
            # Fallback page when frontend.html not found
            return get_fallback_page(), 200, {'Content-Type': 'text/html; charset=utf-8'}

    return app


def get_fallback_page():
    """Fallback HTML page when frontend.html is not found"""
    return '''
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Engineering Assessment Platform</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
            .container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }
            h1 { color: #667eea; }
            h2 { color: #764ba2; margin-top: 30px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }
            code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
            ul { margin: 15px 0; }
            li { margin: 8px 0; }
            .status { background: #e3f2fd; padding: 15px; border-radius: 5px; border-left: 4px solid #2196f3; }
            a { color: #667eea; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Backend API Status: Running</h1>
            <p>Flask backend is active and ready to serve requests.</p>

            <div class="status">
                <strong>Note:</strong> frontend.html not found in templates/ folder.
                Make sure it exists at: <code>templates/frontend.html</code>
            </div>

            <h2>API Endpoints Available</h2>

            <h3>Assignments</h3>
            <ul>
                <li><code>POST /api/assignments</code> - Create assignment</li>
                <li><code>GET /api/assignments/{id}</code> - Get assignment details</li>
            </ul>

            <h3>Links & Access</h3>
            <ul>
                <li><code>POST /api/generate-link/{assignment_id}</code> - Generate student link</li>
                <li><code>GET /student/{link_id}</code> - Student dashboard</li>
            </ul>

            <h3>Submissions & Evaluation</h3>
            <ul>
                <li><code>POST /api/submit-with-files/{link_id}</code> - Submit code</li>
                <li><code>GET /api/submission/{id}</code> - Get results</li>
                <li><code>GET /api/session-logs/{id}</code> - Get session logs</li>
            </ul>

            <h3>System Management</h3>
            <ul>
                <li><code>GET /api/system/status</code> - System status</li>
                <li><code>GET /api/system/health</code> - Health check</li>
                <li><code>POST /api/system/cleanup-old?hours=24</code> - Clean old containers</li>
                <li><code>POST /api/system/cleanup-all</code> - Clean all containers</li>
                <li><code>GET /api/system/containers/{id}/info</code> - Container info</li>
                <li><code>GET /api/system/containers/{id}/logs</code> - Container logs</li>
                <li><code>POST /api/system/containers/{id}/restart</code> - Restart</li>
                <li><code>POST /api/system/containers/{id}/stop</code> - Stop</li>
            </ul>

            <h2>Server Status</h2>
            <ul>
                <li><strong>API:</strong> Running on port 8000</li>
                <li><strong>Database:</strong> Initialized</li>
                <li><strong>Version:</strong> 1.0.0</li>
            </ul>
        </div>
    </body>
    </html>
    '''
