import os
import tempfile
from datetime import timedelta

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    JSON_SORT_KEYS = False

    # Database - store in data/ folder
    DB_PATH = os.getenv('DB_PATH', os.path.join('data', 'assignments.db'))

    # Flask
    DEBUG = False
    TESTING = False

    # Server
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))

    # Session management
    SESSION_TIMEOUT = timedelta(hours=24)

    # Rate limiting
    RATE_LIMIT_REQUESTS = 5
    RATE_LIMIT_WINDOW = 60

    # LLM — routed through Gemini (swap model via GEMINI_MODEL env var)
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL   = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    # TLS verification for outbound Gemini API calls. Defaults to secure
    # (verified) in every environment, including production. Only set to
    # true in a LOCAL .env if your network has a TLS-inspecting proxy that
    # breaks certificate validation (e.g. an antivirus's HTTPS-scanning
    # feature presenting its own locally-generated CA) — never in
    # production, since this disables MITM protection entirely.
    GEMINI_TLS_SKIP_VERIFY = os.getenv(
        'GEMINI_TLS_SKIP_VERIFY', 'false').strip().lower() in ('1', 'true', 'yes')

    # Docker
    DOCKER_HOST = os.getenv('DOCKER_HOST', None)
    DOCKER_PORT_RANGE_START = 7100
    DOCKER_PORT_RANGE_END = 7900
    DOCKER_IMAGE = os.getenv('DOCKER_IMAGE', 'coding-platform-student:latest')

    # AI assistance mode — shared constant so links.py and docker_service.py
    # can't drift out of sync on the default/whitelist (see deferred-work.md).
    DEFAULT_ASSISTANCE_MODE = 'unguarded'
    VALID_ASSISTANCE_MODES = {'guarded', 'unguarded'}

    # Host-side directory for guarded-mode context files, bind-mounted
    # read-only into the container at creation time (Story 9.7).
    GUARDED_MODE_HOST_TMP_ROOT = os.getenv(
        'GUARDED_MODE_HOST_TMP_ROOT',
        os.path.join(tempfile.gettempdir(), 'hire-signal-guarded-mode'))

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DB_PATH = os.path.join('data', 'test_assignments.db')

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    # SECRET_KEY should be set via environment variable in production
    # Fallback to a generated key for development-like environments
    SECRET_KEY = os.getenv('SECRET_KEY', 'prod-secret-key-change-in-production')

# Configuration factory
def get_config(env=None):
    """Get configuration based on environment"""
    if env is None:
        env = os.getenv('FLASK_ENV', 'development')

    config_map = {
        'development': DevelopmentConfig,
        'testing': TestingConfig,
        'production': ProductionConfig
    }

    return config_map.get(env, DevelopmentConfig)
