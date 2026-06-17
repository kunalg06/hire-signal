import uuid
import secrets
from time import time as current_time
from collections import defaultdict
from datetime import datetime, timedelta
from app.config import Config

class RateLimiter:
    """Rate limiting utility"""

    def __init__(self, max_requests=None, window=None):
        self.max_requests = max_requests or Config.RATE_LIMIT_REQUESTS
        self.window = window or Config.RATE_LIMIT_WINDOW
        self._store = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        """Check if client exceeds rate limit. Returns True if allowed."""
        now = current_time()
        timestamps = self._store[client_ip]
        self._store[client_ip] = [ts for ts in timestamps if now - ts < self.window]

        if len(self._store[client_ip]) < self.max_requests:
            self._store[client_ip].append(now)
            return True
        return False

class IDGenerator:
    """ID generation utilities"""

    @staticmethod
    def generate_uuid():
        """Generate UUID"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_link_id():
        """Generate unique link ID"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_file_id():
        """Generate file ID"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_log_id():
        """Generate log ID"""
        return str(uuid.uuid4())

class DateTimeHelper:
    """DateTime utilities"""

    @staticmethod
    def get_future_timestamp(hours=24):
        """Get timestamp for future datetime"""
        return (datetime.now() + timedelta(hours=hours)).isoformat()

    @staticmethod
    def get_now_timestamp():
        """Get current timestamp"""
        return datetime.now().isoformat()

class ValidationHelper:
    """Validation utilities"""

    @staticmethod
    def validate_required_fields(data, required_fields):
        """Validate that required fields are present"""
        if not isinstance(data, dict):
            return False, "Invalid request body"

        missing_fields = [field for field in required_fields if field not in data or not data.get(field)]
        if missing_fields:
            return False, f"Missing required fields: {', '.join(missing_fields)}"

        return True, None

    @staticmethod
    def validate_uuid(value):
        """Validate UUID format"""
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def validate_port(port):
        """Validate port number"""
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except (ValueError, TypeError):
            return False
