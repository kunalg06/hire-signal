from flask import Flask
from app.config import get_config
from app.models.database import Database
from app.routes.assignments import assignments_bp
from app.routes.links import links_bp
from app.routes.submissions import submissions_bp
from app.routes.student import student_bp

def create_app(config_name=None):
    """Application factory"""
    app = Flask(__name__)

    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)

    # Initialize database
    db = Database(config.DB_PATH)
    db.init_db()

    # Register blueprints
    app.register_blueprint(assignments_bp)
    app.register_blueprint(links_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(student_bp)

    # Frontend route
    @app.route('/')
    def index():
        """Serve frontend dashboard"""
        try:
            with open('frontend.html', 'r') as f:
                return f.read(), 200, {'Content-Type': 'text/html'}
        except FileNotFoundError:
            return '''
            <html>
            <body style="font-family: Arial; padding: 20px;">
                <h1>AI Engineering Assessment & Evaluation Platform</h1>
                <p>Backend API is running on port 8000</p>
                <p>Available endpoints:</p>
                <ul>
                    <li>POST /api/assignments - Create assignment</li>
                    <li>GET /api/assignments/{id} - Get assignment</li>
                    <li>POST /api/generate-link/{assignment_id} - Generate student link</li>
                    <li>GET /student/{link_id} - Student dashboard</li>
                    <li>POST /api/submit-with-files/{link_id} - Submit code</li>
                    <li>GET /api/submission/{id} - Get results</li>
                    <li>GET /api/session-logs/{id} - Get session logs</li>
                </ul>
            </body>
            </html>
            ''', 200, {'Content-Type': 'text/html'}

    return app
