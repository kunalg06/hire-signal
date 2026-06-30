import os
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

    # Claude API
    CLAUDE_MODEL = os.getenv('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')

    # Docker
    DOCKER_HOST = os.getenv('DOCKER_HOST', None)
    DOCKER_PORT_RANGE_START = 6000
    DOCKER_PORT_RANGE_END = 7000
    DOCKER_IMAGE = os.getenv('DOCKER_IMAGE', 'coding-platform-student:latest')

    # Anthropic API
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

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
